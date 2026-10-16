"""Assessment and moderation.

The assessor captures a learner's result (mark and outcome) with the marked assessment uploaded as
evidence. A different person then moderates it from that evidence: agreeing, or changing the outcome
with a reason. A learner moderated not yet competent gets a remediation plan and a re-assessment
date; the re-assessment is a new result, moderated in turn, and the first stays on record."""

import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.db import transaction

from assurance.models import Document, Library
from audit.services import record
from core import clock
from core.api_support import Refusal
from learners.evidence import MEDIA_TYPE, _sniff
from learners.models import Enrolment, Moderation, Result

EVIDENCE = "learners.result"
OUTCOMES = {"Competent": "competent", "NotYetCompetent": "not yet competent"}


def evidence(result) -> Document | None:
    return Document.objects.filter(is_active=True, entity_type=EVIDENCE, entity_ref=result.reference).first()


def evidence_path(doc) -> Path:
    return Path(settings.FSA_FILE_ROOT) / doc.storage_key


def media_type(doc) -> str:
    return MEDIA_TYPE[doc.storage_key.rsplit(".", 1)[-1]]


def attendance(enrolment) -> dict | None:
    """Sessions attended out of those with a captured register, for the learner's intake."""
    from delivery.services import effective_attendance

    if not enrolment.plan_block_id:
        return None
    sessions = [s for s in enrolment.plan_block.sessions.filter(is_active=True) if hasattr(s, "register")]
    if not sessions:
        return None
    present = sum(1 for s in sessions if (a := effective_attendance(s).get(enrolment.learner_id)) and a.present)
    return {"present": present, "of": len(sessions), "percent": round(100 * present / len(sessions))}


def assessable(actor):
    """Enrolments this person may capture a result for: confirmed onto an intake (their own, for a facilitator)."""
    qs = Enrolment.objects.filter(is_active=True, stage_index__gte=1, plan_block__isnull=False).select_related(
        "learner", "course", "plan_block")
    if actor.scope("results") == "own":
        qs = qs.filter(plan_block__facilitator=actor)
    return qs


def _store(actor, result, filename, content):
    if not content:
        raise Refusal("invalid", ["Upload the marked assessment."], "The assessment is required.", status=422)
    if len(content) > settings.FSA_UPLOAD_MAX_BYTES:
        raise Refusal("invalid", ["The file is larger than 5 MB."], "The file is too large.", status=422)
    ext = _sniff(content[:8])
    if ext is None:
        raise Refusal("invalid", ["Upload the assessment as a PDF, or a photo or scan as JPG or PNG."], "That file type is not accepted.",
                      status=422)
    digest = hashlib.sha256(content).hexdigest()
    key = f"evidence/assessments/{result.reference}-{digest[:12]}.{ext}"
    target = Path(settings.FSA_FILE_ROOT) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    old = evidence(result)
    if old:
        old.is_active, old.state, old.modified_by = False, "Archived", actor
        old.save()
    name = Path(filename or f"assessment.{ext}").name[:120]
    return Document.objects.create(library=Library.objects.get(code="evidence"),
                                   title=f"Assessment — {result.enrolment.learner.names}, {result.reference} · {name}",
                                   entity_type=EVIDENCE, entity_ref=result.reference, storage_key=key, sha256=digest, state="Held",
                                   created_by=actor, modified_by=actor)


