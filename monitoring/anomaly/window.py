"""
Sliding Window — 장비별·가스별 최근 N개 값 버퍼

구조:
  _buffers[device_uid][gas] = deque(maxlen=BUFFER_SIZE)

WINDOW_SIZE(W): STEP D 계산 단위 (최근 30개)
BUFFER_SIZE:    STEP E 비교 단위 (이전 W개 + 최근 W개 = 2W개)

MVP: Python 메모리 deque (Redis로 교체 가능)
서버 재시작 시 init_from_db()로 버퍼 복원.
"""

from collections import deque

GAS_FIELDS = ['co', 'h2s', 'co2', 'o2', 'no2', 'so2', 'o3', 'nh3', 'voc']
WINDOW_SIZE = 30               # STEP D 단위 (W)
BUFFER_SIZE = WINDOW_SIZE * 2  # STEP E 단위 (2W = 60)

# _buffers[device_uid][gas] = deque(maxlen=BUFFER_SIZE)
_buffers: dict[str, dict[str, deque]] = {}


def _ensure_buffer(device_uid: str) -> None:
    if device_uid not in _buffers:
        _buffers[device_uid] = {
            gas: deque(maxlen=BUFFER_SIZE) for gas in GAS_FIELDS
        }


def push(device_uid: str, reading) -> None:
    """새 GasReading을 버퍼에 추가. ingest_gas() 수신 직후 호출."""
    _ensure_buffer(device_uid)
    buf = _buffers[device_uid]
    for gas in GAS_FIELDS:
        value = getattr(reading, gas, None)
        if value is not None:
            buf[gas].append(float(value))


def get(device_uid: str, gas: str, n: int = WINDOW_SIZE) -> list[float]:
    """
    특정 가스 최근 N개 반환 (오래된 순 → 최신 순).
    버퍼가 비어있으면 DB에서 초기화 후 반환.
    """
    _ensure_buffer(device_uid)
    buf = _buffers[device_uid][gas]

    if not buf:
        init_from_db(device_uid)
        buf = _buffers[device_uid][gas]

    values = list(buf)
    return values[-n:] if len(values) > n else values


def get_vectors(device_uid: str, n: int = WINDOW_SIZE) -> list[list[float]]:
    """
    9개 가스 동시에 N개 반환 → Isolation Forest 입력용.
    반환 형태: [[co, h2s, co2, o2, no2, so2, o3, nh3, voc], ...] (N행 × 9열)
    모든 가스가 유효한 행만 포함.
    """
    _ensure_buffer(device_uid)
    buf = _buffers[device_uid]

    if not any(buf[gas] for gas in GAS_FIELDS):
        init_from_db(device_uid, n=n)

    # 가스별 리스트를 zip으로 묶어서 행 단위로 변환
    lists = [list(buf[gas]) for gas in GAS_FIELDS]
    min_len = min(len(lst) for lst in lists)
    if min_len == 0:
        return []

    rows = [
        [lists[i][j] for i in range(len(GAS_FIELDS))]
        for j in range(max(0, min_len - n), min_len)
    ]
    return rows


def is_ready(device_uid: str, gas: str, min_samples: int = 10) -> bool:
    """Z-score 계산 가능 여부 (최소 샘플 수 충족 여부)."""
    if device_uid not in _buffers:
        return False
    return len(_buffers[device_uid].get(gas, [])) >= min_samples


def init_from_db(device_uid: str, n: int = BUFFER_SIZE) -> None:
    """
    DB에서 최근 N개 읽어 버퍼를 채움.
    서버 재시작 시 또는 버퍼가 비어있을 때 호출.
    quality_flag == 'ok' 인 행만 사용.
    """
    from monitoring.models import GasReading

    _ensure_buffer(device_uid)
    buf = _buffers[device_uid]

    qs = (
        GasReading.objects
        .filter(device__device_uid=device_uid, quality_flag='ok')
        .order_by('-measured_at')[:n]
    )

    # 오래된 순으로 버퍼에 채움
    for reading in reversed(list(qs)):
        for gas in GAS_FIELDS:
            value = getattr(reading, gas, None)
            if value is not None:
                buf[gas].append(float(value))


# ── DB 직접 조회 (버퍼 없이 사용) ─────────────────────────────

def get_window(device_uid: str, gas: str, n: int = WINDOW_SIZE) -> list[float]:
    """
    DB에서 직접 최근 N개 조회 (오래된 순).
    버퍼 없이 one-off 조회가 필요할 때 사용.
    """
    from monitoring.models import GasReading

    qs = (
        GasReading.objects
        .filter(device__device_uid=device_uid, quality_flag='ok')
        .filter(**{f"{gas}__isnull": False})
        .order_by('-measured_at')[:n]
    )
    return [float(getattr(r, gas)) for r in reversed(list(qs))]


def get_window_readings(device_uid: str, n: int = WINDOW_SIZE):
    """
    DB에서 직접 최근 N개 GasReading 객체 반환 (오래된 순).
    Isolation Forest 초기 학습용.
    """
    from monitoring.models import GasReading

    qs = (
        GasReading.objects
        .filter(device__device_uid=device_uid, quality_flag='ok')
        .order_by('-measured_at')[:n]
    )
    return list(reversed(list(qs)))
