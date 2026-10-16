"""Course evaluations: what learners say about the course, the facilitator, the venue and the organisation.

When an intake ends, every confirmed learner on it is given a private link (no sign-in). They answer once.
Answers are read in aggregate: per intake, per course and per facilitator. Who said what is not shown on
the staff screens; only whether each learner has answered, so the administrator knows whom to remind.
"""

import datetime as dt
import secrets

from django.db import transaction

from core import clock
from core.api_support import Refusal
from learners.models import Enrolment, Evaluation

DIMENSIONS = [("content", "Course content"), ("facilitation", "Facilitator"), ("venue", "Venue and materials"),
              ("organisation", "Organisation and communication")]
WINDOW_DAYS = 183  # intakes that ended in the last six months are asked


@transaction.atomic
def request_for_ended(on: dt.date | None = None) -> int:
    """Create the evaluation for each confirmed learner on an intake that has ended. Idempotent."""
    on = on or clock.today()
    missing = (Enrolment.objects.filter(is_active=True, stage_index__gte=1, plan_block__end_date__lt=on,
                                        plan_block__end_date__gte=on - dt.timedelta(days=WINDOW_DAYS), evaluation__isnull=True)
               .exclude(plan_block__state="Cancelled").select_related("plan_block"))
    made = 0
    for e in missing:
        Evaluation.objects.create(enrolment=e, facilitator_id=e.plan_block.facilitator_id, token=secrets.token_urlsafe(24))
        made += 1
    return made


def public_view(token: str) -> dict:
    ev = (Evaluation.objects.select_related("enrolment__learner", "enrolment__course", "enrolment__plan_block__venue", "facilitator")
          .filter(token=token).first())
    if ev is None:
        raise Refusal("not_found", ["This feedback link is not valid. Ask the FSA Academy for a new one."], "Link not found.", status=404)
    b = ev.enrolment.plan_block
    return {"learner": ev.enrolment.learner.names.split()[0], "course": ev.enrolment.course.title,
            "dates": f"{b.start_date:%d %b %Y} to {b.end_date:%d %b %Y}" if b else "", "venue": b.venue.name if b else "",
            "facilitator": ev.facilitator.display_name if ev.facilitator_id else "", "submitted": ev.submitted_at is not None,
            "dimensions": [{"key": k, "label": l} for k, l in DIMENSIONS]}


@transaction.atomic
def submit(token: str, answers: dict):
    ev = Evaluation.objects.select_for_update().filter(token=token).first()
    if ev is None:
        raise Refusal("not_found", ["This feedback link is not valid."], "Link not found.", status=404)
    if ev.submitted_at:
        raise Refusal("already_submitted", ["Your feedback was already received. Thank you."], "Already received.")
    reasons = []
    for key, label in DIMENSIONS:
        v = answers.get(key)
        if not isinstance(v, int) or not 1 <= v <= 5:
            reasons.append(f"Rate “{label}” from 1 to 5.")
    if answers.get("recommend") not in (True, False):
        reasons.append("Say whether you would recommend the course.")
    if reasons:
        raise Refusal("invalid", reasons, "Please complete the form.", status=422)
    for key, _ in DIMENSIONS:
        setattr(ev, key, answers[key])
    ev.recommend = answers["recommend"]
    ev.comments = (answers.get("comments") or "").strip()[:2000]
    ev.submitted_at = clock.now()
    ev.save()


def _avg(rows, key):
    vals = [getattr(r, key) for r in rows if getattr(r, key)]
    return round(sum(vals) / len(vals), 1) if vals else None


def summary(rows) -> dict:
    answered = [r for r in rows if r.submitted_at]
    rec = [r.recommend for r in answered if r.recommend is not None]
    return {"asked": len(rows), "answered": len(answered),
            "responseRate": round(100 * len(answered) / len(rows)) if rows else None,
            "scores": {k: _avg(answered, k) for k, _ in DIMENSIONS},
            "overall": round(sum(s for k, _ in DIMENSIONS if (s := _avg(answered, k))) / max(1, sum(1 for k, _ in DIMENSIONS if _avg(answered, k))), 1)
            if answered else None,
            "recommend": round(100 * sum(rec) / len(rec)) if rec else None}


def by_facilitator(since: dt.date | None = None) -> list[dict]:
    qs = Evaluation.objects.select_related("facilitator")
    if since:
        qs = qs.filter(enrolment__plan_block__end_date__gte=since)
    groups = {}
    for ev in qs:
        groups.setdefault(ev.facilitator.display_name if ev.facilitator_id else "Unknown", []).append(ev)
    return sorted(({"name": k, **summary(v)} for k, v in groups.items()), key=lambda r: (r["scores"]["facilitation"] or 9, r["name"]))
