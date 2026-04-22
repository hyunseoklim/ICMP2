"""
전력 장비 이상 판단 로직

채널 상태 정의:
- COMM_ERROR:    전류/전압/전력 모두 -1 → 통신불능
- PARTIAL_ERROR: 하나라도 -1 → 부분 오류 (데이터 오류)
- STALE:         데이터 없거나 2분 초과 → 수신 지연/중단
- NORMAL:        모두 정상값
"""

from datetime import timedelta
from django.utils import timezone

# 1분 주기 전송 기준, 2분 초과 시 stale 판단
STALE_THRESHOLD = timedelta(minutes=2)


def is_stale(ts) -> bool:
    """마지막 수신 시각 기준 stale 여부"""
    return timezone.now() - ts > STALE_THRESHOLD


def get_channel_status(current, voltage, power) -> str:
    """
    채널 상태 반환
    우선순위: STALE → COMM_ERROR → PARTIAL_ERROR → NORMAL
    """
    # 데이터 없거나 오래됨
    if (
        not current or is_stale(current.measured_at) or
        not voltage or is_stale(voltage.measured_at) or
        not power   or is_stale(power.measured_at)
    ):
        return "STALE"

    values = [current.value, voltage.value, power.value]

    # 전부 -1 → 통신불능
    if all(v == -1 for v in values):
        return "COMM_ERROR"

    # 일부만 -1 → 부분 오류 (데이터 오류)
    if any(v == -1 for v in values):
        return "PARTIAL_ERROR"

    return "NORMAL"


def is_channel_on(channel) -> bool:
    """
    채널 ON 여부
    PowerStatusReading 기준: ON=255, OFF=0
    데이터 없거나 stale이면 False 반환
    """
    from monitoring.models import PowerStatusReading

    status = PowerStatusReading.objects.filter(
        channel=channel
    ).order_by("-received_at").first()

    if not status:
        return False

    if is_stale(status.received_at):
        return False

    return status.status_value == 255


def get_channel_summary(device_uid: str) -> list:
    """
    특정 전력 장비의 채널별 최신 상태 요약
    alerts 앱 / 대시보드에서 사용

    반환 예시:
    [
        {
            "channel":          "slave01",
            "is_on":            True,
            "status":           "NORMAL",
            "is_comm_error":    False,
            "is_partial_error": False,
            "is_stale":         False,
            "current":          30,
            "voltage":          220,
            "power":            6600,
        },
    ]
    """
    from monitoring.models import (
        DeviceChannel,
        CurrentReading,
        VoltageReading,
        PowerReading,
    )

    channels = DeviceChannel.objects.filter(
        device__device_uid=device_uid
    )
    result = []

    for channel in channels:
        current = CurrentReading.objects.filter(
            channel=channel
        ).order_by("-measured_at").first()

        voltage = VoltageReading.objects.filter(
            channel=channel
        ).order_by("-measured_at").first()

        power = PowerReading.objects.filter(
            channel=channel
        ).order_by("-measured_at").first()

        status = get_channel_status(current, voltage, power)

        result.append({
            "channel":          channel.channel_code,
            "is_on":            is_channel_on(channel),
            "status":           status,
            "is_comm_error":    status == "COMM_ERROR",
            "is_partial_error": status == "PARTIAL_ERROR",
            "is_stale":         status == "STALE",
            "current":          current.value if current else None,
            "voltage":          voltage.value if voltage else None,
            "power":            power.value   if power   else None,
        })

    return result