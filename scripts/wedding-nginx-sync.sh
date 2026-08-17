#!/bin/bash
# Nginx site-config sync helper (Session 19).
#
# Invoked as root via passwordless sudo from scripts/deploy.sh whenever
# the freshly-rendered nginx site config (at /tmp/wedding-site.conf.new)
# differs from the live one. Backs up the current file, installs the
# new one, validates via `nginx -t`, rolls back on failure, reloads
# nginx on success.
#
# The sudoers grant lives in infra/phase3/templates/user_data.sh.tftpl
# and pins the invocation to this exact path (an absolute path under
# /home/ec2-user/aws-wedding-website/scripts/) so a typo in deploy.sh
# cannot escalate sudo.
#
# Failure semantics: any nonzero exit leaves /etc/nginx/conf.d/wedding-site.conf
# equal to its pre-invocation state (via the .bak rollback), so nginx
# in memory and nginx on disk stay consistent. See Session 18
# digression 1 for the failure mode this guards against.

set -euo pipefail

NEW=/tmp/wedding-site.conf.new
TARGET=/etc/nginx/conf.d/wedding-site.conf
BACKUP=/etc/nginx/conf.d/wedding-site.conf.bak

if [ ! -f "$NEW" ]; then
    echo "wedding-nginx-sync: expected $NEW to exist" >&2
    exit 1
fi

if [ ! -f "$TARGET" ]; then
    echo "wedding-nginx-sync: expected $TARGET to exist (was user_data run?)" >&2
    exit 1
fi

cp "$TARGET" "$BACKUP"
cp "$NEW" "$TARGET"

if ! nginx -t; then
    echo "wedding-nginx-sync: nginx -t failed; rolling back to $BACKUP" >&2
    cp "$BACKUP" "$TARGET"
    exit 1
fi

systemctl reload nginx
rm -f "$NEW"
echo "wedding-nginx-sync: reloaded"
