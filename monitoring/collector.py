"""
데이터 수집 후처리 로직
- Device.last_seen_at 업데이트
- 데이터 누락 감지는 alerts.tasks.check_missing_devices (AlarmRule.missing_timeout_seconds 기반)
"""
from django.utils import timezone


def update_last_seen(device) -> None:
    """데이터 수신 시 Device.last_seen_at 업데이트. FastAPI /ingest/ 에서 호출."""
    device.last_seen_at = timezone.now()
    device.save(update_fields=["last_seen_at"])
