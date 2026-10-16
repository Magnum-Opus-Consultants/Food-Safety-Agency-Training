"""University placements: from the student list to the report back.

A university sends its student list; the abattoir that hosts the cohort receives the
documents it needs and confirms the placement; the students are marked at the abattoir; and the
university gets its report within twenty days of the period's end. The report is built from the
registers (attendance, results, moderation), so what the university reads is what the hub holds.

Some universities set a rule for who may facilitate their students (UJ: HPCSA-registered only). That
rule blocks confirming the intake, and importing the cohort, with a facilitator who does not meet it.
"""

import datetime as dt
import hashlib
import io
from pathlib import Path

from django.conf import settings
from django.db import transaction

from assurance.models import Document, Library, Placement
from audit.services import record
from core import clock
from core.api_support import Refusal
from learners.evidence import MEDIA_TYPE, _sniff

ABATTOIR = "assurance.placement.abattoir"
REPORT = "assurance.placement.report"
KINDS = {ABATTOIR: "Abattoir document", REPORT: "Placement report"}


# ---- The university's facilitator rule ----------------------------------------------------------

def requirement_gap(university, block, on: dt.date | None = None) -> str | None:
    """Why the intake's facilitator does not meet the university's rule, or None when they do."""
    body = university.facilitator_body
    if body is None or block is None:
        return None
    fac = block.facilitator
    regs = [r for r in fac.registrations.all() if r.is_active and r.body_id == body.code]
    until = max(on or clock.today(), block.end_date)
    if not regs:
        return f"{university.name} requires {body.code}-registered facilitators; {fac.display_name} holds no {body.code} registration."
    reg = max(regs, key=lambda r: r.expires_on)
    if reg.expires_on < until:
        return (f"{university.name} requires {body.code}-registered facilitators; {fac.display_name}’s {body.code} registration "
                f"expires on {reg.expires_on.isoformat()}, before the placement ends.")
    return None


def requirement_blockers(block, on: dt.date | None = None) -> list[str]:
    """Wired into confirming an intake: every university placed on it must accept its facilitator."""
    out = []
    for p in Placement.objects.filter(is_active=True, plan_block=block).select_related("organisation__facilitator_body"):
        gap = requirement_gap(p.organisation, block, on)
        if gap:
            out.append(gap + " The intake cannot be confirmed until another facilitator is assigned.")
    return out


@transaction.atomic
def add_university(actor, name: str, body=None, screen="partnerships"):
    """A new university partner, optionally with its facilitator rule. Names are unique, ignoring case and spacing."""
    from demand.models import Organisation

    if not actor.can("assurance", write=True):
        raise Refusal("forbidden", ["University partners are added by the training manager."], "Not permitted.", status=403)
    name = " ".join((name or "").split())
    if len(name) < 3:
        raise Refusal("invalid", ["Give the university's full name."], "Check the name.", status=422)
    same = Organisation.objects.filter(is_active=True, name__iexact=name).first()
    if same:
        kind = "a university partner" if same.relationship == "University" else f"recorded as a {same.relationship.lower()}"
        raise Refusal("duplicate", [f"{same.name} is already {kind}."], "Already on record.", status=409)
    uni = Organisation.objects.create(name=name[:160], sector="University", relationship="University", facilitator_body=body,
                                      created_by=actor, modified_by=actor)
    return uni, record(actor, f"{uni.name} added as a university partner"
                       + (f"; facilitators must be {body.code}-registered" if body else ""), uni, screen=screen)


@transaction.atomic
def set_requirement(actor, university, body, screen="partnerships"):
    before = university.facilitator_body_id
    if before == (body.code if body else None):
        raise Refusal("nothing_to_change", ["That is already the rule."], "Nothing to change.")
    university.facilitator_body = body
    university.modified_by = actor
    university.save()
    what = (f"{university.name} now requires {body.code}-registered facilitators" if body
            else f"{university.name} no longer requires a facilitator registration")
    return record(actor, what, university, screen=screen, before={"body": before}, after={"body": body.code if body else None})


# ---- Who is on the placement, and how they did ---------------------------------------------------

