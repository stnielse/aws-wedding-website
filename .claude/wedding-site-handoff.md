# Wedding Site — Claude Code Handoff

## Context
This is a self-hosted wedding website built by a professional software engineer who wants full data ownership, privacy control, and resume-relevant AWS experience. The site aims to be live and stable by end of August 2026. All foundational AWS account setup and domain registration are already complete (see "What's already done" below).

---

## What's already done
- AWS account created, MFA enabled on root, IAM admin user created and in use (root is not used day-to-day)
- AWS Budgets alert configured (account-wide, $15/mo threshold)
- Cost Anomaly Detection enabled
- Domain registered via Route 53, hosted zone created with NS + SOA records in place
- ACM certificate requested in us-east-1, DNS validated via Route 53, status: Issued
- `.gitignore` committed covering Python/Django, Node/React/Vite, and Terraform

---

## Goals of the site
- PRIVACY. Public access is not allowed. Site access should be blocked by a sign-in code
- RSVP management (guests look up by name or code, submit attendance + meal choice + plus-one)
- Photo gallery (lots of photos, lightbox, infinite scroll or pagination)
- Photos tastefully spread throughout every page too, not just isolated to the gallery.
- Registry links page
- Possible venmo or paypal API integration to allow guests to send money for honeymoon experiences direct rather than registry gift. Different experience icons, progress bar for total needed vs received, etc.
- Hotel block info page
- FAQ page
- Django admin as the guest management dashboard — no custom admin UI needed

---

## Tech stack decisions (all finalised, do not re-litigate)

**Backend:** Django (latest LTS)
- Django templates + HTMX for all content pages (FAQ, hotel info, registry, nav)
- Minimal JSON endpoints only where React islands need data (RSVP submission, gallery fetch)
- Django admin enabled for all models — this is the management UI
- `django-storages` with S3 backend for all media uploads
- Gunicorn as the application server, systemd-managed, behind nginx

**Frontend:** React islands mounted into specific Django templates via Vite
- Only two React components: `RsvpForm` and `Gallery`. NOTE: More might be necessary if payment app integration is pursued.
- Everything else is plain Django templates + HTMX — no React router, no SPA
- Vite bundles the React components; Django's `collectstatic` picks up the output
- Initial data passed from Django to React via `<script type="application/json">` tags in templates — avoids an extra fetch on page load
- Dev workflow: run `manage.py runserver` and `vite dev` side by side

**Database:** PostgreSQL on Amazon RDS (db.t3.micro)

**Media/photos:** S3 bucket, private, served exclusively via CloudFront OAC (Origin Access Control) — never directly public S3 URLs

**Compute:** EC2 t3.micro (Amazon Linux 2023), IAM instance role (never hardcoded access keys)

**CDN + TLS:** CloudFront distribution — two origins: EC2 for dynamic pages, S3 for media. ACM cert already issued in us-east-1 and ready to attach.

**DNS:** Route 53 (domain already registered here, hosted zone already exists)

**IaC:** Terraform for all AWS resources. Must be written so `terraform destroy` cleanly tears everything down (important for post-wedding teardown)

**CI/CD:** GitHub Actions deploying to EC2 via AWS SSM `send-command` — no SSH keys in CI. Uses GitHub OIDC federation (`role-to-assume`) not long-lived access keys.

---

## Repo structure
```
wedding-site/
├── backend/
│   ├── manage.py
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── local.py        # SQLite, local media storage, DEBUG=True
│   │   │   └── production.py   # RDS, S3 storage, DEBUG=False
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── rsvp/                   # Guest, RSVP models + JSON endpoint for form submission
│   ├── gallery/                # Photo model, S3-backed ImageField, JSON endpoint
│   ├── pages/                  # FAQ, HotelBlock, RegistryLink models + template views
│   ├── templates/
│   │   ├── base.html
│   │   ├── rsvp.html           # mounts RsvpForm React island
│   │   ├── gallery.html        # mounts Gallery React island
│   │   ├── faq.html
│   │   ├── hotel.html
│   │   └── registry.html
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── RsvpForm.jsx
│   │   ├── Gallery.jsx
│   │   └── main.jsx            # ReactDOM.createRoot mounts for each island
│   ├── vite.config.js          # output goes to backend/static/frontend/
│   └── package.json
├── infra/
│   ├── main.tf                 # provider config, terraform backend (S3 + DynamoDB state)
│   ├── vpc.tf                  # VPC, public subnet (EC2), private subnet (RDS)
│   ├── ec2.tf                  # t3.micro instance, security group, instance profile
│   ├── rds.tf                  # db.t3.micro Postgres, private subnet, SG
│   ├── s3.tf                   # media bucket (private), state bucket
│   ├── cloudfront.tf           # distribution, OAC, two origins, HTTPS redirect
│   ├── route53.tf              # A alias record → CloudFront (hosted zone already exists)
│   ├── iam.tf                  # EC2 instance role, GitHub Actions OIDC role, policies
│   ├── budgets.tf              # account-wide budget alert (already set in console but codify it)
│   ├── variables.tf
│   ├── terraform.tfvars.example  # committed — lists all variable names with placeholder values
│   └── terraform.tfvars          # gitignored — real values go here
├── .github/
│   └── workflows/
│       └── deploy.yml
├── .gitignore                  # already committed
└── README.md
```

