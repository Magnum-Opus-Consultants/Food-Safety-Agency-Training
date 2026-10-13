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
KINDS = [  # (magic bytes, extension, media type)
    (b"%PDF-", "pdf", "application/pdf"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
]
MEDIA_TYPE = {ext: media for _, ext, media in KINDS}


def current(enrolment) -> Document | None:
    return Document.objects.filter(is_active=True, entity_type=ENTITY_TYPE, entity_ref=enrolment.reference).first()


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
