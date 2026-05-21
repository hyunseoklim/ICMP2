from django.contrib.auth.models import AbstractUser
from django.db import models


class Position(models.Model):
    name = models.CharField(max_length=100)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "positions"
        ordering = ["order"]
        verbose_name = "직위"
        verbose_name_plural = "직위 목록"

    def __str__(self):
        return self.name


class Department(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True, blank=True)
    leader = models.ForeignKey(
        'User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='led_departments'
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)
    updated_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='updated_departments'
    )

    class Meta:
        db_table            = "departments"
        verbose_name        = "부서"
        verbose_name_plural = "부서 목록"

    def __str__(self):
        return self.name
    
class User(AbstractUser):
    class UserType(models.TextChoices):
        ADMIN = "admin", "슈퍼관리자"
        MANAGER = "manager", "관리자"
        WORKER = "worker", "일반사용자"

    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    user_type = models.CharField(max_length=20, choices=UserType.choices, default=UserType.WORKER)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True,related_name="users")
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