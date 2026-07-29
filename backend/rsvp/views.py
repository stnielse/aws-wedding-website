import json

from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .models import MEAL_CHOICES, Party, RSVP


REPLY_BY_DATE = '1 April 2027'
VALID_MEAL_VALUES = {value for value, _ in MEAL_CHOICES}


def _party_by_code(code):
    return Party.objects.filter(lookup_code__iexact=code.strip()).first()


@require_http_methods(['GET', 'POST'])
def landing(request):
    error = None
    if request.method == 'POST':
        raw = request.POST.get('code', '')
        code = raw.strip().upper()
        if not code:
            error = 'Please enter the code from your invitation.'
        else:
            party = _party_by_code(code)
            if party is None:
                error = "We can't find that code. Double-check the invitation, or email us and we'll look you up."
            else:
                return redirect('rsvp:party', code=party.lookup_code)
    return render(request, 'rsvp_landing.html', {'error': error, 'reply_by': REPLY_BY_DATE})


def party(request, code):
    party_obj = _party_by_code(code)
    if party_obj is None:
        raise Http404('Party not found')

    guests = list(party_obj.guests.all().order_by('id'))
    guest_ids = [g.id for g in guests]
    existing = {r.guest_id: r for r in RSVP.objects.filter(guest_id__in=guest_ids)}

    data = {
        'submitUrl': reverse('rsvp:submit', kwargs={'code': party_obj.lookup_code}),
        'party': {
            'name': party_obj.name,
            'lookupCode': party_obj.lookup_code,
        },
        'guests': [
            {
                'id': g.id,
                'name': g.name,
                'plusOneAllowed': g.plus_one_allowed,
            }
            for g in guests
        ],
        'existingRsvps': [
            _rsvp_to_dict(existing[gid]) for gid in guest_ids if gid in existing
        ],
        'mealChoices': [{'value': v, 'label': l} for v, l in MEAL_CHOICES],
        'replyByDate': REPLY_BY_DATE,
    }
    return render(request, 'rsvp_party.html', {'party': party_obj, 'rsvp_data_json': json.dumps(data)})


@require_http_methods(['POST'])
def submit(request, code):
    party_obj = _party_by_code(code)
    if party_obj is None:
        raise Http404('Party not found')

    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'ok': False, 'errors': [{'message': 'Malformed request.'}]}, status=400)

    entries = payload.get('guests')
    if not isinstance(entries, list) or not entries:
        return JsonResponse({'ok': False, 'errors': [{'message': 'No guest responses submitted.'}]}, status=400)

    guests_by_id = {g.id: g for g in party_obj.guests.all()}
    errors = []
    cleaned = []

    for entry in entries:
        gid = entry.get('guest_id') if isinstance(entry, dict) else None
        guest = guests_by_id.get(gid)
        if guest is None:
            errors.append({'guest_id': gid, 'message': 'That guest is not in this party.'})
            continue

        attending = bool(entry.get('attending'))
        meal_choice = (entry.get('meal_choice') or '').strip()
        plus_one_attending = bool(entry.get('plus_one_attending')) and guest.plus_one_allowed
        plus_one_name = (entry.get('plus_one_name') or '').strip()
        plus_one_meal = (entry.get('plus_one_meal') or '').strip()
        notes = (entry.get('notes') or '').strip()

        if attending:
            if not meal_choice:
                errors.append({'guest_id': guest.id, 'field': 'meal_choice',
                               'message': f'Pick a dinner for {guest.name}.'})
            elif meal_choice not in VALID_MEAL_VALUES:
                errors.append({'guest_id': guest.id, 'field': 'meal_choice',
                               'message': 'That meal choice is not on the menu.'})

            if guest.plus_one_allowed and plus_one_attending:
                if not plus_one_name:
                    errors.append({'guest_id': guest.id, 'field': 'plus_one_name',
                                   'message': f"Tell us {guest.name}'s guest's name."})
                if not plus_one_meal:
                    errors.append({'guest_id': guest.id, 'field': 'plus_one_meal',
                                   'message': f"Pick a dinner for {guest.name}'s guest."})
                elif plus_one_meal not in VALID_MEAL_VALUES:
                    errors.append({'guest_id': guest.id, 'field': 'plus_one_meal',
                                   'message': 'That plus-one meal choice is not on the menu.'})
        else:
            meal_choice = ''
            plus_one_attending = False
            plus_one_name = ''
            plus_one_meal = ''

        cleaned.append({
            'guest': guest,
            'attending': attending,
            'meal_choice': meal_choice,
            'plus_one_attending': plus_one_attending,
            'plus_one_name': plus_one_name,
            'plus_one_meal': plus_one_meal,
            'notes': notes,
        })

    if errors:
        return JsonResponse({'ok': False, 'errors': errors}, status=400)

    receipt = []
    for row in cleaned:
        rsvp, _ = RSVP.objects.update_or_create(
            guest=row['guest'],
            defaults={
                'attending': row['attending'],
                'meal_choice': row['meal_choice'],
                'plus_one_attending': row['plus_one_attending'],
                'plus_one_name': row['plus_one_name'],
                'plus_one_meal': row['plus_one_meal'],
                'notes': row['notes'],
            },
        )
        receipt.append(_rsvp_to_dict(rsvp))

    return JsonResponse({'ok': True, 'receipt': receipt})


def _rsvp_to_dict(rsvp):
    return {
        'guest_id': rsvp.guest_id,
        'guest_name': rsvp.guest.name,
        'attending': rsvp.attending,
        'meal_choice': rsvp.meal_choice,
        'plus_one_attending': rsvp.plus_one_attending,
        'plus_one_name': rsvp.plus_one_name,
        'plus_one_meal': rsvp.plus_one_meal,
        'notes': rsvp.notes,
        'submitted_at': rsvp.submitted_at.isoformat() if rsvp.submitted_at else None,
    }
