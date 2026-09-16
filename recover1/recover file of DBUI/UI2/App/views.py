from django.shortcuts import render
from django.http import JsonResponse, HttpResponse

def hello(request):
    return HttpResponse("Hello, World!")