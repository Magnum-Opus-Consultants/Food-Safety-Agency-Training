import datetime as dt

from django.db.models import Q
from ninja import Router, Schema

from core import clock
from core.api_support import Refusal, iso, ok, require, stamp
from courses.models import Course
from demand import quotes, services
from demand.models import ENQ_STAGES, ENQ_TOPICS, TOPIC_LABEL, Enquiry, Organisation, Quotation
from oversight.rules import QUOTE_APPROVAL_CENTS, rand

router = Router(tags=["demand"])


def clock_text(e: Enquiry, days: int) -> str:
    """The two-working-day response clock as a person reads it: running until the first
    response, then how quickly it was answered."""
    def wd(n):
        return f"{n} working {'day' if n == 1 else 'days'}"
    if e.kind != "Enquiry":
        return "Resolved" if e.resolved_at else f"Open {wd(days)}"
    if e.first_response_at:
        took = clock.working_days_between(e.received_at, e.first_response_at)
        return "Responded the same working day" if took == 0 else f"Responded after {wd(took)}"
    return "Received today, waiting for a response" if days == 0 else f"Waiting {wd(days)} for a response"


def _card_quote(e: Enquiry, q: Quotation):
    registered = sum(1 for x in q.enrolments.all() if x.is_active)
    return {"ref": q.reference, "value": rand(q.value_cents), "learners": q.learner_count, "registered": registered,
            "state": q.state, "course": q.course.title, "courseCode": q.course.code,
            "client": e.contact.organisation.name if e.contact.organisation_id else e.contact.names,
            "needsApproval": q.value_cents > QUOTE_APPROVAL_CENTS and not q.approved_at,
            "canAddDelegates": q.organisation_id is not None and q.state in ("Issued", "Accepted") and registered < q.learner_count}


def enquiry_dict(e: Enquiry):
    days = clock.working_days_since(e.received_at)
    stale = e.kind == "Enquiry" and e.first_response_at is None and days > 2
    return {
        "ref": e.reference,
        "name": e.contact.names,
        "org": e.contact.organisation.name if e.contact.organisation_id else "",
        "course": e.course.title if e.course_id else e.course_interest,
        "courseCode": e.course.code if e.course_id else "",
        "topics": list(e.topics), "topicOther": e.topic_other,
        "topicLabels": [f"Other: {e.topic_other}" if t == "Other" else TOPIC_LABEL.get(t, t) for t in e.topics],
        "email": e.contact.email, "phone": e.contact.phone,
        "enrolment": next((x.reference for x in e.enrolments.all()), None),
        "orgRef": e.contact.organisation.reference if e.contact.organisation_id else "",
        "contactRef": e.contact.reference,
        "quotations": [_card_quote(e, q) for q in e.quotations.all() if q.is_active],
        "kind": e.kind,
        "enquiringFor": e.enquiring_for,
        "channel": e.channel,
        "receivedAt": iso(e.received_at),
        "workingDaysOpen": days,
        "clockText": clock_text(e, days),
        "stageIndex": e.stage_index,
        "stage": e.stage,
        "owner": e.assigned_to.display_name if e.assigned_to_id else None,
        "tone": "bad" if stale or not e.assigned_to_id else ("na" if e.stage_index >= 3 else "info"),
        "stale": stale,
        "resolved": e.resolved_at is not None,
    }


def _period(kind: str, day: dt.date) -> tuple[dt.date, dt.date, dt.date, dt.date]:
    """(first, last, previous start, next start) of the week (Monday to Sunday), month or year holding day."""
    if kind == "month":
        first = day.replace(day=1)
        nxt = (first + dt.timedelta(days=32)).replace(day=1)
        return first, nxt - dt.timedelta(days=1), (first - dt.timedelta(days=1)).replace(day=1), nxt
    if kind == "year":
        first = day.replace(month=1, day=1)
        return first, day.replace(month=12, day=31), first.replace(year=first.year - 1), first.replace(year=first.year + 1)
    monday, sunday = clock.week_of(day)
    return monday, sunday, monday - dt.timedelta(days=7), monday + dt.timedelta(days=7)


