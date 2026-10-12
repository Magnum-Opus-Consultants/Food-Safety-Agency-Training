from ninja import Router

from core.api_support import ok, require
from courses.models import Course

router = Router(tags=["courses"])


@router.get("/courses")
def courses(request):
    require(request, "courses")
    rows = [{
        "code": c.code, "title": c.title, "service": c.service.name, "stream": c.stream.name,
        "streamColour": c.stream.colour, "days": c.duration_days, "mode": c.delivery_mode,
        "entryRequirement": c.entry_requirement, "gated": c.entry_gate == "PrerequisiteAndGrade10",
        "accredited": c.is_accredited, "body": c.accreditation_body.name if c.accreditation_body_id else None,
    } for c in Course.objects.filter(is_active=True).select_related("service", "stream", "accreditation_body")]
    return ok(rows, source="Course catalogue")
