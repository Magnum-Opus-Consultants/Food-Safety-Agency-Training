"""The department picture: nav counts, the desk's six triggers, the attention list.

Rule 6: badge counts are computed from the registers on request, never stored.
Rule 8: an item reaches the head of department's desk only by trigger. It arrives by
itself when the condition becomes true and leaves when it clears.
"""
import datetime as dt

from django.db.models import Exists, OuterRef, Q

from assurance.models import Accreditation, Document, Placement, Risk
from core import clock
from delivery.models import PlanBlock, Session
from delivery.rules import register_state
from demand.models import Enquiry, Quotation, QuotationFollowUp
from identity.models import Account
from learners.models import Enrolment, Moderation, Result
from learners.rules import gate_blockers
from oversight.models import Rotation

QUOTE_APPROVAL_CENTS = 50_000_00  # R 50 000
CHANNEL_LABEL = {"Phone": "phone", "Email": "email", "WhatsApp": "WhatsApp", "DirectLine": "her direct line"}


def rand(cents: int) -> str:
    return "R " + f"{cents // 100:,}".replace(",", " ")


# --- registers ------------------------------------------------------------------------

def stale_enquiries(today):
    open_new = Enquiry.objects.filter(is_active=True, kind="Enquiry", first_response_at__isnull=True).select_related(
        "contact__organisation", "assigned_to", "course"
    )
    return [e for e in open_new if clock.working_days_since(e.received_at) > 2]


def sessions_with_state(today):
    sessions = Session.objects.filter(is_active=True).select_related(
        "plan_block__course", "plan_block__facilitator", "plan_block__venue", "register"
    )
    return [(s, *register_state(s, today)) for s in sessions]


def registers_outstanding(today):
    return [s for s, state, _ in sessions_with_state(today) if state == "Outstanding"]


def awaiting_moderation():
    return Result.objects.filter(is_active=True, moderation__isnull=True)


def awaiting_certificate():
    return Moderation.objects.filter(outcome="Competent", certificate__isnull=True)


def registrations_flagged(today):
    flagged = []
    for account in Account.objects.filter(is_active=True).prefetch_related("registrations"):
        reg = account.current_registration()
        if reg and reg.standing(today) in ("Lapsed", "Expiring"):
            flagged.append((account, reg, reg.standing(today)))
    return flagged


def gate_incomplete():
    enrolments = Enrolment.objects.filter(is_active=True, stage_index=0).select_related("course", "learner")
    return [e for e in enrolments if gate_blockers(e)]


def placement_reports_due(today):
    rows = Placement.objects.filter(is_active=True, report_submitted_at__isnull=True).select_related("organisation")
    return [p for p in rows if p.report_due <= today + dt.timedelta(days=5)]


def risks_escalated():
    return Risk.objects.filter(is_active=True).filter(Q(rating="High") | Q(trigger_breached_at__isnull=False))


def depository_outstanding():
    return Document.objects.filter(is_active=True, state="Outstanding")


def quotes_over_value():
    return Quotation.objects.filter(
        is_active=True, state__in=["Draft", "Issued"], value_cents__gt=QUOTE_APPROVAL_CENTS, approved_at__isnull=True
    ).select_related("organisation", "contact", "course")


def quotes_without_follow_up(today):
    issued = Quotation.objects.filter(is_active=True, state="Issued", issued_on__isnull=False).annotate(
        followed=Exists(QuotationFollowUp.objects.filter(quotation=OuterRef("pk")))
    ).select_related("organisation", "contact", "course")
    return [q for q in issued if not q.followed and q.follow_up_due < today]


def nav_counts(today=None) -> dict:
    """The badge-count contract of 03-api.md. One call serves the whole rail."""
    today = today or clock.today()
    return {
        "StaleEnquiries": len(stale_enquiries(today)),
        "RegistersOutstanding": len(registers_outstanding(today)),
        "AwaitingModeration": awaiting_moderation().count(),
        "AwaitingCertificate": awaiting_certificate().count(),
        "AccredFlags": len(registrations_flagged(today)),
        "GateIncomplete": len(gate_incomplete()),
        "PartnershipReportsDue": len(placement_reports_due(today)),
        "RisksEscalated": risks_escalated().count(),
        "DepositoryOutstanding": depository_outstanding().count(),
        "DeskEscalated": len(escalated(today)),
    }