def students(p):
    """The university's students on the placement's intake, each with attendance and their latest result."""
    from learners.assessment import attendance
    from learners.models import Enrolment

    if p.plan_block_id is None:
        return []
    out = []
    enrolments = (Enrolment.objects.filter(is_active=True, plan_block_id=p.plan_block_id, learner__organisation=p.organisation_id)
                  .select_related("learner", "plan_block").order_by("learner__names"))
    for e in enrolments:
        r = e.results.filter(is_active=True).select_related("moderation__moderated_by", "moderation__certificate").order_by(
            "-assessed_at", "-id").first()
        m = getattr(r, "moderation", None) if r else None
        cert = getattr(m, "certificate", None) if m else None
        if r is None:
            standing = "Not assessed"
        elif m is None:
            standing = "Awaiting moderation"
        else:
            standing = "Competent" if m.outcome == "Competent" else "Not yet competent"
        out.append({"enrolment": e.reference, "learner": e.learner.names, "studentNumber": e.learner.external_ref,
                    "attendance": attendance(e), "result": r.reference if r else None, "mark": float(r.mark) if r else None,
                    "standing": standing, "moderatedBy": m.moderated_by.display_name if m else None,
                    "moderatedOn": m.moderated_at.date().isoformat() if m else None,
                    "remediation": r.remediation_plan if r and m and m.outcome != "Competent" else "",
                    "certificate": cert.reference if cert else None})
    return out


def documents(p, kind=None):
    qs = Document.objects.filter(is_active=True, entity_ref=p.reference, entity_type__in=[kind] if kind else list(KINDS))
    return list(qs.order_by("created_at", "id"))


def checklist(p, roster=None, on: dt.date | None = None) -> list[dict]:
    """The steps from student list to report, each done or not, with what is outstanding."""
    on = on or clock.today()
    roster = students(p) if roster is None else roster
    marked = [s for s in roster if s["standing"] in ("Competent", "Not yet competent")]
    gap = requirement_gap(p.organisation, p.plan_block, on) if p.plan_block_id else None
    block = p.plan_block
    steps = [
        ("intake", "Intake planned", p.plan_block_id is not None,
         f"{block.reference} at {block.venue.name}, {block.start_date.isoformat()} to {block.end_date.isoformat()}" if block
         else "Link the placement to an intake at the abattoir."),
        ("students", "Student list received", bool(roster),
         f"{len(roster)} of {p.cohort_size} students enrolled" if roster else "Import the university's student list."),
        ("facilitator", "Facilitator meets the university's rule", block is not None and gap is None,
         gap or (f"{block.facilitator.display_name}" + (f" — {p.organisation.facilitator_body.code} registered"
                                                         if p.organisation.facilitator_body_id else "") if block else "No intake yet.")),
        ("abattoirDocs", "Documents sent to the abattoir", p.abattoir_docs_sent_on is not None,
         f"Sent {p.abattoir_docs_sent_on.isoformat()}" if p.abattoir_docs_sent_on else "Upload the documents sent to the abattoir."),
        ("abattoirConfirmed", "Abattoir confirmed the placement", p.abattoir_confirmed_on is not None,
         f"Confirmed {p.abattoir_confirmed_on.isoformat()}" if p.abattoir_confirmed_on else "Record the abattoir's confirmation."),
        ("marking", "Students marked at the abattoir and moderated", bool(roster) and len(marked) == len(roster),
         f"{len(marked)} of {len(roster)} moderated" if roster else "No students yet."),
        ("report", "Report submitted to the university", p.report_submitted_at is not None,
         f"Submitted {p.report_submitted_at:%Y-%m-%d}" if p.report_submitted_at else f"Due {p.report_due.isoformat()}"),
    ]
    return [{"key": k, "label": label, "done": done, "note": note} for k, label, done, note in steps]


def standing(p, on: dt.date | None = None):
    on = on or clock.today()
    days = (on - p.period_end).days
    if p.report_submitted_at:
        return f"Report submitted {p.report_submitted_at:%Y-%m-%d}", "ok"
    if days > 20:
        return f"Report overdue — {days} days after period end", "bad"
    if days >= 15:
        return f"Report due soon — day {days} of 20", "warn"
    if days >= 0:
        return f"Report being prepared — day {days} of 20", "info"
    if p.plan_block_id and requirement_gap(p.organisation, p.plan_block, on):
        return "Facilitator does not meet the university's rule", "bad"
    if p.period_start <= on:
        return "Placement in progress", "info"
    return "Being arranged", "na"


