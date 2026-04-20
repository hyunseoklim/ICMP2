from django.db import models


class DashboardWidget(models.Model):
    class WidgetType(models.TextChoices):
        CHART = "chart", "차트"
        TABLE = "table", "테이블"
        GAUGE = "gauge", "게이지"
        MAP = "map", "지도"
        COUNTER = "counter", "카운터"

    widget_name = models.CharField(max_length=200)
    widget_type = models.CharField(max_length=20, choices=WidgetType.choices)
    target_type = models.CharField(max_length=50)
    query_config = models.JSONField()
    position_x = models.PositiveIntegerField(default=0)
    position_y = models.PositiveIntegerField(default=0)
    width = models.PositiveIntegerField(default=1)
    height = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "dashboard_widgets"

    def __str__(self):
        return f"{self.widget_name} ({self.widget_type})"


class DashboardLayout(models.Model):
    layout_name = models.CharField(max_length=200)
    role_code = models.CharField(max_length=50)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "dashboard_layouts"

    def __str__(self):
        return f"{self.layout_name} ({self.role_code})"


class DashboardWidgetBinding(models.Model):
    layout = models.ForeignKey(
        DashboardLayout, on_delete=models.CASCADE, related_name="widget_bindings"
    )
    widget = models.ForeignKey(
        DashboardWidget, on_delete=models.CASCADE, related_name="layout_bindings"
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "dashboard_widget_bindings"
        unique_together = ("layout", "widget")
        ordering = ["display_order"]

    def __str__(self):
        return f"{self.layout.layout_name} - {self.widget.widget_name} (order {self.display_order})"
