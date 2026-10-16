from django.db import models, transaction

from audit.services import record
from core import clock
from core.api_support import Refusal
from demand.models import FOR_LABEL, ENQ_STAGES, ENQ_TOPICS, TOPIC_LABEL, Contact, Enquiry
from identity.models import Account
from oversight.models import Rotation


def route(channel: str):
    """Every channel routes to the admin rotation; the owner can be changed on the enquiry."""
    return Rotation.on_duty("EnquiryTriage", clock.today())


@transaction.atomic
def move_enquiry(actor, enquiry, stage_index: int, screen="enquiries"):
    if not 0 <= stage_index < len(ENQ_STAGES):
        raise Refusal("bad_stage", [f"Stage {stage_index} does not exist."], "Choose one of the five stages.")
    if stage_index == enquiry.stage_index:
        raise Refusal("same_stage", [f"{enquiry.reference} is already at {enquiry.stage}."], "Nothing to change.")
    if stage_index == 2 and enquiry.kind == "Enquiry" and not enquiry.quotations.filter(is_active=True).exists():
        raise Refusal("create_quotation", [
            f"Create the quotation to move {enquiry.reference} to Quoted, so the board shows what was quoted."
        ], "An enquiry reaches Quoted only when a quotation is created from it.")
    if stage_index == 3 and enquiry.kind == "Enquiry" and enquiry.enquiring_for == "Company" and not enquiry.enrolments.exists():
        raise Refusal("add_delegates", [
            f"{enquiry.reference} is for {enquiry.contact.organisation.name if enquiry.contact.organisation_id else 'a company'}: "
            "register the people it is sending as a list on its quotation (Add delegates), not the person who enquired."
        ], "A company enquiry reaches Registered when its delegates are registered.")
    if stage_index == 3 and enquiry.kind == "Enquiry" and not enquiry.enrolments.exists():
        raise Refusal("register_learner", [
            f"Register the learner to move {enquiry.reference} to Registered: capture their details and choose the course and intake."
        ], "An enquiry reaches Registered only when a learner is registered from it.")
    before = enquiry.stage
    enquiry.stage_index = stage_index
    now = clock.now()
    if stage_index > 0 and enquiry.first_response_at is None:
        enquiry.first_response_at = now  # the SLA clock stops on first response
    if stage_index in (3, 4) and enquiry.resolved_at is None:
        enquiry.resolved_at = now
    if stage_index < 3:
        enquiry.resolved_at = None
    enquiry.modified_by = actor
    enquiry.save()
    return record(actor, f"{enquiry.reference} moved from {before} to {enquiry.stage}", enquiry, screen=screen,
                  before={"stage": before}, after={"stage": enquiry.stage})


@transaction.atomic
def resolve(actor, enquiry, screen="desk"):
    if enquiry.resolved_at:
        raise Refusal("already_resolved", [f"{enquiry.reference} was resolved on {enquiry.resolved_at:%Y-%m-%d}."], "Nothing to resolve.")
    enquiry.resolved_at = clock.now()
    if enquiry.first_response_at is None:
        enquiry.first_response_at = enquiry.resolved_at
    enquiry.modified_by = actor
    enquiry.save()
    return record(actor, f"{enquiry.reference} {enquiry.kind.lower()} resolved", enquiry, screen=screen)


def check_topics(kind: str, topics: list[str], other: str, required: bool) -> tuple[list[str], str, list[str]]:
    """Return (topics in their standard order, other text, reasons). Course enquiries say what
    they asked about; "Other" needs a description. Complaints and opportunities carry no topics."""
    if kind != "Enquiry":
        return [], "", []
    order = [code for code, _ in ENQ_TOPICS]
    unknown = [t for t in topics if t not in order]
    clean = [code for code in order if code in topics]
    other = (other or "").strip() if "Other" in clean else ""
    reasons = [f"{t} is not one of the question topics." for t in unknown]
    if required and not clean:
        reasons.append("Tick at least one thing they asked about: accreditation, costs, online or in person, duration, quote or other.")
    if "Other" in clean and not other:
        reasons.append("Describe the other question they asked.")
    return clean, other, reasons


def topics_text(topics: list[str], other: str) -> str:
    return ", ".join(f"Other: {other}" if t == "Other" else TOPIC_LABEL[t] for t in topics)