@router.get("/enquiries")
def enquiries(request, period: str = "week", date: str | None = None, q: str | None = None):
    """The board, one period at a time (week by default, or month or year): enquiries received in it.
    On the current period, enquiries still open from earlier periods are carried over, so unanswered
    work never drops off the board. With q, the period is ignored and every matching enquiry is returned."""
    require(request, "demand")
    today = clock.today()
    if period not in ("week", "month", "year"):
        raise Refusal("invalid", ["Choose week, month or year."], "Choose a period.", status=422)
    try:
        chosen = dt.date.fromisoformat(date) if date else today
    except ValueError:
        raise Refusal("invalid", [f"{date} is not a date."], "Choose a date.", status=422)
    monday, sunday, previous, following = _period(period, chosen)
    current = monday <= today <= sunday
    base = Enquiry.objects.filter(is_active=True).select_related("contact__organisation", "course", "assigned_to").prefetch_related("enrolments", "quotations__course", "quotations__enrolments")
    text = (q or "").strip()
    if text:
        rows = list(base.filter(Q(reference__icontains=text) | Q(contact__names__icontains=text)
                                | Q(contact__organisation__name__icontains=text) | Q(course__title__icontains=text)
                                | Q(course_interest__icontains=text)).order_by("-received_at")[:200])
        carried = set()
    else:
        in_week = Q(received_at__date__gte=monday, received_at__date__lte=sunday)
        carry = Q(received_at__date__lt=monday, stage_index__lt=3) if current else Q(pk__in=[])
        rows = list(base.filter(in_week | carry).order_by("received_at"))
        carried = {e.pk for e in rows if clock.local_date(e.received_at) < monday}
    items = [{**enquiry_dict(e), "carriedOver": e.pk in carried,
              "receivedOn": clock.local_date(e.received_at).isoformat()} for e in rows]

    all_rows = Enquiry.objects.filter(is_active=True)
    this_month = all_rows.filter(received_at__date__gte=today.replace(day=1))
    responded = all_rows.filter(kind="Enquiry", first_response_at__isnull=False).only("received_at", "first_response_at")
    avg = (sum(clock.working_days_between(e.received_at, e.first_response_at) for e in responded) / len(responded)) if responded else 0
    registered = all_rows.filter(stage_index=3).count()
    closed = all_rows.filter(stage_index__in=(3, 4)).count()
    stale = sum(1 for e in all_rows.filter(kind="Enquiry", first_response_at__isnull=True).only("received_at")
                if clock.working_days_since(e.received_at) > 2)
    asked = {code: 0 for code, _ in ENQ_TOPICS}
    for topics in this_month.values_list("topics", flat=True):
        for t in topics or []:
            asked[t] = asked.get(t, 0) + 1
    return ok({
        "stages": ENQ_STAGES,
        "topics": [{"code": c, "label": l} for c, l in ENQ_TOPICS],
        "askedThisMonth": [{"label": TOPIC_LABEL[c], "n": n} for c, n in asked.items()],
        "items": items,
        "stats": [
            {"v": str(this_month.count()), "l": "Received this month", "c": "All channels"},
            {"v": str(stale), "l": "Over two days", "c": "Against the two-working-day standard"},
            {"v": f"{round(100 * registered / closed) if closed else 0}%", "l": "Conversion", "c": "Registered of closed enquiries"},
            {"v": f"{avg:.1f}".replace(".", ","), "l": "Days to respond", "c": "Average, working days"},
        ],
    }, source="Enquiry register · contacts and accounts",
        period={"kind": period, "start": monday.isoformat(), "end": sunday.isoformat(), "current": current,
              "previous": previous.isoformat(), "next": following.isoformat(),
              "carriedOver": sum(1 for e in rows if e.pk in carried and e.kind == "Enquiry")},
        search=text or None)


class StageMove(Schema):
    stageIndex: int


@router.patch("/enquiries/{ref}/stage")
def move(request, ref: str, body: StageMove):
    require(request, "demand", write=True)
    enquiry = Enquiry.objects.select_related("contact__organisation", "course", "assigned_to").filter(reference=ref).first()
    if not enquiry:
        raise Refusal("not_found", [f"No enquiry {ref}."], "Not found.", status=404)
    audit = services.move_enquiry(request.user, enquiry, body.stageIndex, screen=request.headers.get("X-FSA-Screen", "enquiries"))
    return ok(enquiry_dict(enquiry), audit=audit)


