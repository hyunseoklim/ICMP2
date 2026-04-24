from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required(login_url="login")
def worker_list(request):
    return render(request, "facilities/worker_list.html")
