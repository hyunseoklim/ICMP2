from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required(login_url="login")
def monitoring_detail(request):
    return render(request, "monitoring/monitoring_detail.html")


@login_required(login_url="login")
def power_detail(request):
    return render(request, "monitoring/power_detail.html")


@login_required(login_url="login")
def gas_detail(request):
    return render(request, "monitoring/gas_detail.html")
