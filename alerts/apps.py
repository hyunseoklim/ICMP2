from django.apps import AppConfig


class AlertsConfig(AppConfig):
    name = 'alerts'

    def ready(self):
        # Django 시작 시 커스텀 Prometheus 메트릭을 레지스트리에 등록
        from alerts import tasks  # noqa: F401
