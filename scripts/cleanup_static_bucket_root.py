"""One-shot cleanup of stale root-level objects in the static S3 bucket.

Background (Session 14): the EC2 web tier booted once with
``AWS_LOCATION`` unset on the static storage backend, so ``collectstatic``
wrote hashed assets at the bucket root (``admin/``, ``css/``, ``fonts/``,
``frontend/``, ``img/``, ``js/``, plus one root manifest). Session 14
re-collected with ``AWS_LOCATION='static'`` set, putting a second copy
under the ``static/`` prefix. The root-level copies are now unreferenced
by Django's staticfiles manifest and only cost pennies to keep, but
they clutter the console and confuse anyone poking around the bucket.

This script lists every object at the bucket root (technically: every
object whose key does *not* begin with ``static/`` or ``deploy/``),
prints a summary, and — with ``--yes`` — deletes them in bulk. Dry-run
is the default so a careless run is a no-op.

Usage (from repo root):

    .venv/bin/python scripts/cleanup_static_bucket_root.py --dry-run
    .venv/bin/python scripts/cleanup_static_bucket_root.py --yes

The bucket name is discovered from Terraform (``infra/phase3 terraform
output -raw static_bucket_name``) so you don't have to remember it, but
``--bucket <name>`` overrides.

Requires an active AWS SSO session (``aws sso login``) and the ``awscrt``
extra installed in the venv (see ``user_aws_sso_auth`` memory).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import boto3

# Any object whose key starts with one of these prefixes is intentional
# and stays. Everything else at the root is orphan pre-Session-14
# output and gets deleted.
KEEP_PREFIXES = ('static/', 'deploy/')


def discover_bucket_name() -> str:
    """Ask Terraform for the static bucket name so callers don't type it."""
    repo_root = Path(__file__).resolve().parent.parent
    phase3 = repo_root / 'infra' / 'phase3'
    result = subprocess.run(
        ['terraform', f'-chdir={phase3}', 'output', '-raw', 'static_bucket_name'],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def list_orphan_keys(s3, bucket: str) -> list[str]:
    """Every key not under a KEEP_PREFIXES prefix. One paginated pass."""
    paginator = s3.get_paginator('list_objects_v2')
    orphans: list[str] = []
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get('Contents', []):
            key = obj['Key']
            if not any(key.startswith(prefix) for prefix in KEEP_PREFIXES):
                orphans.append(key)
    return orphans


def delete_in_batches(s3, bucket: str, keys: list[str]) -> int:
    """delete_objects accepts up to 1000 keys per call. Returns count deleted."""
    total = 0
    for start in range(0, len(keys), 1000):
        batch = keys[start : start + 1000]
        s3.delete_objects(
            Bucket=bucket,
            Delete={'Objects': [{'Key': k} for k in batch], 'Quiet': True},
        )
        total += len(batch)
    return total


def summarize(keys: list[str], sample: int = 10) -> None:
    print(f'  total orphan objects: {len(keys)}')
    if not keys:
        return
    print(f'  first {min(sample, len(keys))} keys:')
    for key in keys[:sample]:
        print(f'    {key}')
    if len(keys) > sample:
        print(f'    ... and {len(keys) - sample} more')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--bucket',
        help='Static bucket name. Defaults to `terraform output -raw static_bucket_name`.',
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='List orphan keys, do not delete (default).',
    )
    mode.add_argument(
        '--yes',
        dest='dry_run',
        action='store_false',
        help='Actually delete the orphan objects.',
    )
    args = parser.parse_args()

    bucket = args.bucket or discover_bucket_name()
    print(f'bucket: {bucket}')
    print(f'keeping prefixes: {list(KEEP_PREFIXES)}')

    s3 = boto3.client('s3')
    orphans = list_orphan_keys(s3, bucket)
    summarize(orphans)

    if not orphans:
        print('nothing to do.')
        return 0

    if args.dry_run:
        print('\n(dry run) rerun with --yes to delete.')
        return 0

    deleted = delete_in_batches(s3, bucket, orphans)
    print(f'\ndeleted {deleted} objects.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
