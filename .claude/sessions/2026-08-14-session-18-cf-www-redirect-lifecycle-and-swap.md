# Session 18 — CloudFront www→apex redirect, S3 lifecycle rule, EC2 swap hedge

**Date:** 2026-08-14
**Mode:** Execution — infra hardening + cleanup
**Model:** Opus 4.7

---

## Context

Three items from Session 17's handoff, batched into one session:

1. **Fix A — `www` → apex CloudFront 301.** S17 addendum documented
   the visible bug: `https://www.kaitlynandsteventietheknot.com/gallery/`
   fails to mount the React island because the static bundle URL is
   apex-canonical (`AWS_STATIC_CUSTOM_DOMAIN` env is set to the apex),
   so the `www.` page fetch is cross-origin and blocked by CORS. Fix
   is a CloudFront Function on the `www.` alias's viewer-request event
   that 301s to the apex, consolidating on a single canonical origin.
2. **S3 lifecycle rule for orphaned multipart uploads.** S17 bulk-load
   left aborted-multipart parts in `s3://<media>/scratch/gallery-source/`
   after an SSO token expiry mid-`aws s3 sync`. Session 17's cleanup
   swept them once by hand; this session lands the
   `abort_incomplete_multipart_upload { days_after_initiation = 3 }`
   lifecycle rule so the class of leak self-heals. Folded S17's
   "orphan sweep" carry-over into this — same fix.
3. **EC2 swap hedge against Pillow OOM.** S17 post-mortem showed the
   admin upload path shares the same `post_save` derivative-generation
   code path that OOM'd the box during the 324-photo sync. Adding a
   1 GB EBS-backed swap file to the instance (via user_data +
   one-time on-box apply, since `user_data_replace_on_change = false`)
   turns the OOM into a slow-but-alive burst.

### Skipped from S17's handoff
- **Delete scratch prefix** — user already ran it last night.
- **HSTS ramp** — still soak-gated, earliest 2026-08-19.
- **RDS deletion protection** — calendar item 2027-01/02.

---

## Decisions locked this session

### EC2 swap file — 1 GB, EBS-backed, `vm.swappiness=10`, provisioned via user_data + one-time on-box apply

