"""The management dashboard: what the department delivers, which courses succeed, when demand comes,
where interest comes from, and how well the department itself keeps up. Every figure is read from the
registers on each call (enquiries, quotations, enrolments, results, moderation, certificates, registers);
nothing is stored or typed in.
"""

import datetime as dt
from collections import Counter, defaultdict
from statistics import median

from core import clock

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
RESPONSE_DAYS = 2      # an enquiry is answered within two working days
CERTIFICATE_DAYS = 10  # a certificate is issued within ten working days of moderation


def _months(today: dt.date, n: int) -> list[dt.date]:
    first = today.replace(day=1)
    out = []
    for i in range(n - 1, -1, -1):
        y, m = first.year, first.month - i
        while m <= 0:
            y, m = y - 1, m + 12
        out.append(dt.date(y, m, 1))
    return out


def _month_of(value) -> dt.date:
    d = clock.local_date(value) if isinstance(value, dt.datetime) else value
    return d.replace(day=1)


def _wd(a: dt.datetime, b: dt.datetime) -> int:
    return clock.working_days_between(a, b)


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def build(months: int = 12, course: str = "", on: dt.date | None = None) -> dict:
    from courses.models import Course
    from delivery.models import PlanBlock
    from demand.models import SOURCE_LABEL, TOPIC_LABEL, Enquiry, Quotation
    from learners.models import Certificate, Enrolment, Result

    on = on or clock.today()
    span = _months(on, months)
    since = span[0]
    keys = [m.isoformat()[:7] for m in span]

    enquiries = Enquiry.objects.filter(is_active=True, kind="Enquiry").select_related("course", "assigned_to")
    enrolments = Enrolment.objects.filter(is_active=True).select_related("course")
    results = Result.objects.filter(is_active=True).select_related("enrolment__course", "moderation")
    certificates = Certificate.objects.filter(revoked_at__isnull=True).select_related("moderation__result__enrolment__course")
    quotations = Quotation.objects.filter(is_active=True).select_related("course")
    if course:
        enquiries, enrolments = enquiries.filter(course__code=course), enrolments.filter(course__code=course)
        results, quotations = results.filter(enrolment__course__code=course), quotations.filter(course__code=course)
        certificates = certificates.filter(moderation__result__enrolment__course__code=course)
    all_enq, all_enr = list(enquiries), list(enrolments)
    enq = [e for e in all_enq if clock.local_date(e.received_at) >= since]
    enr = [e for e in all_enr if clock.local_date(e.created_at) >= since]
    res = [r for r in results if clock.local_date(r.assessed_at) >= since]
    certs = [c for c in certificates if clock.local_date(c.issued_at) >= since]

    # --- Throughput: month by month ---------------------------------------------------------------
    def per_month(items, when):
        c = Counter(_month_of(when(x)).isoformat()[:7] for x in items)
        return [c.get(k, 0) for k in keys]

    competent = [r for r in res if getattr(r, "moderation", None) and r.moderation.outcome == "Competent"]
    throughput = {
        "months": [f"{MONTH_NAMES[m.month - 1]} {str(m.year)[2:]}" for m in span],
        "series": [
            {"key": "enquiries", "label": "Enquiries", "values": per_month(enq, lambda e: e.received_at)},
            {"key": "registered", "label": "Learners registered", "values": per_month(enr, lambda e: e.created_at)},
            {"key": "assessed", "label": "Learners assessed", "values": per_month(res, lambda r: r.assessed_at)},
            {"key": "certified", "label": "Certificates issued", "values": per_month(certs, lambda c: c.issued_at)},
        ],
        "funnel": [
            {"label": "Registered", "v": len(enr)},
            {"label": "Confirmed", "v": sum(1 for e in enr if e.stage_index >= 1)},
            {"label": "Assessed", "v": len({r.enrolment_id for r in res})},
            {"label": "Competent", "v": len({r.enrolment_id for r in competent})},
            {"label": "Certified", "v": len(certs)},
        ],
    }

    # --- Courses: what is taken and what succeeds -----------------------------------------------
    by_course = defaultdict(lambda: {"enquiries": 0, "registered": 0, "assessed": 0, "competent": 0, "nyc": 0, "certified": 0})
    for e in enq:
        if e.course_id:
            by_course[e.course.title]["enquiries"] += 1
    for e in enr:
        by_course[e.course.title]["registered"] += 1
    for r in res:
        row = by_course[r.enrolment.course.title]
        row["assessed"] += 1
        m = getattr(r, "moderation", None)
        if m:
            row["competent" if m.outcome == "Competent" else "nyc"] += 1
    for c in certs:
        by_course[c.moderation.result.enrolment.course.title]["certified"] += 1
    courses = sorted(({"course": k, **v, "passRate": _pct(v["competent"], v["competent"] + v["nyc"])}
                      for k, v in by_course.items()), key=lambda r: (-r["registered"], r["course"]))

    # --- Seasons: every year on record, by calendar month ---------------------------------------
    enq_m = Counter(clock.local_date(e.received_at).month for e in all_enq)
    enr_m = Counter(clock.local_date(e.created_at).month for e in all_enr)
    combined = {m: enq_m.get(m, 0) + enr_m.get(m, 0) for m in range(1, 13)}
    peaks = [m for m, v in sorted(combined.items(), key=lambda x: -x[1]) if v][:3]
    seasons = {
        "months": MONTH_NAMES,
        "enquiries": [enq_m.get(m, 0) for m in range(1, 13)],
        "registered": [enr_m.get(m, 0) for m in range(1, 13)],
        "peaks": [MONTH_NAMES[m - 1] for m in sorted(peaks)],
        "years": sorted({clock.local_date(e.received_at).year for e in all_enq} | {clock.local_date(e.created_at).year for e in all_enr}),
    }

    # --- Marketing: where interest comes from and what it turns into -----------------------------
    quoted_enquiries = {q.enquiry_id for q in quotations if q.enquiry_id}

    def funnel_of(items):
        n = len(items)
        return {"enquiries": n, "responded": sum(1 for e in items if e.first_response_at),
                "quoted": sum(1 for e in items if e.pk in quoted_enquiries or e.stage_index == 2),
                "registered": sum(1 for e in items if e.stage_index == 3),
                "lost": sum(1 for e in items if e.stage_index == 4)}

    def grouped(key):
        groups = defaultdict(list)
        for e in enq:
            for k in key(e):
                groups[k].append(e)
        return sorted(({"name": k, **funnel_of(v), "conversion": _pct(funnel_of(v)["registered"], len(v))} for k, v in groups.items()),
                      key=lambda r: -r["enquiries"])

    upcoming = set(PlanBlock.objects.filter(is_active=True, start_date__gte=on).exclude(state="Cancelled").values_list("course_id", flat=True))
    recent = [e for e in enq if e.course_id and clock.local_date(e.received_at) >= on - dt.timedelta(days=90)]
    unmet = Counter(e.course.title for e in recent if e.course_id not in upcoming)
    marketing = {
        "funnel": funnel_of(enq),
        "byCourse": grouped(lambda e: [e.course.title if e.course_id else (e.course_interest or "Not specified")]),
        "byChannel": grouped(lambda e: [e.channel]),
        "byTopic": grouped(lambda e: [TOPIC_LABEL.get(t, t) for t in e.topics] or ["No topic noted"]),
        "byWho": grouped(lambda e: ["For a company" if e.enquiring_for == "Company" else "For themselves"]),
        "bySource": grouped(lambda e: [SOURCE_LABEL.get(e.source, "Not recorded")]),
        "unmet": [{"course": k, "enquiries": v} for k, v in unmet.most_common()],
        "campaigns": _campaigns(since, on, course),
    }

    # --- Internal effectiveness ------------------------------------------------------------------
    responded = [e for e in enq if e.first_response_at]
    days = [_wd(e.received_at, e.first_response_at) for e in responded]
    handlers = defaultdict(list)
    for e, d in zip(responded, days):
        handlers[e.assigned_to.display_name if e.assigned_to_id else "Unassigned"].append(d)
    waiting = [e for e in enq if not e.first_response_at and clock.working_days_since(e.received_at) > RESPONSE_DAYS]
    moderated = [r for r in res if getattr(r, "moderation", None)]
    mod_days = [_wd(r.assessed_at, r.moderation.moderated_at) for r in moderated]
    cert_days = [_wd(c.moderation.moderated_at, c.issued_at) for c in certs]
    effectiveness = {
        "enquiries": {"answered": len(responded), "onTime": _pct(sum(1 for d in days if d <= RESPONSE_DAYS), len(days)),
                      "median": median(days) if days else None, "waitingLate": len(waiting), "standard": RESPONSE_DAYS,
                      "byHandler": sorted(({"name": k, "answered": len(v), "onTime": _pct(sum(1 for d in v if d <= RESPONSE_DAYS), len(v)),
                                            "median": median(v)} for k, v in handlers.items()), key=lambda r: -r["answered"])},
        "moderation": {"moderated": len(moderated), "median": median(mod_days) if mod_days else None,
                       "awaiting": sum(1 for r in res if not getattr(r, "moderation", None))},
        "certificates": {"issued": len(certs), "onTime": _pct(sum(1 for d in cert_days if d <= CERTIFICATE_DAYS), len(cert_days)),
                         "median": median(cert_days) if cert_days else None, "standard": CERTIFICATE_DAYS},
        "facilitators": _facilitators(on),
        "feedback": _feedback(since),
    }

    return {
        "period": {"from": since.isoformat(), "to": on.isoformat(), "months": months},
        "course": course,
        "courses_list": [{"code": c.code, "title": c.title} for c in Course.objects.filter(is_active=True).order_by("title")],
        "totals": [
            {"v": str(len(enq)), "l": "Enquiries", "c": f"{_pct(marketing['funnel']['registered'], len(enq)) or 0}% became registrations"},
            {"v": str(len(enr)), "l": "Learners registered", "c": f"Last {months} months"},
            {"v": f"{_pct(len(competent), len([r for r in res if getattr(r, 'moderation', None)])) or 0}%", "l": "Pass rate",
             "c": "Moderated competent, of those moderated"},
            {"v": str(len(certs)), "l": "Certificates issued", "c": f"{effectiveness['certificates']['onTime'] or 0}% within {CERTIFICATE_DAYS} working days"},
        ],
        "throughput": throughput, "courses": courses, "seasons": seasons, "marketing": marketing, "effectiveness": effectiveness,
    }


