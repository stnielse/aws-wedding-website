#!/bin/bash
# Wedding-site deploy step (Session 15).
#
# Runs on the EC2 web tier as ec2-user via SSM SendCommand from
# .github/workflows/deploy.yml. Assumes the box is already
# provisioned (first-boot bring-up is user_data.sh.tftpl's job) --
# venv, git clone, systemd unit, nginx config all already exist.
#
# Usage:
#   scripts/deploy.sh <git_sha> <frontend_tarball_s3_url>
#
# Example (from SSM RunCommand body):
#   sudo -u ec2-user /home/ec2-user/aws-wedding-website/scripts/deploy.sh \
#       a1b2c3d s3://wedding-site-static-123456789012/deploy/frontend-a1b2c3d.tar.gz
#
# Exit codes: 0 on success, non-zero on any step failure. The workflow
# polls SSM GetCommandInvocation and treats non-Success as a red
# build.
#
# Logging: every step echoes what it's about to do, with set -x making
# the effective command visible in SSM's command output for post-hoc
# debug.

set -euxo pipefail

APP_DIR="/home/ec2-user/aws-wedding-website"
GIT_SHA="${1:?git sha required as arg 1}"
ARTIFACT_URL="${2:?frontend tarball s3 url required as arg 2}"

echo "=== deploy begin ($(date -Is)) sha=$GIT_SHA ==="

cd "$APP_DIR"

# ---- Code ----------------------------------------------------------------
# fetch --tags in case a future release ever tags; --prune removes stale
# remote-tracking branches that would otherwise accumulate.
git fetch --tags --prune origin
git checkout --detach "$GIT_SHA"

# ---- Python deps ---------------------------------------------------------
# Idempotent when requirements haven't changed; a couple of seconds when
# they have. Cheaper than gating on a diff check.
"$APP_DIR/.venv/bin/pip" install \
    --disable-pip-version-check \
    -r backend/requirements/production.txt

# ---- Nginx site config sync --------------------------------------------
# Render infra/phase3/templates/nginx-site.conf.tftpl with $DOMAIN
# substituted for ${domain_name}, diff against the live file, and only
# reload nginx if something changed. Same source of truth as user_data
# uses for a fresh instance -- avoids the S18 workflow gap where nginx
# template changes never reached the live box because
# user_data_replace_on_change = false.
#
# envsubst's whitelist form (only '${domain_name}') is load-bearing:
# the template also contains nginx runtime variables ($host,
# $request_uri, $scheme) that would be clobbered as empty shell vars
# by bare envsubst. .env is sourced further down for migrate/collectstatic;
# source it here too so $DOMAIN is available.
set -a
. "$APP_DIR/backend/.env"
set +a
NGINX_TEMPLATE="$APP_DIR/infra/phase3/templates/nginx-site.conf.tftpl"
NGINX_LIVE=/etc/nginx/conf.d/wedding-site.conf
NGINX_NEW=/tmp/wedding-site.conf.new
domain_name="$DOMAIN" envsubst '${domain_name}' \
    < "$NGINX_TEMPLATE" \
    > "$NGINX_NEW"
if cmp -s "$NGINX_NEW" "$NGINX_LIVE"; then
    echo "nginx config unchanged; skipping sync"
    rm -f "$NGINX_NEW"
else
    echo "nginx config changed; syncing"
    sudo "$APP_DIR/scripts/wedding-nginx-sync.sh"
fi

# ---- Frontend (pre-built by CI, downloaded from S3) ---------------------
# The tarball's contents unpack directly into backend/static/frontend/
# (tar was created with -C backend/static/frontend .). Wipe the target
# first so removed assets don't linger.
TARBALL="/tmp/frontend-$GIT_SHA.tar.gz"
aws s3 cp "$ARTIFACT_URL" "$TARBALL"
rm -rf "$APP_DIR/backend/static/frontend"
mkdir -p "$APP_DIR/backend/static/frontend"
tar -xzf "$TARBALL" -C "$APP_DIR/backend/static/frontend"
rm -f "$TARBALL"

# ---- Django -------------------------------------------------------------
# .env is already on disk from first boot; source it so
# migrate/collectstatic see the same env gunicorn sees. Same pattern
# scripts/run-gunicorn.sh uses.
cd "$APP_DIR/backend"
set -a
. "$APP_DIR/backend/.env"
set +a
"$APP_DIR/.venv/bin/python" manage.py migrate \
    --settings=config.settings.production --noinput
"$APP_DIR/.venv/bin/python" manage.py collectstatic \
    --settings=config.settings.production --noinput

# ---- Restart ------------------------------------------------------------
# passwordless sudo for `systemctl restart gunicorn` is granted via
# /etc/sudoers.d/wedding-site-deploy (set up in user_data). Restart
# not reload -- gunicorn's HUP reload is finicky with settings changes
# and this app can absorb a ~1s blip.
sudo /bin/systemctl restart gunicorn

# ---- Post-flight sanity -------------------------------------------------
# Give gunicorn a beat to bind the socket, then hit localhost through
# nginx. Passing `-H "Host: $DOMAIN"` is load-bearing: without it curl
# sends Host=localhost, which ALLOWED_HOSTS rejects with 400 (Django's
# CommonMiddleware fires before anything else). $DOMAIN comes from the
# .env we sourced earlier and matches an entry in ALLOWED_HOSTS.
# 200 or 301/302 is healthy; anything else fails the deploy.
sleep 2
status=$(curl -s -o /dev/null -w '%{http_code}' -H "Host: $DOMAIN" http://localhost/)
case "$status" in
    200|301|302) ;;
    *)
        echo "post-restart localhost returned HTTP $status; failing deploy"
        exit 1
        ;;
esac

echo "=== deploy done ($(date -Is)) sha=$GIT_SHA http=$status ==="