@router.post("/enquiries/{ref}/resolve")
def resolve(request, ref: str):
    require(request, "demand", write=True)
    enquiry = Enquiry.objects.select_related("contact__organisation", "course", "assigned_to").filter(reference=ref).first()
    if not enquiry:
        raise Refusal("not_found", [f"No enquiry {ref}."], "Not found.", status=404)
    audit = services.resolve(request.user, enquiry, screen=request.headers.get("X-FSA-Screen", "desk"))
    return ok(enquiry_dict(enquiry), audit=audit)


class NewEnquiry(Schema):
    names: str
    organisation: str = ""
    topics: list[str] = []
    topicOther: str = ""
    email: str = ""
    phone: str = ""
    channel: str
    kind: str = "Enquiry"
    enquiringFor: str = ""
    courseCode: str = ""
    interest: str = ""


@router.post("/enquiries")
def create(request, body: NewEnquiry):
    require(request, "demand", write=True)
    reasons = []
    if not body.names.strip():
        reasons.append("Name the enquirer.")
    if body.channel not in ("Phone", "Email", "WhatsApp"):
        reasons.append("Choose the channel it arrived on: phone, email or WhatsApp.")
    if body.kind not in ("Enquiry", "Complaint", "Opportunity"):
        reasons.append("Choose enquiry, complaint or opportunity.")
    if body.kind == "Enquiry":
        if body.enquiringFor not in ("Company", "Individual"):
            reasons.append("Say whether they are enquiring for a company or for themselves.")
        elif body.enquiringFor == "Company" and not body.organisation.strip():
            reasons.append("A company enquiry needs the company's name.")
    course = Course.objects.filter(code=body.courseCode).first() if body.courseCode else None
    topics, topic_other, topic_reasons = services.check_topics(body.kind, body.topics, body.topicOther, required=True)
    reasons += topic_reasons
    if body.kind != "Enquiry" and not body.interest.strip():
        reasons.append(f"Describe the {body.kind.lower()}.")
    from core.phone import normalise

    phone, problem = normalise(body.phone)
    if problem:
        reasons.append(f"Phone: {problem}.")
    if body.email.strip() and "@" not in body.email:
        reasons.append(f"{body.email.strip()} is not an email address.")
    if reasons:
        raise Refusal("invalid", reasons, "The enquiry cannot be logged yet.", status=422)
    org = None
    if body.organisation.strip():
        org = Organisation.objects.filter(name__iexact=body.organisation.strip()).first() or Organisation.objects.create(
            name=body.organisation.strip(), created_by=request.user)
    enquiry, audit = services.log_enquiry(request.user, body.names.strip(), org, body.channel, body.kind, course,
                                          body.interest.strip(), screen=request.headers.get("X-FSA-Screen", "enquiries"),
                                          email=body.email.strip(), phone=phone, topics=topics, topic_other=topic_other,
                                          enquiring_for=body.enquiringFor or "Individual")
    enquiry = Enquiry.objects.select_related("contact__organisation", "course", "assigned_to").get(pk=enquiry.pk)
    return ok(enquiry_dict(enquiry), audit=audit)


@router.get("/quotations")
def quotations(request):
    require(request, "demand")
    today = clock.today()
    rows = []
    for q in (Quotation.objects.filter(is_active=True).select_related("organisation", "contact", "course", "assigned_to", "approved_by", "enquiry")
              .prefetch_related("follow_ups").order_by("-created_at", "-reference")):
        overdue = q.state == "Issued" and not q.follow_ups.exists() and q.follow_up_due and q.follow_up_due < today
        over = q.value_cents > 50_000_00 and not q.approved_at
        registered = q.enrolments.filter(is_active=True).count()
        rows.append({
            "registered": registered, "learners": q.learner_count, "courseCode": q.course.code,
            "canAddDelegates": q.organisation_id is not None and q.state in ("Issued", "Accepted") and registered < q.learner_count,
            "ref": q.reference, "client": q.organisation.name if q.organisation_id else q.contact.names,
            "individual": q.organisation_id is None, "contact": q.contact.names, "contactEmail": q.contact.email,
            "enquiry": q.enquiry.reference if q.enquiry_id else None,
            "course": q.course.title, "basis": "Per group" if q.basis == "PerGroup" else "Per learner",
            "value": rand(q.value_cents), "issued": iso(q.issued_on), "followUpDue": iso(q.follow_up_due),
            "owner": q.assigned_to.display_name if q.assigned_to_id else None,
            "state": q.state, "needsApproval": over, "approvedBy": q.approved_by.display_name if q.approved_by_id else None,
            "status": "Approval needed" if over else ("Follow-up overdue" if overdue else q.state),
            "tone": "warn" if over or overdue else ("ok" if q.state == "Accepted" else "info"),
        })
    return ok(rows, source="Quotation register", canApprove=request.user.hub_role == "TrainingManager")


