"""
facilities/services/geofence_checker.py

작업자 위치가 지오펜스 내부인지 판단하는 서비스.

호출 시점: worker-locations/dummy/ GET 폴링 시
의존성:
  - facilities.models.Geofence
  - facilities.models.Worker

설계 원칙:
  - JS는 worker_status 받아서 렌더링만 수행
  - 판단 로직은 서버 전담
  - 원형: 거리 공식
  - 폴리곤: Ray Casting 알고리즘
"""

import math


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
      - 점에서 오른쪽으로 무한 광선을 쏨
      - 광선이 폴리곤 변을 홀수 번 교차하면 내부
      - 짝수 번 교차하면 외부

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

        # 광선이 변을 교차하는지 확인
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside

        j = i

    return inside


# ── 단일 작업자 판단 ──────────────────────────────────────────

def check_worker_in_geofence(worker, loc) -> str:
    """
    작업자의 현재 위치가 어느 지오펜스 내부인지 판단.
    가장 높은 severity의 지오펜스 기준으로 worker_status 결정.

    Args:
        worker: facilities.models.Worker 인스턴스
        loc:    facilities.models.WorkerLocation 인스턴스

    Returns:
        'danger'  — 위험 지오펜스 내부
        'on_duty' — 지오펜스 외부 (정상 근무)
    """
    from facilities.models import Geofence

    if not loc.floor:
        return worker.current_state

    # 해당 floor의 active geofence 조회
    # severity 내림차순 — danger 먼저 판단
    geofences = Geofence.objects.filter(
        floor=loc.floor,
        is_active=True,
    ).exclude(severity='safe').order_by('-severity')

    for geofence in geofences:
        if geofence.geofence_type == 'circle':
            inside = is_inside_circle(loc.x, loc.y, geofence)
        elif geofence.geofence_type == 'polygon':
            inside = is_inside_polygon(loc.x, loc.y, geofence)
        else:
            continue

        if inside:
            # danger 지오펜스 내부 → 즉시 반환
            if geofence.severity == 'danger':
                return 'danger'
            # warning 지오펜스 내부 → 계속 순회 (더 높은 severity 있을 수 있음)
            # 현재는 danger/warning만 있으므로 warning이면 on_duty 유지
            # 추후 warning → 별도 상태 추가 시 여기서 처리

    return 'on_duty'


# ── Worker 상태 업데이트 ──────────────────────────────────────

def sync_worker_status(worker, loc) -> str:
    """
    작업자 지오펜스 내부 판단 후 Worker.current_state 업데이트.

    Returns:
        최종 worker_status 문자열 ('danger' | 'on_duty')
    """
    new_status = check_worker_in_geofence(worker, loc)

    if worker.current_state != new_status:
        worker.current_state = new_status
        worker.save(update_fields=['current_state'])

    return new_status