---

## Django models

```python
# rsvp/models.py
class Guest(models.Model):
    name = models.CharField(max_length=200)
    lookup_code = models.CharField(max_length=20, unique=True)  # printed on invite
    email = models.EmailField(blank=True)
    plus_one_allowed = models.BooleanField(default=False)

class RSVP(models.Model):
    guest = models.OneToOneField(Guest, on_delete=models.CASCADE)
    attending = models.BooleanField()
    meal_choice = models.CharField(max_length=100, blank=True)
    plus_one_attending = models.BooleanField(default=False)
    plus_one_name = models.CharField(max_length=200, blank=True)
    plus_one_meal = models.CharField(max_length=100, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

# gallery/models.py
class Photo(models.Model):
    image = models.ImageField(upload_to='gallery/')  # goes to S3 in production
    caption = models.CharField(max_length=300, blank=True)
    order = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'uploaded_at']

# pages/models.py
class FAQ(models.Model):
    question = models.CharField(max_length=500)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

class RegistryLink(models.Model):
    name = models.CharField(max_length=200)   # e.g. "Crate & Barrel"
    url = models.URLField()
    order = models.PositiveIntegerField(default=0)

class HotelBlock(models.Model):
    hotel_name = models.CharField(max_length=200)
    address = models.TextField()
    booking_url = models.URLField(blank=True)
    booking_code = models.CharField(max_length=100, blank=True)
    rate = models.CharField(max_length=100, blank=True)  # e.g. "$189/night"
    cutoff_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
```

---

## React island mount pattern

In `frontend/src/main.jsx`:
```jsx
import { createRoot } from 'react-dom/client'
import RsvpForm from './RsvpForm'
import Gallery from './Gallery'

const rsvpRoot = document.getElementById('rsvp-root')
if (rsvpRoot) {
  const props = JSON.parse(document.getElementById('rsvp-data').textContent)
  createRoot(rsvpRoot).render(<RsvpForm {...props} />)
}

const galleryRoot = document.getElementById('gallery-root')
if (galleryRoot) {
  const props = JSON.parse(document.getElementById('gallery-data').textContent)
  createRoot(galleryRoot).render(<Gallery {...props} />)
}
```

In `templates/rsvp.html`:
```html
{% extends "base.html" %}
{% block content %}
  <script type="application/json" id="rsvp-data">
    {"csrfToken": "{{ csrf_token }}", "submitUrl": "{% url 'rsvp:submit' %}"}
  </script>
  <div id="rsvp-root"></div>
  {% vite_asset 'src/main.jsx' %}  {# or manual script tag pointing at built bundle #}
{% endblock %}
```

---

## Vite config

```js
// frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../backend/static/frontend',
    emptyOutDir: true,
    rollupOptions: {
      input: 'src/main.jsx',
    }
  }
})
```

Django's `collectstatic` then picks up `backend/static/frontend/` and serves it via nginx in production.

---

## Settings split

`config/settings/base.py` — shared settings, no secrets
`config/settings/local.py`:
```python
from .base import *
DEBUG = True
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'
```