# --- the desk --------------------------------------------------------------------------

TRIGGERS = [
    {"rule": "An enquiry is unanswered after two working days", "kind": "SLA"},
    {"rule": "A quotation exceeds R 50 000", "kind": "Value"},
    {"rule": "A quotation has had no follow-up for fourteen days", "kind": "SLA"},
    {"rule": "Any accreditation, HPCSA or moderation item is at risk", "kind": "Topic"},
    {"rule": "A complaint is received, on any channel", "kind": "Topic"},
    {"rule": "A new industry or partnership opportunity is logged", "kind": "Topic"},
]
CHANNEL_RULE = (
    "Channel rule: her direct line and WhatsApp reach her first. Phone and email route to the admin "
    "rotation and reach her only on a trigger above."
)


def _who(contact):
    org = contact.organisation.name if contact.organisation_id else ""
    return f"{contact.names} — {org}" if org else contact.names


def escalated(today=None) -> list[dict]:
    today = today or clock.today()
    items = []
    for e in stale_enquiries(today):
        days = clock.working_days_since(e.received_at)
        items.append({
            "ref": e.reference, "route": "/enquiries",
            "title": f"{_who(e.contact)} — {e.course.title if e.course else e.course_interest}",
            "detail": f"Received by {CHANNEL_LABEL.get(e.channel, e.channel)} and not yet answered. Assigned to "
                      f"{e.assigned_to.display_name if e.assigned_to else 'nobody — unassigned'}.",
            "trigger": "Enquiry unanswered after two working days", "triggerKind": "SLA",
            "age": f"{days} working days open", "state": "Overdue", "tone": "bad",
        })
    for q in quotes_over_value():
        age = (today - q.issued_on).days if q.issued_on else 0
        items.append({
            "ref": q.reference, "route": "/quotes",
            "title": f"{q.organisation.name if q.organisation else q.contact.names} quotation — {rand(q.value_cents)}",
            "detail": f"Above the R 50 000 approval line. Quoted {'per group' if q.basis == 'PerGroup' else 'per learner'} "
                      f"for {q.learner_count} learners, {q.course.title}.",
            "trigger": "Quote over R 50 000", "triggerKind": "Value",
            "age": f"{age} days open", "state": "Approval", "tone": "warn",
        })
    for q in quotes_without_follow_up(today):
        items.append({
            "ref": q.reference, "route": "/quotes",
            "title": f"{q.organisation.name if q.organisation else q.contact.names} quotation — no follow-up",
            "detail": f"Issued {q.issued_on.isoformat()}; follow-up was due {q.follow_up_due.isoformat()}.",
            "trigger": "No follow-up for fourteen days", "triggerKind": "SLA",
            "age": f"{(today - q.follow_up_due).days} days past follow-up", "state": "Overdue", "tone": "warn",
        })
    for account, reg, standing in registrations_flagged(today):
        booked = PlanBlock.objects.filter(
            facilitator=account, is_active=True, end_date__gte=today
        ).exclude(state="Cancelled").values_list("reference", flat=True)
        if not booked:
            continue
        verb = "lapsed" if standing == "Lapsed" else "expires"
        items.append({
            "ref": account.reference, "route": "/facilitators",
            "title": f"{account.display_name} — {reg.registration_type} {verb} {reg.expires_on.isoformat()}",
            "detail": f"Scheduled on {', '.join(booked)}. "
                      + ("Those blocks cannot be confirmed." if standing == "Lapsed" else "Renew before delivery."),
            "trigger": "Accreditation, HPCSA or moderation item at risk", "triggerKind": "Topic",
            "age": f"{(reg.expires_on - today).days} days", "state": "At risk", "tone": "bad" if standing == "Lapsed" else "warn",
        })
    for acc in Accreditation.objects.filter(is_active=True, expires_on__lte=today + dt.timedelta(days=90)).select_related("body"):
        items.append({
            "ref": acc.reference, "route": "/accreditation",
            "title": f"{acc.body.name} renewal — {acc.scope}, due {acc.expires_on.isoformat()}",
            "detail": "Delivery under this scope stops if the renewal lapses.",
            "trigger": "Accreditation item at risk", "triggerKind": "Topic",
            "age": f"Due in {(acc.expires_on - today).days} days", "state": "Decision", "tone": "bad",
        })
    for e in Enquiry.objects.filter(is_active=True, kind__in=["Complaint", "Opportunity"], resolved_at__isnull=True).select_related("contact__organisation"):
        complaint = e.kind == "Complaint"
        items.append({
            "ref": e.reference, "route": "/enquiries",
            "title": f"{'Complaint' if complaint else 'Opportunity'} — {_who(e.contact)}",
            "detail": e.course_interest,
            "trigger": "Complaint, any channel" if complaint else "Industry or partnership opportunity",
            "triggerKind": "Topic",
            "age": f"{(today - clock.local_date(e.received_at)).days} days open",
            "state": "Complaint" if complaint else "Opportunity", "tone": "bad" if complaint else "info",
        })
    return items


