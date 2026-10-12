from django.db.models import Count, Q
from ninja import Router

from assurance.models import ACC_STEPS, Accreditation, AccreditationProject, Library, Placement, Risk
from core import clock
from core.api_support import iso, ok, require

router = Router(tags=["assurance"])


@router.get("/depository")
def depository(request):
    require(request, "depository")
    libs = Library.objects.select_related("owner").annotate(
        held=Count("documents", filter=Q(documents__state="Held", documents__is_active=True)),
        outstanding=Count("documents", filter=Q(documents__state="Outstanding", documents__is_active=True)),
    )
    rows = [{
        "code": l.code, "name": l.name, "holds": l.holds, "count": l.held, "outstanding": l.outstanding,
        "retention": l.retention_rule, "owner": l.owner.display_name if l.owner_id else None,
        "position": f"{l.outstanding} outstanding" if l.outstanding else "Compliant",
        "tone": "bad" if l.outstanding else "ok",
    } for l in libs]
    outstanding = [{"ref": d.reference, "title": d.title, "library": d.library.name}
                   for lib in libs for d in lib.documents.filter(state="Outstanding", is_active=True)]
    return ok({"libraries": rows, "outstanding": outstanding}, source="Training depository")


@router.get("/accreditations")
def accreditations(request):
    require(request, "assurance")
    today = clock.today()
    held = [{"ref": a.reference, "body": a.body.name, "scope": a.scope, "expires": iso(a.expires_on),
             "tone": "bad" if (a.expires_on - today).days <= 90 else "ok",
             "position": f"Renewal due in {(a.expires_on - today).days} days" if (a.expires_on - today).days <= 90 else "Compliant"}
            for a in Accreditation.objects.filter(is_active=True).select_related("body")]
    projects = [{"ref": p.reference, "body": p.body.name, "scope": p.scope, "owner": p.owner.display_name,
                 "target": iso(p.target_date), "step": p.step_index, "steps": ACC_STEPS}
                for p in AccreditationProject.objects.filter(is_active=True).select_related("body", "owner")]
    return ok({"held": held, "projects": projects}, source="Accreditation register")


@router.get("/partnerships")
def partnerships(request):
    require(request, "assurance")
    today = clock.today()
    rows = []
    for p in Placement.objects.filter(is_active=True).select_related("organisation"):
        days = (today - p.period_end).days
        if p.report_submitted_at:
            position, tone = f"Submitted {p.report_submitted_at:%Y-%m-%d}", "ok"
        elif days > 20:
            position, tone = f"Finding — {days} days after period end", "bad"
        elif days >= 15:
            position, tone = f"Observation — day {days} of 20", "warn"
        elif days >= 0:
            position, tone = f"Day {days} of 20", "info"
        else:
            position, tone = "Placement in progress", "na"
        rows.append({"ref": p.reference, "university": p.organisation.name, "cohort": p.cohort_label,
                     "size": p.cohort_size, "periodEnd": iso(p.period_end), "reportDue": iso(p.report_due),
                     "position": position, "tone": tone})
    return ok(rows, source="University and WIL register")


@router.get("/risks")
def risks(request):
    require(request, "assurance")
    rows = [{"ref": r.reference, "risk": r.risk, "cause": r.cause, "rating": r.rating, "trigger": r.escalation_trigger,
             "breached": r.trigger_breached_at is not None, "owner": r.owner.display_name, "position": r.position,
             "tone": "bad" if r.rating == "High" or r.trigger_breached_at else ("warn" if r.rating == "Medium" else "ok")}
            for r in Risk.objects.filter(is_active=True).select_related("owner")]
    return ok(rows, source="Risk and escalation register")
