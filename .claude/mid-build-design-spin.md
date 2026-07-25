# Mid-Build Design Spin

Brief for a design-oriented Claude session. This repo is mid-build; the
backend and frontend scaffolding are done but there is zero visual design
yet. This brief scopes what to design *now* vs. what to defer.

## What the repo is

Self-hosted wedding site. Django templates + HTMX, with Vite-built React
islands for interactive bits (RSVP form, photo gallery). Six Django models
across three apps: `rsvp` (Guest, RSVP), `gallery` (Photo), `pages` (FAQ,
RegistryLink, HotelBlock). Full architecture — including the island-mount
pattern, model fields, and phase plan — is in
`.claude/wedding-site-handoff.md`. Session logs live under
`.claude/sessions/*.md`; the latest one (Session 06) is where the frontend
scaffold landed.

## What I want you to design

**Visual direction only**, so the Phase 2 build has something real to
build against:

1. **Design system** — color palette (light mode primary; dark mode
   optional), typography (heading + body pairing with self-hostable
   fallbacks, type scale), spacing scale, corner radii, elevation. A
   single-page style-guide artifact is a great deliverable.
2. **Home page mock** — hero (couple's names + date + venue), a short
   intro block, and nav to RSVP / gallery / hotel / registry / FAQ.
3. **RSVP landing mock** — the form: name confirm, attending Y/N, plus-one
   Y/N, dietary notes, meal choice, submit. Show empty, validation-error,
   and post-submit-success states.

## What I do NOT want you to design (yet)

- Full gallery page (upload UX, lightbox, pagination) — designed later
  once Phase 2 exercises the model.
- Hotel / registry / FAQ pages beyond nav-link treatment.
- Admin UI — that's Django admin, untouched by design.
- Transactional emails.
- Anything that requires me to make product decisions I haven't made yet
  (guest-account login? gift-tracking? seating chart?). If you notice a
  gap, flag it; don't invent.

## Deliverable format (matters for adoption)

- **Static HTML + CSS** artifacts, not React components — the site's
  templates are Django's; my build will port the markup/CSS by hand.
- **Self-hostable fonts only.** The site's CSP will block external CDN
  links (Google Fonts, etc.). If you use a Google font, name it and note
  "self-host these files" in the deliverable.
- **Color values as hex plus CSS custom properties** (`--color-*`,
  `--font-*`, `--space-*` naming). The build will lift these into a real
  design-token file.
- **Mobile-first responsive.** RSVP form must be usable on a phone.
- **No JS.** Design is presentational; interactivity is my problem.

## Context you need from me (fill in before handing off)

Fill these in before pasting this brief into the design session, or the
designer will invent them:

- **Couple's names: Kaitlyn Mason and Steven Nielsen**
- **Wedding date: 05-23-2027**
- **Venue / location: Louland Falls, Salt Lake City, UT**
- **Season / setting: late spring, outdoor, mountainous**
- **Tone / aesthetic references: warm, magical, loving. images from our engagements (hosted in S3) peppered throughout the whole site not just limited to the gallery**
- **Existing print materials to match? our save the date print used darker shades of green**

## Handoff back to the build

When the design session is done, drop the outputs into
`design/` at repo root (I'll gitignore intermediate files if needed) and
open a new session log noting: which artifacts landed, which tokens the
Phase 2 build should adopt, and any product questions the designer
surfaced.
