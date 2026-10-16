"""Marketing campaigns and the feedback loop to FSA.

A campaign is recorded with its channel, dates, courses and cost. Each enquiry records how the person heard
about FSA, and names the campaign when one brought them. A campaign's results are then read from the
registers (enquiries it brought, quotations, learners registered, value accepted, cost per registration),
and marketing adds its evaluation and recommendations, which go back to FSA with the figures.
"""

import datetime as dt
from decimal import Decimal, InvalidOperation

from django.db import transaction

from audit.services import record
from core import clock
from core.api_support import Refusal
from demand.models import CAMPAIGN_CHANNELS, SOURCE_LABEL, Campaign


def rand(cents: int) -> str:
    return f"R {cents / 100:,.2f}".replace(",", " ")


def _manager(actor):
    if not actor.can("demand", write=True):
        raise Refusal("forbidden", ["Campaigns are recorded by marketing or the training manager."], "Not permitted.", status=403)


def _cents(value) -> int | None:
    if value in (None, ""):
        return 0
    try:
        d = Decimal(str(value).replace(" ", "").replace(",", ""))
    except InvalidOperation:
        return None
    return int(d * 100) if d >= 0 else None


def _check(name, channel, starts_on, ends_on, cost):
    reasons = []
    if not (name or "").strip():
        reasons.append("Name the campaign.")
    if channel not in CAMPAIGN_CHANNELS:
        reasons.append("Choose the channel it ran on.")
    if starts_on is None or ends_on is None:
        reasons.append("Give the dates it ran.")
    elif ends_on < starts_on:
        reasons.append("The end date is before the start date.")
    if cost is None:
        reasons.append("Give the cost in rand, or leave it at 0.")
    return reasons


@transaction.atomic
def create(actor, *, name, channel, starts_on, ends_on, courses, cost, objective="", screen="campaigns"):
    _manager(actor)
    cents = _cents(cost)
    reasons = _check(name, channel, starts_on, ends_on, cents)
    if reasons:
        raise Refusal("invalid", reasons, "The campaign cannot be recorded yet.", status=422)
    c = Campaign.objects.create(name=name.strip()[:160], channel=channel, starts_on=starts_on, ends_on=ends_on, cost_cents=cents,
                                objective=(objective or "").strip(), created_by=actor, modified_by=actor)
    c.courses.set(courses)
    return c, record(actor, f"{c.reference} campaign recorded — {c.name} ({channel}, {starts_on.isoformat()} to {ends_on.isoformat()}, "
                            f"{rand(cents)})", c, screen=screen)


@transaction.atomic
def update(actor, c, changes: dict, courses=None, screen="campaigns"):
    _manager(actor)
    before, after = {}, {}
    name = changes.get("name", c.name)
    channel = changes.get("channel", c.channel)
    starts_on = changes.get("starts_on", c.starts_on)
    ends_on = changes.get("ends_on", c.ends_on)
    cents = _cents(changes["cost"]) if "cost" in changes else c.cost_cents
    reasons = _check(name, channel, starts_on, ends_on, cents)
    if reasons:
        raise Refusal("invalid", reasons, f"{c.reference} cannot be saved yet.", status=422)
    for field, new in [("name", (name or "").strip()), ("channel", channel), ("starts_on", starts_on), ("ends_on", ends_on),
                       ("cost_cents", cents), ("objective", (changes.get("objective", c.objective) or "").strip()),
                       ("recommendations", (changes.get("recommendations", c.recommendations) or "").strip())]:
        if getattr(c, field) != new:
            before[field], after[field] = str(getattr(c, field)), str(new)
            setattr(c, field, new)
    if courses is not None and set(courses) != set(c.courses.all()):
        before["courses"] = ", ".join(sorted(x.code for x in c.courses.all()))
        after["courses"] = ", ".join(sorted(x.code for x in courses))
        c.courses.set(courses)
    if not after:
        raise Refusal("no_change", ["Nothing was changed."], "There is nothing to save.")
    c.modified_by = actor
    c.save()
    what = "evaluation and recommendations updated" if set(after) == {"recommendations"} else "updated: " + ", ".join(
        k.replace("_cents", "").replace("_", " ") for k in after)
    return record(actor, f"{c.reference} {what}", c, screen=screen, before=before, after=after)


def results(c, on: dt.date | None = None) -> dict:
    """What the campaign brought, read from the registers."""
    from learners.models import Enrolment

    on = on or clock.today()
    enquiries = list(c.enquiries.filter(is_active=True).select_related("course"))
    ids = [e.pk for e in enquiries]
    quotes = [q for e in enquiries for q in e.quotations.all() if q.is_active]
    learners = Enrolment.objects.filter(is_active=True).filter(enquiry_id__in=ids).count() + \
        Enrolment.objects.filter(is_active=True, enquiry__isnull=True, quotation__enquiry_id__in=ids).count()
    accepted = sum(q.value_cents for q in quotes if q.state == "Accepted")
    registered = sum(1 for e in enquiries if e.stage_index == 3)
    by_course = {}
    for e in enquiries:
        key = e.course.title if e.course_id else (e.course_interest or "Not specified")
        by_course[key] = by_course.get(key, 0) + 1
    if on < c.starts_on:
        state, tone = "Planned", "na"
    elif on <= c.ends_on:
        state, tone = "Running", "info"
    else:
        state, tone = "Ended", "ok" if c.recommendations else "warn"
    return {
        "enquiries": len(enquiries), "responded": sum(1 for e in enquiries if e.first_response_at),
        "quoted": len({q.enquiry_id for q in quotes}), "registered": registered, "lost": sum(1 for e in enquiries if e.stage_index == 4),
        "learners": learners, "accepted": rand(accepted), "acceptedCents": accepted,
        "conversion": round(100 * registered / len(enquiries)) if enquiries else None,
        "costPerEnquiry": rand(c.cost_cents // len(enquiries)) if enquiries and c.cost_cents else None,
        "costPerLearner": rand(c.cost_cents // learners) if learners and c.cost_cents else None,
        "returnOnCost": round(accepted / c.cost_cents, 1) if c.cost_cents else None,
        "byCourse": sorted(({"course": k, "enquiries": v} for k, v in by_course.items()), key=lambda r: -r["enquiries"]),
        "state": state, "tone": tone,
        "position": "Evaluation needed — add the recommendations for FSA" if state == "Ended" and not c.recommendations else state,
    }


def source_label(e) -> str:
    if e.source == "Campaign" and e.campaign_id:
        return f"Campaign: {e.campaign.name}"
    return SOURCE_LABEL.get(e.source, "Not recorded")
