"""Tests for the `pages` app — currently focused on home page rendering.

Session 9 introduced real engagement photos in four slots (hero, story arch
portrait, photo-break, four teaser tiles). These tests protect the rendered
markup against regressions: swap-in of the four `<img>` elements, retirement
of the striped `img-slot` divs on home, and the `srcset` shape delivered by
the `{% engagement_photo %}` template tag.
"""

from django.test import Client, TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.response = self.client.get(reverse('pages:home'))

    def test_returns_200(self):
        self.assertEqual(self.response.status_code, 200)

    def test_hero_img_is_present_with_srcset(self):
        html = self.response.content.decode()
        self.assertIn('class="hero__img"', html)
        self.assertIn('srcset="', html)
        self.assertIn(' 640w,', html)
        self.assertIn(' 1024w,', html)
        self.assertIn(' 1600w,', html)
        self.assertIn(' 2400w"', html)

    def test_hero_img_has_intrinsic_dimensions(self):
        html = self.response.content.decode()
        # hero source is 5680x3787; dimensions come from the sidecar so any
        # width/height numeric attribute proves the tag resolved the sidecar.
        self.assertIn('width="5680"', html)
        self.assertIn('height="3787"', html)

    def test_arch_and_break_and_four_teasers_render(self):
        html = self.response.content.decode()
        self.assertIn('class="story__img"', html)
        self.assertIn('class="photo-break__img"', html)
        self.assertEqual(html.count('class="photos-teaser__img"'), 4)

    def test_hero_and_teasers_use_correct_loading_attrs(self):
        html = self.response.content.decode()
        # Hero above the fold — eager + high priority
        self.assertIn('loading="eager"', html)
        self.assertIn('fetchpriority="high"', html)
        # Everything below the hero — lazy. Four teasers + arch + break = 6.
        self.assertGreaterEqual(html.count('loading="lazy"'), 6)

    def test_placeholder_img_slots_are_gone_on_home(self):
        """Regression fence: a future revert that reintroduces the striped
        placeholder divs on home would silently ship wireframes."""
        html = self.response.content.decode()
        self.assertNotIn('img-slot--16-9', html)
        self.assertNotIn('img-slot--3-4-arch', html)
        self.assertNotIn('img-slot--1-1', html)

    def test_hero_srcset_urls_point_at_derivatives(self):
        html = self.response.content.decode()
        self.assertIn('img/engagement/derivatives/hero-640', html)
        self.assertIn('img/engagement/derivatives/hero-2400', html)


class ComingSoonPagesTests(TestCase):
    """Coming-soon interior pages still render — smoke coverage only."""

    def test_travel_returns_200(self):
        self.assertEqual(self.client.get(reverse('pages:travel')).status_code, 200)

    def test_registry_returns_200(self):
        self.assertEqual(self.client.get(reverse('pages:registry')).status_code, 200)

    def test_gallery_returns_200(self):
        self.assertEqual(self.client.get(reverse('pages:gallery')).status_code, 200)