class Delegate(Schema):
    names: str
    idNumber: str = ""
    idType: str = "SAID"
    email: str = ""
    phone: str = ""


class Delegates(Schema):
    blockRef: str
    delegates: list[Delegate]
    consent: bool = False


@router.post("/quotations/{ref}/delegates")
def add_delegates(request, ref: str, body: Delegates):
    """A corporate client's delegate list, registered against its per-group quotation."""
    from learners.registration import Person, register_delegates

    require(request, "learners", write=True, message="Delegates are registered by the enquiry handler or training manager.")
    enrolments, audit = register_delegates(
        request.user, ref, body.blockRef, [Person(d.names, d.email, d.phone, id_number=d.idNumber, id_type=d.idType) for d in body.delegates], body.consent,
        screen=request.headers.get("X-FSA-Screen", "quotes"))
    return ok({"enrolments": [e.reference for e in enrolments]}, audit=audit)


def _enquiry(ref):
    e = (Enquiry.objects.select_related("contact__organisation", "course", "assigned_to")
         .prefetch_related("enrolments", "quotations__course", "quotations__enrolments").filter(reference=ref, is_active=True).first())
    if not e:
        raise Refusal("not_found", [f"No enquiry {ref}."], "Not found.", status=404)
    return e


def enquiry_detail(request, e: Enquiry):
    from audit.models import AuditEntry

    d = enquiry_dict(e)
    registered = e.enrolments.exists()
    d.update({
        "notes": e.notes,
        "interest": e.course_interest,
        "ownerRef": e.assigned_to.reference if e.assigned_to_id else "",
        "receivedAt": stamp(e.received_at),
        "canEdit": request.user.can("demand", write=True),
        "courseLocked": registered,
        "kindLocked": registered,
        "forLocked": e.quotations.filter(is_active=True).exists(),
        "owners": [{"ref": a.reference, "name": a.display_name} for a in services.owner_options()],
        "history": [a.as_dict() for a in AuditEntry.objects.filter(entity_type="demand.enquiry", entity_ref=e.reference)[:20]]
                   if request.user.can_see_audit else [],
        "historyVisible": request.user.can_see_audit,
        "updatedAt": stamp(e.modified_at), "updatedBy": e.modified_by.display_name if e.modified_by_id else None,
    })
    return d


@router.get("/enquiries/{ref}")
def enquiry(request, ref: str):
    require(request, "demand")
    return ok(enquiry_detail(request, _enquiry(ref)))


class EnquiryEdit(Schema):
    topics: list[str] | None = None
    topicOther: str | None = None
    names: str | None = None
    organisation: str | None = None
    email: str | None = None
    phone: str | None = None
    channel: str | None = None
    kind: str | None = None
    courseCode: str | None = None
    interest: str | None = None
    ownerRef: str | None = None
    notes: str | None = None
    enquiringFor: str | None = None


@router.patch("/enquiries/{ref}")
def edit(request, ref: str, body: EnquiryEdit):
    """Correct an enquiry's details. The received time and the stage are not edited here."""
    require(request, "demand", write=True, message="Enquiries are corrected by the enquiry handler or training manager.")
    e = _enquiry(ref)
    changes = body.dict(exclude_none=True)
    audit = services.update_enquiry(request.user, e, changes, screen=request.headers.get("X-FSA-Screen", "enquiries"))
    return ok(enquiry_detail(request, _enquiry(ref)), audit=audit)


# --- clients and new quotations ------------------------------------------------------------

def _client_dict(o: Organisation):
    return {"ref": o.reference, "name": o.name, "sector": o.sector, "relationship": o.relationship,
            "contacts": [{"ref": c.reference, "names": c.names, "email": c.email, "phone": c.phone}
                         for c in o.contacts.filter(is_active=True).order_by("names")]}


@router.get("/clients")
def clients(request):
    """Companies a quotation can be addressed to (universities are partners, not quoted clients)."""
    require(request, "demand")
    rows = (Organisation.objects.filter(is_active=True).exclude(relationship__in=["University", "Partner"])
            .prefetch_related("contacts").order_by("name"))
    return ok([_client_dict(o) for o in rows])