@transaction.atomic
def capture(actor, *, enrolment_ref, mark, outcome, notes, filename, content, screen="results"):
    enrolment = assessable(actor).filter(reference=enrolment_ref).first()
    if enrolment is None:
        raise Refusal("not_assessable", [f"{enrolment_ref} is not a confirmed learner on one of your intakes."], "Choose a learner to assess.",
                      status=422)
    if enrolment.plan_block.start_date > clock.today():
        raise Refusal("not_started", [f"{enrolment.plan_block.reference} starts on {enrolment.plan_block.start_date.isoformat()}."],
                      "Learners are assessed once their intake has started.")
    reasons = []
    try:
        value = Decimal(str(mark))
        if not 0 <= value <= 100:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        reasons.append("Give the mark as a percentage from 0 to 100.")
        value = None
    if outcome not in OUTCOMES:
        reasons.append("Choose the outcome: competent or not yet competent.")
    if reasons:
        raise Refusal("invalid", reasons, "The result cannot be saved yet.", status=422)
    previous = enrolment.results.filter(is_active=True).select_related("moderation").order_by("-assessed_at", "-id").first()
    reassessing = None
    if previous is not None:
        m = getattr(previous, "moderation", None)
        if m is None:
            raise Refusal("awaiting_moderation", [f"{previous.reference} for {enrolment.learner.names} is still awaiting moderation."],
                          "Moderate the first result before capturing another.")
        if m.outcome == "Competent":
            raise Refusal("already_competent", [f"{enrolment.learner.names} was moderated competent on {previous.reference}."],
                          "Nothing to re-assess.")
        reassessing = previous
    session = enrolment.plan_block.sessions.filter(is_active=True).order_by("-day", "-id").first()
    result = Result.objects.create(enrolment=enrolment, session=session, assessed_by=actor, assessed_at=clock.now(), mark=value,
                                   outcome=outcome, remediation_plan="", created_by=actor, modified_by=actor)
    doc = _store(actor, result, filename, content)
    if enrolment.stage_index < 2:
        enrolment.stage_index, enrolment.modified_by = 2, actor  # assessed: in training
        enrolment.save(update_fields=["stage_index", "modified_by", "modified_at"])
    what = (f"{result.reference} captured for {enrolment.learner.names} — {value.normalize():f}%, {OUTCOMES[outcome]}"
            + (f"; re-assessment after {reassessing.reference}" if reassessing else "") + f"; assessment uploaded ({doc.reference})"
            + (f"; {notes.strip()}" if (notes or "").strip() else ""))
    return result, record(actor, what[:400], result, screen=screen)


@transaction.atomic
def replace_evidence(actor, result, filename, content, screen="results"):
    if hasattr(result, "moderation"):
        raise Refusal("moderated", [f"{result.reference} has been moderated; its evidence is fixed."], "Evidence is fixed.")
    if result.assessed_by_id != actor.pk and not actor.can("moderation", write=True):
        raise Refusal("forbidden", ["Only the assessor replaces the assessment."], "Not permitted.", status=403)
    doc = _store(actor, result, filename, content)
    return record(actor, f"{result.reference} assessment replaced ({doc.reference})", result, screen=screen)


@transaction.atomic
def moderate(actor, result, *, outcome=None, notes="", remediation="", reassess_by=None, screen="results"):
    """Agree with the assessor, or change the outcome with a reason. Not yet competent needs a
    remediation plan and a re-assessment date. Nobody moderates their own assessment."""
    if hasattr(result, "moderation"):
        raise Refusal("already_moderated", [f"{result.reference} was moderated on {result.moderation.moderated_at:%Y-%m-%d}."],
                      "Nothing to moderate.")
    if result.assessed_by_id == actor.pk:
        raise Refusal("own_assessment", [f"You assessed {result.reference}; another person moderates it."], "Not your own work.", status=403)
    final = outcome or result.outcome
    reasons = []
    if final not in OUTCOMES:
        reasons.append("The outcome is competent or not yet competent.")
    changed = final != result.outcome
    if changed and not (notes or "").strip():
        reasons.append(f"Give the reason for changing the outcome from {OUTCOMES[result.outcome]} to {OUTCOMES.get(final, final)}.")
    needs_plan = final == "NotYetCompetent" and not result.remediation_plan
    if needs_plan and not (remediation or "").strip():
        reasons.append("Record the remediation plan for the learner.")
    if final == "NotYetCompetent" and reassess_by is None and not result.remediation_plan:
        reasons.append("Give the re-assessment date.")
    if reasons:
        raise Refusal("invalid", reasons, "The moderation cannot be recorded yet.", status=422)
    if final == "NotYetCompetent" and (remediation or "").strip():
        result.remediation_plan = remediation.strip() + (f" Re-assessment by {reassess_by.isoformat()}." if reassess_by else "")
        result.save(update_fields=["remediation_plan"])
    Moderation.objects.create(result=result, moderated_by=actor, moderated_at=clock.now(), outcome=final, notes=(notes or "").strip())
    verdict = (f"outcome changed from {OUTCOMES[result.outcome]} to {OUTCOMES[final]} — {notes.strip()}" if changed
               else f"agreed: {OUTCOMES[final]}" + (f" — {notes.strip()}" if (notes or "").strip() else ""))
    if final == "NotYetCompetent" and reassess_by:
        verdict += f"; re-assessment by {reassess_by.isoformat()}"
    return record(actor, f"{result.reference} moderation recorded — {verdict}"[:400], result, screen=screen,
                  before={"outcome": result.outcome}, after={"outcome": final})