def _campaigns(since, on, course=""):
    """Campaigns that ran in the period, with what each brought."""
    from demand.campaigns import rand, results
    from demand.models import Campaign

    qs = Campaign.objects.filter(is_active=True, ends_on__gte=since, starts_on__lte=on).prefetch_related("courses")
    if course:
        qs = qs.filter(courses__code=course).distinct()
    rows = []
    for c in qs:
        r = results(c, on)
        rows.append({"ref": c.reference, "name": c.name, "channel": c.channel, "starts": c.starts_on.isoformat(), "ends": c.ends_on.isoformat(),
                     "cost": rand(c.cost_cents), **{k: r[k] for k in ("enquiries", "registered", "learners", "accepted", "conversion",
                                                                      "costPerLearner", "returnOnCost", "state", "tone", "position")},
                     "evaluated": bool(c.recommendations)})
    return rows


def _feedback(since):
    """What learners said, for intakes that ended in the period."""
    from learners import evaluations
    from learners.models import Evaluation

    rows = list(Evaluation.objects.filter(enrolment__plan_block__end_date__gte=since))
    return {**evaluations.summary(rows), "dimensions": [{"key": k, "label": l} for k, l in evaluations.DIMENSIONS],
            "byFacilitator": evaluations.by_facilitator(since)}


def _facilitators(on):
    from delivery.performance import indicators
    from delivery.planning import facilitator_options

    rows = []
    for a in facilitator_options():
        w = indicators(a, on)
        if w["items"]:
            rows.append({"name": a.display_name, "position": w["position"], "tone": w["tone"],
                         "items": [{"label": i["label"], "tone": i["tone"], "note": i["note"]} for i in w["items"]]})
    return sorted(rows, key=lambda r: ({"bad": 0, "warn": 1, "ok": 2}.get(r["tone"], 3), r["name"]))