class NewClient(Schema):
    name: str
    sector: str = ""
    contactNames: str = ""
    email: str = ""
    phone: str = ""


@router.post("/clients")
def add_client(request, body: NewClient):
    require(request, "demand", write=True)
    org, contact, audit = quotes.add_client(request.user, name=body.name, sector=body.sector, contact_names=body.contactNames,
                                            email=body.email, phone=body.phone, screen=request.headers.get("X-FSA-Screen", "quotes"))
    return ok({**_client_dict(org), "contactRef": contact.reference}, audit=audit)


class NewContact(Schema):
    names: str
    email: str = ""
    phone: str = ""


@router.post("/clients/{ref}/contacts")
def add_contact(request, ref: str, body: NewContact):
    require(request, "demand", write=True)
    org = Organisation.objects.filter(reference=ref, is_active=True).first()
    if org is None:
        raise Refusal("not_found", [f"No client {ref}."], "Not found.", status=404)
    contact, audit = quotes.add_contact(request.user, org, names=body.names, email=body.email, phone=body.phone,
                                        screen=request.headers.get("X-FSA-Screen", "quotes"))
    return ok({**_client_dict(org), "contactRef": contact.reference}, audit=audit)


class NewQuotation(Schema):
    organisationRef: str = ""
    contactRef: str = ""
    courseCode: str = ""
    basis: str = "PerGroup"
    learners: int | None = None
    value: str = ""
    enquiryRef: str = ""
    issue: bool = False


@router.post("/quotations")
def add_quotation(request, body: NewQuotation):
    require(request, "demand", write=True)
    screen = request.headers.get("X-FSA-Screen", "quotes")
    quote, audit = quotes.create_quotation(request.user, organisation_ref=body.organisationRef, contact_ref=body.contactRef,
                                           course_code=body.courseCode, basis=body.basis, learners=body.learners or 0,
                                           value=body.value, enquiry_ref=body.enquiryRef, screen=screen)
    if body.issue and not (quote.value_cents > QUOTE_APPROVAL_CENTS and not quote.approved_at):
        audit = quotes.issue(request.user, quote, screen=screen)
    return ok({"ref": quote.reference, "state": quote.state}, audit=audit)


def _quote(ref):
    q = Quotation.objects.filter(reference=ref, is_active=True).select_related("organisation", "contact").first()
    if q is None:
        raise Refusal("not_found", [f"No quotation {ref}."], "Not found.", status=404)
    return q


@router.post("/quotations/{ref}/approve")
def approve_quotation(request, ref: str):
    require(request, "demand")
    audit = quotes.approve(request.user, _quote(ref), screen=request.headers.get("X-FSA-Screen", "quotes"))
    return ok({"ref": ref}, audit=audit)


@router.post("/quotations/{ref}/issue")
def issue_quotation(request, ref: str):
    require(request, "demand", write=True)
    audit = quotes.issue(request.user, _quote(ref), screen=request.headers.get("X-FSA-Screen", "quotes"))
    return ok({"ref": ref}, audit=audit)


# --- accounts: corporate (companies) and public (individuals) ------------------------------

@router.get("/accounts/corporate")
def corporate_accounts(request):
    """Companies the Academy deals with: clients (their people have trained) and prospects (enquired
    or quoted only). Universities are partners and are listed under placements instead."""
    require(request, "demand")
    from django.db.models import Count, Max
    from django.db.models import Q as Qx

    from learners.models import Enrolment

    orgs = (Organisation.objects.filter(is_active=True).exclude(relationship__in=["University", "Partner"])
            .annotate(n_contacts=Count("contacts", filter=Qx(contacts__is_active=True), distinct=True),
                      n_enquiries=Count("contacts__enquiries", filter=Qx(contacts__enquiries__is_active=True,
                                                                         contacts__enquiries__enquiring_for="Company"), distinct=True),
                      last_enquiry=Max("contacts__enquiries__received_at"))
            .prefetch_related("contacts").order_by("name"))
    quotes = {}
    for q in Quotation.objects.filter(is_active=True, organisation__isnull=False).values("organisation_id", "state", "value_cents"):
        row = quotes.setdefault(q["organisation_id"], {"n": 0, "open": 0, "open_cents": 0})
        row["n"] += 1
        if q["state"] in ("Draft", "Issued"):
            row["open"] += 1
            row["open_cents"] += q["value_cents"]
    learners = dict(Enrolment.objects.filter(is_active=True, learner__organisation__isnull=False)
                    .values("learner__organisation_id").annotate(n=Count("learner", distinct=True))
                    .values_list("learner__organisation_id", "n"))
    rows = []
    for o in orgs:
        main = next((c for c in o.contacts.all() if c.is_active), None)
        qt = quotes.get(o.pk, {"n": 0, "open": 0, "open_cents": 0})
        rows.append({
            "ref": o.reference, "name": o.name, "sector": o.sector, "relationship": o.relationship,
            "contact": main.names if main else "", "contactEmail": main.email if main else "", "contactPhone": main.phone if main else "",
            "contacts": o.n_contacts, "enquiries": o.n_enquiries, "quotations": qt["n"], "openQuotes": qt["open"],
            "openValue": rand(qt["open_cents"]) if qt["open_cents"] else "", "learners": learners.get(o.pk, 0),
            "lastEnquiry": iso(clock.local_date(o.last_enquiry)) if o.last_enquiry else None,
        })
    return ok(rows, source="Organisations · enquiries · quotations · enrolments")