| Area | Decision |
|---|---|
| Choice | Add a swap-file bootstrap block to `infra/phase3/templates/user_data.sh.tftpl` — creates `/swapfile` at 1 GB, `mkswap`+`swapon`, appends to `/etc/fstab` for reboot persistence, drops `vm.swappiness=10` into `/etc/sysctl.d/99-swappiness.conf`. Because `user_data_replace_on_change = false` on `aws_instance.web`, Terraform won't re-run user_data against the live instance; the same commands get applied once by hand via SSM against the current box. Future rebuilds (AMI bump, size change) pick up the change from user_data automatically. |
| Why | **Why OOM happened.** t3.micro has 1 GB RAM. A single Pillow resize on a 6000×4500 source JPEG allocates a raw pixel buffer of `6000 × 4500 × 3 ≈ 81 MB`, plus a second target-size buffer, plus a transient EXIF-transpose buffer — the working set can hit ~250-300 MB per photo. With three gunicorn workers (~200 MB each), nginx, systemd, SSM Agent, and kernel resident, that spike blows past 1 GB and the kernel OOM killer chooses by process size — gunicorn goes first (fat), then nginx and SSM Agent as pressure continues. The box looks `running` in the EC2 console but is unreachable to everything. **What swap changes.** Swap is a disk-backed extension of virtual memory. When RAM fills, the kernel pages cold pages (idle gunicorn workers waiting for a request, kernel caches, mostly-static SSM Agent memory) out to disk, freeing physical RAM for the hot pages (Pillow's active decode/resize buffers). Nothing gets killed unless RAM + swap are both exhausted. For a bounded burst — one admin photo upload — the spike lasts seconds; swap absorbs it and the OOM killer never fires. **Why not upsize.** t3.small (2 GB RAM) also fixes it but costs an extra ~$15/mo forever for RAM used a few dozen times over the site's lifetime. 1 GB EBS swap costs ~$0.08/mo. **The `swappiness=10` knob.** AL2023 default is 60, which lets the kernel lazily swap cold pages during idle periods. On a "swap as safety net" box, that means gunicorn workers get swapped out during quiet moments and every subsequent cold request pays disk-latency page-in. `swappiness=10` keeps swap unused until RAM pressure is real, so normal request paths never touch disk. **Sizing.** 1 GB gives comfortable headroom for a 2-3× Pillow burst without meaningful impact on the 20 GB root volume. Uses `dd if=/dev/zero` (not `fallocate`) because `fallocate` on XFS can produce a swap file that mkswap rejects; `dd` always works. |

### `www → apex` 301 via CloudFront Function

*(Details to fill in as the change lands.)*

### S3 lifecycle — `abort_incomplete_multipart_upload` on media bucket

*(Details to fill in as the change lands.)*

---

## Progress

- [x] Session log created (this file).
- [ ] CloudFront Function `www_to_apex_redirect` added to `infra/phase3/cloudfront.tf`; attached to `www.` alias viewer-request event.
- [ ] S3 lifecycle configuration added to `infra/phase3/s3_media.tf` — `abort_incomplete_multipart_upload { days_after_initiation = 3 }`.
- [x] Swap-file provisioning added to `infra/phase3/templates/user_data.sh.tftpl` (for future instance rebuilds).
- [ ] Swap file applied once to the current live instance via SSM (recipe below).
- [ ] `terraform plan` reviewed with user; `terraform apply` run by user.
- [ ] Unit tests written + passing.
- [ ] Session log finalized.

## Applying swap to the current live instance

`user_data_replace_on_change = false` and `user_data` only fires on
first boot anyway, so the swap block added to
`infra/phase3/templates/user_data.sh.tftpl` this session takes effect
on **future** instance rebuilds only. The live t3.micro needs a
one-time apply. Two options.

**Option A — interactive SSM session (easier for one-time work):**

```
INSTANCE_ID=$(terraform -chdir=infra/phase3 output -raw ec2_instance_id)
aws ssm start-session --target "$INSTANCE_ID"

# Then, inside the session:
sudo bash -c '
    set -e
    if [ ! -f /swapfile ]; then
        dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
        chmod 0600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo "/swapfile none swap sw 0 0" >> /etc/fstab
    fi
    cat > /etc/sysctl.d/99-swappiness.conf <<EOF
vm.swappiness=10
EOF
    sysctl -p /etc/sysctl.d/99-swappiness.conf
    free -m
    cat /proc/sys/vm/swappiness
'
```

`free -m` should show a `Swap:` row with `total ≈ 1024`. `cat
/proc/sys/vm/swappiness` should print `10`.

**Option B — SSM send-command (scripted, matches deploy pattern):**

Build the payload as real JSON via `jq` — never the `--parameters
"commands=[...]"` shorthand (S17 CLAUDE.md rule).

```
INSTANCE_ID=$(terraform -chdir=infra/phase3 output -raw ec2_instance_id)

BOX_CMD='set -e
if [ ! -f /swapfile ]; then
    dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
    chmod 0600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi
cat > /etc/sysctl.d/99-swappiness.conf <<EOF
vm.swappiness=10
EOF
sysctl -p /etc/sysctl.d/99-swappiness.conf
free -m
cat /proc/sys/vm/swappiness'
PARAMS=$(jq -n --arg cmd "$BOX_CMD" '{commands: [$cmd]}')

command_id=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --comment "S18 swap-file provision" \
    --parameters "$PARAMS" \
    --query 'Command.CommandId' --output text)
echo "Dispatched: $command_id"

aws ssm wait command-executed --command-id "$command_id" --instance-id "$INSTANCE_ID"
aws ssm get-command-invocation --command-id "$command_id" --instance-id "$INSTANCE_ID" \
  --output json \
  | jq -r '"status: \(.Status)", "----- stdout -----", .StandardOutputContent, "----- stderr -----", .StandardErrorContent'
```

SSM Send-Command runs as root by default (Systems Manager Agent
identity), so no `sudo` wrapper needed inside the payload.

Either option is idempotent — the `[ ! -f /swapfile ]` guard makes
re-running safe.

## Files created / modified this session

**Created:**
- `.claude/sessions/2026-08-14-session-18-cf-www-redirect-lifecycle-and-swap.md` — this log.

**Modified:**
- `infra/phase3/templates/user_data.sh.tftpl` — added swap-file bootstrap block (1 GB `/swapfile`, `vm.swappiness=10`) between the header setup and `dnf -y update`. Runs only if `/swapfile` doesn't already exist, so re-runs are no-ops.

## Session 19 handoff

*(Filled in at wrap.)*

## Open questions / follow-ups

*(Carried from S17 unless noted.)*

- **HSTS ramp** — earliest 2026-08-19, gated on ERROR/CRITICAL log filter staying quiet.
- **RDS deletion protection** — flip 2027-01/02.
- **Photo alt-text / captions** — bulk sync leaves both blank; add via admin as time allows.
- **`<picture>` mobile crop for hero** — carried from S15.
- **`django-vite`** — deferred, not blocking.
- **Q1 dietary + Q6 schedule** — open from Session 7 (RSVP).