`config/settings/production.py`:
```python
from .base import *
import os
DEBUG = False
ALLOWED_HOSTS = [os.environ['DOMAIN']]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': os.environ['DB_HOST'],
        'PORT': '5432',
    }
}

# Django 5.x `STORAGES` dict (replaces the pre-5.0 `DEFAULT_FILE_STORAGE` /
# `STATICFILES_STORAGE` scalars). django-storages provides the S3 backend.
STORAGES = {
    'default': {
        'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

AWS_STORAGE_BUCKET_NAME = os.environ['AWS_STORAGE_BUCKET_NAME']
AWS_S3_REGION_NAME = os.environ['AWS_REGION']
AWS_S3_CUSTOM_DOMAIN = os.environ['CLOUDFRONT_DOMAIN']  # serve media via CloudFront
AWS_DEFAULT_ACL = None  # bucket is private, CloudFront handles access
```

All production env vars loaded from a `.env` file on EC2, referenced by the systemd `EnvironmentFile` directive — never hardcoded, never committed.

---

## Terraform key decisions
- **State backend:** S3 bucket + DynamoDB table for locking (provision these manually first, before `terraform init` — they can't bootstrap themselves)
- **VPC:** one public subnet (EC2) + one private subnet (RDS), same AZ, no NAT gateway needed
- **Security groups:** RDS SG allows port 5432 inbound from EC2 SG only (reference SG, not CIDR). EC2 SG allows 80/443 from `0.0.0.0/0`, port 22 from your home IP `/32` only
- **EC2 IAM instance role** (not access keys) with least-privilege inline policy: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket` scoped to the one media bucket ARN. Attach `AmazonSSMManagedInstanceCore` managed policy separately for SSM/CI access
- **S3 bucket:** block all public access, OAC for CloudFront access only
- **CloudFront:** path-based routing — `/media/*` → S3 origin, everything else → EC2 origin. HTTPS only, redirect HTTP → HTTPS. Attach the already-issued ACM cert (us-east-1) by ARN
- **Route 53:** A record as alias (not CNAME) pointing at CloudFront distribution domain — alias records are free and required for apex domains. The hosted zone already exists, so Terraform should use a `data` source to look it up rather than creating a new one
- **`terraform destroy` must be clean** — tag every resource, avoid manual console changes after initial apply

---

## GitHub Actions deploy workflow

```yaml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - name: Build frontend
        run: cd frontend && npm ci && npm run build

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::ACCOUNT_ID:role/github-actions-deploy
          aws-region: us-east-1

      - name: Deploy via SSM
        run: |
          aws ssm send-command \
            --instance-ids "${{ secrets.EC2_INSTANCE_ID }}" \
            --document-name "AWS-RunShellScript" \
            --parameters 'commands=[
              "cd /home/ubuntu/wedding-site",
              "git pull origin main",
              "source backend/venv/bin/activate",
              "pip install -r backend/requirements.txt --quiet",
              "python backend/manage.py migrate --settings=config.settings.production",
              "python backend/manage.py collectstatic --noinput --settings=config.settings.production",
              "sudo systemctl restart gunicorn"
            ]'
```

Use GitHub OIDC federation for the `role-to-assume` — not long-lived access keys stored as secrets. The GitHub Actions IAM role in Terraform should trust `token.actions.githubusercontent.com` as the OIDC provider and scope the trust policy to your specific repo.

---

## EC2 server setup (run once after provisioning)

```bash
# On the EC2 instance after first SSH in
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv nginx git

# Clone repo
git clone https://github.com/yourname/wedding-site.git /home/ubuntu/wedding-site

# Python venv
cd /home/ubuntu/wedding-site/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env file (populate with real values)
cp .env.example .env
nano .env
```

**Gunicorn systemd service** (`/etc/systemd/system/gunicorn.service`):
```ini
[Unit]
Description=Gunicorn for wedding site
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/wedding-site/backend
EnvironmentFile=/home/ubuntu/wedding-site/backend/.env
ExecStart=/home/ubuntu/wedding-site/backend/venv/bin/gunicorn \
          --workers 3 \
          --bind unix:/run/gunicorn.sock \
          config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

**nginx config** (`/etc/nginx/sites-available/wedding-site`):
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location /static/ {
        alias /home/ubuntu/wedding-site/backend/staticfiles/;
    }

    location / {
        proxy_pass http://unix:/run/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

TLS is terminated at CloudFront — nginx only needs to handle HTTP internally. Enable and start:
```bash
sudo systemctl enable gunicorn && sudo systemctl start gunicorn
sudo ln -s /etc/nginx/sites-available/wedding-site /etc/nginx/sites-enabled/
sudo systemctl enable nginx && sudo systemctl start nginx
```

---

## Build order (strict — do not skip ahead)

1. **Phase 0 - minimal necessary site spun up** the URL should bring users to a minimal HLTM page, akin to a maintenance mode, saying the site is currently under construction. as of now it is DNS_PROBE_FINISHED_NXDOMAIN
2. **Phase 1 — local scaffolding:** Django project, all apps, all models, admin registered, SQLite working, Vite scaffold, one React island mounted and confirmed working in a Django template locally
3. **Phase 2 — core features:** Full RSVP flow working locally, all content pages (FAQ, hotel, registry) in templates + HTMX, gallery component working with local media storage
4. **Phase 3 — Terraform:** Provision all AWS infrastructure. S3 bucket can be provisioned early if you want to test `django-storages` locally against real S3 before full deploy
5. **Phase 4 — deploy:** EC2 server setup, gunicorn + nginx, GitHub Actions CI/CD, production settings wired up
6. **Phase 5 — hardening:** HTTPS-only, rate limiting on RSVP endpoint, server-side file validation, RDS backup restore test, mobile responsiveness pass
7. **Phase 6 — pre-wedding:** Light load test on RSVP form, final data export plan documented (pg_dump + S3 sync to local)

Do not touch AWS until Phase 1 is complete and working locally. Debugging Django on EC2 behind nginx/gunicorn/CloudFront is significantly harder than debugging it locally.

---

## Amendments (post-original-handoff)

This section captures decisions and re-mappings made after the original handoff
was written. The phase structure above is the source of truth for *what* gets
built; this section is the source of truth for *how the sessions map onto the
phases* and for any working conventions the original handoff didn't specify.

### Timeline
- Wedding is **early 2027**; the site should live through **June 2027** and
  then be torn down. The original "end of August 2026" / "end of June 2026"
  language above is stale — treat the 2027 dates as authoritative.

### Phase 1 split across sessions

The original handoff treats Phase 1 (local scaffolding) as one lump of work.
In practice it's being split across three sessions so each one stays
reviewable and has a clean stopping point:

| Session | Slice of Phase 1 | Status |
|---|---|---|
| **Session 4** (this session, 2026-07-17) | Django project skeleton — `django-admin startproject config backend`, settings split (`base.py`/`local.py`/`production.py`), Python deps pinned. **No apps yet.** SQLite migrations run, admin loads. | in progress |
| **Session 5** | The three apps (`rsvp`, `gallery`, `pages`) + models per handoff + admin registrations. Migrations for the new models. | pending |
| **Session 6** | Vite + React scaffold + one island (probably `RsvpForm`) mounted into a Django template to prove the integration point works. Freeze Node deps. Completes Phase 1. | pending |

Sessions 7+ pick up at **Phase 2 (core features)** as originally scoped. All
subsequent phase numbers are unchanged; only the session numbering shifts.

### Per-project Python virtualenv

The user runs many Python projects on this machine, so this project must be
fully isolated. Convention:

- Virtualenv lives at repo root as `.venv/` (already covered by the
  `.venv/` line in `.gitignore`).
- Python interpreter is **3.12** (Homebrew's `python3.12`) — Django 5.2 LTS
  supports 3.10-3.13; picking the middle keeps us on a mature, well-tested
  target rather than the newest release.
- Every backend command in this repo runs inside the venv. Activate with
  `source .venv/bin/activate` from repo root before `python manage.py …`,
  `pip install`, etc.
- Never rely on the system Python (Homebrew's, or an Anaconda base env) for
  project deps — dependency drift between projects is the exact thing the
  venv exists to prevent.

---

## Critical rules
- Never use root AWS credentials for anything — IAM admin user only
- Never commit `.env`, `terraform.tfvars`, `*.tfstate`, or any file containing secrets
- Never hardcode AWS access keys anywhere — EC2 uses an instance role, CI uses OIDC
- All secrets in production come from the `.env` file on EC2, loaded via systemd `EnvironmentFile`
- IAM policies are least-privilege — no `*` on actions or resources
- `terraform destroy` must cleanly remove everything — no orphaned resources after the wedding
- Set a CloudWatch log retention policy on any log groups created — default is forever and will accrue charges silently
- Do not enable GuardDuty, Inspector, Security Hub, or Macie — their free trials start on enable and bill automatically when they expire