@router.get("/accounts/corporate/{ref}")
def corporate_account(request, ref: str):
    require(request, "demand")
    from learners.models import Learner

    o = Organisation.objects.filter(reference=ref, is_active=True).first()
    if o is None:
        raise Refusal("not_found", [f"No company {ref}."], "Not found.", status=404)
    enquiries = (Enquiry.objects.filter(is_active=True, contact__organisation=o).select_related("contact", "course")
                 .order_by("-received_at"))
    return ok({
        "ref": o.reference, "name": o.name, "sector": o.sector, "relationship": o.relationship,
        "contacts": [{"ref": c.reference, "names": c.names, "email": c.email, "phone": c.phone}
                     for c in o.contacts.filter(is_active=True).order_by("names")],
        "enquiries": [{"ref": e.reference, "received": iso(clock.local_date(e.received_at)), "who": e.contact.names,
                       "course": e.course.title if e.course_id else e.course_interest, "stage": e.stage, "kind": e.kind,
                       "for": e.enquiring_for} for e in enquiries],
        "quotations": [{"ref": q.reference, "course": q.course.title, "value": rand(q.value_cents), "state": q.state,
                        "learners": q.learner_count, "registered": q.enrolments.filter(is_active=True).count(),
                        "issued": iso(q.issued_on)}
                       for q in Quotation.objects.filter(is_active=True, organisation=o).select_related("course").order_by("-created_at")],
        "learners": [{"ref": l.reference, "name": l.names,
                      "enrolments": [f"{x.reference} · {x.course.title} · {x.stage}" for x in l.enrolments.all() if x.is_active]}
                     for l in Learner.objects.filter(is_active=True, organisation=o).prefetch_related("enrolments__course").order_by("names")],
    })


@router.get("/accounts/public")
def public_accounts(request):
    """Individuals: people who enquired for themselves, and public applicants who registered. A person
    may work at a company (shown as their employer) without being part of that company's account."""
    require(request, "demand")
    from learners.models import Learner

    rows, seen = [], set()
    individual = (Enquiry.objects.filter(is_active=True, kind="Enquiry", enquiring_for="Individual")
                  .select_related("contact__organisation", "course")
                  .prefetch_related("enrolments__learner", "enrolments__course", "quotations")
                  .order_by("-received_at"))
    for e in individual:
        enrolled = [x for x in e.enrolments.all() if x.is_active]
        learner = enrolled[0].learner if enrolled else None
        if learner:
            seen.add(learner.pk)
        rows.append({
            "key": e.reference, "name": e.contact.names, "employer": e.contact.organisation.name if e.contact.organisation_id else "",
            "email": e.contact.email, "phone": e.contact.phone, "since": iso(clock.local_date(e.received_at)),
            "enquiry": e.reference, "enquiryStage": e.stage, "course": e.course.title if e.course_id else e.course_interest,
            "learnerRef": learner.reference if learner else None,
            "enrolments": [f"{x.reference} · {x.course.title} · {x.stage}" for x in enrolled],
            "quotations": [f"{q.reference} · {rand(q.value_cents)} · {q.state}" for q in e.quotations.all() if q.is_active],
        })
    for l in (Learner.objects.filter(is_active=True, learner_type="Public").exclude(pk__in=seen)
              .select_related("organisation", "contact").prefetch_related("enrolments__course").order_by("-created_at")):
        rows.append({
            "key": l.reference, "name": l.names, "employer": l.organisation.name if l.organisation_id else "",
            "email": l.contact.email if l.contact_id else "", "phone": l.contact.phone if l.contact_id else "",
            "since": iso(clock.local_date(l.created_at)), "enquiry": None, "enquiryStage": None, "course": "",
            "learnerRef": l.reference, "quotations": [],
            "enrolments": [f"{x.reference} · {x.course.title} · {x.stage}" for x in l.enrolments.all() if x.is_active],
        })
    return ok(rows, source="Individual enquiries · public learners")


