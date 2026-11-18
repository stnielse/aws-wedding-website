"""Tests for the storage + logging plumbing added in Session 10, the
ALLOWED_HOSTS parsing added in Session 13, and the CloudFront-aware
settings (CSRF_TRUSTED_ORIGINS, secure cookies, proxy SSL header,
S3 location prefixes) added in Session 14."""

import importlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from config.log_formatters import JsonFormatter, SkipClient4xx
from config.storage_backends import ManifestS3StaticStorage


class ManifestS3StaticStorageTests(SimpleTestCase):
    def test_mro_composes_manifest_mixin_and_s3_static_storage(self):
        from django.contrib.staticfiles.storage import ManifestFilesMixin
        from storages.backends.s3 import S3StaticStorage

        mro = ManifestS3StaticStorage.__mro__
        self.assertIn(ManifestFilesMixin, mro)
        self.assertIn(S3StaticStorage, mro)
        # ManifestFilesMixin must appear before S3StaticStorage so its
        # post_process hook wins.
        self.assertLess(mro.index(ManifestFilesMixin), mro.index(S3StaticStorage))

    def test_inherits_manifest_hashing_api(self):
        # The mixin exposes hashed_name — that's the smoke test for whether
        # collectstatic will actually hash filenames.
        self.assertTrue(hasattr(ManifestS3StaticStorage, 'hashed_name'))
        self.assertTrue(hasattr(ManifestS3StaticStorage, 'post_process'))


