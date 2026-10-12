"""The build plan's acceptance tests and the twelve rules, exercised through the real API.

Run: python manage.py test tests
"""
import datetime as dt

from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from core.models import DemoClock
from core.seed import seed
from delivery.models import Attendance, AttendanceRegister, Session
from learners.models import Certificate, Moderation, Result


class Api(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.passwords = seed(passwords={})

    def login(self, ref):
        from identity.models import Account

        username = Account.objects.get(reference=ref).username
        r = self.client.post("/api/fsa/auth/login", {"username": username, "password": self.passwords[username]},
                             content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)

    def get(self, path):
        r = self.client.get(path)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def send(self, method, path, body=None, screen="test"):
        return getattr(self.client, method)(path, body or {}, content_type="application/json", HTTP_X_FSA_SCREEN=screen)

    def counts(self):
        return self.get("/api/fsa/nav-counts")["data"]


PALESA, THANDI, NALEDI, SIPHO, MOKOENA = "USR-0005", "USR-0007", "USR-0009", "USR-0010", "USR-0006"


def sa_id(dob: str, seq: int) -> str:
    """A well-formed test SA ID number (YYMMDD + sequence + citizenship + 8 + Luhn check digit)."""
    body = f"{dob}{seq:04d}08"
    for check in range(10):
        candidate = body + str(check)
        total = 0
        for i, ch in enumerate(reversed(candidate)):
            n = int(ch) * (2 if i % 2 else 1)
            total += n - 9 if n > 9 else n
        if total % 10 == 0:
            return candidate
    raise AssertionError("no check digit")


class NavCounts(Api):
    def test_counts_match_the_prototype_on_2026_09_09(self):
        self.login(PALESA)
        c = self.counts()
        self.assertEqual(c["StaleEnquiries"], 1)          # ENQ-0419
        self.assertEqual(c["RegistersOutstanding"], 2)    # SES-0312, SES-0314 (the report's "two")
        self.assertEqual(c["AwaitingModeration"], 4)      # RES-0292…0295
        self.assertEqual(c["AwaitingCertificate"], 1)     # RES-0289
        self.assertEqual(c["AccredFlags"], 3)             # William, Dr Steyn, Sipho
        self.assertEqual(c["GateIncomplete"], 2)          # ENR-0518 (44%), ENR-0519 (no Grade 10)
        self.assertEqual(c["PartnershipReportsDue"], 1)   # UJ, due 2026-09-10
        self.assertEqual(c["RisksEscalated"], 2)          # TRK-01 high, TRK-02 breached
        self.assertEqual(c["DepositoryOutstanding"], 3)

    def test_phase1_acceptance_badge_moves_after_a_state_change_with_nothing_cached(self):
        """A state change on one screen moves a badge count on the rail at the next navigation."""
        self.login(THANDI)
        self.assertEqual(self.counts()["RegistersOutstanding"], 2)
        marks = {r: True for r in ["LRN-1841", "LRN-1842", "LRN-1843", "LRN-1844", "LRN-1845"]}
        r = self.send("post", "/api/fsa/sessions/SES-0312/attendance", {"marks": marks}, screen="sessions")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.counts()["RegistersOutstanding"], 1)