def running_without(today=None) -> list[dict]:
    """Everything else carries a named owner, a count and its escalation condition."""
    today = today or clock.today()

    def rota(area):
        member = Rotation.on_duty(area, today)
        return f"Admin rotation · this week {member.display_name}" if member else None

    enquiries = Enquiry.objects.filter(is_active=True, kind="Enquiry", resolved_at__isnull=True).exclude(channel="DirectLine")
    quotes = Quotation.objects.filter(is_active=True, state="Issued")
    enrolments = Enrolment.objects.filter(is_active=True, stage_index__lt=4)
    registers = registers_outstanding(today)
    marking = awaiting_moderation()
    filing = depository_outstanding()
    overdue_quotes = len(quotes_without_follow_up(today))

    def row(title, owner, escalates, qs_or_list, unassigned=0, state=None, tone=None):
        n = len(qs_or_list) if isinstance(qs_or_list, list) else qs_or_list.count()
        if owner is None:
            owner, state, tone = "Unassigned — no one on rotation", "Unassigned", "bad"
        elif unassigned:
            state, tone = f"{unassigned} unassigned", "bad"
        return {"title": title, "owner": owner, "escalates": escalates, "n": n,
                "state": state or "On standard", "tone": tone or "ok"}

    return [
        row("Enquiry triage — phone and email", rota("EnquiryTriage"), "unanswered after two working days", enquiries,
            unassigned=enquiries.filter(assigned_to__isnull=True).count()),
        row("Quotation follow-up at fourteen days", rota("QuoteFollowUp"), "no follow-up at 14 days, or the value is over R 50 000",
            quotes, unassigned=quotes.filter(assigned_to__isnull=True).count(),
            state=f"{overdue_quotes} overdue" if overdue_quotes else None, tone="warn" if overdue_quotes else None),
        row("Learner database and enrolment capture", rota("LearnerRecords"), "an entry gate is waived", enrolments,
            unassigned=enrolments.filter(assigned_to__isnull=True).count()),
        row("Marking and result capture", "Session facilitator and assessor", "marking is older than ten working days", marking,
            state="Awaiting moderation" if marking.exists() else None, tone="warn" if marking.exists() else None),
        row("Attendance register capture and lock", "Session facilitator", "a delivered session has no register", registers,
            state="Outstanding" if registers else None, tone="bad" if registers else None),
        row("Record filing to the depository", rota("Filing"), "a retention deadline is missed", filing),
    ]


# --- home ------------------------------------------------------------------------------