@transaction.atomic
def log_enquiry(actor, names, organisation, channel, kind, course, interest, screen="enquiries", email="", phone="",
                topics=None, topic_other="", enquiring_for="Individual", source="", campaign=None):
    contact = Contact.objects.create(names=names, organisation=organisation, email=email, phone=phone, created_by=actor)
    assignee = route(channel)
    enquiry = Enquiry.objects.create(
        contact=contact, kind=kind, channel=channel, received_at=clock.now(), course=course,
        course_interest=interest, topics=topics or [], topic_other=topic_other, assigned_to=assignee, created_by=actor,
        enquiring_for=enquiring_for if kind == "Enquiry" else "Individual",
        source=source if kind == "Enquiry" else "", campaign=campaign if source == "Campaign" else None,
    )
    who = assignee.display_name if assignee else "nobody — unassigned, flagged for action"
    audit = record(actor, f"{enquiry.reference} logged from {channel} and routed to {who}", enquiry, screen=screen)
    return enquiry, audit


CHANNEL_LABELS = {"Phone": "phone", "Email": "email", "WhatsApp": "WhatsApp"}


def owner_options():
    """Who an enquiry can be assigned to: accounts that can work the demand register."""
    from identity.models import Account

    return (Account.objects.filter(is_active=True, state="Active", is_service_account=False)
            .filter(models.Q(segments__segment_id="demand", segments__access="write") | models.Q(hub_role="TrainingManager"))
            .distinct().order_by("display_name"))


