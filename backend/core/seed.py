"""Demo seed: the illustrative data from FSA Training Hub.dc.html, business clock 2026-09-09.

People and reporting lines are real (2026 operating model). Everything else is invented.
"""
import datetime as dt
from decimal import Decimal

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from assurance.models import Accreditation, AccreditationProject, Document, Library, Placement, Risk
from audit.services import record
from core.credentials import existing_passwords, new_password, username_for, write_logins
from core.models import Body, DemoClock, PublicHoliday, RefCounter, Service, Stream, Venue
from courses.models import Course
from delivery.models import Attendance, AttendanceRegister, PlanBlock, Session
from demand.models import Contact, Enquiry, Organisation, Quotation
from identity.models import Account, AccountSegment, FacilitatorRegistration, Segment
from learners.models import Certificate, Enrolment, Learner, Moderation, Result
from oversight.models import Rotation

D = dt.date.fromisoformat
# What each seeded enquirer asked about (meeting review: accreditation, costs, online or in person,
# duration, quote).
SEED_TOPICS = {
    "ENQ-0421": ["Costs", "Duration"], "ENQ-0420": ["Quote"], "ENQ-0419": ["Delivery", "Costs"],
    "ENQ-0417": ["Accreditation", "Costs"], "ENQ-0415": ["Quote"], "ENQ-0411": ["Accreditation", "Duration"],
    "ENQ-0408": ["Costs"],
}
SEED_NOTES = {"ENQ-0415": "Group of 12 delegates."}
KEEP_TABLES = {"django_migrations", "django_content_type", "auth_permission", "auth_group", "auth_group_permissions"}


def at(day: dt.date, hour=9, minute=0):
    return timezone.make_aware(dt.datetime(day.year, day.month, day.day, hour, minute))


def truncate_all():
    """TRUNCATE bypasses the row-level append-only triggers, which is what a demo reset needs."""
    with connection.cursor() as cur:
        tables = [t for t in connection.introspection.table_names() if t not in KEEP_TABLES]
        cur.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE")