# ---- Files ---------------------------------------------------------------------------------------

def _store(actor, p, kind, filename, content, library="agreements"):
    if not content:
        raise Refusal("invalid", ["Choose the file to upload."], "No file.", status=422)
    if len(content) > settings.FSA_UPLOAD_MAX_BYTES:
        raise Refusal("invalid", ["The file is larger than 5 MB."], "The file is too large.", status=422)
    ext = _sniff(content[:8])
    if ext is None:
        raise Refusal("invalid", ["Upload a PDF, or a photo or scan as JPG or PNG."], "That file type is not accepted.", status=422)
    digest = hashlib.sha256(content).hexdigest()
    key = f"placements/{p.reference}/{kind.rsplit('.', 1)[-1]}-{digest[:12]}.{ext}"
    target = Path(settings.FSA_FILE_ROOT) / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    name = Path(filename or f"{kind.rsplit('.', 1)[-1]}.{ext}").name[:120]
    return Document.objects.create(library=Library.objects.get(code=library),
                                   title=f"{KINDS[kind]} — {p.organisation.name}, {p.reference} · {name}"[:200],
                                   entity_type=kind, entity_ref=p.reference, storage_key=key, sha256=digest, state="Held",
                                   created_by=actor, modified_by=actor)


def path_of(doc) -> Path:
    return Path(settings.FSA_FILE_ROOT) / doc.storage_key


def media_type(doc) -> str:
    return MEDIA_TYPE.get(doc.storage_key.rsplit(".", 1)[-1], "application/octet-stream")


@transaction.atomic
def add_abattoir_document(actor, p, filename, content, screen="partnerships"):
    if p.plan_block_id is None:
        raise Refusal("no_intake", ["Link the placement to an intake at the abattoir first."], "No abattoir yet.")
    doc = _store(actor, p, ABATTOIR, filename, content)
    first = p.abattoir_docs_sent_on is None
    if first:
        p.abattoir_docs_sent_on = clock.today()
        p.modified_by = actor
        p.save()
    return record(actor, f"{p.reference} document sent to {p.plan_block.venue.name} — {doc.title.rsplit(' · ', 1)[-1]} ({doc.reference})",
                  p, screen=screen)


@transaction.atomic
def confirm_abattoir(actor, p, on: dt.date, screen="partnerships"):
    if p.plan_block_id is None:
        raise Refusal("no_intake", ["Link the placement to an intake at the abattoir first."], "No abattoir yet.")
    if p.abattoir_docs_sent_on is None:
        raise Refusal("docs_outstanding", [f"No documents have been sent to {p.plan_block.venue.name} yet."],
                      "Send the abattoir its documents first.")
    if on > clock.today():
        raise Refusal("invalid", ["The confirmation date is in the future."], "Check the date.", status=422)
    p.abattoir_confirmed_on = on
    p.modified_by = actor
    p.save()
    return record(actor, f"{p.reference} placement confirmed by {p.plan_block.venue.name} on {on.isoformat()}", p, screen=screen)


# ---- The report back -----------------------------------------------------------------------------

def report_blockers(p, roster=None, on: dt.date | None = None) -> list[str]:
    on = on or clock.today()
    roster = students(p) if roster is None else roster
    out = []
    if p.report_submitted_at:
        out.append(f"The report was submitted on {p.report_submitted_at:%Y-%m-%d}.")
    if p.period_end > on:
        out.append(f"The placement runs until {p.period_end.isoformat()}; report once it has ended.")
    if not roster:
        out.append("No students are enrolled on this placement.")
    pending = [s["learner"] for s in roster if s["standing"] in ("Not assessed", "Awaiting moderation")]
    if pending:
        out.append(f"{len(pending)} not yet marked and moderated: {', '.join(pending)}.")
    return out


