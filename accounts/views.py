import re

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render


def _validate_username(value):
    if not value:
        return "아이디를 입력해주세요."
    if not re.fullmatch(r"[a-zA-Z0-9]+", value):
        return "아이디는 영문 또는 숫자만 입력할 수 있습니다."
    if not (4 <= len(value) <= 20):
        return "아이디를 4~20자로 입력해주세요."
    return None


def _validate_password(value):
    if not value:
        return "비밀번호를 입력해주세요."
    if len(value) < 8:
        return "비밀번호를 8자 이상 입력해야 합니다."
    has_letter = bool(re.search(r"[a-zA-Z]", value))
    has_number = bool(re.search(r"[0-9]", value))
    has_special = bool(re.search(r"[^a-zA-Z0-9]", value))
    if sum([has_letter, has_number, has_special]) < 2:
        return "비밀번호는 영문, 숫자, 특수문자 중 2가지 이상을 포함해야 합니다."
    return None


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")

        username_error = _validate_username(username)
        password_error = _validate_password(password)

        if username_error or password_error:
            return render(request, "accounts/login.html", {
                "username": username,
                "username_error": username_error,
                "password_error": password_error,
            })

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")

        return render(request, "accounts/login.html", {
            "username": username,
            "auth_error": "아이디 또는 비밀번호가 올바르지 않습니다.",
        })

    return render(request, "accounts/login.html")


def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def profile_view(request):
    return render(request, "accounts/profile.html")


@login_required
def change_password_view(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "잘못된 요청입니다."}, status=405)

    current = request.POST.get("current_password", "")
    new_pw = request.POST.get("new_password", "")
    confirm = request.POST.get("confirm_password", "")

    if not current:
        return JsonResponse({"ok": False, "field": "current", "error": "현재 사용 중인 비밀번호를 입력해 주세요."})

    if not request.user.check_password(current):
        return JsonResponse({"ok": False, "field": "current", "error": "현재 비밀번호가 일치하지 않습니다. 다시 확인해 주세요."})

    if not new_pw:
        return JsonResponse({"ok": False, "field": "new", "error": "새로운 비밀번호를 입력해 주세요."})

    if current == new_pw:
        return JsonResponse({"ok": False, "field": "new", "error": "현재 사용 중인 비밀번호는 신규 비밀번호로 사용할 수 없습니다."})

    has_letter = bool(re.search(r"[a-zA-Z]", new_pw))
    has_number = bool(re.search(r"[0-9]", new_pw))
    has_special = bool(re.search(r"[^a-zA-Z0-9]", new_pw))
    if not (8 <= len(new_pw) <= 16) or sum([has_letter, has_number, has_special]) < 2:
        return JsonResponse({"ok": False, "field": "new", "error": "8~16자의 영문, 숫자, 특수문자를 조합하여 입력해 주세요."})

    if not confirm:
        return JsonResponse({"ok": False, "field": "confirm", "error": "비밀번호 확인을 위해 한 번 더 입력해 주세요."})

    if new_pw != confirm:
        return JsonResponse({"ok": False, "field": "confirm", "error": "입력하신 신규 비밀번호와 일치하지 않습니다."})

    request.user.set_password(new_pw)
    request.user.save()
    update_session_auth_hash(request, request.user)
    return JsonResponse({"ok": True})
    