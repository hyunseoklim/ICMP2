"""
데이터 수집 후처리 로직
- Device.last_seen_at 업데이트
- 장비 오프라인 감지
- 데이터 누락 감지
"""
from datetime import timedelta
from django.utils import timezone


OFFLINE_THRESHOLD_MINUTES = 5  # 5분 이상 데이터 없으면 오프라인


def update_last_seen(device) -> None:
    """
    데이터 수신 시 Device.last_seen_at 업데이트
    FastAPI /ingest/ 에서 호출
    """
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])


def check_device_offline(device) -> bool:
    """
    마지막 수신 시각 기준 장비 오프라인 여부
    """
    if device.last_seen_at is None:
        return True

    threshold = timezone.now() - timedelta(minutes=OFFLINE_THRESHOLD_MINUTES)
    return device.last_seen_at < threshold


def check_data_missing(device_uid: str) -> bool:
    """
    마지막 GasReading 수신 시각 기준 데이터 누락 여부
    alerts 앱에서 AlarmEvent 생성 시 사용
    """
    from monitoring.models import GasReading

    latest = GasReading.objects.filter(
        device__device_uid=device_uid
    ).order_by("-measured_at").first()

    if not latest:
        return True

    threshold = timezone.now() - timedelta(minutes=OFFLINE_THRESHOLD_MINUTES)
    return latest.measured_at < threshold


def get_offline_devices() -> list:
    """
    현재 오프라인 상태인 장비 목록 반환
    대시보드 / alerts 앱에서 사용
    """
    from monitoring.models import Device

    threshold = timezone.now() - timedelta(minutes=OFFLINE_THRESHOLD_MINUTES)

    return Device.objects.filter(
        device_type="gas",
        last_seen_at__lt=threshold
    ) | Device.objects.filter(
        device_type="gas",
        last_seen_at__isnull=True
    )