@transaction.atomic
def seed(passwords: dict[str, str] | None = None, write_file: bool = False) -> dict[str, str]:
    """Load the demo data. Returns {username: password}; optionally writes demo-logins.txt."""
    # The prototype's data is dated around 2026-09-09. Pin that date only when FSA_DEMO_TODAY asks
    # for it (the tests do); otherwise the hub runs on the real date and the sample data is as old as it is.
    today = D(settings.DEMO_TODAY) if settings.DEMO_TODAY else D("2026-09-09")
    if settings.DEMO_TODAY:
        DemoClock.objects.update_or_create(pk=1, defaults={"today": today})

    # --- reference data ---------------------------------------------------------------
    for code, name in [("IMI", "IMI & Classification"), ("AUD", "Auditing"), ("VET", "Vet Services")]:
        Service.objects.create(code=code, name=name)
    streams = {}
    for i, (code, name, colour) in enumerate([
        ("RME", "Meat examiner — red meat", "#088298"), ("PME-P", "Meat examiner — poultry", "#0B5A97"),
        ("PME", "PME 1 and PME 2", "#04414C"), ("SHORT", "Short courses", "#5A5B5E"),
        ("UNI", "University and vet placements", "#2C2D30"),
    ], start=1):
        streams[code] = Stream.objects.create(code=code, name=name, colour=colour, sort_order=i)
    venues = {}
    for name, prov, online in [
        ("HQ Lynnwood, training room 1", "Gauteng", False), ("HQ Lynnwood, training room 2", "Gauteng", False),
        ("Cato Ridge Abattoir, KZN", "KwaZulu-Natal", False), ("Hammarsdale, KZN", "KwaZulu-Natal", False),
        ("Rustenburg Abattoir", "North West", False), ("Bloemfontein Abattoir", "Free State", False),
        ("Malmesbury Abattoir", "Western Cape", False), ("Online — Teams", "", True),
    ]:
        venues[name] = Venue.objects.create(name=name, province=prov, is_online=online)
    bodies = {code: Body.objects.create(code=code, name=name) for code, name in [
        ("AGRISETA", "AgriSETA"), ("SAATCA", "SAATCA"), ("HPCSA", "HPCSA"), ("QCTO", "QCTO")]}
    for day, name in [
        ("2026-01-01", "New Year's Day"), ("2026-03-21", "Human Rights Day"), ("2026-04-03", "Good Friday"),
        ("2026-04-06", "Family Day"), ("2026-04-27", "Freedom Day"), ("2026-05-01", "Workers' Day"),
        ("2026-06-16", "Youth Day"), ("2026-08-10", "National Women's Day (observed)"), ("2026-09-24", "Heritage Day"),
        ("2026-12-16", "Day of Reconciliation"), ("2026-12-25", "Christmas Day"), ("2026-12-26", "Day of Goodwill"),
    ]:
        PublicHoliday.objects.create(day=D(day), name=name)

    # --- accounts (real people and reporting lines) ----------------------------------
    people = [
        ("USR-0001", "Louis Visagie", "Chief Executive Officer", "Board of Directors", "Director", None),
        ("USR-0002", "Armand Visagie", "GM Operations, Commercial Growth and Technical Services", "", "Director", "USR-0001"),
        ("USR-0003", "Nicole Bergh", "GM Corporate Services, Compliance and Business Enablement", "", "Director", "USR-0001"),
        ("USR-0004", "Hein Nel", "Vets and Audits — SAATCA lead auditor", "", "Moderator", "USR-0001"),
        ("USR-0005", "Palesa Mpana", "Head of training — Shared Roles and Overlap", "A. Visagie and N. Bergh", "TrainingManager", None),
        ("USR-0006", "P. Mokoena", "Training administrator — Administration and Office Support", "", "EnquiryHandler", "USR-0005"),
        ("USR-0007", "Thandi Ncube", "Facilitator — IMI and Classification", "", "Facilitator", "USR-0005"),
        ("USR-0008", "William", "Facilitator and assessor — IMI and Classification", "", "Assessor", "USR-0005"),
        ("USR-0009", "Naledi Phiri", "Facilitator — short courses", "", "Facilitator", "USR-0005"),
        ("USR-0010", "Sipho Dlamini", "Facilitator — classification", "", "Facilitator", "USR-0005"),
        ("USR-0011", "Dr Riaan Steyn", "Veterinary Services — abattoir programme", "", "Facilitator", "USR-0004"),
        ("USR-0012", "HR and Administration", "Service account — HR Hub link", "", "SystemAdministrator", "USR-0003"),
        # On the prototype's desk rotation but not in the confirmed account list (open item).
        ("USR-0013", "N. Sibeko", "Administration and Office Support — rotation member", "", "EnquiryHandler", "USR-0005"),
        ("USR-0014", "R. Adams", "Administration and Office Support — rotation member", "", "EnquiryHandler", "USR-0005"),
    ]
    acc = {}
    reuse = existing_passwords() if passwords is None else passwords
    credentials = {}
    for ref, name, position, label, role, reports in people:
        service = ref == "USR-0012"
        username = "hr.service" if service else username_for(name)
        password = None if service else (reuse.get(username) or new_password())
        acc[name] = Account.objects.create_user(
            username, name, password, reference=ref, position=position, reports_to_label=label, hub_role=role,
            reports_to=next((a for a in acc.values() if a.reference == reports), None),
            is_service_account=service,
        )
        if password:
            credentials[username] = password
    for name, reg, body, expires in [
        ("Thandi Ncube", "Assessor — meat examination", "AGRISETA", "2027-05-31"),
        ("Dr Riaan Steyn", "HPCSA veterinary registration", "HPCSA", "2026-11-14"),
        ("William", "Assessor — meat examination", "AGRISETA", "2026-09-30"),
        ("Naledi Phiri", "Assessor — short courses", "AGRISETA", "2028-02-28"),
        ("Sipho Dlamini", "Assessor — classification", "AGRISETA", "2026-06-30"),
        ("Palesa Mpana", "Moderator — all registered scope", "AGRISETA", "2027-09-30"),
    ]:
        FacilitatorRegistration.objects.create(account=acc[name], registration_type=reg, body=bodies[body], expires_on=D(expires))
    sipho = acc["Sipho Dlamini"]
    sipho.state, sipho.suspended_at = "Suspended", at(D("2026-06-30"), 0, 5)
    sipho.suspended_reason = "Assessor — classification lapsed on 2026-06-30"
    sipho.save()

    for code, name in [
        ("overview", "Training home"), ("demand", "Enquiries, contacts and quotes"),
        ("courses", "Catalogue, development and packs"), ("delivery", "Plan, sessions and attendance"),
        ("learners", "Learners and enrolments"), ("results", "Results"), ("moderation", "Moderation"),
        ("certification", "Certification"), ("assurance", "Accreditation, partnerships and risk"),
        ("depository", "Training depository"), ("reporting", "Dashboard and monthly report"),
        ("admin", "Accounts and segment access"),
    ]:
        Segment.objects.create(code=code, name=name)
    grants = {
        "Palesa Mpana": [(s, "write", "all") for s in ["demand", "courses", "delivery", "learners", "results", "moderation",
                                                        "certification", "assurance", "depository", "reporting"]],
        # P. Mokoena submits the university placement reports (monthly report actions, TRK-03), so reads assurance.
        "P. Mokoena": [("demand", "write", "all"), ("learners", "write", "all"), ("depository", "write", "all"), ("assurance", "read", "all"),
                       ("courses", "read", "all"), ("delivery", "read", "all")],
        "N. Sibeko": [("demand", "write", "all"), ("learners", "write", "all"), ("courses", "read", "all")],
        "R. Adams": [("depository", "write", "all"), ("courses", "read", "all")],
        "Hein Nel": [("results", "read", "all"), ("moderation", "write", "all"), ("assurance", "read", "all"),
                     ("courses", "read", "all")],
        "HR and Administration": [("admin", "write", "all"), ("learners", "read", "all")],
    }
    for name in ["Thandi Ncube", "William", "Naledi Phiri", "Sipho Dlamini", "Dr Riaan Steyn"]:
        grants[name] = [("delivery", "write", "own"), ("results", "write", "own"), ("courses", "read", "all")]
    grants["Dr Riaan Steyn"].append(("assurance", "read", "all"))
    for name, regions in {"Thandi Ncube": ["KwaZulu-Natal"], "William": ["Gauteng", "Free State"], "Naledi Phiri": ["Gauteng", "Online"],
                          "Sipho Dlamini": ["Gauteng", "North West"], "Dr Riaan Steyn": ["North West"],
                          "Palesa Mpana": ["Gauteng", "Online"]}.items():
        acc[name].regions = regions
        acc[name].save(update_fields=["regions"])
    for name, rows in grants.items():
        for seg, access, scope in rows:
            AccountSegment.objects.create(account=acc[name], segment_id=seg, access=access, scope=scope)

    monday = today - dt.timedelta(days=today.weekday())
    for area, name in [("EnquiryTriage", "P. Mokoena"), ("QuoteFollowUp", "P. Mokoena"),
                       ("LearnerRecords", "N. Sibeko"), ("Filing", "R. Adams")]:
        # Four weeks of rotation from the demo week, so moving the clock forward keeps an owner on duty.
        Rotation.objects.create(function_area=area, member=acc[name], period=(monday, D("2027-01-01")))  # through 31 December

    # --- courses --------------------------------------------------------------------
    courses = {}
    for code, title, svc, stream, pack, days, mode, gate, req, accredited, body in [
        ("TRN-PME1", "PME 1 — primary meat examiner", "IMI", "PME", "Meat examiner streams", 15, "Contact", "PrerequisiteAndGrade10", "Prerequisite test ≥ 50% and Grade 10", True, "AGRISETA"),
        ("TRN-PME2", "PME 2 — primary meat examiner", "IMI", "PME", "Meat examiner streams", 15, "Contact", "PriorCourse", "PME 1 competent", True, "AGRISETA"),
        ("TRN-MER", "Meat examiner — red meat", "IMI", "RME", "Meat examiner streams", 20, "Contact and workplace", "PrerequisiteAndGrade10", "Prerequisite test ≥ 50% and Grade 10", True, "AGRISETA"),
        ("TRN-MEP", "Meat examiner — poultry", "IMI", "PME-P", "Meat examiner streams", 12, "Contact and workplace", "PrerequisiteAndGrade10", "Prerequisite test ≥ 50% and Grade 10", True, "AGRISETA"),
        ("TRN-GAME", "Game meat examiner", "IMI", "RME", "Meat examiner streams", 8, "Contact", "PrerequisiteAndGrade10", "Prerequisite test ≥ 50% and Grade 10", True, "AGRISETA"),
        ("TRN-CLASS", "Carcass classification refresher", "IMI", "SHORT", "Short courses", 3, "Contact", "Documented", "Registered classifier", False, None),
        ("TRN-HACCP", "HACCP awareness", "AUD", "SHORT", "Short courses", 2, "Contact or online", "None", "None", False, None),
        ("TRN-HYG", "Food hygiene and GMP", "AUD", "SHORT", "Short courses", 1, "Contact or online", "None", "None", False, None),
        ("TRN-IA", "Internal auditor (SAATCA aligned)", "AUD", "SHORT", "Short courses", 5, "Contact", "Documented", "Two years industry experience", True, "SAATCA"),
        ("TRN-VET", "Veterinary student abattoir programme", "VET", "UNI", "Veterinary WIL programme", 10, "Workplace", "Documented", "University placement letter", False, None),
    ]:
        courses[code] = Course.objects.create(
            code=code, title=title, service_id=svc, stream=streams[stream], pack_type=pack, duration_days=days,
            delivery_mode=mode, entry_gate=gate, entry_requirement=req, is_accredited=accredited,
            accreditation_body=bodies.get(body) if body else None,
        )
    courses["TRN-PME2"].prior_course = courses["TRN-PME1"]
    courses["TRN-PME2"].save()
    from courses.models import EARLIEST, CourseRequirement

    for c in courses.values():
        CourseRequirement.objects.create(
            course=c, version=1, effective_from=EARLIEST, kind=c.entry_gate,
            pass_mark=Decimal("50") if c.entry_gate == "PrerequisiteAndGrade10" else None, prior_course=c.prior_course,
            description=c.entry_requirement if c.entry_gate == "Documented" else "",
            reason="Requirement in the course catalogue when the Training Hub went live",
        )

    # --- organisations, contacts, enquiries, quotations --------------------------------
    orgs = {}
    for name, sector, rel in [
        ("Karan Beef, Heidelberg", "Abattoir", "Prospect"), ("Rainbow, Hammarsdale", "Poultry", "Client"),
        ("Cato Ridge Abattoir", "Abattoir", "Client"), ("Sovereign Foods, Uitenhage", "Poultry", "Prospect"),
        ("Chalmar Beef, Bapsfontein", "Abattoir", "Client"), ("University of Pretoria", "University", "University"),
        ("Bull Brand, Krugersdorp", "Processing", "Prospect"),
        ("Mangosuthu University of Technology", "University", "University"), ("Durban University of Technology", "University", "University"),
        ("Central University of Technology", "University", "University"), ("Cape Peninsula University of Technology", "University", "University"),
        ("University of Johannesburg", "University", "University"), ("Tshwane University of Technology", "University", "University"),
    ]:
        orgs[name] = Organisation.objects.create(name=name, sector=sector, relationship=rel)
    orgs["University of Johannesburg"].facilitator_body = bodies["HPCSA"]  # UJ is strict: HPCSA-registered facilitators only
    orgs["University of Johannesburg"].save()

    enquiries = {}
    for ref, names, org, kind, channel, days, course, interest, stage, owner in [
        ("ENQ-0421", "Lerato Mahlangu", "Karan Beef, Heidelberg", "Enquiry", "WhatsApp", 1, "TRN-MER", "", 0, "P. Mokoena"),
        ("ENQ-0420", "Sibusiso Khumalo", "Rainbow, Hammarsdale", "Enquiry", "Email", 2, "TRN-MEP", "", 0, "P. Mokoena"),
        ("ENQ-0419", "Zanele Dube", "Cato Ridge Abattoir", "Enquiry", "WhatsApp", 4, "TRN-CLASS", "", 0, "Thandi Ncube"),
        ("ENQ-0417", "Anika van Wyk", "Sovereign Foods, Uitenhage", "Enquiry", "Phone", 5, "TRN-PME1", "", 1, "P. Mokoena"),
        ("ENQ-0415", "Training desk", "Chalmar Beef, Bapsfontein", "Enquiry", "Email", 7, "TRN-HACCP", "", 2, "Naledi Phiri"),
        ("ENQ-0411", "Dr M. Sithole", "University of Pretoria", "Enquiry", "Email", 12, "TRN-VET", "", 3, "P. Mokoena"),
        ("ENQ-0408", "Kobus Erasmus", "Bull Brand, Krugersdorp", "Enquiry", "Phone", 16, "TRN-GAME", "", 4, "Naledi Phiri"),
        ("ENQ-0422", "Delegate — Cato Ridge", "Cato Ridge Abattoir", "Complaint", "Phone", 2, None,
         "Attendance register for SES-0312 not signed; the delegate cannot be certificated until it is captured and locked.", 0, "Palesa Mpana"),
        ("ENQ-0423", "Operations director", "Karan Beef, Heidelberg", "Opportunity", "Phone", 0, None,
         "Group training agreement — red meat examiner plus classification refreshers across two sites.", 0, "Palesa Mpana"),
    ]:
        contact = Contact.objects.create(names=names, organisation=orgs[org])
        received = at(today - dt.timedelta(days=days), 9, 15)
        enquiries[ref] = Enquiry.objects.create(
            reference=ref, contact=contact, kind=kind, channel=channel, received_at=received,
            enquiring_for="Company" if kind == "Enquiry" else "Individual",
            course=courses.get(course) if course else None, course_interest=interest, stage_index=stage,
            first_response_at=received + dt.timedelta(hours=20) if stage > 0 else None,
            resolved_at=received + dt.timedelta(days=2) if stage >= 3 else None,
            assigned_to=acc[owner],
            topics=SEED_TOPICS.get(ref, []), notes=SEED_NOTES.get(ref, ""),
        )
    for ref, enq, course, basis, n, rands, issued in [
        ("QTE-0221", "ENQ-0420", "TRN-MEP", "PerGroup", 16, 68_400, "2026-09-05"),
        ("QTE-0218", "ENQ-0415", "TRN-HACCP", "PerGroup", 12, 18_600, "2026-08-20"),
        ("QTE-0216", "ENQ-0417", "TRN-PME1", "PerLearner", 1, 14_500, "2026-09-01"),
    ]:
        e = enquiries[enq]
        Quotation.objects.create(reference=ref, enquiry=e, contact=e.contact, organisation=e.contact.organisation,
                                 course=courses[course], basis=basis, learner_count=n, value_cents=rands * 100,
                                 issued_on=D(issued), state="Issued", assigned_to=acc["P. Mokoena"])

    # --- the plan and sessions --------------------------------------------------------
    blocks, booked_target = {}, {}
    for ref, ses, course, stream, fac, venue, mode, cadence, s, e, booked, cap, hours, notes, state in [
        ("PLN-01", "SES-0312", "TRN-MER", "RME", "Thandi Ncube", "Cato Ridge Abattoir, KZN", "Contact and workplace", "Monthly", "2026-08-24", "2026-09-04", 5, 8, 96, "Practical on the red meat line. Register signed daily by the abattoir supervisor.", "Confirmed"),
        ("PLN-02", "SES-0314", "TRN-HACCP", "SHORT", "Naledi Phiri", "HQ Lynnwood, training room 2", "Contact", "AdHoc", "2026-09-03", "2026-09-04", 4, 16, 0, "Chalmar Beef group booking, quoted per group.", "Confirmed"),
        ("PLN-03", "SES-0316", "TRN-VET", "UNI", "Dr Riaan Steyn", "Rustenburg Abattoir", "Workplace", "AdHoc", "2026-09-07", "2026-09-18", 5, 5, 80, "University of Pretoria cohort of five, marked at the abattoir. Report due twenty days after period end.", "Confirmed"),
        ("PLN-04", "SES-0320", "TRN-PME1", "PME", "William", "HQ Lynnwood, training room 1", "Contact", "Quarterly", "2026-09-14", "2026-09-25", 6, 12, 24, "Prerequisite tests written and invigilated on day one.", "Confirmed"),
        ("PLN-05", "SES-0322", "TRN-HYG", "SHORT", "Naledi Phiri", "Online — Teams", "Online", "AdHoc", "2026-09-22", "2026-09-22", 11, 25, 0, "", "Confirmed"),
        ("PLN-06", "SES-0318", "TRN-MEP", "PME-P", "Thandi Ncube", "Hammarsdale, KZN", "Contact and workplace", "Monthly", "2026-10-05", "2026-10-16", 2, 10, 80, "Fill is low — follow up the Rainbow quotation.", "Confirmed"),
        ("PLN-07", "SES-0324", "TRN-CLASS", "SHORT", "Sipho Dlamini", "Rustenburg Abattoir", "Contact", "AdHoc", "2026-10-21", "2026-10-23", 7, 12, 8, "Cannot be confirmed until the facilitator accreditation is renewed.", "Draft"),
        ("PLN-08", "SES-0326", "TRN-VET", "UNI", "Dr Riaan Steyn", "Cato Ridge Abattoir, KZN", "Workplace", "AdHoc", "2026-11-02", "2026-11-13", 0, 5, 80, "University of Johannesburg cohort — student list awaited from UJ.", "Confirmed"),
        ("PLN-09", "SES-0328", "TRN-IA", "SHORT", "Palesa Mpana", "HQ Lynnwood, training room 1", "Contact", "AdHoc", "2026-11-16", "2026-11-20", 3, 14, 0, "Subject to the SAATCA renewal due 2026-11-30.", "Confirmed"),
        ("PLN-10", "SES-0330", "TRN-GAME", "RME", "William", "Bloemfontein Abattoir", "Contact", "Quarterly", "2026-12-01", "2026-12-08", 0, 10, 32, "Held until the 2026 revision is signed off.", "Draft"),
        ("PLN-11", "SES-0309", "TRN-PME1", "PME", "William", "HQ Lynnwood, training room 1", "Contact", "Quarterly", "2026-08-10", "2026-08-28", 3, 12, 24, "", "Confirmed"),
        ("PLN-12", "SES-0305", "TRN-HYG", "SHORT", "Naledi Phiri", "Online — Teams", "Online", "AdHoc", "2026-08-18", "2026-08-18", 1, 25, 0, "", "Confirmed"),
        ("PLN-13", "SES-0332", "TRN-HACCP", "SHORT", "Naledi Phiri", "HQ Lynnwood, training room 2", "Contact", "AdHoc", "2026-10-12", "2026-10-13", 0, 16, 0, "Chalmar Beef group intake against QTE-0218; delegate list awaited from the client.", "Confirmed"),
    ]:
        b = PlanBlock.objects.create(
            reference=ref, course=courses[course], stream=streams[stream], facilitator=acc[fac], venue=venues[venue],
            delivery_mode=mode, intake_cadence=cadence, start_date=D(s), end_date=D(e),
            capacity=cap, practical_hours=hours, notes=notes, state=state,
            confirmed_at=at(D(s) - dt.timedelta(days=21)) if state == "Confirmed" else None,
            confirmed_by=acc["Palesa Mpana"] if state == "Confirmed" else None,
        )
        blocks[ref] = b
        booked_target[ref] = booked
        Session.objects.create(reference=ses, plan_block=b)

    # --- learners and enrolments ------------------------------------------------------
    learners = {}
    for ref, names, kind, org in [
        ("LRN-1841", "Lerato Mahlangu", "Public", None), ("LRN-1842", "Bongani Zulu", "Public", None),
        ("LRN-1843", "Precious Naidoo", "Corporate", "Karan Beef, Heidelberg"), ("LRN-1844", "Sipho Mthembu", "Corporate", "Karan Beef, Heidelberg"),
        ("LRN-1845", "Elmarie Botha", "Public", None),
        ("LRN-1852", "Johan Kruger", "Corporate", "Chalmar Beef, Bapsfontein"), ("LRN-1853", "Nomvula Sithole", "Corporate", "Chalmar Beef, Bapsfontein"),
        ("LRN-1854", "Farhana Patel", "Public", None), ("LRN-1855", "Tebogo Mabaso", "Corporate", "Chalmar Beef, Bapsfontein"),
        ("LRN-1820", "Anika van Wyk", "Public", None), ("LRN-1821", "Musa Ngcobo", "Public", None), ("LRN-1822", "Karin Lubbe", "Public", None),
        ("LRN-1861", "P. Nkosi (UP)", "University", "University of Pretoria"), ("LRN-1862", "L. Fourie (UP)", "University", "University of Pretoria"),
        ("LRN-1863", "S. Reddy (UP)", "University", "University of Pretoria"), ("LRN-1864", "M. Sebola (UP)", "University", "University of Pretoria"),
        ("LRN-1865", "C. de Villiers (UP)", "University", "University of Pretoria"),
        ("LRN-1871", "Sibusiso Khumalo", "Public", None), ("LRN-1872", "Ayanda Mkhize", "Public", None),
        ("LRN-1873", "Thabo Molefe", "Corporate", None),
    ]:
        learners[ref] = Learner.objects.create(reference=ref, names=names, learner_type=kind,
                                               organisation=orgs.get(org) if org else None)
    enrol = {}
    for ref, lrn, blk, basis, stage, test, g10 in [
        ("ENR-0512", "LRN-1841", "PLN-01", "PerLearner", 3, 69, True), ("ENR-0513", "LRN-1842", "PLN-01", "PerLearner", 3, 61, True),
        ("ENR-0514", "LRN-1843", "PLN-01", "PerGroup", 3, 58, True), ("ENR-0515", "LRN-1844", "PLN-01", "PerGroup", 3, 55, True),
        ("ENR-0516", "LRN-1845", "PLN-01", "PerLearner", 3, 77, True),
        ("ENR-0507", "LRN-1852", "PLN-02", "PerGroup", 3, None, True), ("ENR-0509", "LRN-1853", "PLN-02", "PerGroup", 3, None, True),
        ("ENR-0510", "LRN-1854", "PLN-02", "PerLearner", 3, None, True), ("ENR-0511", "LRN-1855", "PLN-02", "PerGroup", 3, None, True),
        ("ENR-0505", "LRN-1861", "PLN-03", "UniversityAgreement", 3, None, True), ("ENR-0504", "LRN-1862", "PLN-03", "UniversityAgreement", 3, None, True),
        ("ENR-0503", "LRN-1863", "PLN-03", "UniversityAgreement", 3, None, True), ("ENR-0502", "LRN-1864", "PLN-03", "UniversityAgreement", 3, None, True),
        ("ENR-0501", "LRN-1865", "PLN-03", "UniversityAgreement", 3, None, True),
        ("ENR-0498", "LRN-1820", "PLN-11", "PerLearner", 4, 74, True), ("ENR-0499", "LRN-1821", "PLN-11", "PerLearner", 4, 66, True),
        ("ENR-0500", "LRN-1822", "PLN-11", "PerLearner", 4, 52, True), ("ENR-0490", "LRN-1854", "PLN-12", "PerLearner", 4, None, True),
        ("ENR-0517", "LRN-1871", "PLN-06", "PerLearner", 0, 62, True),
        ("ENR-0518", "LRN-1872", "PLN-06", "PerLearner", 0, 44, True),
        ("ENR-0519", "LRN-1873", None, "PerGroup", 0, 71, False),
    ]:
        block = blocks.get(blk) if blk else None
        enrol[ref] = Enrolment.objects.create(
            reference=ref, learner=learners[lrn], course=block.course if block else courses["TRN-PME1"],
            plan_block=block, basis=basis, stage_index={0: 0, 3: 2, 4: 3}[stage],  # prototype numbering: 3 in training, 4 completed
            prerequisite_result=Decimal(test) if test is not None else None, grade10_evidence_held=g10,
            assigned_to=acc["N. Sibeko"],
        )

    # Seats booked is derived from enrolments, so every seat the prototype shows as booked gets a
    # registered learner behind it. Invented people carry no ID number: a generated one could be real.
    backing = {
        "PLN-04": ("Public", None, ["Thabo Nkosi", "Refilwe Masondo", "Jacques Pretorius", "Nokuthula Zwane",
                                    "Kagiso Letsoalo", "Annelize Venter"]),
        "PLN-05": ("Corporate", "Chalmar Beef, Bapsfontein", ["Pieter Joubert", "Lindiwe Khoza", "Mpho Radebe",
                   "Chantelle Adams", "Sizwe Mahlaba", "Deon Smit", "Palesa Tshabalala", "Riaan Coetzee",
                   "Zodwa Mthethwa", "Gift Maluleke", "Marlize Fourie"]),
        "PLN-07": ("Corporate", "Cato Ridge Abattoir", ["Sibongile Cele", "Andile Mkhize", "Wayne Naidoo",
                   "Thulani Ngcobo", "Bheki Shezi", "Prakash Govender", "Nandi Ntuli"]),
        "PLN-09": ("Corporate", "Sovereign Foods, Uitenhage", ["Liezl Steyn", "Monde Mabandla", "Carol Hendricks"]),
    }
    for blk, (kind, org, names) in backing.items():
        block = blocks[blk]
        missing = booked_target[blk] - Enrolment.objects.filter(plan_block=block).count()
        assert missing == len(names), f"{blk}: {missing} seats to back, {len(names)} names"
        gated = block.course.entry_gate == "PrerequisiteAndGrade10"
        for i, n in enumerate(names):
            learner = Learner.objects.create(names=n, learner_type=kind, organisation=orgs.get(org) if org else None)
            Enrolment.objects.create(
                learner=learner, course=block.course, plan_block=block, stage_index=1,
                basis="PerGroup" if kind == "Corporate" else "PerLearner",
                prerequisite_result=Decimal(58 + (i * 7) % 35) if gated else None, grade10_evidence_held=True,
                assigned_to=acc["N. Sibeko"],
            )
    for ref, target in booked_target.items():
        actual = Enrolment.objects.filter(plan_block=blocks[ref], is_active=True).count()
        assert actual == target, f"{ref}: {actual} enrolments, prototype shows {target} booked"

    # SES-0309 and SES-0305 were captured and locked before the demo date.
    palesa = acc["Palesa Mpana"]
    for ses_ref, blk in [("SES-0309", "PLN-11"), ("SES-0305", "PLN-12")]:
        session = Session.objects.get(reference=ses_ref)
        fac = blocks[blk].facilitator
        when = at(blocks[blk].end_date, 16, 30)
        for e in Enrolment.objects.filter(plan_block=blocks[blk]):
            Attendance.objects.create(session=session, learner=e.learner, present=True, captured_at=when, captured_by=fac)
        AttendanceRegister.objects.create(session=session, locked_at=when, locked_by=fac)

    # --- results, moderation, certificates --------------------------------------------
    results = {}
    for ref, enr, ses, assessor, mark in [
        ("RES-0288", "ENR-0498", "SES-0309", "William", 78), ("RES-0289", "ENR-0499", "SES-0309", "William", 64),
        ("RES-0290", "ENR-0500", "SES-0309", "William", 41), ("RES-0292", "ENR-0513", "SES-0312", "Thandi Ncube", 71),
        ("RES-0293", "ENR-0514", "SES-0312", "Thandi Ncube", 58), ("RES-0294", "ENR-0515", "SES-0312", "Thandi Ncube", 47),
        ("RES-0295", "ENR-0516", "SES-0312", "Thandi Ncube", 83), ("RES-0287", "ENR-0490", "SES-0305", "Naledi Phiri", 88),
    ]:
        results[ref] = Result.objects.create(
            reference=ref, enrolment=enrol[enr], session=Session.objects.get(reference=ses), assessed_by=acc[assessor],
            assessed_at=at(D("2026-09-01")), mark=Decimal(mark), outcome="Competent" if mark >= 50 else "NotYetCompetent",
            remediation_plan="" if mark >= 50 else "Re-assessment on the summative instrument after a supervised practical week.",
        )
    for ref in ["RES-0288", "RES-0289", "RES-0290", "RES-0287"]:
        Moderation.objects.create(result=results[ref], moderated_by=palesa, moderated_at=at(D("2026-09-07"), 8, 12),
                                  outcome=results[ref].outcome)

    # --- assurance --------------------------------------------------------------------
    libraries = {}
    for i, (code, name, holds, rule, owner) in enumerate([
        ("certificates", "Certificates", "Issued certificates and issue records", "Two years live, then NAS archive", "Palesa Mpana"),
        ("evidence", "Assessment evidence", "Scripts, logbooks, hours documents", "Two years live, then NAS archive", "Palesa Mpana"),
        ("moderation", "Moderation records", "Moderation instruments and outcomes", "Two years live, then NAS archive", "Palesa Mpana"),
        ("registers", "Attendance registers", "Locked registers per session", "Two years live, then NAS archive", "P. Mokoena"),
        ("manuals", "Learner manuals", "Current versions, version controlled", "Current version live; superseded archived", "Palesa Mpana"),
        ("agreements", "University agreements", "Placement agreements and 20-day reports", "Life of agreement plus two years", "P. Mokoena"),
    ]):
        libraries[code] = Library.objects.create(code=code, name=name, holds=holds, retention_rule=rule,
                                                 owner=acc[owner], sort_order=i)
    for ref, res, issued in [("CERT-2026-0412", "RES-0288", "2026-09-07"), ("CERT-2026-0410", "RES-0287", "2026-08-25")]:
        doc = Document.objects.create(library=libraries["certificates"], title=f"Certificate {ref}",
                                      entity_type="learners.certificate", entity_ref=ref,
                                      storage_key=f"certificates/2026/{ref}.pdf", state="Held")
        Certificate.objects.create(reference=ref, moderation=results[res].moderation, issued_at=at(D(issued), 10),
                                   issued_by=palesa, verification_code=f"demo{ref[-4:]}", document=doc)
    for ses in ["SES-0309", "SES-0305"]:
        Document.objects.create(library=libraries["registers"], title=f"Attendance register {ses}",
                                entity_type="delivery.session", entity_ref=ses, storage_key=f"registers/{ses}.pdf")
    for ses in ["SES-0312", "SES-0314"]:
        Document.objects.create(library=libraries["registers"], title=f"Attendance register {ses}",
                                entity_type="delivery.session", entity_ref=ses, state="Outstanding")
    Document.objects.create(library=libraries["agreements"], title="Placement report PLC-0006 — University of Johannesburg",
                            entity_type="assurance.placement", entity_ref="PLC-0006", state="Outstanding")
    for title, lib in [("PME 1 learner manual v4", "manuals"), ("Red meat learner manual v6", "manuals"),
                       ("University of Pretoria placement agreement 2026", "agreements"),
                       ("SES-0309 moderation record", "moderation"), ("SES-0309 assessment scripts", "evidence")]:
        Document.objects.create(library=libraries[lib], title=title, storage_key=f"{lib}/{title.lower().replace(' ', '-')}.pdf")

    Accreditation.objects.create(reference="ACC-0001", body=bodies["AGRISETA"],
                                 scope="Meat examination — red meat, poultry, game, PME 1 and 2",
                                 granted_on=D("2023-03-01"), expires_on=D("2028-02-29"))
    Accreditation.objects.create(reference="ACC-0002", body=bodies["SAATCA"], scope="Internal auditor training",
                                 granted_on=D("2023-12-01"), expires_on=D("2026-11-30"))
    from assurance.workflow import spread

    for held in Accreditation.objects.all():
        held.courses.set([c for c in courses.values() if c.is_accredited and c.accreditation_body_id == held.body_id])
    for ref, body, scope, owner, target, step in [
        ("ACC-P01", "QCTO", "Occupational certificate — meat inspector", "Palesa Mpana", "2027-06-30", 1),
        ("ACC-P02", "AGRISETA", "Extension of scope — game meat examination", "William", "2027-02-28", 0),
        ("ACC-P03", "SAATCA", "Renewal — internal auditor training", "Palesa Mpana", "2026-11-30", 2),
    ]:
        project = AccreditationProject.objects.create(
            reference=ref, body=bodies[body], scope=scope, owner=acc[owner], target_date=D(target), step_index=step,
            step_due=spread(D(target) - dt.timedelta(days=240), D(target)),
            step_done=[D(target) - dt.timedelta(days=240)] * step + [None] * (6 - step), step_notes=[""] * 6)
        if "game" in scope.lower():
            project.courses.set([courses["TRN-GAME"]])
        if scope.lower().startswith("renewal"):
            project.renews = Accreditation.objects.get(reference="ACC-0002")
            project.courses.set([courses["TRN-IA"]])
            project.save()
    for ref, org, blk, label, s, e, submitted in [
        ("PLC-0007", "University of Pretoria", "PLN-03", "UP cohort — September", "2026-09-07", "2026-09-18", None),
        ("PLC-0006", "University of Johannesburg", None, "UJ cohort — August", "2026-08-10", "2026-08-21", None),
        ("PLC-0005", "Tshwane University of Technology", None, "TUT cohort — July", "2026-07-06", "2026-07-17", "2026-08-03"),
    ]:
        Placement.objects.create(reference=ref, organisation=orgs[org], plan_block=blocks.get(blk) if blk else None,
                                 cohort_label=label, cohort_size=5, period_start=D(s), period_end=D(e),
                                 report_submitted_at=at(D(submitted), 12) if submitted else None)
    for ref, risk, cause, rating, trig, breach, owner, pos in [
        ("TRK-01", "KwaZulu-Natal delivery stops if the one accredited facilitator is absent", "Single cover in the province", "High",
         "Facilitator absent for more than three working days, or utilisation above 90%", None, "Palesa Mpana", "Second facilitator requested"),
        ("TRK-02", "Internal auditor delivery suspended if the SAATCA renewal lapses", "Assessment instrument update outstanding", "Medium",
         "Supporting documents incomplete 60 days before 2026-11-30", "2026-09-01", "Palesa Mpana", "Supporting documents in progress"),
        ("TRK-03", "University reports submitted after the twenty-day deadline", "Manual tracking of placement periods", "Medium",
         "Any report unsubmitted at day 15", None, "P. Mokoena", "Tracked on the partnerships register"),
    ]:
        Risk.objects.create(reference=ref, risk=risk, cause=cause, rating=rating, escalation_trigger=trig,
                            trigger_breached_at=at(D(breach), 8) if breach else None, owner=acc[owner], position=pos)

    # Advance reference counters past the seeded references so new records continue the series.
    import re

    highest = {}
    for model in [Account, Enquiry, Quotation, Organisation, Contact, PlanBlock, Session, Learner, Enrolment, Result,
                  Accreditation, AccreditationProject, Placement, Risk, Document]:
        for ref in model.objects.values_list("reference", flat=True):
            m = re.match(r"^(.*)-(\d+)$", ref)
            if m:
                highest[m.group(1)] = max(highest.get(m.group(1), 0), int(m.group(2)))
    for ref in Certificate.objects.values_list("reference", flat=True):
        prefix, n = ref.rsplit("-", 1)
        highest[prefix] = max(highest.get(prefix, 0), int(n))
    for prefix, n in highest.items():
        RefCounter.objects.update_or_create(prefix=prefix, defaults={"last_value": n})

    # The prototype's audit trail, so the screens open with history.
    for when, what, who, screen in [
        ("2026-09-07 09:22", "CERT-2026-0412 issued and filed to the depository", "Palesa Mpana", "certificates"),
        ("2026-09-08 11:05", "SES-0316 placement letters issued to UP", "P. Mokoena", "sessions"),
        ("2026-09-08 16:40", "ENQ-0421 logged from WhatsApp and routed", "P. Mokoena", "enquiries"),
        ("2026-09-09 08:12", "RES-0288 moderation recorded — competent", "Palesa Mpana", "results"),
    ]:
        from audit.models import AuditEntry

        AuditEntry.objects.create(at=timezone.make_aware(dt.datetime.fromisoformat(when)), actor=acc[who],
                                  actor_name=who, actor_role=acc[who].hub_role, what=what, screen=screen)
    record(None, "Demo data loaded from the prototype — business clock set to " + today.isoformat(), screen="system")

    if write_file:
        notes = {
            "Sipho Dlamini": "Suspended — registration lapsed 2026-06-30. Sign-in is refused and says why.",
            "William": "Registration expires 2026-09-30; move the demo clock past it and access stops that day.",
            "Thandi Ncube": "Facilitator for SES-0312 — use this account for the attendance register walkthrough.",
            "Palesa Mpana": "Head of training — the desk, moderation, certification, and the demo clock arrows.",
        }
        rows = [{"name": a.display_name, "position": a.position, "role": a.get_hub_role_display(),
                 "username": a.username, "password": credentials[a.username], "note": notes.get(a.display_name, "")}
                for a in acc.values() if a.username in credentials]
        write_logins(rows, today.isoformat())
    return credentials
