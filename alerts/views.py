from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required(login_url="login")
def event_list(request):
    return render(request, "alerts/event_list.html")
