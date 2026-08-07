# Launch checklist — kaitlynandsteventietheknot.com

Pre-wedding verification pass. Wedding date: **2027-05-23**. Run
this checklist in two waves:

- **T–8 weeks** (~2027-03-28): first pass. Everything except the
  final content freeze and the on-demand RDS snapshot. Anything
  red gets fixed with time to spare.
- **T–1 week** (~2027-05-16): final pass. Content freeze, manual
  RDS snapshot, no more deploys unless a real bug lands.

Every step has a concrete command or click-path. If a step needs
more than a paragraph of context to explain the *why*, the source
of truth is the referenced session log — this file stays terse.

---

## 0. Prereqs

```
aws sso login
cd /Users/stevennielsen/aws-wedding-website
INSTANCE_ID=$(terraform -chdir=infra/phase3 output -raw ec2_instance_id)
DIST_ID=$(terraform -chdir=infra/phase3 output -raw cloudfront_distribution_id)
```

Everything below assumes `$INSTANCE_ID` and `$DIST_ID` are set.

---

## 1. Access + admin

- [ ] **Admin login works.** Hit
      `https://kaitlynandsteventietheknot.com/admin/`, log in
      with the prod superuser (created during Session 16 build,
      not part of the launch pass), confirm Guest / Household /
      Event models render. If the DB has been restored from a
      snapshot or replaced since Session 16, re-create the
      superuser via SSM Session Manager first:
      ```
      aws ssm start-session --target "$INSTANCE_ID"
      cd /home/ec2-user/aws-wedding-website
      sudo -u ec2-user bash -c '
        set -a; . backend/.env; set +a
        .venv/bin/python backend/manage.py createsuperuser \
          --settings=config.settings.production
      '
      ```

## 2. Deploy pipeline

- [ ] **Branch protection active.** Settings → Rules → Rulesets →
      `main-protected` is Active. Required checks:
      `pr-checks / python` and `pr-checks / frontend`. Bypass:
      `stnielse` only.
- [ ] **Latest deploy on `main` is green end-to-end.** Actions
      tab → `deploy` workflow → most recent run: `python`,
      `frontend`, `deploy` all green. Deploy step's stdout ends
      with `=== deploy done ... http=200 ===`.
- [ ] **`workflow_dispatch` redeploy works.** Actions → `deploy`
      → Run workflow → main. Confirms a no-code-change redeploy
      succeeds (useful if we ever rotate a secret in the .env
      file on the box and just need to restart gunicorn).

## 3. Security posture

- [ ] **HSTS at full 1-year.** After S17's ramp completes:
      ```
      curl -sI https://kaitlynandsteventietheknot.com/ | grep -i strict-transport
      # strict-transport-security: max-age=31536000; includeSubDomains
      ```
- [ ] **TLS 1.2+ only.** CloudFront distribution's viewer
      certificate has `minimum_protocol_version = "TLSv1.2_2021"`
      per `infra/phase3/cloudfront.tf`. Verify serving cert:
      ```
      echo | openssl s_client -connect kaitlynandsteventietheknot.com:443 \
        -servername kaitlynandsteventietheknot.com 2>/dev/null \
        | openssl x509 -noout -subject -issuer -dates
      ```
- [ ] **ACM cert expiry > 60 days out.** Cert auto-renews, but
      verify:
      ```
      aws acm list-certificates --region us-east-1 \
        --query 'CertificateSummaryList[?DomainName==`kaitlynandsteventietheknot.com`].[CertificateArn,NotAfter]' \
        --output table
      ```
- [ ] **EC2 SG has no 22 ingress.** Access is SSM Session Manager
      only.
      ```
      aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=wedding-site-ec2" \
        --query 'SecurityGroups[0].IpPermissions[?FromPort==`22`]' \
        --output json
      # should be: []
      ```
