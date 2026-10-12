# FSA Academy Training Hub — demo build

The training department's back office: Next.js front end, Django API, PostgreSQL. Built to the
design pack in `../FSA Training Hub/design_handoff_fsa_training_hub/` and the architecture in
`../architecture/training-hub-architecture.html`.

The demo is real screens, real rules and illustrative data. Whatever the department captures is
saved in Postgres and survives a refresh; every rule is enforced by the API, and the most
important ones again by the database.

## Run it

You need Node 20+ and Python 3.12+. Three terminals:

```bash
# 1. Database — a local PostgreSQL 18 downloaded through npm (no system install)
cd tools/devdb && npm install && npm start            # localhost:5433

# 2. API — Django on :8210
cd backend
python -m venv .venv && .venv/Scripts/activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py reset_demo --yes                     # loads the prototype data and writes ../demo-logins.txt
python manage.py runserver 127.0.0.1:8210

# 3. Front end — Next.js on :3210
cd web && npm install && npm run dev
```

Open http://localhost:3210 and sign in with a username and password from `demo-logins.txt`
(project root, git-ignored). `python manage.py reset_demo` restores the demo data at any time and
keeps the same passwords; delete `demo-logins.txt` first to issue new ones.

Sign-in is a real username and password, checked against a PBKDF2 hash. Five failed attempts lock a
username for fifteen minutes, a wrong password gets the same message whether or not the username
exists, and a suspended account is refused only after its password is proven. Microsoft Entra ID
single sign-on replaces this for production. API docs are at http://localhost:8210/api/fsa/docs while `DJANGO_DEBUG` is on.

Ports 3210 and 8210 avoid clashing with other local apps on 3000 and 8000. Next.js runs with
`--webpack` because Windows Application Control blocks the native Turbopack binary on this machine;
where it isn't blocked, `next dev` without the flag works too.

## Try the definition of done

1. Sign in as **Thandi Ncube** (facilitator). You land on the department picture.
2. Open **Sessions & attendance** — you see only your own sessions. Open **SES-0312**, mark each
   learner present or absent, and press **Capture and lock register**. The rail's badge drops from
   2 to 1. Try to capture it again: refused. Record a correction: a new audited entry, the original
   is kept.
3. Sign out, sign in as **Palesa Mpana** (head of training). Open **Head of department desk**: each
   escalated item names the trigger that put it there; the work running without her names its
   owner on this week's rotation.
4. Use the **›** beside the date to move the demo clock a day. ENQ-0420 crosses two working days
   and appears on the desk by itself (phase 2 acceptance). Move it to Responded on the enquiry
   board and it leaves.
5. On **Certification**, issue a certificate for RES-0293: refused, and the refusal says why. Record
   its moderation on **Results & moderation**, then issue it.
6. On **Training plan & schedule**, open PLN-07 and confirm it: hard-blocked because Sipho
   Dlamini's registration lapsed. Try signing in as Sipho: suspended.

Every action above appears in the audit trail at the foot of the screen that caused it.

## How a learner becomes part of the system

Three routes, one set of rules (`backend/learners/registration.py`): consent recorded (POPIA), a
free seat on the chosen intake (the seat is booked on the plan), no second enrolment on the same
intake, one audit entry per registration.

1. **Individual, from an enquiry.** On the enquiry board, drag a card to *Registered* (or use
   **Register learner** on the card). The form opens prefilled from the enquiry; on save the learner,
   the enrolment at *Applied* and the enquiry's move to Registered happen together. An enquiry cannot
   reach Registered any other way. **Register a learner** on *Enrolments* does the same without an enquiry.
2. **Corporate group.** On *Quotes & corporate accounts*, **Add delegates** on a per-group quotation:
   paste the client's list (name, email, phone — or straight from Excel). Refused beyond the number
   quoted or the intake's free seats; all or nothing. The first delegates accept the quotation.
   Try QTE-0218 (Chalmar Beef, HACCP) onto PLN-13.
3. **University cohort.** On *Universities & vet placements*, **Import cohort list**: upload the
   university's CSV or paste it (name, student number, email). Students are matched on student
   number, so re-importing skips those already enrolled. Placement students start at *Registered*
   because the placement agreement is their entry requirement. Try University of Johannesburg onto PLN-08.

The entry gate still governs everything that starts at *Applied*: prerequisite ≥ 50% **and** Grade 10.

**One person, one record.** Individuals and delegates need an SA ID or passport number (optional
for university students, who have a student number). The number is validated (13 digits, a real
date of birth, the check digit), encrypted before it is stored, and never returned by the API: the
screens show only the last four digits. A keyed hash of it finds the same person again, whichever
client or university sends them, so a second registration attaches to the existing record. A
record captured before ID numbers were recorded is matched once on name and organisation and given
the ID. Keys: `FSA_PII_ENCRYPTION_KEY` and `FSA_PII_INDEX_KEY` (see `.env.example`); production
refuses to start without them.

