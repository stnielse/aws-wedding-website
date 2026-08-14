from django.shortcuts import render


def home(request):
    return render(request, 'home.html')


def travel(request):
    return render(request, 'coming_soon.html', {'page_title': 'Travel & where to stay'})


def registry(request):
    return render(request, 'coming_soon.html', {'page_title': 'Registry'})
