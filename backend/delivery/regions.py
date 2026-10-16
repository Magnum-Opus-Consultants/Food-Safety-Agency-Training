"""Where facilitators deliver, and whether every region is covered.

Each facilitator is assigned one or more regions: South Africa's provinces, and Online for intakes
delivered on Teams. An intake's region is its venue's province (or Online). Planning prefers a
facilitator who covers the intake's region; one from elsewhere is a warning, never a block, because a
facilitator may travel. A region with one facilitator is a risk (KZN): if that person is absent or not
keeping up, delivery there stops.
"""

import datetime as dt

from django.db import transaction

from audit.services import record
from core import clock
from core.api_support import Refusal

PROVINCES = ["Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo", "Mpumalanga", "North West", "Northern Cape",
             "Western Cape"]
ONLINE = "Online"
REGIONS = PROVINCES + [ONLINE]


def region_of(venue) -> str | None:
    if venue is None:
        return None
    if venue.is_online:
        return ONLINE
    return venue.province or None


def out_of_region(block) -> str | None:
    """Why the intake's facilitator does not cover its region, or None."""
    region = region_of(block.venue)
    fac = block.facilitator
    if region is None or region in (fac.regions or []):
        return None
    if not fac.regions:
        return f"{fac.display_name} has no regions assigned; {block.reference} is delivered in {region}."
    return (f"{fac.display_name} covers {', '.join(fac.regions)}, not {region}, where {block.reference} is delivered. "
            "Confirm the travel, or give the intake to a facilitator in the region.")


def facilitators():
    from delivery.planning import facilitator_options

    return list(facilitator_options().prefetch_related("registrations"))


def cover(on: dt.date | None = None, horizon_days: int = 120) -> list[dict]:
    """Per region: the facilitators who cover it (and can deliver: registration current, not suspended),
    the intakes coming up there, and how many of those are run from outside the region."""
    from delivery.models import PlanBlock

    on = on or clock.today()
    people = facilitators()
    blocks = list(PlanBlock.objects.filter(is_active=True, end_date__gte=on, start_date__lte=on + dt.timedelta(days=horizon_days))
                  .exclude(state="Cancelled").select_related("venue", "facilitator", "course"))
    rows = []
    for region in REGIONS:
        covering = [a for a in people if region in (a.regions or [])]
        able = [a for a in covering if a.state != "Suspended" and (r := a.current_registration()) and r.expires_on >= on]
        here = [b for b in blocks if region_of(b.venue) == region]
        imported = [b for b in here if region not in (b.facilitator.regions or [])]
        if not able and here:
            position, tone = "No facilitator covers this region", "bad"
        elif not able:
            position, tone = "No cover", "na"
        elif len(able) == 1:
            position, tone = f"Single cover — {able[0].display_name} only", "warn"
        else:
            position, tone = "In order", "ok"
        rows.append({"region": region, "facilitators": [{"ref": a.reference, "name": a.display_name, "able": a in able} for a in covering],
                     "intakes": [{"ref": b.reference, "course": b.course.title, "start": b.start_date.isoformat(),
                                  "facilitator": b.facilitator.display_name, "fromOutside": b in imported} for b in here],
                     "position": position, "tone": tone})
    return rows


@transaction.atomic
def set_regions(actor, account, regions: list[str], screen="facilitators"):
    if not actor.can("delivery", write=True) or actor.scope("delivery") == "own":
        raise Refusal("forbidden", ["Regions are assigned by the training manager."], "Not permitted.", status=403)
    unknown = [r for r in regions if r not in REGIONS]
    if unknown:
        raise Refusal("invalid", [f"{', '.join(unknown)} is not a region."], "Check the regions.", status=422)
    chosen = [r for r in REGIONS if r in regions]  # one of each, in the standard order
    before = list(account.regions or [])
    if chosen == before:
        raise Refusal("nothing_to_change", ["Those are already the regions."], "Nothing to change.")
    account.regions = chosen
    account.save(update_fields=["regions"])
    return record(actor, f"{account.display_name} regions set to {', '.join(chosen) or 'none'}", account, screen=screen,
                  before={"regions": before}, after={"regions": chosen})
