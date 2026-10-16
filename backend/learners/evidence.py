"""Grade 10 evidence: the uploaded document behind the second minimum prerequisite.

The file is kept in the private file store and recorded as a Document in the evidence library, linked
to the enrolment. Holding a current file is what makes `grade10_evidence_held` true; removing the file
deletes it and makes the flag false again. Both are audited. The gate only changes while the
enrolment is at its first stage, Registered, so evidence cannot be swapped once the gate has been verified.
"""

import hashlib
from pathlib import Path

from django.conf import settings
from django.db import transaction

from assurance.models import Document, Library
from audit.services import record
from core import clock
from core.api_support import Refusal

ENTITY_TYPE = "learners.enrolment.grade10"
TEST_TYPE = "learners.enrolment.prereqtest"  # the marked prerequisite test, filed with the result captured from it
KINDS = [  # (magic bytes, extension, media type)
    (b"%PDF-", "pdf", "application/pdf"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
]
MEDIA_TYPE = {ext: media for _, ext, media in KINDS}


def current(enrolment) -> Document | None:
    return Document.objects.filter(is_active=True, entity_type=ENTITY_TYPE, entity_ref=enrolment.reference).first()


def current_test(enrolment) -> Document | None:
    return Document.objects.filter(is_active=True, entity_type=TEST_TYPE, entity_ref=enrolment.reference).first()


@transaction.atomic
def capture_test(actor, enrolment, result, filename: str, content: bytes, screen="enrolments"):
    """A new prerequisite test result, with the marked test it was read from. Both, together."""
    from decimal import Decimal, InvalidOperation

    _gate_open(enrolment)
    reasons = []
    try:
        value = Decimal(str(result))
        if not 0 <= value <= 100:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        value = None
        reasons.append("Give the result as a percentage from 0 to 100.")
    if not content:
        reasons.append("Upload the marked test the result comes from.")
    elif len(content) > settings.FSA_UPLOAD_MAX_BYTES:
        reasons.append("The file is larger than 5 MB.")
    elif _sniff(content[:8]) is None:
        reasons.append("Upload the test as a PDF, or a photo or scan as JPG or PNG.")
    if reasons:
        raise Refusal("invalid", reasons, "The result cannot be saved yet.", status=422)
    ext = _sniff(content[:8])
    digest = hashlib.sha256(content).hexdigest()
    key = f"evidence/prerequisite-tests/{enrolment.reference}-{digest[:12]}.{ext}"
    target = Path(settings.FSA_FILE_ROOT) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    replaced = current_test(enrolment)
    if replaced:  # the earlier test stays in the archive with the earlier result in the audit trail
        replaced.is_active, replaced.state, replaced.modified_by = False, "Archived", actor
        replaced.save()
    name = Path(filename or f"test.{ext}").name[:120]
    doc = Document.objects.create(
        library=Library.objects.get(code="evidence"), title=f"Prerequisite test — {enrolment.learner.names} · {name}",
        entity_type=TEST_TYPE, entity_ref=enrolment.reference, storage_key=key, sha256=digest, state="Held",
        created_by=actor, modified_by=actor,
    )
    from learners.models import PrerequisiteAttempt

    before = str(enrolment.prerequisite_result) if enrolment.prerequisite_result is not None else None
    if before is not None and not enrolment.prerequisite_attempts.exists():
        # A result captured before attempts were kept becomes the first attempt, without a file.
        PrerequisiteAttempt.objects.create(enrolment=enrolment, result=enrolment.prerequisite_result, created_by=enrolment.modified_by)
    attempt = PrerequisiteAttempt.objects.create(enrolment=enrolment, result=value, document=doc, created_by=actor, modified_by=actor)
    enrolment.prerequisite_result = value
    enrolment.modified_by = actor
    enrolment.save()
    n = enrolment.prerequisite_attempts.filter(id__lte=attempt.id).count()
    return record(actor, f"{enrolment.reference} prerequisite test attempt {n}: {value.normalize():f}% captured — {name} ({doc.reference})",
                  enrolment, screen=screen, before={"prerequisiteResult": before}, after={"prerequisiteResult": str(value), "document": doc.reference})


def path_of(doc: Document) -> Path:
    return Path(settings.FSA_FILE_ROOT) / doc.storage_key


def _gate_open(enrolment):
    if enrolment.stage_index > 0:
        raise Refusal("gate_closed", ["The minimum prerequisites were verified at an earlier stage and can no longer change."],
                      "The Grade 10 evidence can only be changed while the enrolment is at its first stage, Registered.")


def _sniff(head: bytes):
    for magic, ext, _ in KINDS:
        if head.startswith(magic):
            return ext
    return None


@transaction.atomic
def attach(actor, enrolment, filename: str, content: bytes, screen="enrolments"):
    _gate_open(enrolment)
    if not content:
        raise Refusal("invalid", ["The file is empty."], "Choose the Grade 10 document.", status=422)
    if len(content) > settings.FSA_UPLOAD_MAX_BYTES:
        raise Refusal("invalid", [f"The file is {len(content) / 1048576:.1f} MB; the limit is "
                                  f"{settings.FSA_UPLOAD_MAX_BYTES // 1048576} MB."], "The file is too large.", status=422)
    ext = _sniff(content[:8])
    if ext is None:
        raise Refusal("invalid", ["Upload a PDF, or a photo or scan as JPG or PNG."], "That file type is not accepted.", status=422)

    digest = hashlib.sha256(content).hexdigest()
    key = f"evidence/grade10/{enrolment.reference}-{digest[:12]}.{ext}"
    target = Path(settings.FSA_FILE_ROOT) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)

    replaced = current(enrolment)
    if replaced:
        _discard(replaced, actor)
    name = Path(filename or f"grade10.{ext}").name[:120]
    doc = Document.objects.create(
        library=Library.objects.get(code="evidence"), title=f"Grade 10 evidence — {enrolment.learner.names} · {name}",
        entity_type=ENTITY_TYPE, entity_ref=enrolment.reference, storage_key=key, sha256=digest, state="Held",
        created_by=actor, modified_by=actor,
    )
    enrolment.grade10_evidence_held = True
    enrolment.modified_by = actor
    enrolment.save()
    verb = "replaced" if replaced else "uploaded"
    return doc, record(actor, f"{enrolment.reference} Grade 10 evidence {verb} — {name} ({doc.reference})", enrolment,
                       screen=screen, after={"document": doc.reference, "sha256": digest})


def _discard(doc: Document, actor):
    file = path_of(doc)
    doc.is_active = False
    doc.state = "Archived"
    doc.archive_ref = f"deleted {clock.now().isoformat(timespec='seconds')}"
    doc.modified_by = actor
    doc.save()
    # Delete the bytes only once the transaction has committed, so a rollback never loses a file.
    transaction.on_commit(lambda: file.unlink(missing_ok=True))


@transaction.atomic
def remove(actor, enrolment, screen="enrolments"):
    _gate_open(enrolment)
    doc = current(enrolment)
    if doc is None and not enrolment.grade10_evidence_held:
        raise Refusal("nothing_to_change", ["No Grade 10 evidence is on file for this enrolment."], "Nothing to remove.")
    if doc:
        _discard(doc, actor)
    enrolment.grade10_evidence_held = False
    enrolment.modified_by = actor
    enrolment.save()
    what = f"{enrolment.reference} Grade 10 evidence removed" + (f" — {doc.reference} deleted" if doc else "")
    return record(actor, what, enrolment, screen=screen, before={"document": doc.reference if doc else None})
