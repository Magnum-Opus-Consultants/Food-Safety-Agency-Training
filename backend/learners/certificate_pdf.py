"""The certificate as a PDF: A4 landscape, FSA Academy branding, the learner, the course and its
accreditation, the certificate number and verification code, and the signatory. Rendered from the
certificate record each time, so the PDF always matches what the register holds."""

import io
from pathlib import Path

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

TEAL = colors.HexColor("#088298")
TEAL_DARK = colors.HexColor("#076B7D")
INK = colors.HexColor("#0F1A1F")
MUTED = colors.HexColor("#485861")
LINE = colors.HexColor("#C9D3D8")
LOGO = Path(settings.BASE_DIR).parent / "web" / "public" / "brand" / "fsa-logo.png"


def _long_date(d):
    return f"{d.day} {d:%B %Y}"


def render(cert) -> bytes:
    result = cert.moderation.result
    enrolment = result.enrolment
    learner, course = enrolment.learner, enrolment.course
    from assurance.workflow import covering

    accreditation = covering(course, cert.issued_at.date()) if course.is_accredited else None
    w, h = landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setTitle(f"Certificate {cert.reference} — {learner.names}")
    c.setAuthor("FSA Academy")
    c.setSubject(f"Certificate of competence: {course.title}")

    # Frame: a teal border with a thin inner rule.
    c.setStrokeColor(TEAL)
    c.setLineWidth(6)
    c.rect(12 * mm, 12 * mm, w - 24 * mm, h - 24 * mm)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.8)
    c.rect(17 * mm, 17 * mm, w - 34 * mm, h - 34 * mm)

    if LOGO.exists():
        c.drawImage(str(LOGO), w / 2 - 22 * mm, h - 52 * mm, width=44 * mm, height=23 * mm, preserveAspectRatio=True, mask="auto")

    c.setFillColor(TEAL_DARK)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(w / 2, h - 60 * mm, "FOOD SAFETY AGENCY  ·  FSA ACADEMY")
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(w / 2, h - 76 * mm, "Certificate of Competence")

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 13)
    c.drawCentredString(w / 2, h - 92 * mm, "This is to certify that")
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(w / 2, h - 106 * mm, learner.names)
    if learner.id_last4:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 9.5)
        kind = "SA ID" if learner.id_type == "SAID" else "Passport"
        c.drawCentredString(w / 2, h - 113 * mm, f"{kind} ending {learner.id_last4}")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 13)
    c.drawCentredString(w / 2, h - 124 * mm, "has been assessed and found competent in")
    c.setFillColor(TEAL_DARK)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w / 2, h - 136 * mm, course.title)
    if accreditation:
        c.setFillColor(MUTED)
        c.setFont("Helvetica", 10)
        number = f", accreditation {accreditation.number}" if accreditation.number else ""
        c.drawCentredString(w / 2, h - 144 * mm, f"Delivered under {accreditation.body.name} accreditation{number}")

    # Signature (left) and certificate details (right).
    base = 40 * mm
    c.setStrokeColor(INK)
    c.setLineWidth(0.6)
    c.line(40 * mm, base + 10 * mm, 120 * mm, base + 10 * mm)
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40 * mm, base + 4 * mm, cert.issued_by.display_name)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9.5)
    c.drawString(40 * mm, base - 1 * mm, "Training manager, FSA Academy")

    right = w - 40 * mm
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(right, base + 4 * mm, f"Certificate {cert.reference}")
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 9.5)
    c.drawRightString(right, base - 1 * mm, f"Issued {_long_date(cert.issued_at.date())}")
    c.drawRightString(right, base - 6 * mm, f"Verification code {cert.verification_code}")

    if cert.revoked_at:
        c.saveState()
        c.setFillColor(colors.Color(0.79, 0.15, 0.17, alpha=0.25))
        c.setFont("Helvetica-Bold", 90)
        c.translate(w / 2, h / 2)
        c.rotate(25)
        c.drawCentredString(0, 0, "REVOKED")
        c.restoreState()

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(w / 2, 21 * mm, "Verify this certificate with the FSA Academy using its number and verification code.")
    c.showPage()
    c.save()
    return buf.getvalue()
