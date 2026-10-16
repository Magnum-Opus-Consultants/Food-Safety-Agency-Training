from ninja import Router

from core import clock
from core.api_support import Refusal, ok, require
from oversight import rules
from oversight.models import Rotation

router = Router(tags=["oversight"])


@router.get("/nav-counts")
def nav_counts(request):
    """One endpoint, computed from the registers on every call. Never cached, never stored.
    Each account gets only the counts it attends to."""
    return ok(rules.nav_counts(account=request.user), today=clock.today().isoformat(), clockMoved=clock.is_moved())


@router.get("/training/home")
def home(request):
    require(request, "overview")
    today = clock.today()
    me = request.user
    return ok({"hero": rules.hero(today, me), "attention": rules.attention(today, me), "week": rules.week_strip(today, me)},
              today=today.isoformat())


@router.get("/desk")
def desk(request):
    require(request, "overview")
    if not request.user.can_see_desk:
        raise Refusal("forbidden", ["The head of department desk is for the head of department (the training manager) and directors."],
                      "This desk is not part of your role.", status=403)
    today = clock.today()
    escalated = rules.escalated(today)
    running = rules.running_without(today)
    on_rotation = [
        {"area": label, "member": (m.display_name if (m := Rotation.on_duty(code, today)) else None)}
        for code, label in Rotation._meta.get_field("function_area").choices
    ]
    return ok({
        "escalated": escalated,
        "running": running,
        "runningTotal": sum(r["n"] for r in running),
        "triggers": rules.TRIGGERS,
        "channelRule": rules.CHANNEL_RULE,
        "rotation": on_rotation,
    }, today=today.isoformat())


@router.get("/dashboard")
def dashboard(request, months: int = 12, course: str = ""):
    """The management dashboard, read from the registers on every call."""
    from oversight import dashboard as board

    require(request, "reporting", message="The management dashboard is for the training manager and the GMs.")
    if months not in (3, 6, 12, 24):
        raise Refusal("invalid", ["Choose 3, 6, 12 or 24 months."], "Check the period.", status=422)
    return ok(board.build(months, course), source="Enquiries · quotations · enrolments · results · moderation · certificates · registers")
