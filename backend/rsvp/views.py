from django.shortcuts import render


def rsvp(request):
    return render(request, 'rsvp.html')
