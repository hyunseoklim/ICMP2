"""
전력 채널별 슬라이딩 윈도우 버퍼

구조:
  _buffers[(device_uid, channel_code)] = deque(maxlen=WINDOW_SIZE)
  값은 load_ratio (부하율 %) 로 정규화해서 저장

서버 재시작 시 init_from_db()로 버퍼 복원.
"""

from collections import deque

WINDOW_SIZE = 30  # 최근 30개 (30분치)
MIN_SAMPLES = 20  # ARIMA 최소 학습 샘플

# _buffers[(device_uid, channel_code)] = deque(maxlen=WINDOW_SIZE)
_buffers: dict[tuple, deque] = {}


def _key(device_uid: str, channel_code: str) -> tuple:
    return (device_uid, channel_code)


def push(device_uid: str, channel_code: str, load_ratio: float) -> None:
    """새 부하율 값을 버퍼에 추가. ingest_power() 수신 직후 호출."""
    k = _key(device_uid, channel_code)
    if k not in _buffers:
        _buffers[k] = deque(maxlen=WINDOW_SIZE)
    _buffers[k].append(round(load_ratio, 2))


def get(device_uid: str, channel_code: str) -> list[float]:
    """채널 버퍼의 최근 값 목록 반환 (오래된 순 → 최신 순)."""
    k = _key(device_uid, channel_code)
    return list(_buffers.get(k, []))


def is_ready(device_uid: str, channel_code: str) -> bool:
    """ARIMA 계산 가능 여부 (MIN_SAMPLES 충족)."""
    return len(get(device_uid, channel_code)) >= MIN_SAMPLES


def init_from_db(device_uid: str, channel_code: str) -> None:
    """
    DB에서 최근 WINDOW_SIZE개 읽어 버퍼를 채움.
    서버 재시작 시 또는 버퍼가 비어있을 때 호출.
    """
    from monitoring.models import PowerReading, DeviceChannel

    ch = DeviceChannel.objects.filter(
        device__device_uid=device_uid,
        channel_code=channel_code,
        is_active=True,
    ).first()
    if not ch:
        return

    rated = ch.rated_power_w or 1000
    qs = (
        PowerReading.objects
        .filter(channel=ch, quality_flag='ok', power_w__gte=0)
        .order_by('-measured_at')[:WINDOW_SIZE]
    )
    k = _key(device_uid, channel_code)
    if k not in _buffers:
        _buffers[k] = deque(maxlen=WINDOW_SIZE)

    for r in reversed(list(qs)):
        _buffers[k].append(round(r.power_w / rated * 100, 2))
