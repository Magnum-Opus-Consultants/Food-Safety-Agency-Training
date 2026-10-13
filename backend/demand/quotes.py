"""Clients and quotations: adding a client (a company and its contact person), drafting a quotation,
approving one over R 50 000, and issuing it. Every step is audited."""

from decimal import Decimal, InvalidOperation

from django.db import transaction

from audit.services import record
from core import clock
from core.api_support import Refusal
from core.phone import normalise
from courses.models import Course
from demand.models import Contact, Enquiry, Organisation, Quotation
from oversight.models import Rotation
from oversight.rules import QUOTE_APPROVAL_CENTS, rand


def _contact_problems(names, email, phone):
    reasons = [] if (names or "").strip() else ["Name the contact person at the client."]
    if (email or "").strip() and "@" not in email:
        reasons.append(f"{email.strip()} is not an email address.")
    number, problem = normalise(phone or "")
    if problem:
        reasons.append(f"Phone: {problem}.")
    return reasons, number


@transaction.atomic
def add_client(actor, *, name, sector, contact_names, email, phone, screen="quotes"):
    name = (name or "").strip()
    reasons = [] if name else ["Give the company's name."]
    existing = Organisation.objects.filter(name__iexact=name, is_active=True).first() if name else None
    if existing:
        reasons.append(f"{existing.name} is already a client ({existing.reference}). Choose it from the list instead.")
    more, number = _contact_problems(contact_names, email, phone)
    reasons += more
    if reasons:
        raise Refusal("invalid", reasons, "The client cannot be added yet.", status=422)
    org = Organisation.objects.create(name=name, sector=(sector or "").strip(), relationship="Client", created_by=actor)
    contact = Contact.objects.create(organisation=org, names=contact_names.strip(), email=(email or "").strip(), phone=number,
                                     created_by=actor)
    audit = record(actor, f"Client {org.reference} {org.name} added, contact {contact.names}", org, screen=screen,
                   after={"Client": org.name, "Sector": org.sector or "—", "Contact": contact.names})
    return org, contact, audit


@transaction.atomic
def add_contact(actor, org, *, names, email, phone, screen="quotes"):
    reasons, number = _contact_problems(names, email, phone)
    if reasons:
        raise Refusal("invalid", reasons, "The contact cannot be added yet.", status=422)
    contact = Contact.objects.create(organisation=org, names=names.strip(), email=(email or "").strip(), phone=number, created_by=actor)
    return contact, record(actor, f"Contact {contact.names} added to {org.name}", org, screen=screen)