class Desk(Api):
    def refs(self):
        return {i["ref"] for i in self.get("/api/fsa/desk")["data"]["escalated"]}

    def test_phase2_acceptance_enquiry_arrives_by_itself_and_leaves_when_answered(self):
        self.login(PALESA)
        self.assertNotIn("ENQ-0420", self.refs())  # two working days on 2026-09-09: inside the standard
        r = self.send("post", "/api/fsa/clock", {"days": 1})
        self.assertEqual(r.status_code, 200, r.content)
        desk = self.get("/api/fsa/desk")["data"]["escalated"]
        item = next(i for i in desk if i["ref"] == "ENQ-0420")
        self.assertEqual(item["trigger"], "Enquiry unanswered after two working days")
        self.assertEqual(item["triggerKind"], "SLA")
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0420/stage", {"stageIndex": 1}, screen="enquiries")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertNotIn("ENQ-0420", self.refs())

    def test_every_item_on_the_desk_names_its_trigger(self):
        self.login(PALESA)
        desk = self.get("/api/fsa/desk")["data"]
        triggers = {i["trigger"] for i in desk["escalated"]}
        self.assertTrue(all(i["trigger"] for i in desk["escalated"]))
        self.assertIn("Quote over R 50 000", triggers)
        self.assertIn("No follow-up for fourteen days", triggers)
        self.assertIn("Complaint, any channel", triggers)
        self.assertIn("Industry or partnership opportunity", triggers)
        self.assertTrue(all(r["owner"] for r in desk["running"]))

    def test_a_resolved_complaint_leaves_the_desk(self):
        self.login(PALESA)
        self.assertIn("ENQ-0422", self.refs())
        self.assertEqual(self.send("post", "/api/fsa/enquiries/ENQ-0422/resolve").status_code, 200)
        self.assertNotIn("ENQ-0422", self.refs())


class Attendance_(Api):
    def test_register_must_mark_every_learner_and_names_who_is_missing(self):
        self.login(THANDI)
        r = self.send("post", "/api/fsa/sessions/SES-0312/attendance", {"marks": {"LRN-1841": True}})
        self.assertEqual(r.status_code, 409)
        self.assertIn("Bongani Zulu is not marked present or absent", r.json()["blockedBy"])

    def test_register_locks_on_save_and_a_correction_is_a_new_entry(self):
        self.login(THANDI)
        marks = {r: True for r in ["LRN-1841", "LRN-1842", "LRN-1843", "LRN-1844", "LRN-1845"]}
        r = self.send("post", "/api/fsa/sessions/SES-0312/attendance", {"marks": marks})
        self.assertEqual(r.status_code, 200)
        self.assertIn("captured and locked", r.json()["meta"]["audit"]["what"])
        again = self.send("post", "/api/fsa/sessions/SES-0312/attendance", {"marks": marks})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["error"], "register_locked")
        fix = self.send("post", "/api/fsa/sessions/SES-0312/attendance/correction",
                        {"learnerRef": "LRN-1842", "present": False, "reason": "Left site on day 3; supervisor sign-off"})
        self.assertEqual(fix.status_code, 200, fix.content)
        rows = Attendance.objects.filter(session__reference="SES-0312", learner__reference="LRN-1842")
        self.assertEqual(rows.count(), 2)                          # original kept, correction added
        self.assertTrue(rows.get(supersedes__isnull=True).present)  # original unchanged
        detail = self.get("/api/fsa/sessions/SES-0312")["data"]
        bongani = next(l for l in detail["learners"] if l["ref"] == "LRN-1842")
        self.assertFalse(bongani["present"])

    def test_the_database_refuses_to_edit_a_captured_attendance_row(self):
        row = Attendance.objects.filter(session__reference="SES-0309").first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            Attendance.objects.filter(pk=row.pk).update(present=False)

    def test_facilitator_cannot_capture_someone_elses_session(self):
        self.login(NALEDI)
        marks = {r: True for r in ["LRN-1841", "LRN-1842", "LRN-1843", "LRN-1844", "LRN-1845"]}
        r = self.send("post", "/api/fsa/sessions/SES-0312/attendance", {"marks": marks})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"], "not_your_session")

    def test_facilitator_sees_only_own_sessions(self):
        self.login(THANDI)
        refs = {s["ref"] for s in self.get("/api/fsa/sessions")["data"]["items"]}
        self.assertEqual(refs, {"SES-0312", "SES-0318"})


