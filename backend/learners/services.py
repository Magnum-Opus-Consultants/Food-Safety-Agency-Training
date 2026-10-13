import secrets
from decimal import Decimal

from django.db import transaction

from assurance.models import Document, Library
from audit.services import record
from core import clock
from core.api_support import Refusal
from core.models import next_ref
from learners.models import ENR_STAGES, Certificate, Moderation
from learners.rules import advance_blockers, certificate_blockers


@transaction.atomic
def moderate(actor, result, outcome: str | None = None, notes: str = "", screen="results"):
    if hasattr(result, "moderation"):
        raise Refusal("already_moderated", [f"{result.reference} was moderated on "
                                            f"{result.moderation.moderated_at:%Y-%m-%d}."], "Nothing to moderate.")
    outcome = outcome or result.outcome
    Moderation.objects.create(result=result, moderated_by=actor, moderated_at=clock.now(), outcome=outcome, notes=notes)
    label = "competent" if outcome == "Competent" else "not yet competent"
    return record(actor, f"{result.reference} moderation recorded — {label}", result, screen=screen,
                  after={"outcome": outcome})


@transaction.atomic
def issue_certificate(actor, result, screen="certificates"):
    """Rule 4. The API refuses; the database trigger refuses again if a code path ever skips this."""
    reasons = certificate_blockers(result)
    if reasons:
        error = "not_moderated" if not hasattr(result, "moderation") else "not_issuable"
        raise Refusal(error, reasons, f"A certificate cannot be issued for {result.reference}.")
    reference = next_ref(f"CERT-{clock.today().year}")
    library = Library.objects.get(code="certificates")
    # PDF rendering (WeasyPrint, in the worker) is the next build step; the depository entry is filed now.
    document = Document.objects.create(
        library=library, title=f"Certificate {reference} — {result.enrolment.learner.names}",
        entity_type="learners.certificate", entity_ref=reference,
        storage_key=f"certificates/{clock.today().year}/{reference}.pdf", state="Held", created_by=actor,
    )
    cert = Certificate.objects.create(
        reference=reference, moderation=result.moderation, issued_at=clock.now(), issued_by=actor,
        verification_code=secrets.token_hex(8), document=document,
    )
    audit = record(actor, f"{reference} issued for {result.reference} and filed to the depository", result,
                   screen=screen, after={"certificate": reference})
    return cert, audit


@transaction.atomic
def advance_enrolment(actor, enrolment, screen="enrolments"):
    """Rules 1 and 2: the gate blocks the stage and says what is outstanding."""
    reasons = advance_blockers(enrolment)
    if reasons:
        raise Refusal("gate_incomplete", reasons, "This enrolment cannot advance until its minimum prerequisites are met.")
    before = enrolment.stage
    enrolment.stage_index += 1
    enrolment.modified_by = actor
    enrolment.save()
    return record(actor, f"{enrolment.reference} advanced from {before.lower()} to {enrolment.stage.lower()}",
                  enrolment, screen=screen, before={"stage": before}, after={"stage": enrolment.stage})


@transaction.atomic
def update_gate(actor, enrolment, prerequisite_result=None, grade10_evidence_held=None, screen="enrolments"):
    if enrolment.stage_index > 0:
        raise Refusal("gate_closed", ["The minimum prerequisites were verified at an earlier stage and can no longer change."],
                      "The minimum prerequisites can only be changed while the enrolment is at its first stage, Registered.")
    changes = []
    before = {"prerequisiteResult": str(enrolment.prerequisite_result) if enrolment.prerequisite_result is not None else None,
              "grade10EvidenceHeld": enrolment.grade10_evidence_held}
    if prerequisite_result is not None:
        enrolment.prerequisite_result = Decimal(str(prerequisite_result))
        changes.append(f"prerequisite result {prerequisite_result:g}%")
    if grade10_evidence_held:
        raise Refusal("upload_required", ["Upload the Grade 10 document (PDF, JPG or PNG); the file is the evidence, not a tick."],
                      "Grade 10 evidence is an uploaded document.", status=422)
    if not changes:
        raise Refusal("nothing_to_change", ["Send a prerequisite result or the Grade 10 evidence state."], "No change.")
    enrolment.modified_by = actor
    enrolment.save()
    return record(actor, f"{enrolment.reference} minimum prerequisites updated — {', '.join(changes)}", enrolment, screen=screen,
                  before=before)


STAGE_NAMES = ENR_STAGES