- [ ] **RDS `deletion_protection = true`.** Flip before this
      checklist runs. See `infra/phase3/README.md` "RDS deletion
      protection" section.
      ```
      terraform -chdir=infra/phase3 state show aws_db_instance.wedding \
        | grep deletion_protection
      ```
- [ ] **No long-lived AWS keys anywhere.** Repo grep + GH Actions
      secret list:
      ```
      git grep -InE 'AKIA[0-9A-Z]{16}|aws_access_key_id' -- \
        ':!*.tfstate' ':!*.tfstate.backup' ':!*/venv/*' ':!.claude/sessions/*'
      gh secret list          # should show zero AWS_* secrets
      gh variable list        # should show 3 vars: AWS_DEPLOY_ROLE_ARN, STATIC_BUCKET_NAME, EC2_INSTANCE_ID
      ```

## 4. Observability

- [ ] **SNS email subscription confirmed.**
      ```
      aws sns list-subscriptions \
        --query 'Subscriptions[?contains(TopicArn, `wedding-site`)]' \
        --output table
      # SubscriptionArn should be a real ARN, not "PendingConfirmation".
      ```
- [ ] **CloudWatch Agent running on the instance.**
      ```
      aws ssm send-command \
        --instance-ids "$INSTANCE_ID" \
        --document-name AWS-RunShellScript \
        --parameters 'commands=["sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a status"]' \
        --query 'Command.CommandId' --output text
      # ... then get-command-invocation. Expected: status: running
      ```
- [ ] **Alarm fires end-to-end.** Log a synthetic ERROR from the
      Django shell on the box, confirm an email lands within
      ~5 min. `LAUNCH DRILL` in the message so nobody thinks it's
      a real regression.
      ```
      aws ssm start-session --target "$INSTANCE_ID"
      cd /home/ec2-user/aws-wedding-website
      sudo -u ec2-user bash -c '
        set -a; . backend/.env; set +a
        .venv/bin/python backend/manage.py shell \
          --settings=config.settings.production \
          -c "import logging; logging.getLogger(\"launch-drill\").error(\"LAUNCH DRILL — ignore\")"
      '
      ```
      Wait for the email at `s.conwaynielsen@gmail.com`. Delete the
      metric-filter alarm-history entry if it clutters the console.

## 5. Backups + recovery

- [ ] **RDS automated backups on** (7-day retention, per
      `infra/phase3/rds.tf`).
      ```
      aws rds describe-db-instances \
        --db-instance-identifier wedding-site \
        --query 'DBInstances[0].[BackupRetentionPeriod,PreferredBackupWindow]' \
        --output text
      # 7   07:00-09:00
      ```
- [ ] **Most recent automated snapshot < 24h old.**
      ```
      aws rds describe-db-snapshots \
        --db-instance-identifier wedding-site \
        --snapshot-type automated \
        --query 'reverse(sort_by(DBSnapshots, &SnapshotCreateTime))[0].[DBSnapshotIdentifier,SnapshotCreateTime,Status]' \
        --output text
      ```
- [ ] **On-demand snapshot taken in the T–1 week wave.** Manual,
      identifiable, kept indefinitely.
      ```
      aws rds create-db-snapshot \
        --db-instance-identifier wedding-site \
        --db-snapshot-identifier wedding-site-t-minus-1-week-$(date +%Y%m%d)
      ```
- [ ] **Media bucket versioning on** (per `infra/phase3/s3_media.tf`).
      ```
      aws s3api get-bucket-versioning \
        --bucket "$(terraform -chdir=infra/phase3 output -raw media_bucket_name)"
      # Status: Enabled
      ```

## 6. Content readiness (T–1 week wave)

- [ ] **All page copy final.** Home, our story, FAQ, RSVP,
      registry, travel, schedule. Grep for placeholder markers:
      ```
      git grep -InE 'TODO|TBD|placeholder|FIXME|lorem ipsum' -- backend/
      ```
- [ ] **Dates + venue accurate everywhere.** Grep for "2027-05-23"
      / "May 23" / "Louland Falls" / "Salt Lake City" — every
      reference matches, no stale dates from earlier drafts.