@transaction.atomic
def update_enquiry(actor, enquiry, changes: dict, screen="enquiries"):
    """Correct an enquiry's details. Every changed field is audited with its previous value.

    Not editable: the reference, the received time (it drives the two-working-day SLA clock) and
    the stage (moved on the board, so the clock and the Registered rule apply)."""
    from courses.models import Course
    from identity.models import Account
    from demand.models import Organisation

    contact = enquiry.contact
    reasons, before, after = [], {}, {}

    def note(field, old, new):
        if (old or "") != (new or ""):
            before[field], after[field] = old or "", new or ""

    if "names" in changes:
        names = (changes["names"] or "").strip()
        if not names:
            reasons.append("The enquirer's name cannot be blank.")
        else:
            note("Name", contact.names, names)
    if "email" in changes:
        email = (changes["email"] or "").strip()
        if email and "@" not in email:
            reasons.append(f"{email} is not an email address.")
        else:
            note("Email", contact.email, email)
    if "phone" in changes:
        from core.phone import normalise

        phone, problem = normalise(changes["phone"])
        if problem:
            reasons.append(f"Phone: {problem}.")
        else:
            note("Phone", contact.phone, phone)
    if "organisation" in changes:
        note("Organisation", contact.organisation.name if contact.organisation_id else "", (changes["organisation"] or "").strip())
    if "channel" in changes:
        if changes["channel"] not in CHANNEL_LABELS:
            reasons.append("Choose the channel it arrived on: phone, email or WhatsApp.")
        else:
            note("Channel", enquiry.channel, changes["channel"])
    if "kind" in changes:
        if changes["kind"] not in ("Enquiry", "Complaint", "Opportunity"):
            reasons.append("Choose enquiry, complaint or opportunity.")
        elif changes["kind"] != enquiry.kind and enquiry.enrolments.exists():
            reasons.append(f"{enquiry.reference} has registered a learner, so it stays a course enquiry.")
        else:
            note("Kind", enquiry.kind, changes["kind"])
    new_course = enquiry.course
    if "courseCode" in changes:
        code = (changes["courseCode"] or "").strip()
        new_course = Course.objects.filter(code=code).first() if code else None
        if code and new_course is None:
            reasons.append(f"There is no course {code} in the catalogue.")
        elif new_course != enquiry.course and enquiry.enrolments.exists():
            reasons.append(f"{enquiry.reference} has already registered a learner on {enquiry.course.title if enquiry.course else 'its course'}. "
                           "Change the course on the enrolment instead.")
        else:
            note("Course", enquiry.course.title if enquiry.course else "", new_course.title if new_course else "")
    kind_after = changes.get("kind", enquiry.kind) if changes.get("kind") in ("Enquiry", "Complaint", "Opportunity") else enquiry.kind
    if "interest" in changes:
        label = "Course not in catalogue" if kind_after == "Enquiry" else "Details"
        note(label, enquiry.course_interest, (changes["interest"] or "").strip())
    interest_after = (changes.get("interest", enquiry.course_interest) or "").strip()
    if kind_after != "Enquiry" and not interest_after:
        reasons.append(f"Describe the {kind_after.lower()}.")
    new_topics, new_other = enquiry.topics, enquiry.topic_other
    if "topics" in changes or "topicOther" in changes or "kind" in changes:
        new_topics, new_other, topic_reasons = check_topics(
            kind_after, changes.get("topics", enquiry.topics) or [], changes.get("topicOther", enquiry.topic_other),
            required="topics" in changes)
        reasons += topic_reasons
        note("Asked about", topics_text(enquiry.topics, enquiry.topic_other), topics_text(new_topics, new_other))
    new_owner = enquiry.assigned_to
    if "ownerRef" in changes:
        ref = (changes["ownerRef"] or "").strip()
        new_owner = owner_options().filter(reference=ref).first() if ref else None
        if ref and new_owner is None:
            reasons.append("The owner must be someone who works the enquiry queue.")
        else:
            note("Owner", enquiry.assigned_to.display_name if enquiry.assigned_to else "", new_owner.display_name if new_owner else "")
    if "notes" in changes:
        note("Additional remarks", enquiry.notes, (changes["notes"] or "").strip())
    for_after = enquiry.enquiring_for
    if "enquiringFor" in changes and kind_after == "Enquiry":
        for_after = changes["enquiringFor"]
        if for_after not in FOR_LABEL:
            reasons.append("Say whether they are enquiring for a company or for themselves.")
        elif for_after == "Individual" and enquiry.quotations.filter(is_active=True).exists():
            reasons.append(f"{enquiry.reference} has a quotation, so it stays a company enquiry.")
        else:
            note("Enquiring for", FOR_LABEL[enquiry.enquiring_for], FOR_LABEL[for_after])
    new_source, new_campaign = enquiry.source, enquiry.campaign
    if "source" in changes or "campaignRef" in changes:
        from demand.campaigns import source_label
        from demand.models import SOURCE_LABEL, Campaign

        new_source = changes.get("source", enquiry.source) or ""
        ref = changes.get("campaignRef", enquiry.campaign.reference if enquiry.campaign_id else "") or ""
        new_campaign = Campaign.objects.filter(is_active=True, reference=ref).first() if new_source == "Campaign" and ref else None
        if new_source and new_source not in SOURCE_LABEL:
            reasons.append("Choose how they heard about FSA.")
        elif new_source == "Campaign" and new_campaign is None:
            reasons.append("Choose the campaign that brought them.")
        else:
            class _E:  # what the label would read after the change
                source, campaign, campaign_id = new_source, new_campaign, new_campaign.pk if new_campaign else None
            note("Heard about us", source_label(enquiry) if enquiry.source else "", source_label(_E) if new_source else "")
    org_after = (changes["organisation"] or "").strip() if "organisation" in changes else (
        contact.organisation.name if contact.organisation_id else "")
    if kind_after == "Enquiry" and for_after == "Company" and not org_after:
        reasons.append("A company enquiry needs the company's name.")

    if reasons:
        raise Refusal("invalid", reasons, f"{enquiry.reference} cannot be saved yet.", status=422)
    if not after:
        raise Refusal("no_change", ["Nothing was changed."], "There is nothing to save.")

    if "Name" in after: contact.names = after["Name"]
    if "Email" in after: contact.email = after["Email"]
    if "Phone" in after: contact.phone = after["Phone"]
    if "Organisation" in after:
        org_name = after["Organisation"]
        contact.organisation = (Organisation.objects.filter(name__iexact=org_name).first()
                                or Organisation.objects.create(name=org_name, created_by=actor)) if org_name else None
    contact.modified_by = actor
    contact.save()
    if "Channel" in after: enquiry.channel = after["Channel"]
    if "Kind" in after: enquiry.kind = after["Kind"]
    if "Course" in after: enquiry.course = new_course
    if "Course not in catalogue" in after: enquiry.course_interest = after["Course not in catalogue"]
    if "Details" in after: enquiry.course_interest = after["Details"]
    if "Asked about" in after: enquiry.topics, enquiry.topic_other = new_topics, new_other
    if "Owner" in after: enquiry.assigned_to = new_owner
    if "Additional remarks" in after: enquiry.notes = after["Additional remarks"]
    if "Enquiring for" in after: enquiry.enquiring_for = for_after
    if "Heard about us" in after: enquiry.source, enquiry.campaign = new_source, new_campaign
    enquiry.modified_by = actor
    enquiry.save()

    def short(v):
        return v if len(v) <= 40 else v[:37] + "…"
    summary = "; ".join(f"{k.lower()} {short(before[k]) or '—'} → {short(after[k]) or '—'}" for k in after if k != "Additional remarks")
    if "Additional remarks" in after:
        summary = (summary + "; " if summary else "") + "additional remarks updated"
    return record(actor, f"{enquiry.reference} details corrected — {summary}", enquiry, screen=screen, before=before, after=after)