class Certification(Api):
    def test_phase4_acceptance_unmoderated_result_cannot_produce_a_certificate(self):
        self.login(PALESA)
        r = self.send("post", "/api/fsa/certificates", {"resultRef": "RES-0292"})
        self.assertEqual(r.status_code, 409)
        body = r.json()
        self.assertEqual(body["error"], "not_moderated")
        self.assertIn("has not been moderated", body["blockedBy"][0])
        self.assertEqual(self.send("post", "/api/fsa/results/RES-0292/moderate", {}).status_code, 200)
        ok = self.send("post", "/api/fsa/certificates", {"resultRef": "RES-0292"})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertRegex(ok.json()["data"]["ref"], r"^CERT-2026-04\d\d$")

    def test_not_yet_competent_is_refused(self):
        self.login(PALESA)
        r = self.send("post", "/api/fsa/certificates", {"resultRef": "RES-0290"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("not yet competent", r.json()["blockedBy"][0])

    def test_facilitator_cannot_moderate_or_issue(self):
        self.login(THANDI)
        self.assertEqual(self.send("post", "/api/fsa/results/RES-0292/moderate", {}).status_code, 403)
        self.assertEqual(self.send("post", "/api/fsa/certificates", {"resultRef": "RES-0289"}).status_code, 403)

    def test_the_database_refuses_a_certificate_on_a_not_competent_moderation(self):
        moderation = Moderation.objects.get(result__reference="RES-0290")
        with self.assertRaises(DatabaseError), transaction.atomic():
            Certificate.objects.create(reference="CERT-X", moderation=moderation, issued_at=dt.datetime.now(dt.UTC),
                                       issued_by_id=moderation.moderated_by_id, verification_code="x")


class Scheduling(Api):
    def test_lapsed_facilitator_block_cannot_be_confirmed_and_says_why(self):
        self.login(PALESA)
        r = self.send("post", "/api/fsa/plan/PLN-07/confirm")
        self.assertEqual(r.status_code, 409)
        reason = r.json()["blockedBy"][0]
        self.assertIn("Sipho Dlamini", reason)
        self.assertIn("lapsed on 2026-06-30", reason)
        self.assertIn("Scheduling is blocked", reason)

    def test_expiry_inside_a_block_is_an_observation(self):
        self.login(PALESA)
        blocks = {b["ref"]: b for b in self.get("/api/fsa/plan")["data"]}
        self.assertEqual(blocks["PLN-06"]["warnings"][0]["kind"], "fill")
        self.assertTrue(any(w["kind"] == "accreditation" and w["tone"] == "bad" for w in blocks["PLN-07"]["warnings"]))

    def test_suspended_account_cannot_sign_in(self):
        r = self.client.post("/api/fsa/auth/login", {"username": "sipho.dlamini", "password": self.passwords["sipho.dlamini"]},
                             content_type="application/json")
        self.assertEqual(r.status_code, 403)
        self.assertIn("suspended", r.json()["blockedBy"][0])

    def test_account_is_refused_the_day_its_registration_lapses(self):
        self.login("USR-0008")  # William, registration expires 2026-09-30
        self.assertEqual(self.client.get("/api/fsa/me").status_code, 200)
        DemoClock.objects.filter(pk=1).update(today=dt.date(2026, 10, 1))
        self.assertEqual(self.client.get("/api/fsa/me").status_code, 401)


class EntryGate(Api):
    def test_gate_names_what_is_outstanding(self):
        self.login(MOKOENA)
        low = self.send("patch", "/api/fsa/enrolments/ENR-0518/stage")
        self.assertEqual(low.status_code, 409)
        self.assertEqual(low.json()["blockedBy"], ["Prerequisite test result is 44% — 50% is required"])
        no_g10 = self.send("patch", "/api/fsa/enrolments/ENR-0519/stage")
        self.assertEqual(no_g10.json()["blockedBy"], ["Grade 10 evidence not filed"])
        self.assertEqual(self.send("patch", "/api/fsa/enrolments/ENR-0517/stage").status_code, 200)

    def test_completing_the_gate_lets_it_advance(self):
        self.login(MOKOENA)
        self.assertEqual(self.send("patch", "/api/fsa/enrolments/ENR-0519/gate", {"grade10EvidenceHeld": True}).status_code, 200)
        self.assertEqual(self.send("patch", "/api/fsa/enrolments/ENR-0519/stage").status_code, 200)
        self.assertEqual(self.counts()["GateIncomplete"], 1)


class AuditTrail(Api):
    def test_every_mutation_returns_and_stores_its_audit_entry(self):
        self.login(PALESA)
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0421/stage", {"stageIndex": 1}, screen="enquiries")
        entry = r.json()["meta"]["audit"]
        self.assertEqual(entry["who"], "Palesa Mpana")
        trail = self.get("/api/fsa/audit?screen=enquiries")["data"]
        self.assertEqual(trail[0]["what"], "ENQ-0421 moved from New to Responded")

    def test_the_audit_trail_is_append_only(self):
        with connection.cursor() as cur, self.assertRaises(DatabaseError), transaction.atomic():
            cur.execute("UPDATE audit_auditentry SET what = 'edited'")


class SignIn(Api):
    def test_wrong_password_is_refused_without_saying_which_part_was_wrong(self):
        r = self.client.post("/api/fsa/auth/login", {"username": "palesa.mpana", "password": "wrong"}, content_type="application/json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["blockedBy"], ["The username or password is incorrect."])
        r = self.client.post("/api/fsa/auth/login", {"username": "nobody", "password": "wrong"}, content_type="application/json")
        self.assertEqual(r.json()["blockedBy"], ["The username or password is incorrect."])

    def test_five_failures_lock_the_username(self):
        for _ in range(5):
            self.client.post("/api/fsa/auth/login", {"username": "naledi.phiri", "password": "x"}, content_type="application/json")
        r = self.client.post("/api/fsa/auth/login", {"username": "naledi.phiri", "password": self.passwords["naledi.phiri"]},
                             content_type="application/json")
        self.assertEqual(r.status_code, 429)

    def test_the_service_account_cannot_sign_in(self):
        r = self.client.post("/api/fsa/auth/login", {"username": "hr.service", "password": ""}, content_type="application/json")
        self.assertEqual(r.status_code, 401)

    def test_the_picker_endpoints_are_gone(self):
        self.assertEqual(self.client.get("/api/fsa/auth/accounts").status_code, 404)

    def test_username_can_be_typed_as_the_name_and_pasted_spaces_are_ignored(self):
        for typed in ["Louis Visagie", "LOUIS.VISAGIE", "  louis.visagie  ", "Dr Riaan Steyn"]:
            expected = "riaan.steyn" if "Riaan" in typed else "louis.visagie"
            r = self.client.post("/api/fsa/auth/login", {"username": typed, "password": f" {self.passwords[expected]} "},
                                 content_type="application/json")
            self.assertEqual(r.status_code, 200, typed)


class Registration(Api):
    """How a learner becomes part of the system: the three routes and their refusals."""

    def register(self, **body):
        base = {"blockRef": "PLN-06", "consent": True, "names": "Themba Nkosi", "email": "themba@example.org",
                "learnerType": "Public", "idType": "SAID", "idNumber": sa_id("900215", 5001)}
        base.update(body)
        return self.send("post", "/api/fsa/enrolments", base, screen="enrolments")

    def test_an_enquiry_reaches_registered_only_by_registering_the_learner(self):
        self.login(MOKOENA)
        moved = self.send("patch", "/api/fsa/enquiries/ENQ-0420/stage", {"stageIndex": 3})
        self.assertEqual(moved.status_code, 409)
        self.assertEqual(moved.json()["error"], "register_learner")
        r = self.register(enquiryRef="ENQ-0420", names="Sibusiso Khumalo", idNumber=sa_id("950830", 5123),
                          prerequisiteResult=66, grade10EvidenceHeld=True)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["stage"], "Applied")
        self.assertIn("ENQ-0420 moved from New to Registered", r.json()["meta"]["audit"]["what"])
        enq = next(e for e in self.get("/api/fsa/enquiries")["data"]["items"] if e["ref"] == "ENQ-0420")
        self.assertEqual(enq["stage"], "Registered")
        self.assertEqual(enq["enrolment"], r.json()["data"]["ref"])

    def test_registration_books_a_seat_and_the_gate_still_applies(self):
        self.login(MOKOENA)
        before = next(i for i in self.get("/api/fsa/intakes?course=TRN-MEP")["data"] if i["ref"] == "PLN-06")["free"]
        r = self.register()
        self.assertEqual(r.status_code, 200, r.content)
        after = next(i for i in self.get("/api/fsa/intakes?course=TRN-MEP")["data"] if i["ref"] == "PLN-06")["free"]
        self.assertEqual(after, before - 1)
        self.assertEqual(r.json()["data"]["gateBlockedBy"], ["Prerequisite test result not captured", "Grade 10 evidence not filed"])
        self.assertEqual(self.counts()["GateIncomplete"], 3)

    def test_consent_and_details_are_required_and_named(self):
        self.login(MOKOENA)
        no_consent = self.register(consent=False)
        self.assertEqual(no_consent.json()["error"], "consent_required")
        no_name = self.register(names="")
        self.assertEqual(no_name.status_code, 422)
        self.assertIn("Row 1: the learner's name is missing.", no_name.json()["blockedBy"])

    def test_a_full_intake_and_a_second_enrolment_are_refused(self):
        self.login(MOKOENA)
        full = self.register(blockRef="PLN-03", learnerType="University", organisation="University of Pretoria")
        self.assertEqual(full.json()["error"], "intake_full")
        self.assertIn("PLN-03 has 0 of 5 seats free", full.json()["blockedBy"][0])
        twice = self.register(learnerRef="LRN-1871")  # Sibusiso Khumalo is already on PLN-06
        self.assertEqual(twice.json()["error"], "already_enrolled")

    def test_a_facilitator_cannot_register_learners(self):
        self.login(THANDI)
        self.assertEqual(self.register().status_code, 403)

    def test_group_delegates_are_registered_against_the_quotation(self):
        self.login(MOKOENA)
        delegates = [{"names": f"Chalmar delegate {i}", "idNumber": sa_id("880101", 6000 + i)} for i in range(1, 4)]
        r = self.send("post", "/api/fsa/quotations/QTE-0218/delegates", {"blockRef": "PLN-05", "delegates": delegates, "consent": True})
        self.assertEqual(r.status_code, 409)  # HACCP quote, but PLN-05 is Food hygiene: wrong course for the intake
        self.assertIn("not HACCP awareness", r.json()["blockedBy"][0])
        from delivery.models import PlanBlock
        from core.models import Stream, Venue
        from courses.models import Course
        from identity.models import Account
        haccp = Course.objects.get(code="TRN-HACCP")
        PlanBlock.objects.create(reference="PLN-20", course=haccp, stream=Stream.objects.get(code="SHORT"),
                                 facilitator=Account.objects.get(username="naledi.phiri"), venue=Venue.objects.first(),
                                 delivery_mode="Contact", start_date=dt.date(2026, 10, 1), end_date=dt.date(2026, 10, 2),
                                 capacity=16, state="Confirmed")
        ok = self.send("post", "/api/fsa/quotations/QTE-0218/delegates", {"blockRef": "PLN-20", "delegates": delegates, "consent": True})
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(len(ok.json()["data"]["enrolments"]), 3)
        self.assertIn("quotation accepted", ok.json()["meta"]["audit"]["what"])
        too_many = [{"names": f"Extra {i}", "idNumber": sa_id("870505", 7000 + i)} for i in range(10)]
        over = self.send("post", "/api/fsa/quotations/QTE-0218/delegates", {"blockRef": "PLN-20", "delegates": too_many, "consent": True})
        self.assertIn("quoted for 12 learners; 3 are already registered, so 9 more", over.json()["blockedBy"][0])
        per_learner = self.send("post", "/api/fsa/quotations/QTE-0216/delegates", {"blockRef": "PLN-04", "delegates": delegates, "consent": True})
        self.assertIn("quoted per learner", per_learner.json()["blockedBy"][0])

    def test_university_cohort_import_matches_on_student_number(self):
        self.login(MOKOENA)
        uj = next(u["ref"] for u in self.get("/api/fsa/universities")["data"] if u["name"] == "University of Johannesburg")
        students = [{"names": f"UJ student {i}", "studentNumber": f"2190{i}"} for i in range(1, 4)]
        r = self.send("post", "/api/fsa/partnerships/cohort", {"organisationRef": uj, "blockRef": "PLN-08", "students": students, "consent": True})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["imported"], 3)
        students.append({"names": "UJ student 4", "studentNumber": "21904"})
        again = self.send("post", "/api/fsa/partnerships/cohort", {"organisationRef": uj, "blockRef": "PLN-08", "students": students, "consent": True})
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual((again.json()["data"]["imported"], again.json()["data"]["skipped"]), (1, 3))  # matched on student number
        more = [{"names": f"UJ extra {i}", "studentNumber": f"2299{i}"} for i in range(3)]
        full = self.send("post", "/api/fsa/partnerships/cohort", {"organisationRef": uj, "blockRef": "PLN-08", "students": more, "consent": True})
        self.assertEqual(full.json()["error"], "intake_full")
        self.assertIn("PLN-08 has 1 of 5 seats free; this registration needs 3", full.json()["blockedBy"][0])
        missing = self.send("post", "/api/fsa/partnerships/cohort",
                            {"organisationRef": uj, "blockRef": "PLN-08", "students": [{"names": "No number"}], "consent": True})
        self.assertIn("the student number is missing", missing.json()["blockedBy"][0])



class IdentityAndSeats(Api):
    """POPIA-safe identity numbers, matching on them, and seats derived from enrolments."""

    def test_an_invalid_id_number_is_refused_and_says_why(self):
        self.login(MOKOENA)
        good = sa_id("900215", 5001)
        bad = good[:-1] + str((int(good[-1]) + 1) % 10)
        r = self.send("post", "/api/fsa/enrolments", {"blockRef": "PLN-06", "consent": True, "names": "Themba Nkosi",
                                                      "idNumber": bad})
        self.assertEqual(r.status_code, 422)
        self.assertIn("the check digit does not match", r.json()["blockedBy"][0])

    def test_the_same_id_twice_in_one_list_is_refused(self):
        self.login(MOKOENA)
        same = sa_id("880101", 6001)
        rows = [{"names": "J. Kruger", "idNumber": same}, {"names": "Johan Kruger", "idNumber": same}]
        r = self.send("post", "/api/fsa/quotations/QTE-0221/delegates", {"blockRef": "PLN-06", "delegates": rows, "consent": True})
        self.assertIn("Row 2 repeats row 1 (Johan Kruger).", r.json()["blockedBy"])

    def test_a_person_already_on_file_is_matched_not_duplicated(self):
        from learners.models import Learner

        self.login(MOKOENA)
        number = sa_id("910704", 5555)
        first = self.send("post", "/api/fsa/enrolments", {"blockRef": "PLN-06", "consent": True, "names": "Ayanda Zulu",
                                                          "learnerType": "Corporate", "organisation": "Rainbow, Hammarsdale",
                                                          "idNumber": number})
        self.assertEqual(first.status_code, 200, first.content)
        before = Learner.objects.count()
        # The same person arrives again on another client's list, spelt differently, onto another intake.
        from delivery.models import PlanBlock
        from core.models import Stream, Venue
        from identity.models import Account
        from courses.models import Course
        PlanBlock.objects.create(reference="PLN-21", course=Course.objects.get(code="TRN-MEP"), stream=Stream.objects.get(code="PME-P"),
                                 facilitator=Account.objects.get(username="thandi.ncube"), venue=Venue.objects.first(),
                                 delivery_mode="Contact", start_date=dt.date(2026, 11, 2), end_date=dt.date(2026, 11, 13),
                                 capacity=10, state="Confirmed")
        again = self.send("post", "/api/fsa/quotations/QTE-0221/delegates",
                          {"blockRef": "PLN-21", "consent": True, "delegates": [{"names": "A. Zulu", "idNumber": number}]})
        self.assertEqual(again.status_code, 200, again.content)
        self.assertEqual(Learner.objects.count(), before)          # no second record
        self.assertIn("matched existing", again.json()["meta"]["audit"]["what"])
        onto_same = self.send("post", "/api/fsa/quotations/QTE-0221/delegates",
                              {"blockRef": "PLN-06", "consent": True, "delegates": [{"names": "Ayanda Z.", "idNumber": number}]})
        self.assertEqual(onto_same.json()["error"], "already_enrolled")

    def test_the_id_number_is_never_stored_or_returned_in_the_clear(self):
        from audit.models import AuditEntry
        from django.db import connection
        from learners.models import Learner

        self.login(MOKOENA)
        number = sa_id("930312", 5777)
        r = self.send("post", "/api/fsa/enrolments", {"blockRef": "PLN-06", "consent": True, "names": "Karabo Sithole",
                                                      "idNumber": number})
        self.assertNotIn(number, r.content.decode())
        listing = self.client.get("/api/fsa/learners")
        self.assertNotIn(number, listing.content.decode())
        karabo = next(l for l in listing.json()["data"] if l["name"] == "Karabo Sithole")
        self.assertEqual(karabo["idNumber"], "SA ID •••• " + number[-4:])
        self.assertFalse(any(number in str(e.after) + e.what for e in AuditEntry.objects.all()))
        with connection.cursor() as cur:
            cur.execute("SELECT id_number_cipher FROM learners_learner WHERE names = 'Karabo Sithole'")
            stored = bytes(cur.fetchone()[0])
        self.assertNotIn(number.encode(), stored)
        from core import pii
        self.assertEqual(pii.decrypt(Learner.objects.get(names="Karabo Sithole").id_number_cipher), number)

    def test_seats_booked_is_the_count_of_enrolments(self):
        from learners.models import Enrolment

        self.login(PALESA)
        blocks = {b["ref"]: b for b in self.get("/api/fsa/plan")["data"]}
        for ref, b in blocks.items():
            self.assertEqual(b["seats"], Enrolment.objects.filter(plan_block__reference=ref, is_active=True).count(), ref)
        self.assertEqual(blocks["PLN-04"]["seats"], 6)
        self.assertEqual(blocks["PLN-05"]["seats"], 11)

    def test_a_record_from_before_id_numbers_gets_its_id_instead_of_a_twin(self):
        from learners.models import Learner

        self.login(MOKOENA)
        before = Learner.objects.filter(names="Johan Kruger").count()   # LRN-1852, seeded without an ID
        r = self.send("post", "/api/fsa/quotations/QTE-0218/delegates",
                      {"blockRef": "PLN-13", "consent": True,
                       "delegates": [{"names": "Johan Kruger", "idNumber": sa_id("840517", 5021)}]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Learner.objects.filter(names="Johan Kruger").count(), before)
        self.assertIn("matched existing LRN-1852", r.json()["meta"]["audit"]["what"])
        self.assertEqual(Learner.objects.get(reference="LRN-1852").id_last4, sa_id("840517", 5021)[-4:])