- [ ] **All photos uploaded to media bucket + alt-text present.**
      Django admin → check every Photo record has non-empty
      `alt_text`. (Photo alt-text was flagged as pending in
      Session 15's open questions.)
- [ ] **Hotel block hyperlinks come from Django admin, not the
      template.** Follow-up item from Session 16 — resolves the
      unmerged PR that hardcoded them.
- [ ] **RSVP flow end-to-end works with a real submission.**
      Create a throwaway guest in admin, use its RSVP link,
      submit, confirm:
      - Confirmation page renders.
      - `EmailAddress.subscribe_to_wedding_updates` toggles as
        expected in admin.
      - Confirmation email lands (SES / whatever the mail
        backend is at that point).
      Delete the throwaway guest after.
- [ ] **Q1 dietary + Q6 schedule questions resolved.** Still open
      from Session 7 — either implemented or explicitly scoped
      out.

## 7. DNS + reachability

- [ ] **Apex + www both resolve to CloudFront.**
      ```
      dig +short kaitlynandsteventietheknot.com
      dig +short www.kaitlynandsteventietheknot.com
      # Both should return CloudFront IPs (resolves to d*.cloudfront.net).
      ```
- [ ] **Apex responds 200 over HTTPS.**
      ```
      curl -sI https://kaitlynandsteventietheknot.com/ | head -1
      # HTTP/2 200
      ```
- [ ] **HTTP redirects to HTTPS.**
      ```
      curl -sI http://kaitlynandsteventietheknot.com/ | grep -iE '^(HTTP/|location:)'
      # HTTP/1.1 301 Moved Permanently
      # location: https://kaitlynandsteventietheknot.com/
      ```
- [ ] **www redirects (or serves) — whichever we settled on.**
      Check `infra/phase3/route53.tf` for the current behavior.

## 8. Cost + surprise-services check

- [ ] **Monthly cost trend on track (~$25/mo).** Cost Explorer →
      last full month, filter by service. Alarm if any single
      service > $10/mo unexpectedly.
- [ ] **No paid security services enabled** (per handoff
      critical rules — free trials auto-bill on expiry).
      ```
      aws guardduty list-detectors --output json          # []
      aws inspector2 batch-get-account-status --output json | grep -i status
      aws securityhub describe-hub 2>&1 | grep -Ei 'not.*subscribed|invalid'
      aws macie2 get-macie-session 2>&1 | grep -i disabled
      ```

## 9. Post-launch (T+1 day after the wedding)

- [ ] Bump `SECURE_HSTS_SECONDS` back down (or leave at
      31536000 — HSTS lasts a year, so no urgency).
- [ ] Take a final RDS snapshot for the archive.
- [ ] Photo backup off S3 to somewhere else (Google Drive,
      local disk) — the site tears down in June 2027 per
      [[project-timeline]].
- [ ] Start the June 2027 teardown checklist (separate doc,
      out of scope here).

---

## Notes

- **Why no load testing.** ~50 guests, mostly desktop, wedding
  site read-heavy with a burst of RSVP form submits over a few
  weeks. t3.micro + `db.t3.micro` handle this comfortably —
  Session 12/13 stress-tested during build.
- **Why no CloudFront invalidation step.** Default cache
  behavior is `CachingDisabled` (dynamic Django pages go
  straight to EC2 origin). `/static/*` uses hashed filenames
  from `ManifestS3StaticStorage` — new build produces new
  filenames, so cache-hit-on-stale-content is impossible.
  `/media/*` objects are content-URI-stable (no overwrites at
  the same key). Invalidation would only matter if we cached
  the default behavior, and we don't. See Session 16 log.
- **What's out of scope.** Pen testing, WAF, DDoS mitigation
  beyond CloudFront's built-in edge protection. This is a
  low-traffic private-audience site, not a production SaaS.