def report_pdf(p, prepared_by=None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from learners.certificate_pdf import INK, LINE, LOGO, MUTED, TEAL, TEAL_DARK

    roster = students(p)
    block = p.plan_block
    styles = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10.5, textColor=MUTED)
    h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=INK)
    h2 = ParagraphStyle("h2", parent=body, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=TEAL_DARK, spaceBefore=8)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Placement report {p.reference} — {p.organisation.name}", author="FSA Academy")
    story = []
    if LOGO.exists():
        story += [Image(str(LOGO), width=34 * mm, height=18 * mm, kind="proportional", hAlign="LEFT"), Spacer(1, 4 * mm)]
    story += [Paragraph("Placement report", h1),
              Paragraph(f"{p.organisation.name} · {p.cohort_label} · {p.reference}", body), Spacer(1, 4 * mm)]

    def kv(rows):
        t = Table([[Paragraph(f"<b>{k}</b>", body), Paragraph(v, body)] for k, v in rows], colWidths=[45 * mm, None])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    fac = block.facilitator if block else None
    regs = ", ".join(f"{r.body_id} {r.registration_no or r.registration_type} (to {r.expires_on.isoformat()})"
                     for r in fac.registrations.all() if r.is_active) if fac else ""
    story += [Paragraph("The placement", h2), kv([
        ("Period", f"{p.period_start.isoformat()} to {p.period_end.isoformat()}"),
        ("Abattoir", f"{block.venue.name}" + (f", {block.venue.province}" if block and block.venue.province else "") if block else "—"),
        ("Programme", block.course.title if block else "—"),
        ("Facilitator", f"{fac.display_name}" + (f" — {regs}" if regs else "") if fac else "—"),
        ("Abattoir placement", (f"Documents sent {p.abattoir_docs_sent_on.isoformat()}" if p.abattoir_docs_sent_on else "Documents not sent")
         + (f"; confirmed {p.abattoir_confirmed_on.isoformat()}" if p.abattoir_confirmed_on else "")),
    ])]

    competent = sum(1 for s in roster if s["standing"] == "Competent")
    nyc = sum(1 for s in roster if s["standing"] == "Not yet competent")
    story += [Paragraph("Outcomes", h2),
              Paragraph(f"{len(roster)} students placed: <b>{competent} competent</b>, {nyc} not yet competent"
                        + (f", {len(roster) - competent - nyc} still to be marked" if len(roster) - competent - nyc else "")
                        + ". Students were marked at the abattoir; every result is moderated by a second person.", body),
              Spacer(1, 3 * mm)]
    head = ["Student", "Student no.", "Attendance", "Mark", "Outcome", "Moderated"]
    data = [head] + [[Paragraph(s["learner"], body), s["studentNumber"] or "—",
                      f"{s['attendance']['present']}/{s['attendance']['of']} ({s['attendance']['percent']}%)" if s["attendance"] else "—",
                      f"{s['mark']:g}%" if s["mark"] is not None else "—", Paragraph(s["standing"], body),
                      Paragraph(f"{s['moderatedBy']}, {s['moderatedOn']}" if s["moderatedBy"] else "—", small)] for s in roster]
    t = Table(data, colWidths=[42 * mm, 24 * mm, 26 * mm, 15 * mm, 30 * mm, None], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F8F9")])]))
    story.append(t if roster else Paragraph("No students are enrolled on this placement.", body))
    plans = [s for s in roster if s["remediation"]]
    if plans:
        story += [Paragraph("Remediation", h2)] + [Paragraph(f"<b>{s['learner']}</b>: {s['remediation']}", body) for s in plans]
    story += [Spacer(1, 8 * mm),
              Paragraph(f"Prepared by {prepared_by.display_name if prepared_by else 'FSA Academy'} on {clock.today().isoformat()}. "
                        f"Report due to the university by {p.report_due.isoformat()} (twenty days after the period ends).", small)]
    doc.build(story)
    return buf.getvalue()


@transaction.atomic
def submit_report(actor, p, screen="partnerships"):
    reasons = report_blockers(p)
    if reasons:
        raise Refusal("not_ready", reasons, "The report cannot be submitted yet.")
    pdf = report_pdf(p, actor)
    doc = _store(actor, p, REPORT, f"{p.reference}-report.pdf", pdf)
    # The seeded "outstanding report" placeholder for this placement is now held.
    Document.objects.filter(is_active=True, entity_type="assurance.placement", entity_ref=p.reference, state="Outstanding").update(
        state="Archived", is_active=False)
    p.report_submitted_at = clock.now()
    p.modified_by = actor
    p.save()
    late = (clock.today() - p.report_due).days
    return record(actor, f"{p.reference} report submitted to {p.organisation.name} ({doc.reference})"
                  + (f" — {late} days late" if late > 0 else ""), p, screen=screen)
