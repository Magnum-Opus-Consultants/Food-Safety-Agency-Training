from ninja import Router

from core import clock
from core.api_support import ok, require
from oversight import rules
from oversight.models import Rotation

router = Router(tags=["oversight"])


@router.get("/nav-counts")
def nav_counts(request):
    """One endpoint, computed from the registers on every call. Never cached, never stored."""
    return ok(rules.nav_counts(), today=clock.today().isoformat())


@router.get("/training/home")
def home(request):
    require(request, "overview")
    today = clock.today()
    return ok({"hero": rules.hero(today), "attention": rules.attention(today), "week": rules.week_strip(today)},
              today=today.isoformat())


@router.get("/desk")
def desk(request):
    require(request, "overview")
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