class JsonFormatterTests(SimpleTestCase):
    def setUp(self):
        self.formatter = JsonFormatter()

    def _format(self, record):
        return json.loads(self.formatter.format(record))

    def _make_record(self, msg='hello', level=logging.INFO, **extra):
        record = logging.LogRecord(
            name='test.logger',
            level=level,
            pathname=__file__,
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_core_fields(self):
        payload = self._format(self._make_record())
        self.assertEqual(payload['level'], 'INFO')
        self.assertEqual(payload['logger'], 'test.logger')
        self.assertEqual(payload['message'], 'hello')
        self.assertRegex(payload['timestamp'], r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')

    def test_extra_kwargs_surface_at_top_level(self):
        payload = self._format(self._make_record(guest_id=42, party_code='FALLS-3K7'))
        self.assertEqual(payload['guest_id'], 42)
        self.assertEqual(payload['party_code'], 'FALLS-3K7')

    def test_reserved_logrecord_attrs_are_not_leaked(self):
        payload = self._format(self._make_record())
        # None of the internal LogRecord fields should end up as JSON keys.
        for reserved in ('args', 'levelno', 'pathname', 'msg', 'process'):
            self.assertNotIn(reserved, payload)

    def test_exception_info_nested(self):
        try:
            raise ValueError('boom')
        except ValueError:
            import sys

            record = self._make_record(msg='oops', level=logging.ERROR)
            record.exc_info = sys.exc_info()
        payload = self._format(record)
        self.assertIn('exception', payload)
        self.assertEqual(payload['exception']['type'], 'ValueError')
        self.assertEqual(payload['exception']['message'], 'boom')
        self.assertIn('ValueError: boom', payload['exception']['stack'])

    def test_non_json_serializable_extra_falls_back_to_str(self):
        class Weird:
            def __str__(self):
                return 'weird-repr'

        payload = self._format(self._make_record(thing=Weird()))
        self.assertEqual(payload['thing'], 'weird-repr')


class SkipClient4xxTests(SimpleTestCase):
    """SkipClient4xx drops 4xx WARNING records from django.request (bot
    scanner noise) and keeps everything else. See Session 20."""

    def setUp(self):
        self.filter = SkipClient4xx()

    def _make_record(self, level=logging.WARNING, **extra):
        record = logging.LogRecord(
            name='django.request',
            level=level,
            pathname=__file__,
            lineno=1,
            msg='Not Found: %s',
            args=('/wp-admin/install.php',),
            exc_info=None,
        )
        for key, value in extra.items():
            setattr(record, key, value)
        return record

    def test_drops_404(self):
        # The prototypical case: bots probing /.env, /wp-admin, etc.
        self.assertFalse(self.filter.filter(self._make_record(status_code=404)))

    def test_drops_all_4xx(self):
        for status in (400, 401, 403, 404, 418, 429, 499):
            with self.subTest(status=status):
                record = self._make_record(status_code=status)
                self.assertFalse(self.filter.filter(record))

    def test_keeps_5xx(self):
        # 5xx must never be filtered -- these are what the django-errors
        # CloudWatch alarm exists to catch.
        for status in (500, 502, 503, 504):
            with self.subTest(status=status):
                record = self._make_record(level=logging.ERROR, status_code=status)
                self.assertTrue(self.filter.filter(record))

    def test_keeps_boundary_at_500(self):
        # Strict >= 500 boundary: 499 out, 500 in.
        self.assertFalse(self.filter.filter(self._make_record(status_code=499)))
        self.assertTrue(self.filter.filter(self._make_record(status_code=500)))

    def test_keeps_records_without_status_code(self):
        # Defense-in-depth: non-request logs routed through a shared
        # handler must not be silently swallowed. Only status-bearing 4xx
        # records get dropped.
        record = self._make_record()
        self.assertFalse(hasattr(record, 'status_code'))
        self.assertTrue(self.filter.filter(record))


class ProductionLoggingWiringTests(SimpleTestCase):
    """Verify the LOGGING dict in production.settings wires SkipClient4xx
    onto django.request. Guards against the filter class existing but
    silently unhooked -- the failure mode that would let the whole class
    of scanner-noise WARNINGs back into CloudWatch."""

    def test_skip_client_4xx_registered_as_filter(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertIn('skip_client_4xx', module.LOGGING['filters'])
        self.assertEqual(
            module.LOGGING['filters']['skip_client_4xx']['()'],
            'config.log_formatters.SkipClient4xx',
        )

    def test_django_request_logger_uses_the_filter(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        request_logger = module.LOGGING['loggers']['django.request']
        self.assertIn('skip_client_4xx', request_logger.get('filters', []))

    def test_django_request_level_stays_warning(self):
        # Filter is the gate, not the level. Bumping the level to ERROR
        # would double up the muting and hide 4xx records from any future
        # filter change; keep the level at WARNING so intent stays in one
        # place.
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertEqual(module.LOGGING['loggers']['django.request']['level'], 'WARNING')


class AllowedHostsParsingTests(SimpleTestCase):
    """production.settings parses ALLOWED_HOSTS as a comma-separated env var
    (Session 13). Falls back to [DOMAIN] when ALLOWED_HOSTS is unset."""

    # Minimum env every reimport of production.settings needs; ALLOWED_HOSTS
    # is set/omitted per-test to exercise the parsing branch.
    _base_env = {
        'DJANGO_SECRET_KEY': 'test-secret-key-not-used-outside-tests',
        'DOMAIN': 'example.com',
        'DB_NAME': 'wedding',
        'DB_USER': 'wedding_admin',
        'DB_PASSWORD': 'test-pw',
        'DB_HOST': 'db.example.com',
        'DB_PORT': '5432',
        'AWS_STORAGE_BUCKET_NAME': 'media-bucket',
        'AWS_STATIC_BUCKET_NAME': 'static-bucket',
        'AWS_REGION': 'us-east-1',
    }

    def _reimport_production(self):
        sys.modules.pop('config.settings.production', None)
        return importlib.import_module('config.settings.production')

    def test_defaults_to_domain_when_allowed_hosts_unset(self):
        env = dict(self._base_env)
        env.pop('ALLOWED_HOSTS', None)
        with mock.patch.dict(os.environ, env, clear=True):
            module = self._reimport_production()
        self.assertEqual(module.ALLOWED_HOSTS, ['example.com'])

    def test_splits_comma_separated_values(self):
        env = {**self._base_env, 'ALLOWED_HOSTS': '203.0.113.7,example.com,www.example.com'}
        with mock.patch.dict(os.environ, env, clear=True):
            module = self._reimport_production()
        self.assertEqual(
            module.ALLOWED_HOSTS,
            ['203.0.113.7', 'example.com', 'www.example.com'],
        )

    def test_strips_whitespace_and_drops_empty_entries(self):
        env = {**self._base_env, 'ALLOWED_HOSTS': ' a.example.com , ,b.example.com,'}
        with mock.patch.dict(os.environ, env, clear=True):
            module = self._reimport_production()
        self.assertEqual(module.ALLOWED_HOSTS, ['a.example.com', 'b.example.com'])


# The Session 14 tests all reimport production.settings under a mocked env.
# Share the base env used above so a new required var lands in exactly one
# spot.
_PROD_BASE_ENV = AllowedHostsParsingTests._base_env


def _reimport_production():
    sys.modules.pop('config.settings.production', None)
    return importlib.import_module('config.settings.production')


class CsrfTrustedOriginsTests(SimpleTestCase):
    """production.settings parses CSRF_TRUSTED_ORIGINS as a comma-separated
    env var, falling back to https://<DOMAIN> + https://www.<DOMAIN>."""

    def test_defaults_to_apex_and_www_https(self):
        env = dict(_PROD_BASE_ENV)
        env.pop('CSRF_TRUSTED_ORIGINS', None)
        with mock.patch.dict(os.environ, env, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.CSRF_TRUSTED_ORIGINS,
            ['https://example.com', 'https://www.example.com'],
        )

    def test_splits_comma_separated_values(self):
        env = {
            **_PROD_BASE_ENV,
            'CSRF_TRUSTED_ORIGINS': 'https://a.example.com,https://b.example.com',
        }
        with mock.patch.dict(os.environ, env, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.CSRF_TRUSTED_ORIGINS,
            ['https://a.example.com', 'https://b.example.com'],
        )

    def test_strips_whitespace_and_drops_empty_entries(self):
        env = {
            **_PROD_BASE_ENV,
            'CSRF_TRUSTED_ORIGINS': ' https://a.example.com , ,https://b.example.com,',
        }
        with mock.patch.dict(os.environ, env, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.CSRF_TRUSTED_ORIGINS,
            ['https://a.example.com', 'https://b.example.com'],
        )


class SecureCookieAndProxyHeaderTests(SimpleTestCase):
    """production.settings sets SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE,
    and trusts X-Forwarded-Proto from CloudFront."""

    def test_secure_proxy_ssl_header_is_x_forwarded_proto(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.SECURE_PROXY_SSL_HEADER,
            ('HTTP_X_FORWARDED_PROTO', 'https'),
        )

    def test_session_and_csrf_cookies_are_secure(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertTrue(module.SESSION_COOKIE_SECURE)
        self.assertTrue(module.CSRF_COOKIE_SECURE)

    def test_secure_ssl_redirect_stays_off(self):
        # CloudFront handles the HTTP->HTTPS redirect at the edge; Django
        # should not compete.
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertFalse(getattr(module, 'SECURE_SSL_REDIRECT', False))

    def test_hsts_seconds_set_to_soak_value(self):
        # Session 15 lands SECURE_HSTS_SECONDS=60 as a short soak.
        # If this needs to change, ramp deliberately (60 -> 3600 -> a
        # week -> a year); don't drift the value silently.
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertEqual(module.SECURE_HSTS_SECONDS, 60)


class StorageLocationPrefixTests(SimpleTestCase):
    """production.settings sets location='media' / 'static' on the S3
    storage backends so keys match CloudFront's /media/* and /static/*
    behaviors."""

    def test_media_backend_uses_media_prefix(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertEqual(module.STORAGES['default']['OPTIONS']['location'], 'media')

    def test_static_backend_uses_static_prefix(self):
        with mock.patch.dict(os.environ, _PROD_BASE_ENV, clear=True):
            module = _reimport_production()
        self.assertEqual(
            module.STORAGES['staticfiles']['OPTIONS']['location'],
            'static',
        )


# --------------------------------------------------------------------------
# Infra guardrails (Session 21)
# --------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SECURITY_GROUPS_TF = _REPO_ROOT / 'infra' / 'phase3' / 'security_groups.tf'

# The AWS-managed prefix list that holds CloudFront's origin-facing ranges.
# Hardcoded here on purpose: in the test it is the *expected* constant, and
# the point of the assertion is that security_groups.tf resolves it by this
# name rather than by a region-specific pl-* id.
_CLOUDFRONT_PREFIX_LIST_NAME = 'com.amazonaws.global.cloudfront.origin-facing'


def _parse_hcl_blocks(text):
    """Return {(block_type, *labels): body_text} for top-level HCL blocks.

    Deliberately minimal -- just enough to assert on declared intent in
    security_groups.tf without adding an HCL-parser dependency to the
    project's pinned requirements. Comment lines are stripped first so a
    '#'-commented brace cannot throw off the brace matching, and the
    header regex is anchored at column zero so nested blocks (tags = {})
    are not picked up as top-level.
    """
    stripped = '\n'.join(
        line for line in text.splitlines() if not line.lstrip().startswith('#')
    )
    blocks = {}
    header = re.compile(r'^([a-z_]+)((?:\s+"[^"]+")*)\s*\{', re.MULTILINE)
    for match in header.finditer(stripped):
        labels = tuple(re.findall(r'"([^"]+)"', match.group(2)))
        depth = 0
        cursor = match.end() - 1
        while cursor < len(stripped):
            if stripped[cursor] == '{':
                depth += 1
            elif stripped[cursor] == '}':
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        blocks[(match.group(1),) + labels] = stripped[match.end():cursor]
    return blocks


class InfraSecurityGroupTests(SimpleTestCase):
    """Guardrails on infra/phase3/security_groups.tf.

    Session 21 locked EC2 port 80 down to the CloudFront origin-facing
    prefix list after the NGINX2ROOT disclosure. These assert the declared
    intent in HCL, which means they run in CI with no AWS credentials and
    in terraform-destroyed states. They guard the regression most likely
    to happen silently: someone restoring 0.0.0.0/0 to debug a thing and
    leaving it there. Live-state verification is the post-apply smoke
    step, not this.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = _SECURITY_GROUPS_TF.read_text()
        cls.blocks = _parse_hcl_blocks(cls.source)
        cls.ingress_rules = {
            labels[-1]: body
            for labels, body in cls.blocks.items()
            if labels[:2] == ('resource', 'aws_vpc_security_group_ingress_rule')
        }
        cls.egress_rules = {
            labels[-1]: body
            for labels, body in cls.blocks.items()
            if labels[:2] == ('resource', 'aws_vpc_security_group_egress_rule')
        }

    def test_parser_found_the_expected_rule_resources(self):
        # If the parser silently matches nothing, every assertion below
        # passes vacuously. Anchor it.
        self.assertIn('ec2_http', self.ingress_rules)
        self.assertIn('rds_from_ec2', self.ingress_rules)
        self.assertIn('ec2_all_out', self.egress_rules)

    def test_no_ingress_rule_is_open_to_the_world(self):
        offenders = [
            name for name, body in self.ingress_rules.items() if '0.0.0.0/0' in body
        ]
        self.assertEqual(
            offenders,
            [],
            'ingress rule(s) open to 0.0.0.0/0: ' + ', '.join(offenders),
        )

    def test_http_ingress_is_gated_on_the_cloudfront_prefix_list(self):
        body = self.ingress_rules['ec2_http']
        self.assertIn('from_port         = 80', body)
        self.assertIn(
            'data.aws_ec2_managed_prefix_list.cloudfront_origin_facing.id',
            body,
        )
        # prefix_list_id and cidr_ipv4 are mutually exclusive in this
        # resource; a stray cidr_ipv4 would mean the lockdown was undone.
        self.assertNotIn('cidr_ipv4', body)

    def test_prefix_list_is_resolved_by_name_not_a_hardcoded_id(self):
        data_block = self.blocks.get(
            ('data', 'aws_ec2_managed_prefix_list', 'cloudfront_origin_facing')
        )
        self.assertIsNotNone(
            data_block,
            'the CloudFront managed prefix list data source is missing',
        )
        self.assertIn(_CLOUDFRONT_PREFIX_LIST_NAME, data_block)
        # pl-* ids differ per region, so a literal one here is a bug.
        self.assertIsNone(
            re.search(r'"pl-[0-9a-f]+"', self.source),
            'hardcoded prefix-list id found; resolve it by name instead',
        )

    def test_dead_port_443_ingress_rule_stays_deleted(self):
        self.assertNotIn('ec2_https', self.ingress_rules)
        # Nothing listens on 443 on the box (nginx declares only
        # `listen 80`) and CloudFront dials plaintext via
        # origin_protocol_policy = "http-only". Re-adding a 443 rule
        # would also push the SG past its 60-rule quota, since the
        # prefix list weighs 55.
        for name, body in self.ingress_rules.items():
            self.assertNotIn('= 443', body, f'{name} re-opens port 443')

    def test_ipv6_ingress_stays_closed(self):
        # nginx has `listen [::]:80`, but no IPv6 ingress rule exists so
        # it is unreachable from outside. Adding the IPv6 companion
        # prefix list would double the quota weight to 110 (> 60).
        for name, body in self.ingress_rules.items():
            self.assertNotIn('cidr_ipv6', body, f'{name} opens IPv6 ingress')

    def test_egress_still_allows_outbound(self):
        # SSM, dnf updates, S3, RDS and the CloudWatch agent are all
        # outbound. A future over-zealous lockdown that clamps egress
        # would cut the deploy path; this is the canary for that.
        self.assertIn('0.0.0.0/0', self.egress_rules['ec2_all_out'])
        self.assertIn('ip_protocol       = "-1"', self.egress_rules['ec2_all_out'])
