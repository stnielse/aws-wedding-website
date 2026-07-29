import json

from django.test import Client, TestCase
from django.urls import reverse

from .models import RSVP, Guest, Party


def _post_json(client, url, payload, csrf_token):
    return client.post(
        url,
        data=json.dumps(payload),
        content_type='application/json',
        HTTP_X_CSRFTOKEN=csrf_token,
    )


class LandingTests(TestCase):
    def setUp(self):
        self.party = Party.objects.create(name='Alvarez–Okafor', lookup_code='FALLS-3K7')

    def test_get_landing_renders_lookup_form(self):
        response = self.client.get(reverse('rsvp:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="code"')
        self.assertContains(response, "Let's find your invitation")

    def test_post_valid_code_redirects_to_party_page(self):
        response = self.client.post(reverse('rsvp:landing'), {'code': 'falls-3k7'})
        self.assertRedirects(
            response,
            reverse('rsvp:party', kwargs={'code': 'FALLS-3K7'}),
            fetch_redirect_response=False,
        )

    def test_post_unknown_code_re_renders_with_error(self):
        response = self.client.post(reverse('rsvp:landing'), {'code': 'NOPE-XYZ'})
        self.assertEqual(response.status_code, 200)
        # HTML-escapes the apostrophe, so match on unpunctuated substring.
        self.assertContains(response, 'Double-check the invitation')

    def test_post_empty_code_re_renders_with_error(self):
        response = self.client.post(reverse('rsvp:landing'), {'code': '   '})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please enter the code')


class PartyPageTests(TestCase):
    def setUp(self):
        self.party = Party.objects.create(name='Alvarez–Okafor', lookup_code='FALLS-3K7')
        self.marguerite = Guest.objects.create(party=self.party, name='Marguerite Alvarez', plus_one_allowed=True)
        self.daniel = Guest.objects.create(party=self.party, name='Daniel Okafor', plus_one_allowed=False)

    def test_get_valid_code_renders_party_page(self):
        response = self.client.get(reverse('rsvp:party', kwargs={'code': 'FALLS-3K7'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="rsvp-root"')
        self.assertContains(response, 'id="rsvp-data"')
        self.assertContains(response, 'Marguerite Alvarez')

    def test_case_insensitive_lookup(self):
        response = self.client.get(reverse('rsvp:party', kwargs={'code': 'falls-3k7'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Marguerite Alvarez')

    def test_unknown_code_returns_404(self):
        response = self.client.get(reverse('rsvp:party', kwargs={'code': 'NOPE-XYZ'}))
        self.assertEqual(response.status_code, 404)

    def test_party_page_serializes_expected_shape(self):
        response = self.client.get(reverse('rsvp:party', kwargs={'code': 'FALLS-3K7'}))
        raw = response.content.decode('utf-8')
        start = raw.index('id="rsvp-data">') + len('id="rsvp-data">')
        end = raw.index('</script>', start)
        data = json.loads(raw[start:end])
        self.assertIn('csrfToken', data)
        self.assertIn('submitUrl', data)
        self.assertEqual(data['party']['lookupCode'], 'FALLS-3K7')
        self.assertEqual(len(data['guests']), 2)
        self.assertEqual(data['existingRsvps'], [])
        self.assertEqual([m['value'] for m in data['mealChoices']], ['short_rib', 'trout', 'farrotto'])

    def test_party_page_populates_existing_rsvps_when_present(self):
        RSVP.objects.create(guest=self.marguerite, attending=True, meal_choice='trout')
        RSVP.objects.create(guest=self.daniel, attending=False)
        response = self.client.get(reverse('rsvp:party', kwargs={'code': 'FALLS-3K7'}))
        raw = response.content.decode('utf-8')
        start = raw.index('id="rsvp-data">') + len('id="rsvp-data">')
        end = raw.index('</script>', start)
        data = json.loads(raw[start:end])
        self.assertEqual(len(data['existingRsvps']), 2)
        marguerite_rsvp = next(r for r in data['existingRsvps'] if r['guest_id'] == self.marguerite.id)
        self.assertEqual(marguerite_rsvp['meal_choice_label'], 'Trout, almondine')


class SubmitTests(TestCase):
    def setUp(self):
        self.party = Party.objects.create(name='Alvarez–Okafor', lookup_code='FALLS-3K7')
        self.marguerite = Guest.objects.create(party=self.party, name='Marguerite Alvarez', plus_one_allowed=True)
        self.daniel = Guest.objects.create(party=self.party, name='Daniel Okafor', plus_one_allowed=False)
        # Enforce CSRF checks — the submit endpoint is only reachable via POST
        # with a valid token, and we want the tests to cover that path.
        self.client = Client(enforce_csrf_checks=True)
        # Warm-up GET to seed the csrftoken cookie the way a real browser would.
        get = self.client.get(reverse('rsvp:party', kwargs={'code': 'FALLS-3K7'}))
        self.csrf_token = get.cookies['csrftoken'].value
        self.submit_url = reverse('rsvp:submit', kwargs={'code': 'FALLS-3K7'})

    def _payload(self, **overrides):
        default = {
            'guests': [
                {
                    'guest_id': self.marguerite.id,
                    'attending': True,
                    'meal_choice': 'trout',
                    'plus_one_attending': True,
                    'plus_one_name': 'Daniel Okafor',
                    'plus_one_meal': 'short_rib',
                    'notes': 'No shellfish.',
                },
                {
                    'guest_id': self.daniel.id,
                    'attending': True,
                    'meal_choice': 'farrotto',
                    'plus_one_attending': False,
                    'plus_one_name': '',
                    'plus_one_meal': '',
                    'notes': '',
                },
            ]
        }
        default.update(overrides)
        return default

    def test_valid_submit_creates_rsvps_and_returns_receipt(self):
        response = _post_json(self.client, self.submit_url, self._payload(), self.csrf_token)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertEqual(len(body['receipt']), 2)
        self.assertEqual(RSVP.objects.count(), 2)
        marguerite_row = RSVP.objects.get(guest=self.marguerite)
        self.assertEqual(marguerite_row.meal_choice, 'trout')
        self.assertTrue(marguerite_row.plus_one_attending)
        self.assertEqual(marguerite_row.plus_one_name, 'Daniel Okafor')

    def test_second_submit_updates_existing_rows(self):
        _post_json(self.client, self.submit_url, self._payload(), self.csrf_token)
        edited = self._payload()
        edited['guests'][0]['meal_choice'] = 'short_rib'
        edited['guests'][0]['plus_one_attending'] = False
        edited['guests'][0]['plus_one_name'] = ''
        edited['guests'][0]['plus_one_meal'] = ''
        response = _post_json(self.client, self.submit_url, edited, self.csrf_token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(RSVP.objects.count(), 2)  # updated, not duplicated
        marguerite_row = RSVP.objects.get(guest=self.marguerite)
        self.assertEqual(marguerite_row.meal_choice, 'short_rib')
        self.assertFalse(marguerite_row.plus_one_attending)

    def test_missing_meal_returns_400_with_error(self):
        payload = self._payload()
        payload['guests'][0]['meal_choice'] = ''
        response = _post_json(self.client, self.submit_url, payload, self.csrf_token)
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body['ok'])
        self.assertTrue(any(
            e.get('field') == 'meal_choice' and e.get('guest_id') == self.marguerite.id
            for e in body['errors']
        ))
        self.assertEqual(RSVP.objects.count(), 0)

    def test_declined_guest_does_not_need_meal(self):
        payload = self._payload()
        payload['guests'][0]['attending'] = False
        payload['guests'][0]['meal_choice'] = ''
        payload['guests'][0]['plus_one_attending'] = False
        payload['guests'][0]['plus_one_name'] = ''
        payload['guests'][0]['plus_one_meal'] = ''
        response = _post_json(self.client, self.submit_url, payload, self.csrf_token)
        self.assertEqual(response.status_code, 200)
        marguerite_row = RSVP.objects.get(guest=self.marguerite)
        self.assertFalse(marguerite_row.attending)
        self.assertEqual(marguerite_row.meal_choice, '')

    def test_plus_one_attending_requires_name_and_meal(self):
        payload = self._payload()
        payload['guests'][0]['plus_one_name'] = ''
        payload['guests'][0]['plus_one_meal'] = ''
        response = _post_json(self.client, self.submit_url, payload, self.csrf_token)
        self.assertEqual(response.status_code, 400)
        body = response.json()
        fields = {e.get('field') for e in body['errors']}
        self.assertIn('plus_one_name', fields)
        self.assertIn('plus_one_meal', fields)

    def test_invalid_meal_value_rejected(self):
        payload = self._payload()
        payload['guests'][0]['meal_choice'] = 'lobster_thermidor'
        response = _post_json(self.client, self.submit_url, payload, self.csrf_token)
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertTrue(any(e.get('field') == 'meal_choice' for e in body['errors']))

    def test_guest_id_not_in_party_rejected(self):
        stranger = Party.objects.create(name='Other', lookup_code='OTHER-XX')
        outsider = Guest.objects.create(party=stranger, name='Outsider')
        payload = {
            'guests': [
                {
                    'guest_id': outsider.id,
                    'attending': True,
                    'meal_choice': 'trout',
                    'plus_one_attending': False,
                    'plus_one_name': '',
                    'plus_one_meal': '',
                    'notes': '',
                }
            ]
        }
        response = _post_json(self.client, self.submit_url, payload, self.csrf_token)
        self.assertEqual(response.status_code, 400)

    def test_submit_to_unknown_party_returns_404(self):
        response = _post_json(
            self.client,
            reverse('rsvp:submit', kwargs={'code': 'NOPE-XYZ'}),
            self._payload(),
            self.csrf_token,
        )
        self.assertEqual(response.status_code, 404)

    def test_malformed_json_returns_400(self):
        response = self.client.post(
            self.submit_url,
            data='not-json',
            content_type='application/json',
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )
        self.assertEqual(response.status_code, 400)


class ModelTests(TestCase):
    def test_party_uppercases_lookup_code_on_save(self):
        party = Party.objects.create(name='Test', lookup_code='falls-3k7')
        self.assertEqual(party.lookup_code, 'FALLS-3K7')

    def test_party_strips_whitespace_from_lookup_code(self):
        party = Party.objects.create(name='Test', lookup_code='  spaced-code  ')
        self.assertEqual(party.lookup_code, 'SPACED-CODE')

    def test_str_methods(self):
        party = Party.objects.create(name='Alvarez–Okafor', lookup_code='ABC-123')
        guest = Guest.objects.create(party=party, name='Marguerite')
        rsvp = RSVP.objects.create(guest=guest, attending=True, meal_choice='trout')
        self.assertEqual(str(party), 'Alvarez–Okafor')
        self.assertEqual(str(guest), 'Marguerite')
        self.assertEqual(str(rsvp), 'RSVP: Marguerite')
