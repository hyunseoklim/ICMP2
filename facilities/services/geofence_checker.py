"""
facilities/services/geofence_checker.py

작업자 위치가 지오펜스 내부인지 판단하는 서비스.

변경 이력:
  - safety_status 필드 분리 적용
    current_state : 근무 여부 (on_duty / off_duty) — 변경 없음
    safety_status : geofence 판단 결과 (safe / warning / danger) — 신규
  - off_duty 작업자는 geofence 판단 스킵 → safety_status = safe 유지
  - warning 구역 처리 추가
  - 우선순위: danger > warning > safe
"""


# ── 원형 내부 판단 ────────────────────────────────────────────

def is_inside_circle(x: float, y: float, geofence) -> bool:
    """
    작업자 좌표(x, y)가 원형 지오펜스 내부인지 판단.
    공식: (x - cx)² + (y - cy)² <= r²
    """
    if geofence.center_x is None or geofence.center_y is None or geofence.radius is None:
        return False

    dx = x - geofence.center_x
    dy = y - geofence.center_y
    return (dx * dx + dy * dy) <= (geofence.radius * geofence.radius)


# ── 폴리곤 내부 판단 (Ray Casting) ───────────────────────────

def is_inside_polygon(x: float, y: float, geofence) -> bool:
    """
    작업자 좌표(x, y)가 폴리곤 지오펜스 내부인지 판단.
    알고리즘: Ray Casting
    polygon_data 형태: [[x1,y1], [x2,y2], ...]
    """
    if not geofence.polygon_data:
        return False

    polygon = geofence.polygon_data
    n = len(polygon)
    if n < 3:
        return False

    inside = False
    j = n - 1

    for i in range(n):
        xi, yi = polygon[i][0], polygon[i][1]
        xj, yj = polygon[j][0], polygon[j][1]

        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside

        j = i

    return inside


# ── 단일 작업자 판단 ──────────────────────────────────────────

def check_worker_in_geofence(worker, loc) -> str:
    """
    작업자의 현재 위치가 어느 지오펜스 내부인지 판단.

    Rules:
      - off_duty  → 즉시 'safe' 반환 (판단 스킵)
      - on_duty   → 전체 geofence 순회
                    danger 내부  → 즉시 'danger' 반환
                    warning 내부 → 'warning' 기록 후 계속 순회
                    순회 종료    → warning 기록 있으면 'warning', 없으면 'safe'

    Returns:
        'danger' | 'warning' | 'safe'
    """
    from facilities.models import Geofence

    # off_duty는 geofence 판단 없이 safe 처리
    if worker.current_state == 'off_duty':
        return 'safe'

    if not loc or not loc.floor:
        return 'safe'

    # 해당 floor의 active geofence 조회
    # danger 먼저 판단하기 위해 severity 내림차순 정렬
    geofences = Geofence.objects.filter(
        floor=loc.floor,
        is_active=True,
    ).exclude(severity='safe').order_by('-severity')

    found_warning = False

    for geofence in geofences:
        if geofence.geofence_type == 'circle':
            inside = is_inside_circle(loc.x, loc.y, geofence)
        elif geofence.geofence_type == 'polygon':
            inside = is_inside_polygon(loc.x, loc.y, geofence)
        else:
            continue

        if not inside:
            continue

        if geofence.severity == 'danger':
            # danger 구역 진입 — 즉시 반환 (더 높은 우선순위 없음)
            return 'danger'

        if geofence.severity == 'warning':
            # warning 구역 진입 — 기록 후 계속 순회 (danger가 있을 수 있음)
            found_warning = True

    return 'warning' if found_warning else 'safe'


# ── Worker safety_status 업데이트 ────────────────────────────

def sync_worker_status(worker, loc) -> str:
    """
    geofence 판단 후 Worker.safety_status 업데이트.

    - current_state는 변경하지 않음 (근무 여부는 별도 관리)
    - safety_status만 업데이트

    Returns:
        최종 safety_status 문자열 ('danger' | 'warning' | 'safe')
    """
    new_safety = check_worker_in_geofence(worker, loc)

    if worker.safety_status != new_safety:
        worker.safety_status = new_safety
        worker.save(update_fields=['safety_status'])

    return new_safety


def deactivate_stale_workers() -> int:
    """위치 수신이 STALE_THRESHOLD를 초과(또는 없음)한 on_duty 작업자를 off_duty로 정리한다.

    데이터가 끊긴 작업자가 지도/현황에 '근무 중'(+위험)으로 유령처럼 남는 것을 막는다.
    지오펜스 sweep과 동일 패턴 — 조회 경로(dummy GET)는 off_duty를 제외하므로 자동 정상화.
    current_state=off_duty + safety_status=safe 로 리셋한다.

    시각 비교는 기계 로직이므로 aware UTC(timezone.now())를 쓴다 — core/timeutils는
    사람용 KST 표시 전용이라 여기 부적합. (monitoring STALE 판정·geofence sweep과 동일)

    Returns: 정리한 작업자 수
    """
    from django.utils import timezone
    from facilities.models import Worker, WorkerLocation
    from monitoring.services import STALE_THRESHOLD

    cutoff = timezone.now() - STALE_THRESHOLD
    count = 0
    for w in Worker.objects.exclude(current_state='off_duty'):
        last = (WorkerLocation.objects
                .filter(worker=w)
                .order_by('-measured_at')
                .values_list('measured_at', flat=True)
                .first())
        if last is None or last < cutoff:
            w.current_state = 'off_duty'
            w.safety_status = 'safe'
            w.save(update_fields=['current_state', 'safety_status'])
            count += 1
    return count