**Seats booked is a count, not a number typed in.** It is the active enrolments on the intake,
counted while the intake is locked, so two registrations cannot both take the last seat and the
figure cannot drift from the people behind it.

## Tests

```bash
cd backend && .venv/Scripts/python manage.py test tests
```

40 tests against a real Postgres: the prototype's badge counts, the phase 1, 2 and 4 acceptance
tests, the register lock and corrections, the certificate guard (API and database trigger), the
scheduling hard block, suspension on the day a registration lapses, the two-part entry gate, and
the append-only audit trail, sign-in (generic refusal, lockout, no service-account login), the three registration routes, identity-number matching and
encryption, and seats derived from enrolments.

## Layout

```
backend/                Django 5.2 LTS + Django Ninja
  fsa/                  settings, urls, the API root and session auth
  core/                 row metadata, references, reference data, business clock, seed
  identity/             accounts, segments, registrations, sign-in, users
  audit/                audit entries (append-only trigger)
  courses/ demand/ delivery/ learners/ assurance/ oversight/
    models.py           the register
    rules.py            pure functions that return blockedBy reasons
    services.py         mutations: one transaction, one audit entry
    api.py              endpoints: segment check, then service
  tests/                acceptance tests
web/                    Next.js 16 (App Router) + TanStack Query
  app/(staff)/          24 routes; unbuilt screens are stubs with their copy
  components/           Shell (rail, header) and design-system stand-ins
  lib/                  API client, nav config with badge keys, hooks
tools/devdb/            local PostgreSQL for developers
```

## Where the twelve rules live

| # | Rule | Enforced in |
| --- | --- | --- |
| 1–2 | Two-part entry gate; refusal names what is outstanding | `learners/rules.py` · API 409 `blockedBy` · `<Blocked>` |
| 3 | Register locks on save; correction is a new entry | `delivery/services.py` · DB triggers in `delivery/migrations/0003` |
| 4 | No certificate before moderation | `learners/rules.py` · DB trigger in `learners/migrations/0002` |
| 5 | Lapsed facilitator cannot be scheduled | `delivery/rules.py` · sign-in refused the day it lapses |
| 6–7 | Badges and figures derived, never stored | `oversight/rules.py` · `/nav-counts` · no-store fetches |
| 8 | Desk reached only by trigger | `oversight/rules.py · escalated()` |
| 11 | Every state change audited | `audit/services.record` inside each transaction · append-only trigger |
| 12 | Fixed status vocabulary | `components/ui.tsx · Status` |

Rules 9–10 (pack snapshot, recorded exclusions) belong to the pack composer, phase 5.

## Built, stubbed and not yet built

**Full:** training home, head of department desk, enquiry board (drag between stages, log and
route), sessions and attendance (capture, lock, correct), enrolments (gate capture and advance),
results (moderation), certification (guarded issue, depository filing), demo clock.

**Read:** catalogue, quotes, plan (as a register with derived warnings and the confirm hard block),
facilitators, learner directory, accreditation, partnerships (20-day clock), risk, depository, users.

**Stub:** management dashboard, monthly report, contacts, course development, packs, integrations,
data layer.

**Not yet built, in build order:** planner horizons (year, month, week) and block editor; pack
composer; course development gate; dashboard and printable A4 report; certificate PDFs (WeasyPrint
in a worker); Entra ID sign-in; generated OpenAPI client (Orval); optimistic concurrency (ETag /
If-Match); Outlook, WhatsApp and IMI integrations.

## Not in the pack, stood in for

- **Design: matched to the FSA APS portal** (aps-demo.fsa-pty.co.za), so FSA systems look and operate
  alike: the dark collapsible sidebar with grouped icon navigation, white page headings on the photo
  background, white 12px cards, the dark-headed zebra registers, teal `#007890` primary, APS buttons
  and modals, Font Awesome 6.4, system font. Values were read (read-only) from the APS front end.
  The logo and background in `web/public/brand/` are APS's own. The design pack's FSA Design System
  (Jost, Arial, red primary) differs; FSA should confirm APS is the standard to follow.
- **HR Hub shell.** `components/Shell.tsx` is written to become the shared `@fsa/shell` package.

## Open items for FSA, found while building

- The desk derives **9** escalated items from the seed where the prototype shows a hand-picked 6: each
  facilitator registration at risk is its own item. Confirm whether they should group.
- "Delivered" is taken as **the block has ended**, which gives the monthly report's two outstanding
  registers. The prototype counted from the start date (three).
- Which registration each course requires is unspecified; any current registration satisfies the
  hard block until FSA supplies the mapping (`Course.required_registration_type`).
- N. Sibeko and R. Adams are on the rotation but not in the confirmed account list; they are seeded
  as rotation members.
- Nav-count field names follow `03-api.md`; the prototype's data-layer page uses different names.
