from ninja import Router, Schema

from core import clock
from core.api_support import Refusal, iso, ok, require
from courses.models import Course
from demand import services
from demand.models import ENQ_STAGES, Enquiry, Organisation, Quotation
from oversight.rules import rand

router = Router(tags=["demand"])


def enquiry_dict(e: Enquiry):
    days = clock.working_days_since(e.received_at)
    stale = e.kind == "Enquiry" and e.first_response_at is None and days > 2
    return {
        "ref": e.reference,
        "name": e.contact.names,
        "org": e.contact.organisation.name if e.contact.organisation_id else "",
        "course": e.course.title if e.course_id else e.course_interest,
        "courseCode": e.course.code if e.course_id else "",
        "email": e.contact.email, "phone": e.contact.phone,
        "enrolment": next((x.reference for x in e.enrolments.all()), None),
        "kind": e.kind,
        "channel": e.channel,
        "receivedAt": iso(e.received_at),
        "workingDaysOpen": days,
        "stageIndex": e.stage_index,
        "stage": e.stage,
        "owner": e.assigned_to.display_name if e.assigned_to_id else None,
        "tone": "bad" if stale or not e.assigned_to_id else ("na" if e.stage_index >= 3 else "info"),
        "stale": stale,
        "resolved": e.resolved_at is not None,
    }


@router.get("/enquiries")
def enquiries(request):
    require(request, "demand")
    rows = Enquiry.objects.filter(is_active=True).select_related("contact__organisation", "course", "assigned_to").prefetch_related("enrolments")
    items = [enquiry_dict(e) for e in rows]
    month = clock.today().replace(day=1)
    this_month = [e for e in rows if clock.local_date(e.received_at) >= month]
    responded = [e for e in rows if e.first_response_at and e.kind == "Enquiry"]
    avg = (sum(clock.working_days_since(e.received_at) - clock.working_days_since(e.first_response_at) for e in responded)
           / len(responded)) if responded else 0
    registered = sum(1 for e in rows if e.stage_index == 3)
    closed = sum(1 for e in rows if e.stage_index in (3, 4))
    return ok({
        "stages": ENQ_STAGES,
        "items": items,
        "stats": [
            {"v": str(len(this_month)), "l": "Received this month", "c": "All channels"},
            {"v": str(sum(1 for i in items if i["stale"])), "l": "Over two days", "c": "Against the two-working-day standard"},
            {"v": f"{round(100 * registered / closed) if closed else 0}%", "l": "Conversion", "c": "Registered of closed enquiries"},
            {"v": f"{avg:.1f}".replace(".", ","), "l": "Days to respond", "c": "Average, working days"},
        ],
    }, source="Enquiry register · contacts and accounts")


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
    channel: str
    kind: str = "Enquiry"
    courseCode: str = ""
    interest: str = ""


@router.post("/enquiries")
def create(request, body: NewEnquiry):
    require(request, "demand", write=True)
    reasons = []
    if not body.names.strip():
        reasons.append("Name the enquirer.")
    if body.channel not in ("Phone", "Email", "WhatsApp", "DirectLine"):
        reasons.append("Choose the channel it arrived on: phone, email, WhatsApp or direct line.")
    if body.kind not in ("Enquiry", "Complaint", "Opportunity"):
        reasons.append("Choose enquiry, complaint or opportunity.")
    course = Course.objects.filter(code=body.courseCode).first() if body.courseCode else None
    if not course and not body.interest.strip():
        reasons.append("Choose a course or describe what they asked about.")
    if reasons:
        raise Refusal("invalid", reasons, "The enquiry cannot be logged yet.", status=422)
    org = None
    if body.organisation.strip():
        org = Organisation.objects.filter(name__iexact=body.organisation.strip()).first() or Organisation.objects.create(
            name=body.organisation.strip(), created_by=request.user)
    enquiry, audit = services.log_enquiry(request.user, body.names.strip(), org, body.channel, body.kind, course,
                                          body.interest.strip(), screen=request.headers.get("X-FSA-Screen", "enquiries"))
    enquiry = Enquiry.objects.select_related("contact__organisation", "course", "assigned_to").get(pk=enquiry.pk)
    return ok(enquiry_dict(enquiry), audit=audit)


@router.get("/quotations")
def quotations(request):
    require(request, "demand")
    today = clock.today()
    rows = []
    for q in Quotation.objects.filter(is_active=True).select_related("organisation", "contact", "course", "assigned_to").prefetch_related("follow_ups"):
        overdue = q.state == "Issued" and not q.follow_ups.exists() and q.follow_up_due and q.follow_up_due < today
        over = q.value_cents > 50_000_00 and not q.approved_at
        registered = q.enrolments.filter(is_active=True).count()
        rows.append({
            "registered": registered, "learners": q.learner_count, "courseCode": q.course.code,
            "canAddDelegates": q.basis == "PerGroup" and q.state in ("Issued", "Accepted") and registered < q.learner_count,
            "ref": q.reference, "client": q.organisation.name if q.organisation_id else q.contact.names,
            "course": q.course.title, "basis": "Per group" if q.basis == "PerGroup" else "Per learner",
            "value": rand(q.value_cents), "issued": iso(q.issued_on), "followUpDue": iso(q.follow_up_due),
            "owner": q.assigned_to.display_name if q.assigned_to_id else None,
            "status": "Approval needed" if over else ("Follow-up overdue" if overdue else q.state),
            "tone": "warn" if over or overdue else ("ok" if q.state == "Accepted" else "info"),
        })
    return ok(rows, source="Quotation register")


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
