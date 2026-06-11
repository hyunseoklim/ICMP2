"""
facilities/services/geofence_service.py

가스 수치 기반 지오펜스 자동 생성/갱신/비활성화 서비스.

호출 시점: GasReading 저장 후 (monitoring 앱에서 호출)
의존성:
  - monitoring.services.calc_danger_level  — 위험도 판단
  - facilities.models.SensorLocation       — 센서 위치 조회
  - facilities.models.Geofence             — 지오펜스 생성/갱신

설계 원칙:
  - monitoring 앱이 이 서비스를 호출하지만
    이 파일은 facilities 앱에 위치 (위치 정보는 facilities 담당)
  - monitoring 앱 import는 함수 내부에서만 수행 (순환 import 방지)
"""

import logging
import re

logger = logging.getLogger(__name__)

# 가스 수치 기반 지오펜스 반경 (임시값, 추후 확정값으로 교체)
GEOFENCE_RADIUS = {
    'warning': 3.0,  # m
    'danger':  5.0,  # m
}

# 한국어 → 영어 severity 매핑
SEVERITY_MAP = {
    '위험': 'danger',
    '주의': 'warning',
    '정상': 'safe',
}


def update_geofence_from_gas(reading) -> None:
    """
    GasReading 인스턴스를 받아 지오펜스를 생성/갱신/비활성화한다.

    흐름:
      1. calc_danger_level()로 위험도 판단
      2. SensorLocation에서 해당 device의 위치(floor, x, y) 조회
      3. 정상이면 기존 자동 생성 지오펜스 비활성화
      4. 주의/위험이면 Geofence 생성 또는 갱신

    Args:
        reading: monitoring.models.GasReading 인스턴스
    """
    from monitoring.services import calc_danger_level
    from facilities.models import SensorLocation, Geofence

    # 1. 위험도 판단
    level_kr = calc_danger_level(reading)
    severity = SEVERITY_MAP.get(level_kr, 'safe')

    # 2. 센서 위치 조회
    try:
        sensor = SensorLocation.objects.get(
            device_id=reading.device_id,
            is_active=True,
        )
    except SensorLocation.DoesNotExist:
        # 지도에 등록되지 않은 센서 → 지오펜스 생성 불필요
        return

    # 3. 정상이면 기존 자동 생성 지오펜스 비활성화
    if severity == 'safe':
        updated = Geofence.objects.filter(
            floor=sensor.floor,
            name=_auto_name(sensor),
            is_active=True,
        )
        for g in updated:
            g.is_active = False
            g.save(update_fields=['is_active'])
            _broadcast_geofence(g, msg_type='delta')  # ← 추가
        return

    # 4. 주의/위험 — 생성 또는 갱신
    radius = GEOFENCE_RADIUS[severity]

    geofence, created = Geofence.objects.get_or_create(
        floor=sensor.floor,
        name=_auto_name(sensor),
        defaults={
            'geofence_type': 'circle',
            'severity':      severity,
            'center_x':      sensor.x,
            'center_y':      sensor.y,
            'radius':        radius,
            'is_active':     True,
            'description':   f'가스센서 자동 생성 — device_id={sensor.device_id}',
        }
    )

    if not created:
        # 기존 지오펜스 갱신 — severity/radius/is_active 업데이트
        update_fields = []

        if geofence.severity != severity:
            geofence.severity = severity
            update_fields.append('severity')

        if geofence.radius != radius:
            geofence.radius = radius
            update_fields.append('radius')

        if geofence.center_x != sensor.x:
            geofence.center_x = sensor.x
            update_fields.append('center_x')

        if geofence.center_y != sensor.y:
            geofence.center_y = sensor.y
            update_fields.append('center_y')

        if not geofence.is_active:
            geofence.is_active = True
            update_fields.append('is_active')

        if update_fields:
            geofence.save(update_fields=update_fields)
    _broadcast_geofence(geofence, msg_type='delta')  # ← 추가

def deactivate_stale_geofences() -> int:
    """
    자동 생성 지오펜스 중, 원본 가스센서의 최신 GasReading이 STALE_THRESHOLD를
    초과(또는 reading 자체가 없음)한 것을 비활성화하고 delta broadcast 한다.

    배경:
      update_geofence_from_gas()는 '정상' reading이 도착해야만 비활성화한다.
      데이터 수신이 끊기면(스토리 종료·장비 단절·다른 센서로만 데이터 유입) 해당
      센서의 reading 자체가 오지 않아 danger/warning 지오펜스가 영구히 남는다.
      이 sweep이 그 갭을 메운다 (celery beat 주기 호출).

    링크 방식:
      자동 지오펜스 name='[자동] {device_name}', description에 'device_id={id}' 포함.
      description에서 device_id를 파싱해 GasReading 최신 수신 시각을 확인한다.

    Returns: 비활성화한 지오펜스 수
    """
    from django.utils import timezone
    from facilities.models import Geofence
    from monitoring.models import GasReading
    from monitoring.services import STALE_THRESHOLD

    cutoff = timezone.now() - STALE_THRESHOLD
    count = 0

    autos = Geofence.objects.filter(name__startswith='[자동] ', is_active=True)
    for g in autos:
        m = re.search(r'device_id=(\d+)', g.description or '')
        if not m:
            continue
        device_id = int(m.group(1))
        last = (GasReading.objects
                .filter(device_id=device_id)
                .order_by('-measured_at')
                .values_list('measured_at', flat=True)
                .first())
        if last is None or last < cutoff:
            g.is_active = False
            g.save(update_fields=['is_active'])
            _broadcast_geofence(g, msg_type='delta')
            count += 1
            logger.info('[geofence_sweep] 비활성화 id=%s name=%s (last=%s)',
                        g.id, g.name, last)
    return count


def _broadcast_geofence(geofence, msg_type='delta') -> None:
    """
    geofence 변경사항을 WebSocket으로 broadcast.
    msg_type: 'delta' — 변경분만, 'full' — 전체 재로드 신호
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        payload = {
            'id':            geofence.id,
            'name':          geofence.name,
            'geofence_type': geofence.geofence_type,
            'severity':      geofence.severity,
            'is_active':     geofence.is_active,
            'center_x':      geofence.center_x,
            'center_y':      geofence.center_y,
            'radius':        geofence.radius,
            'polygon_data':  geofence.polygon_data,
        }

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'floor_{geofence.floor_id}_geofence',
            {
                'type':     'geofence.update',
                'msg_type': msg_type,
                'data':     [payload],
            },
        )
    except Exception as e:
        logger.warning('[geofence_ws] broadcast 실패: %s', e)

def _auto_name(sensor) -> str:
    """
    자동 생성 지오펜스 이름.
    동일 센서의 기존 지오펜스를 찾는 기준으로 사용.
    """
    return f'[자동] {sensor.device_name}'