from django.db import transaction

from audit.services import record
from core import clock
from core.api_support import Refusal
from demand.models import ENQ_STAGES, Contact, Enquiry
from identity.models import Account
from oversight.models import Rotation


def route(channel: str):
    """Channel rule: her direct line reaches her first; everything else goes to the rotation."""
    if channel == "DirectLine":
        return Account.objects.filter(hub_role="TrainingManager", state="Active", is_active=True).order_by("id").first()
    return Rotation.on_duty("EnquiryTriage", clock.today())


@transaction.atomic
def move_enquiry(actor, enquiry, stage_index: int, screen="enquiries"):
    if not 0 <= stage_index < len(ENQ_STAGES):
        raise Refusal("bad_stage", [f"Stage {stage_index} does not exist."], "Choose one of the five stages.")
    if stage_index == enquiry.stage_index:
        raise Refusal("same_stage", [f"{enquiry.reference} is already at {enquiry.stage}."], "Nothing to change.")
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


@transaction.atomic
def log_enquiry(actor, names, organisation, channel, kind, course, interest, screen="enquiries"):
    contact = Contact.objects.create(names=names, organisation=organisation, created_by=actor)
    assignee = route(channel)
    enquiry = Enquiry.objects.create(
        contact=contact, kind=kind, channel=channel, received_at=clock.now(), course=course,
        course_interest=interest, assigned_to=assignee, created_by=actor,
    )
    who = assignee.display_name if assignee else "nobody — unassigned, shown as a finding"
    audit = record(actor, f"{enquiry.reference} logged from {channel} and routed to {who}", enquiry, screen=screen)
    return enquiry, audit