def _cents(value: str) -> int | None:
    try:
        amount = Decimal(str(value).replace("R", "").replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0:
        return None
    return int((amount * 100).quantize(Decimal("1")))


@transaction.atomic
def create_quotation(actor, *, organisation_ref, contact_ref, course_code, basis, learners, value, enquiry_ref="",
                     screen="quotes"):
    reasons = []
    enquiry = Enquiry.objects.filter(reference=enquiry_ref, is_active=True).select_related("contact").first() if enquiry_ref else None
    if enquiry_ref and enquiry is None:
        reasons.append(f"No enquiry {enquiry_ref}.")
    elif enquiry is not None and enquiry.kind != "Enquiry":
        reasons.append(f"{enquiry.reference} is a {enquiry.kind.lower()}, not a course enquiry.")
    # An individual enquiring for themselves is quoted personally, per learner. Their employer, if
    # recorded, is not the client, so the quotation stays off the corporate accounts.
    individual = enquiry is not None and enquiry.enquiring_for == "Individual"
    org = None
    if not individual:
        org = Organisation.objects.filter(reference=organisation_ref, is_active=True).first() if organisation_ref else None
        if organisation_ref and org is None:
            reasons.append(f"No client {organisation_ref}.")
        if org is None and not organisation_ref:
            reasons.append("A company quotation needs the client company: choose or add it.")
    contact = Contact.objects.filter(reference=contact_ref, is_active=True).first()
    if contact is None:
        reasons.append("Choose the contact person the quotation is addressed to.")
    elif individual and contact.pk != enquiry.contact_id:
        reasons.append(f"Quote {enquiry.reference} to {enquiry.contact.names}, who enquired.")
    elif org is not None and contact.organisation_id != org.pk:
        reasons.append(f"{contact.names} is not a contact at {org.name}.")
    course = Course.objects.filter(code=course_code, is_active=True).first()
    if course is None:
        reasons.append("Choose the course being quoted.")
    if basis not in ("PerGroup", "PerLearner"):
        reasons.append("Choose per group or per learner.")
    elif individual and basis != "PerLearner":
        reasons.append(f"{enquiry.contact.names} is enquiring for themselves: quote per learner.")
    if not learners or learners < 1:
        reasons.append("Give the number of learners, at least one.")
    cents = _cents(value)
    if cents is None:
        reasons.append("Give the quoted value in rand, for example 68400 or 68 400.00.")
    if reasons:
        raise Refusal("invalid", reasons, "The quotation cannot be saved yet.", status=422)
    quote = Quotation.objects.create(
        enquiry=enquiry, contact=contact, organisation=org, course=course, basis=basis, learner_count=learners,
        value_cents=cents, state="Draft", assigned_to=Rotation.on_duty("QuoteFollowUp", clock.today()) or actor,
        created_by=actor,
    )
    needs = cents > QUOTE_APPROVAL_CENTS
    audit = record(actor, f"{quote.reference} drafted for {org.name if org else contact.names}"
                          + (f" from {enquiry.reference}" if enquiry else "") + f" — {course.title}, "
                          f"{learners} {'learner' if learners == 1 else 'learners'}, {rand(cents)}"
                          + (" — over R 50 000, needs the head of department's approval before it is issued" if needs else ""),
                   quote, screen=screen)
    return quote, audit


@transaction.atomic
def approve(actor, quote, screen="quotes"):
    if actor.hub_role != "TrainingManager":
        raise Refusal("forbidden", ["A quotation over R 50 000 is approved by the head of department."], "Not yours to approve.",
                      status=403)
    if quote.value_cents <= QUOTE_APPROVAL_CENTS:
        raise Refusal("not_needed", [f"{quote.reference} is {rand(quote.value_cents)}; only quotations over R 50 000 need approval."],
                      "No approval needed.")
    if quote.approved_at:
        raise Refusal("already_approved", [f"{quote.reference} was approved by {quote.approved_by.display_name}."], "Already approved.")
    quote.approved_at, quote.approved_by, quote.modified_by = clock.now(), actor, actor
    quote.save()
    return record(actor, f"{quote.reference} approved at {rand(quote.value_cents)}", quote, screen=screen)


@transaction.atomic
def issue(actor, quote, screen="quotes"):
    reasons = []
    if quote.state != "Draft":
        reasons.append(f"{quote.reference} is already {quote.state.lower()}.")
    if quote.value_cents > QUOTE_APPROVAL_CENTS and not quote.approved_at:
        reasons.append(f"{quote.reference} is {rand(quote.value_cents)}, over R 50 000: the head of department approves it before it is issued.")
    if reasons:
        raise Refusal("cannot_issue", reasons, "The quotation cannot be issued yet.")
    quote.state, quote.issued_on, quote.modified_by = "Issued", clock.today(), actor
    quote.save()
    moved = ""
    enquiry = quote.enquiry
    if enquiry is not None and enquiry.stage_index < 2:
        # Issuing the quotation answers the enquiry: it moves to Quoted, and the response clock stops.
        before = enquiry.stage
        enquiry.stage_index = 2
        enquiry.first_response_at = enquiry.first_response_at or clock.now()
        enquiry.modified_by = actor
        enquiry.save()
        moved = f"; {enquiry.reference} moved from {before} to Quoted"
    return record(actor, f"{quote.reference} issued to {quote.organisation.name if quote.organisation_id else quote.contact.names}; "
                         f"follow-up due {quote.follow_up_due.isoformat()}{moved}", quote, screen=screen)


@transaction.atomic
def edit_draft(actor, quote, *, course_code=None, basis=None, learners=None, value=None, approve=False, screen="quotes"):
    """Change a quotation before it is issued. Once issued it stands as sent: it is not edited,
    withdrawn or declined. Only the head of department (the training manager) edits a draft, and may
    approve it in the same step."""
    quote = Quotation.objects.select_for_update(of=("self",)).select_related("course", "organisation", "contact").get(pk=quote.pk)
    if actor.hub_role != "TrainingManager":
        raise Refusal("forbidden", ["A draft quotation is edited by the head of department (the training manager)."],
                      "Not yours to edit.", status=403)
    if quote.state != "Draft":
        raise Refusal("issued", [f"{quote.reference} was issued on {quote.issued_on.isoformat() if quote.issued_on else 'its issue date'} "
                                 "and stands as sent to the client; an issued quotation is not changed."], "Issued quotations are not edited.")
    reasons, before, after = [], {}, {}

    def note(label, old, new):
        if old != new:
            before[label], after[label] = old, new

    course = quote.course
    if course_code is not None:
        course = Course.objects.filter(code=course_code, is_active=True).first()
        if course is None:
            reasons.append("Choose the course being quoted.")
        else:
            note("Course", quote.course.title, course.title)
    new_basis = quote.basis
    if basis is not None:
        if basis not in ("PerGroup", "PerLearner"):
            reasons.append("Choose per group or per learner.")
        elif quote.organisation_id is None and basis != "PerLearner":
            reasons.append("An individual is quoted per learner.")
        else:
            new_basis = basis
            label = {"PerGroup": "Per group", "PerLearner": "Per learner"}
            note("Basis", label[quote.basis], label[basis])
    new_learners = quote.learner_count
    if learners is not None:
        if learners < 1:
            reasons.append("Give the number of learners, at least one.")
        else:
            new_learners = learners
            note("Learners", str(quote.learner_count), str(learners))
    cents = quote.value_cents
    if value is not None:
        cents = _cents(value)
        if cents is None:
            reasons.append("Give the quoted value in rand, for example 68400 or 68 400.00.")
            cents = quote.value_cents
        else:
            note("Value", rand(quote.value_cents), rand(cents))
    if reasons:
        raise Refusal("invalid", reasons, f"{quote.reference} cannot be saved yet.", status=422)
    if not after and not approve:
        raise Refusal("no_change", ["Nothing was changed."], "There is nothing to save.")

    quote.course, quote.basis, quote.learner_count, quote.value_cents = course, new_basis, new_learners, cents
    over = cents > QUOTE_APPROVAL_CENTS
    approval = ""
    if after and quote.approved_at and not approve:
        quote.approved_at, quote.approved_by = None, None
        approval = " — approval withdrawn: the changed quotation needs approving again" if over else ""
    if approve:
        if not over:
            approval = " — R 50 000 or less, so no approval is needed"
        else:
            quote.approved_at, quote.approved_by = clock.now(), actor
            approval = f" — approved at {rand(cents)}"
    quote.modified_by = actor
    quote.save()
    summary = "; ".join(f"{k.lower()} {before[k]} → {after[k]}" for k in after) or "no changes"
    what = f"{quote.reference} draft {'edited' if after else 'reviewed'} — {summary}{approval}"
    return quote, record(actor, what, quote, screen=screen, before=before or None, after=after or None)
