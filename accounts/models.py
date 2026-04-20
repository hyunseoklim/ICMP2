from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class UserType(models.TextChoices):
        ADMIN = "admin", "관리자"
        MANAGER = "manager", "현장 관리자"
        WORKER = "worker", "작업자"

    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    user_type = models.CharField(max_length=20, choices=UserType.choices, default=UserType.WORKER)
    department = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=100, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "users"

    def __str__(self):
        return f"{self.name} ({self.username})"


class Role(models.Model):
    role_code = models.CharField(max_length=50, unique=True)
    role_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "roles"

    def __str__(self):
        return f"{self.role_name} ({self.role_code})"


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")

    class Meta:
        db_table = "user_roles"
        unique_together = ("user", "role")

    def __str__(self):
        return f"{self.user.username} - {self.role.role_code}"


class LoginHistory(models.Model):
    class LoginResult(models.TextChoices):
        SUCCESS = "success", "성공"
        FAILURE = "failure", "실패"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_histories")
    ip_address = models.GenericIPAddressField()
    login_result = models.CharField(max_length=10, choices=LoginResult.choices)
    login_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "login_histories"
        ordering = ["-login_at"]

    def __str__(self):
        return f"{self.user.username} [{self.login_result}] @ {self.login_at}"