def attention(today=None) -> list[dict]:
    today = today or clock.today()
    registers = registers_outstanding(today)
    stale = stale_enquiries(today)
    accreditations = Accreditation.objects.filter(is_active=True, expires_on__lte=today + dt.timedelta(days=90)).select_related("body")
    refs = lambda items: ", ".join(i.reference for i in items)
    rows = [
        {"title": "Attendance registers outstanding", "n": len(registers), "tone": "bad", "route": "/sessions",
         "detail": f"{refs(registers)} {'has' if len(registers) == 1 else 'have'} been delivered without a captured register."
                   if registers else "Every delivered session has a locked register."},
        {"title": "Results awaiting moderation", "n": awaiting_moderation().count(), "tone": "warn", "route": "/results",
         "detail": "Every result is moderated by the training manager before issue."},
        {"title": "Certificates awaiting issue", "n": awaiting_certificate().count(), "tone": "info", "route": "/certificates",
         "detail": "Moderated and ready for the training manager to sign and issue."},
        {"title": "Enquiries over the response standard", "n": len(stale), "tone": "bad", "route": "/enquiries",
         "detail": "Two working days from receipt, whatever the channel."},
        {"title": "Accreditation renewal due", "n": accreditations.count(), "tone": "warn", "route": "/accreditation",
         "detail": "; ".join(f"{a.body.name} renewal {a.expires_on.isoformat()}" for a in accreditations) or "No renewal inside ninety days."},
    ]
    return rows


def week_strip(today=None) -> list[dict]:
    today = today or clock.today()
    monday, sunday = clock.week_of(today)
    rows = []
    for b in PlanBlock.objects.filter(is_active=True, start_date__lte=sunday, end_date__gte=monday).exclude(state="Cancelled").select_related(
        "course", "venue", "facilitator"
    ):
        rows.append({
            "date": f"{b.start_date:%d %b} – {b.end_date:%d %b}" if b.start_date != b.end_date else f"{b.start_date:%d %b}",
            "sort": b.start_date.isoformat(),
            "course": b.course.title,
            "detail": f"{b.reference} · {b.venue.name} · {b.facilitator.display_name} · {b.seats_booked} of {b.capacity} seats",
        })
    for p in Placement.objects.filter(is_active=True, report_submitted_at__isnull=True).select_related("organisation"):
        if monday <= p.report_due <= sunday:
            rows.append({
                "date": f"{p.report_due:%d %b}", "sort": p.report_due.isoformat(),
                "course": f"{p.organisation.name} placement report due",
                "detail": f"Twenty days from period end {p.period_end.isoformat()}",
            })
    return sorted(rows, key=lambda r: r["sort"])


def hero(today=None) -> dict:
    today = today or clock.today()
    month_start = today.replace(day=1)
    next_month = (month_start + dt.timedelta(days=32)).replace(day=1)
    sessions_month = Session.objects.filter(
        is_active=True, plan_block__start_date__lt=next_month, plan_block__end_date__gte=month_start
    ).exclude(plan_block__state="Cancelled").count()
    live = Enrolment.objects.filter(is_active=True, stage_index__in=[2, 3]).count()
    mod = awaiting_moderation().count()
    stale = len(stale_enquiries(today))
    registers = len(registers_outstanding(today))
    renewals = Accreditation.objects.filter(is_active=True, expires_on__lte=today + dt.timedelta(days=90)).count()

    def pl(n, one, many):
        return f"{n} {one if n == 1 else many}"

    words = {0: "no", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    statement = (
        f"The department is delivering to plan, with {words.get(registers, registers)} attendance "
        f"{'register' if registers == 1 else 'registers'} and {words.get(renewals, renewals)} accreditation "
        f"{'renewal' if renewals == 1 else 'renewals'} outstanding."
    )
    return {
        "statement": statement,
        "stats": [
            {"v": str(sessions_month), "l": f"Sessions in {today:%B}", "c": "Planned and delivered this month"},
            {"v": str(live), "l": "Live enrolments", "c": "Registered or in training"},
            {"v": str(mod), "l": "Awaiting moderation", "c": pl(mod, "result", "results") + " assessed, not moderated"},
            {"v": str(stale), "l": "Enquiries over two days", "c": "Against the two-working-day standard"},
        ],
    }
