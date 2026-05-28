from django.apps import AppConfig


class FacilitiesConfig(AppConfig):
    name = 'facilities'

    def ready(self):
        from . import signals  # noqa: F401