@router.get("/quotations/{ref}")
def quotation_detail(request, ref: str):
    """One quotation: who it is for, what was quoted, where it is in its life, the enquiry it answers
    and the people registered against it."""
    require(request, "demand")
    q = (Quotation.objects.filter(reference=ref, is_active=True)
         .select_related("organisation", "contact", "contact__organisation", "course", "enquiry", "assigned_to", "approved_by", "created_by")
         .prefetch_related("follow_ups").first())
    if q is None:
        raise Refusal("not_found", [f"No quotation {ref}."], "Not found.", status=404)
    enrolments = q.enrolments.filter(is_active=True).select_related("learner", "plan_block").order_by("reference")
    per_head = q.value_cents // q.learner_count if q.learner_count else 0
    over = q.value_cents > QUOTE_APPROVAL_CENTS
    return ok({
        "ref": q.reference, "state": q.state, "individual": q.organisation_id is None,
        "client": q.organisation.name if q.organisation_id else q.contact.names,
        "employer": q.contact.organisation.name if q.organisation_id is None and q.contact.organisation_id else "",
        "contact": {"names": q.contact.names, "email": q.contact.email, "phone": q.contact.phone},
        "course": q.course.title, "courseCode": q.course.code, "basis": "Per group" if q.basis == "PerGroup" else "Per learner",
        "learners": q.learner_count, "value": rand(q.value_cents), "perLearner": rand(per_head),
        "createdAt": stamp(q.created_at), "createdBy": q.created_by.display_name if q.created_by_id else None,
        "issued": iso(q.issued_on), "followUpDue": iso(q.follow_up_due),
        "owner": q.assigned_to.display_name if q.assigned_to_id else None,
        "approval": ("Approved by " + q.approved_by.display_name + " on " + stamp(q.approved_at)) if q.approved_at
                    else ("Needed: over R 50 000" if over else "Not needed: R 50 000 or less"),
        "enquiry": {"ref": q.enquiry.reference, "received": iso(clock.local_date(q.enquiry.received_at)), "stage": q.enquiry.stage}
                   if q.enquiry_id else None,
        "canEdit": q.state == "Draft" and request.user.hub_role == "TrainingManager",
        "canApprove": request.user.hub_role == "TrainingManager" and q.state == "Draft",
        "needsApproval": over and not q.approved_at, "valueRands": f"{q.value_cents / 100:.2f}", "basisCode": q.basis,
        "followUps": [{"at": stamp(f.at), "by": f.by.display_name if f.by_id else None, "note": f.note}
                      for f in q.follow_ups.select_related("by").order_by("at")],
        "delegates": [{"enrolment": e.reference, "learner": e.learner.names, "learnerRef": e.learner.reference,
                       "intake": e.plan_block.reference if e.plan_block_id else None,
                       "start": iso(e.plan_block.start_date) if e.plan_block_id else None, "stage": e.stage} for e in enrolments],
    })


class QuoteEdit(Schema):
    courseCode: str | None = None
    basis: str | None = None
    learners: int | None = None
    value: str | None = None
    approve: bool = False


@router.patch("/quotations/{ref}")
def edit_quotation(request, ref: str, body: QuoteEdit):
    """Edit a draft. The head of department can pass approve=true to approve it in the same step."""
    require(request, "demand", write=True)
    quote, audit = quotes.edit_draft(request.user, _quote(ref), course_code=body.courseCode, basis=body.basis,
                                     learners=body.learners, value=body.value, approve=body.approve,
                                     screen=request.headers.get("X-FSA-Screen", "quotes"))
    return ok({"ref": quote.reference, "state": quote.state}, audit=audit)
