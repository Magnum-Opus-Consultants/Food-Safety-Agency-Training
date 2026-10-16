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
        if method == "post" and path == "/api/fsa/enquiries" and body is not None and "source" not in body:
            body = {**body, "source": "Unknown"}  # "how did you hear about us" is asked on every enquiry; most tests don't care
        return getattr(self.client, method)(path, body or {}, content_type="application/json", HTTP_X_FSA_SCREEN=screen)

    def counts(self):
        return self.get("/api/fsa/nav-counts")["data"]


PALESA, THANDI, NALEDI, SIPHO, MOKOENA = "USR-0005", "USR-0007", "USR-0009", "USR-0010", "USR-0006"
NICOLE = "USR-0003"  # a director: the audit trail is read by directors and system administrators


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
        self.assertEqual(self.counts()["RegistersOutstanding"], 1)  # her own SES-0312; SES-0314 is not hers
        marks = {r: True for r in ["LRN-1841", "LRN-1842", "LRN-1843", "LRN-1844", "LRN-1845"]}
        r = self.send("post", "/api/fsa/sessions/SES-0312/attendance", {"marks": marks}, screen="sessions")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.counts()["RegistersOutstanding"], 0)


class OwnWork(Api):
    """Each person sees only what they attend to; the training manager sees the whole department."""

    def home_titles(self):
        return {a["title"] for a in self.get("/api/fsa/training/home")["data"]["attention"]}

    def test_enquiry_handler_sees_only_enquiries_enrolments_and_depository(self):
        self.login(MOKOENA)
        self.assertEqual(set(self.counts()), {"StaleEnquiries", "GateIncomplete", "DepositoryOutstanding"})
        self.assertEqual(self.home_titles(), {"Enquiries over the response period", "Quotations to follow up",
                                              "Draft quotations to issue", "Enrolments with minimum prerequisites outstanding",
                                              "Depository documents outstanding"})

    def test_facilitator_sees_only_own_registers(self):
        self.login(THANDI)
        self.assertEqual(set(self.counts()), {"RegistersOutstanding"})
        rows = self.get("/api/fsa/training/home")["data"]["attention"]
        self.assertEqual([r["title"] for r in rows], ["Attendance registers outstanding"])
        self.assertIn("SES-0312", rows[0]["detail"])
        self.assertNotIn("SES-0314", rows[0]["detail"])

    def test_training_manager_still_sees_the_whole_department(self):
        self.login(PALESA)
        self.assertIn("DeskEscalated", self.counts())
        self.assertEqual(len(self.counts()), 10)
        self.assertTrue({"Attendance registers outstanding", "Results awaiting moderation", "Certificates awaiting issue",
                         "Enquiries over the response period", "Accreditation renewal due"} <= self.home_titles())


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
        self.assertIn("cannot be confirmed until the registration is renewed", reason)

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
        self.assertEqual(no_g10.json()["blockedBy"], ["Grade 10 evidence not uploaded"])
        self.assertEqual(self.send("patch", "/api/fsa/enrolments/ENR-0517/stage").status_code, 200)

    def upload(self, ref, content=b"%PDF-1.7 grade 10 statement", name="matric.pdf"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return self.client.post(f"/api/fsa/enrolments/{ref}/grade10", {"file": SimpleUploadedFile(name, content)},
                                HTTP_X_FSA_SCREEN="enrolments")

    def test_completing_the_gate_lets_it_advance(self):
        self.login(MOKOENA)
        r = self.upload("ENR-0519")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["grade10File"]["name"], "matric.pdf")
        self.assertIn("ENR-0519 Grade 10 evidence uploaded — matric.pdf", r.json()["meta"]["audit"]["what"])
        self.assertEqual(self.send("patch", "/api/fsa/enrolments/ENR-0519/stage").status_code, 200)
        self.assertEqual(self.counts()["GateIncomplete"], 1)
        # Once the gate is verified the evidence is fixed.
        self.assertEqual(self.client.delete("/api/fsa/enrolments/ENR-0519/grade10").json()["error"], "gate_closed")

    def test_grade10_evidence_is_a_document_not_a_tick(self):
        self.login(MOKOENA)
        ticked = self.send("patch", "/api/fsa/enrolments/ENR-0519/gate", {"grade10EvidenceHeld": True})
        self.assertEqual(ticked.json()["error"], "upload_required")
        wrong = self.upload("ENR-0519", content=b"MZ: an executable, not a document", name="matric.pdf")
        self.assertEqual(wrong.status_code, 422)
        self.assertEqual(wrong.json()["message"], "That file type is not accepted.")

    def test_the_evidence_can_be_viewed_and_removing_it_deletes_the_file(self):
        from learners import evidence
        from learners.models import Enrolment

        self.login(MOKOENA)
        self.upload("ENR-0519")
        view = self.client.get("/api/fsa/enrolments/ENR-0519/grade10")
        self.assertEqual(view.status_code, 200)
        self.assertEqual(view["Content-Type"], "application/pdf")
        self.assertTrue(b"".join(view.streaming_content).startswith(b"%PDF-"))
        stored = evidence.path_of(evidence.current(Enrolment.objects.get(reference="ENR-0519")))
        self.assertTrue(stored.exists())
        with self.captureOnCommitCallbacks(execute=True):
            gone = self.client.delete("/api/fsa/enrolments/ENR-0519/grade10", HTTP_X_FSA_SCREEN="enrolments")
        self.assertEqual(gone.status_code, 200)
        self.assertIsNone(gone.json()["data"]["grade10File"])
        self.assertFalse(gone.json()["data"]["grade10"])
        self.assertFalse(stored.exists())
        self.assertEqual(self.client.get("/api/fsa/enrolments/ENR-0519/grade10").status_code, 404)
        self.client.logout()
        self.assertIn(self.client.get("/api/fsa/enrolments/ENR-0519/grade10").status_code, (401, 403))


class AuditTrail(Api):
    def test_every_mutation_returns_and_stores_its_audit_entry(self):
        self.login(PALESA)
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0421/stage", {"stageIndex": 1}, screen="enquiries")
        entry = r.json()["meta"]["audit"]
        self.assertEqual(entry["who"], "Palesa Mpana")
        self.assertEqual(self.client.get("/api/fsa/audit?screen=enquiries").status_code, 403)  # not a director
        self.login(NICOLE)
        trail = self.get("/api/fsa/audit?screen=enquiries")["data"]
        self.assertEqual(trail[0]["what"], "ENQ-0421 moved from New to Responded")

    def test_only_directors_and_system_administrators_see_the_trail(self):
        self.login(MOKOENA)
        self.assertFalse(self.get("/api/fsa/me")["data"]["canSeeAudit"])
        self.assertEqual(self.get("/api/fsa/enquiries/ENQ-0421")["data"]["history"], [])
        self.assertEqual(self.client.get("/api/fsa/audit").status_code, 403)
        self.login(PALESA)
        self.assertEqual(self.get("/api/fsa/courses/TRN-PME1")["data"]["trail"], [])
        self.login(NICOLE)
        self.assertTrue(self.get("/api/fsa/me")["data"]["canSeeAudit"])

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

    def test_a_result_below_the_minimum_cannot_be_registered(self):
        self.login(MOKOENA)
        before = self.get("/api/fsa/intakes?course=TRN-PME1")["data"]
        r = self.register(blockRef="PLN-04", prerequisiteResult=30)
        self.assertEqual(r.status_code, 422, r.content)
        self.assertEqual(r.json()["error"], "below_minimum")
        self.assertEqual(self.get("/api/fsa/intakes?course=TRN-PME1")["data"], before)  # no seat taken
        self.assertEqual(self.register(blockRef="PLN-04").status_code, 200)  # not yet written: registers, prerequisites outstanding

    def test_an_enquiry_reaches_registered_only_by_registering_the_learner(self):
        self.login(MOKOENA)
        # A company enquiry registers the people it sends, on its quotation, never the person who asked.
        moved = self.send("patch", "/api/fsa/enquiries/ENQ-0420/stage", {"stageIndex": 3})
        self.assertEqual(moved.json()["error"], "add_delegates")
        self.assertEqual(self.register(enquiryRef="ENQ-0420", names="Sibusiso Khumalo").json()["error"], "company_enquiry")
        # An individual enquiring for themselves is quoted personally and registered from the enquiry.
        logged = self.send("post", "/api/fsa/enquiries", {"names": "Brian Everest", "organisation": "MOC", "channel": "Phone",
                                                         "courseCode": "TRN-MEP", "topics": ["Quote"], "enquiringFor": "Individual"})
        e = logged.json()["data"]
        self.assertEqual(self.send("patch", f"/api/fsa/enquiries/{e['ref']}/stage", {"stageIndex": 3}).json()["error"], "register_learner")
        q = self.send("post", "/api/fsa/quotations", {"enquiryRef": e["ref"], "contactRef": e["contactRef"], "courseCode": "TRN-MEP",
                                                     "basis": "PerLearner", "learners": 1, "value": "4200", "issue": True})
        self.assertEqual(q.status_code, 200, q.content)
        corporate = [r["name"] for r in self.get("/api/fsa/accounts/corporate")["data"] if r["quotations"]]
        self.assertNotIn("MOC", corporate)  # his employer is not quoted
        r = self.register(enquiryRef=e["ref"], names="Brian Everest", idNumber=sa_id("950830", 5123), prerequisiteResult=66)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["stage"], "Registered")
        self.assertIn(f"{e['ref']} moved from Quoted to Registered; {q.json()['data']['ref']} accepted", r.json()["meta"]["audit"]["what"])
        enq = self.get(f"/api/fsa/enquiries/{e['ref']}")["data"]
        self.assertEqual((enq["stage"], enq["enrolment"]), ("Registered", r.json()["data"]["ref"]))

    def test_registration_books_a_seat_and_the_gate_still_applies(self):
        self.login(MOKOENA)
        before = next(i for i in self.get("/api/fsa/intakes?course=TRN-MEP")["data"] if i["ref"] == "PLN-06")["free"]
        r = self.register()
        self.assertEqual(r.status_code, 200, r.content)
        after = next(i for i in self.get("/api/fsa/intakes?course=TRN-MEP")["data"] if i["ref"] == "PLN-06")["free"]
        self.assertEqual(after, before - 1)
        self.assertEqual(r.json()["data"]["gateBlockedBy"], ["Prerequisite test result not captured", "Grade 10 evidence not uploaded"])
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
        # A company quoted per learner also sends its people as a list; QTE-0216 is for one learner.
        self.assertIn("was quoted for 1 learners; 0 are already registered, so 1 more can be added, not 3", per_learner.json()["blockedBy"][0])

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


class EnquiryEditing(Api):
    def test_details_can_be_corrected_and_each_change_is_audited(self):
        self.login(MOKOENA)
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0421",
                      {"names": "Lerato M. Mahlangu", "email": "lerato@karanbeef.co.za", "channel": "Phone",
                       "notes": "Called back; wants the October intake."}, screen="enquiries")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()["data"]
        self.assertEqual((d["name"], d["email"], d["channel"], d["notes"]),
                         ("Lerato M. Mahlangu", "lerato@karanbeef.co.za", "Phone", "Called back; wants the October intake."))
        what = r.json()["meta"]["audit"]["what"]
        self.assertIn("name Lerato Mahlangu → Lerato M. Mahlangu", what)
        self.assertIn("channel WhatsApp → Phone", what)
        self.assertIn("additional remarks updated", what)
        from audit.models import AuditEntry
        entry = AuditEntry.objects.filter(entity_ref="ENQ-0421").first()
        self.assertEqual(entry.before["Channel"], "WhatsApp")      # previous value kept
        self.login(NICOLE)
        self.assertEqual(self.get("/api/fsa/enquiries/ENQ-0421")["data"]["history"][0]["what"], what)

    def test_the_owner_can_be_reassigned_to_someone_who_works_the_queue(self):
        self.login(MOKOENA)
        owners = {o["name"]: o["ref"] for o in self.get("/api/fsa/enquiries/ENQ-0419")["data"]["owners"]}
        self.assertIn("N. Sibeko", owners)
        self.assertNotIn("Thandi Ncube", owners)                     # a facilitator does not work the queue
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0419", {"ownerRef": owners["N. Sibeko"]})
        self.assertEqual(r.json()["data"]["owner"], "N. Sibeko")
        bad = self.send("patch", "/api/fsa/enquiries/ENQ-0419", {"ownerRef": "USR-0007"})
        self.assertEqual(bad.status_code, 422)

    def test_refusals_name_the_problem(self):
        self.login(MOKOENA)
        blank = self.send("patch", "/api/fsa/enquiries/ENQ-0421", {"names": "  ", "email": "not-an-email"})
        self.assertEqual(blank.status_code, 422)
        self.assertIn("The enquirer's name cannot be blank.", blank.json()["blockedBy"])
        self.assertIn("not-an-email is not an email address.", blank.json()["blockedBy"])
        nothing = self.send("patch", "/api/fsa/enquiries/ENQ-0421", {"names": "Lerato Mahlangu"})
        self.assertEqual(nothing.json()["error"], "no_change")

    def test_the_course_is_locked_once_a_learner_is_registered(self):
        self.login(MOKOENA)
        d = self.send("post", "/api/fsa/quotations/QTE-0221/delegates", {"blockRef": "PLN-06", "consent": True,
                      "delegates": [{"names": "Rainbow delegate", "idNumber": sa_id("950830", 5123)}]})  # ENQ-0420's quotation
        self.assertIn("ENQ-0420 moved from New to Registered", d.json()["meta"]["audit"]["what"])
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0420", {"courseCode": "TRN-PME1"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("Change the course on the enrolment instead.", r.json()["blockedBy"][0])
        ok_edit = self.send("patch", "/api/fsa/enquiries/ENQ-0420", {"phone": "082 555 0110"})
        self.assertEqual(ok_edit.status_code, 200)

    def test_the_received_time_cannot_be_moved(self):
        self.login(MOKOENA)
        before = self.get("/api/fsa/enquiries/ENQ-0419")["data"]["receivedAt"]
        self.send("patch", "/api/fsa/enquiries/ENQ-0419", {"receivedAt": "2026-09-09T09:00:00", "notes": "x"})
        self.assertEqual(self.get("/api/fsa/enquiries/ENQ-0419")["data"]["receivedAt"], before)

    def test_a_facilitator_cannot_edit_enquiries(self):
        self.login(THANDI)
        self.assertEqual(self.send("patch", "/api/fsa/enquiries/ENQ-0421", {"notes": "x"}).status_code, 403)


class PhoneNumbers(Api):
    def test_a_namibian_number_is_stored_with_its_country_code(self):
        self.login(MOKOENA)
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0421", {"phone": "+264 081 234 5678"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["phone"], "+264 812345678")

    def test_a_local_number_is_read_as_south_african(self):
        self.login(MOKOENA)
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0421", {"phone": "082 555 0101"})
        self.assertEqual(r.json()["data"]["phone"], "+27 825550101")

    def test_a_number_without_a_country_code_is_refused_and_says_why(self):
        self.login(MOKOENA)
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0421", {"phone": "812345678"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("needs a country code", r.json()["blockedBy"][0])

    def test_logging_and_registering_store_international_numbers(self):
        self.login(MOKOENA)
        logged = self.send("post", "/api/fsa/enquiries", {"names": "Tjiuai Kambonde", "organisation": "Meatco, Windhoek", "enquiringFor": "Company",
                                                          "channel": "WhatsApp", "courseCode": "TRN-MER", "phone": "+264 81 555 0142",
                                                          "topics": ["Costs"]})
        self.assertEqual(logged.json()["data"]["phone"], "+264 815550142")
        reg = self.send("post", "/api/fsa/enrolments", {"blockRef": "PLN-06", "consent": True, "names": "Tjiuai Kambonde",
                                                        "idType": "Passport", "idNumber": "P1234567", "phone": "+264 81 555 0142"})
        self.assertEqual(reg.status_code, 200, reg.content)
        from learners.models import Learner
        self.assertEqual(Learner.objects.get(names="Tjiuai Kambonde").phone, "+264 815550142")


class EnquiryTopics(Api):
    def test_logging_needs_at_least_one_topic_and_other_needs_a_description(self):
        self.login(MOKOENA)
        base = {"names": "Pieter Botha", "channel": "Phone", "kind": "Enquiry", "courseCode": "TRN-HACCP", "enquiringFor": "Individual"}
        none = self.send("post", "/api/fsa/enquiries", base)
        self.assertEqual(none.status_code, 422)
        self.assertIn("Tick at least one thing they asked about", none.json()["blockedBy"][0])
        blank_other = self.send("post", "/api/fsa/enquiries", {**base, "topics": ["Costs", "Other"]})
        self.assertIn("Describe the other question they asked.", blank_other.json()["blockedBy"])
        ok_ = self.send("post", "/api/fsa/enquiries", {**base, "topics": ["Other", "Costs"], "topicOther": "Can delegates write in Afrikaans?"})
        self.assertEqual(ok_.status_code, 200, ok_.content)
        self.assertEqual(ok_.json()["data"]["topics"], ["Costs", "Other"])           # standard order
        self.assertEqual(ok_.json()["data"]["topicLabels"], ["Costs", "Other: Can delegates write in Afrikaans?"])

    def test_topics_can_be_changed_and_the_change_is_audited(self):
        self.login(MOKOENA)
        r = self.send("patch", "/api/fsa/enquiries/ENQ-0421", {"topics": ["Costs", "Delivery"]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("asked about Costs, Duration → Costs, Online or in person", r.json()["meta"]["audit"]["what"])
        cleared = self.send("patch", "/api/fsa/enquiries/ENQ-0421", {"topics": []})
        self.assertEqual(cleared.status_code, 422)

    def test_complaints_carry_details_not_topics(self):
        self.login(MOKOENA)
        r = self.send("post", "/api/fsa/enquiries", {"names": "Abattoir manager", "channel": "Email", "kind": "Complaint",
                                                     "topics": ["Costs"], "interest": "Certificate not received"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["topics"], [])
        no_details = self.send("post", "/api/fsa/enquiries", {"names": "Abattoir manager", "channel": "Email", "kind": "Complaint"})
        self.assertIn("Describe the complaint.", no_details.json()["blockedBy"])

    def test_the_board_counts_what_was_asked_this_month(self):
        self.login(MOKOENA)
        asked = {a["label"]: a["n"] for a in self.get("/api/fsa/enquiries")["data"]["askedThisMonth"]}
        self.assertEqual(asked["Costs"], 3)   # ENQ-0421, 0419, 0417 received in September

    def test_organisation_email_and_phone_are_optional(self):
        self.login(MOKOENA)
        r = self.send("post", "/api/fsa/enquiries", {"names": "Walk-in caller", "channel": "Phone", "topics": ["Duration"], "enquiringFor": "Individual"})
        self.assertEqual(r.status_code, 200, r.content)
        ref = r.json()["data"]["ref"]
        cleared = self.send("patch", f"/api/fsa/enquiries/{ref}", {"organisation": "", "email": "", "phone": "", "topics": ["Costs"]})
        self.assertEqual(cleared.status_code, 200, cleared.content)


class EnquiryBoardByWeek(Api):
    def test_the_board_shows_one_week_and_carries_open_work_forward(self):
        self.login(MOKOENA)
        r = self.get("/api/fsa/enquiries")
        week = r["meta"]["period"]
        self.assertEqual((week["start"], week["end"], week["current"]), ("2026-09-07", "2026-09-13", True))
        for e in r["data"]["items"]:
            if e["carriedOver"]:
                self.assertLess(e["receivedOn"], week["start"])
                self.assertLess(e["stageIndex"], 3, f"{e['ref']} is closed and should not be carried over")
            else:
                self.assertTrue(week["start"] <= e["receivedOn"] <= week["end"])
        earlier = self.get(f"/api/fsa/enquiries?date={week['previous']}")
        self.assertFalse(earlier["meta"]["period"]["current"])
        self.assertFalse(any(e["carriedOver"] for e in earlier["data"]["items"]))
        for e in earlier["data"]["items"]:
            self.assertTrue("2026-08-31" <= e["receivedOn"] <= "2026-09-06")

    def test_search_ignores_the_week(self):
        self.login(MOKOENA)
        found = self.get("/api/fsa/enquiries?q=ENQ-0408&date=2020-01-06")["data"]["items"]
        self.assertEqual([e["ref"] for e in found], ["ENQ-0408"])

    def test_a_month_or_a_year_can_be_chosen_instead(self):
        self.login(MOKOENA)
        month = self.get("/api/fsa/enquiries?period=month&date=2026-08-20")["meta"]["period"]
        self.assertEqual((month["start"], month["end"], month["previous"], month["next"], month["current"]),
                         ("2026-08-01", "2026-08-31", "2026-07-01", "2026-09-01", False))
        year = self.get("/api/fsa/enquiries?period=year")
        self.assertEqual((year["meta"]["period"]["start"], year["meta"]["period"]["end"]), ("2026-01-01", "2026-12-31"))
        self.assertTrue(year["meta"]["period"]["current"])
        self.assertGreaterEqual(len(year["data"]["items"]), len(self.get("/api/fsa/enquiries")["data"]["items"]))
        self.assertEqual(self.client.get("/api/fsa/enquiries?period=decade").status_code, 422)


class CourseCatalogue(Api):
    def test_a_course_is_added_with_its_prerequisites(self):
        self.login(PALESA)
        r = self.send("post", "/api/fsa/courses", {
            "code": "trn-pme3", "title": "PME 3 — senior meat examiner", "service": "IMI", "stream": "PME", "days": 10,
            "mode": "Contact", "body": "AGRISETA", "kind": "PriorCourse", "priorCourse": "TRN-PME2"}, screen="catalogue")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["code"], "TRN-PME3")
        self.assertEqual(r.json()["data"]["entryRequirement"], "PME 2 competent")
        self.assertIn("TRN-PME3 PME 3 — senior meat examiner added to the catalogue", r.json()["meta"]["audit"]["what"])
        again = self.send("post", "/api/fsa/courses", {"code": "TRN-PME3", "title": "x", "service": "IMI", "stream": "PME",
                                                      "days": 1, "mode": "Contact", "kind": "None"})
        self.assertEqual(again.status_code, 422)
        self.assertIn("already in the catalogue", again.json()["blockedBy"][0])
        self.login(MOKOENA)
        self.assertEqual(self.send("post", "/api/fsa/courses", {"code": "TRN-X1", "title": "x", "service": "IMI", "stream": "PME",
                                                                "days": 1, "mode": "Contact", "kind": "None"}).status_code, 403)

    def test_prerequisites_change_only_from_the_next_intake_without_learners(self):
        self.login(PALESA)
        change = {"kind": "PrerequisiteAndGrade10", "passMark": 60, "reason": "Regulation R.1072 amendment"}
        early = self.send("post", "/api/fsa/courses/TRN-PME1/requirements", {**change, "effectiveFrom": "2026-09-10"})
        self.assertEqual(early.status_code, 422)
        self.assertIn("PLN-04 (starts 2026-09-14)", early.json()["blockedBy"][0])
        self.assertIn("from 2026-09-15", early.json()["blockedBy"][0])
        ok_ = self.send("post", "/api/fsa/courses/TRN-PME1/requirements", {**change, "effectiveFrom": "2026-09-15"})
        self.assertEqual(ok_.status_code, 200, ok_.content)
        self.assertEqual(ok_.json()["data"]["entryRequirement"], "Prerequisite test ≥ 50% and Grade 10")  # still in force today
        self.assertEqual(ok_.json()["data"]["upcoming"][0]["label"], "Prerequisite test ≥ 60% and Grade 10")
        # Learners registering on PLN-04 keep the 50% they were registered under.
        self.login(MOKOENA)
        intake = [i for i in self.get("/api/fsa/intakes?course=TRN-PME1")["data"] if i["ref"] == "PLN-04"][0]
        self.assertEqual(intake["passMark"], 50)
        self.assertEqual(self.register(blockRef="PLN-04", prerequisiteResult=55).status_code, 200)
        self.login(NICOLE)
        detail = self.get("/api/fsa/courses/TRN-PME1")["data"]
        self.assertEqual([v["version"] for v in detail["versions"]], [2, 1])
        self.assertIn("entry requirement version 2: Prerequisite test ≥ 50% and Grade 10 → Prerequisite test ≥ 60% and Grade 10, "
                      "from 2026-09-15 — Regulation R.1072 amendment", detail["trail"][0]["what"])

    def register(self, **body):
        base = {"blockRef": "PLN-06", "consent": True, "names": "Lerato Dlamini", "learnerType": "Public",
                "idType": "SAID", "idNumber": sa_id("910304", 5034)}
        base.update(body)
        return self.send("post", "/api/fsa/enrolments", base, screen="enrolments")

    def test_the_requirement_history_cannot_be_edited_or_deleted(self):
        from django.db import DatabaseError, transaction
        from courses.models import CourseRequirement

        first = CourseRequirement.objects.get(course__code="TRN-PME1", version=1)
        with self.assertRaises(DatabaseError), transaction.atomic():
            CourseRequirement.objects.filter(pk=first.pk).update(reason="rewritten")
        with self.assertRaises(DatabaseError), transaction.atomic():
            CourseRequirement.objects.filter(pk=first.pk).delete()

    def test_course_details_are_edited_with_a_trail(self):
        self.login(PALESA)
        r = self.send("patch", "/api/fsa/courses/TRN-HACCP", {"title": "HACCP awareness", "service": "AUD", "stream": "SHORT",
                                                              "days": 3, "mode": "Contact or online", "body": ""})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("TRN-HACCP course details edited — duration 2 days → 3 days", r.json()["meta"]["audit"]["what"])
        self.login(NICOLE)
        self.assertEqual(self.get("/api/fsa/courses/TRN-HACCP")["data"]["trail"][0]["what"], r.json()["meta"]["audit"]["what"])


class ClientsAndQuotations(Api):
    def new_client(self, name="Karan Beef, Heidelberg Feedlot"):
        return self.send("post", "/api/fsa/clients", {"name": name, "sector": "Red meat", "contactNames": "Anele Zungu",
                                                      "email": "anele@karan.example", "phone": "082 555 0199"}, screen="quotes")

    def test_a_client_is_added_then_quoted_issued_and_given_its_delegates(self):
        self.login(MOKOENA)
        c = self.new_client()
        self.assertEqual(c.status_code, 200, c.content)
        client, contact = c.json()["data"]["ref"], c.json()["data"]["contactRef"]
        self.assertEqual(c.json()["data"]["contacts"][0]["phone"], "+27 825550199")
        self.assertEqual(self.new_client("karan beef, heidelberg feedlot").status_code, 422)  # no twin companies
        q = self.send("post", "/api/fsa/quotations", {"organisationRef": client, "contactRef": contact, "courseCode": "TRN-HACCP",
                                                     "basis": "PerGroup", "learners": 3, "value": "12 600", "issue": True}, screen="quotes")
        self.assertEqual(q.status_code, 200, q.content)
        self.assertEqual(q.json()["data"]["state"], "Issued")
        self.assertIn("issued to Karan Beef, Heidelberg Feedlot; follow-up due 2026-09-23", q.json()["meta"]["audit"]["what"])
        ref = q.json()["data"]["ref"]
        rows = [{"names": f"Karan delegate {i}", "idNumber": sa_id("870612", 6100 + i)} for i in range(1, 4)]
        d = self.send("post", f"/api/fsa/quotations/{ref}/delegates", {"blockRef": "PLN-13", "delegates": rows, "consent": True})
        self.assertEqual(d.status_code, 200, d.content)

    def test_over_r50000_waits_for_the_head_of_trainings_approval(self):
        self.login(MOKOENA)
        c = self.new_client().json()["data"]
        q = self.send("post", "/api/fsa/quotations", {"organisationRef": c["ref"], "contactRef": c["contactRef"], "courseCode": "TRN-MER",
                                                     "basis": "PerGroup", "learners": 20, "value": "84000", "issue": True})
        self.assertEqual(q.json()["data"]["state"], "Draft")
        ref = q.json()["data"]["ref"]
        refused = self.send("post", f"/api/fsa/quotations/{ref}/issue")
        self.assertIn("head of department approves it before it is issued", refused.json()["blockedBy"][0])
        self.assertEqual(self.send("post", f"/api/fsa/quotations/{ref}/approve").status_code, 403)
        self.login(PALESA)
        self.assertEqual(self.send("post", f"/api/fsa/quotations/{ref}/approve").status_code, 200)
        self.login(MOKOENA)
        self.assertEqual(self.send("post", f"/api/fsa/quotations/{ref}/issue").status_code, 200)


class QuotingAnEnquiry(Api):
    def test_an_enquiry_reaches_quoted_only_through_a_quotation_that_the_card_shows(self):
        self.login(MOKOENA)
        moved = self.send("patch", "/api/fsa/enquiries/ENQ-0419/stage", {"stageIndex": 2})
        self.assertEqual(moved.json()["error"], "create_quotation")
        enq = self.get("/api/fsa/enquiries/ENQ-0420")["data"]
        self.assertEqual(enq["quotations"][0]["ref"], "QTE-0221")
        card = [e for e in self.get("/api/fsa/enquiries?q=ENQ-0421")["data"]["items"] if e["ref"] == "ENQ-0421"][0]
        q = self.send("post", "/api/fsa/quotations", {"enquiryRef": "ENQ-0421", "organisationRef": card["orgRef"],
                                                     "contactRef": card["contactRef"], "courseCode": "TRN-MER",
                                                     "basis": "PerGroup" if card["orgRef"] else "PerLearner",
                                                     "learners": 2, "value": "8400", "issue": True}, screen="enquiries")
        self.assertEqual(q.status_code, 200, q.content)
        self.assertIn("ENQ-0421 moved from", q.json()["meta"]["audit"]["what"])
        after = self.get("/api/fsa/enquiries/ENQ-0421")["data"]
        self.assertEqual(after["stage"], "Quoted")
        self.assertEqual(after["quotations"][0]["value"].replace(" ", " "), "R 8 400")



class CompanyOrIndividual(Api):
    def test_an_individual_is_registered_directly_and_never_quoted(self):
        self.login(MOKOENA)
        unsaid = self.send("post", "/api/fsa/enquiries", {"names": "Thabo Molefe", "channel": "Phone", "topics": ["Costs"]})
        self.assertIn("for a company or for themselves", unsaid.json()["blockedBy"][0])
        no_company = self.send("post", "/api/fsa/enquiries", {"names": "Thabo Molefe", "channel": "Phone", "topics": ["Costs"],
                                                              "enquiringFor": "Company"})
        self.assertIn("needs the company's name", no_company.json()["blockedBy"][0])
        # Works at a company, but asks for himself: the employer is kept, the enquiry is an individual's.
        r = self.send("post", "/api/fsa/enquiries", {"names": "Thabo Molefe", "organisation": "Karan Beef, Heidelberg",
                                                    "channel": "Phone", "topics": ["Costs"], "courseCode": "TRN-HACCP",
                                                    "enquiringFor": "Individual"})
        self.assertEqual(r.status_code, 200, r.content)
        e = r.json()["data"]
        self.assertEqual((e["enquiringFor"], e["org"]), ("Individual", "Karan Beef, Heidelberg"))
        q = self.send("post", "/api/fsa/quotations", {"enquiryRef": e["ref"], "contactRef": e["contactRef"], "courseCode": "TRN-HACCP",
                                                     "basis": "PerGroup", "learners": 3, "value": "6300"})
        self.assertIn("enquiring for themselves: quote per learner", q.json()["blockedBy"][0])
        # The same person can be re-classified if they were in fact asking for their company.
        fixed = self.send("patch", f"/api/fsa/enquiries/{e['ref']}", {"enquiringFor": "Company"})
        self.assertEqual(fixed.status_code, 200, fixed.content)
        self.assertIn("enquiring for For themselves (individual) → For a company", fixed.json()["meta"]["audit"]["what"])


class Accounts(Api):
    def test_companies_and_individuals_are_listed_apart(self):
        self.login(MOKOENA)
        corporate = {r["name"]: r for r in self.get("/api/fsa/accounts/corporate")["data"]}
        self.assertIn("Rainbow, Hammarsdale", corporate)
        self.assertNotIn("University of Pretoria", corporate)
        rainbow = self.get(f"/api/fsa/accounts/corporate/{corporate['Rainbow, Hammarsdale']['ref']}")["data"]
        self.assertEqual(rainbow["quotations"][0]["ref"], "QTE-0221")
        self.send("post", "/api/fsa/enquiries", {"names": "Thabo Molefe", "organisation": "Karan Beef, Heidelberg", "channel": "Phone",
                                                 "topics": ["Costs"], "enquiringFor": "Individual"})
        public = self.get("/api/fsa/accounts/public")["data"]
        thabo = [r for r in public if r["name"] == "Thabo Molefe" and r["enquiry"]][0]
        self.assertEqual(thabo["employer"], "Karan Beef, Heidelberg")
        karan = self.get(f"/api/fsa/accounts/corporate/{corporate['Karan Beef, Heidelberg']['ref']}")["data"]
        self.assertNotIn(thabo["enquiry"], [e["ref"] for e in karan["enquiries"] if e["for"] == "Company"])


class QuotationDetail(Api):
    def test_a_quotation_opens_with_its_enquiry_contact_and_people(self):
        self.login(MOKOENA)
        d = self.get("/api/fsa/quotations/QTE-0221")["data"]
        self.assertEqual((d["client"], d["contact"]["names"], d["enquiry"]["ref"], d["learners"]),
                         ("Rainbow, Hammarsdale", "Sibusiso Khumalo", "ENQ-0420", 16))
        self.assertEqual(d["approval"], "Needed: over R 50 000")
        self.assertEqual(d["perLearner"].replace("\u2009", " "), "R 4 275")
        self.assertEqual(self.client.get("/api/fsa/quotations/QTE-9999").status_code, 404)


class DeskAccess(Api):
    def test_the_desk_is_the_head_of_departments_not_the_enquiry_handlers(self):
        self.login(MOKOENA)
        self.assertFalse(self.get("/api/fsa/me")["data"]["canSeeDesk"])
        self.assertEqual(self.client.get("/api/fsa/desk").status_code, 403)
        self.login(PALESA)
        self.assertTrue(self.get("/api/fsa/me")["data"]["canSeeDesk"])
        self.assertEqual(self.client.get("/api/fsa/desk").status_code, 200)
        self.login(NICOLE)
        self.assertEqual(self.client.get("/api/fsa/desk").status_code, 200)



class EditingADraft(Api):
    def draft(self):
        self.login(MOKOENA)
        c = self.send("post", "/api/fsa/clients", {"name": "Test Meats", "contactNames": "Jan Broader"}).json()["data"]
        q = self.send("post", "/api/fsa/quotations", {"organisationRef": c["ref"], "contactRef": c["contactRef"], "courseCode": "TRN-PME1",
                                                     "basis": "PerGroup", "learners": 20, "value": "70000", "issue": True})
        return q.json()["data"]["ref"]

    def test_the_head_of_training_edits_a_draft_then_approves_it(self):
        ref = self.draft()
        self.assertEqual(self.send("patch", f"/api/fsa/quotations/{ref}", {"value": "84000", "approve": True}).status_code, 403)
        self.login(PALESA)
        r = self.send("patch", f"/api/fsa/quotations/{ref}", {"value": "84 000", "approve": True})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("value R", r.json()["meta"]["audit"]["what"])
        self.assertIn("approved at R", r.json()["meta"]["audit"]["what"])
        d = self.get(f"/api/fsa/quotations/{ref}")["data"]
        self.assertFalse(d["needsApproval"])
        self.login(MOKOENA)
        self.assertEqual(self.send("post", f"/api/fsa/quotations/{ref}/issue").status_code, 200)

    def test_only_the_head_of_department_edits_and_an_issued_quotation_stands(self):
        ref = self.draft()
        self.login(PALESA)
        self.send("post", f"/api/fsa/quotations/{ref}/approve")
        self.login(MOKOENA)
        self.assertEqual(self.send("patch", f"/api/fsa/quotations/{ref}", {"learners": 24}).status_code, 403)
        self.assertFalse(self.get(f"/api/fsa/quotations/{ref}")["data"]["canEdit"])
        self.login(PALESA)
        issued = self.send("patch", "/api/fsa/quotations/QTE-0218", {"value": "1"})
        self.assertEqual(issued.json()["error"], "issued")



class PlanningIntakes(Api):
    def fields(self, **kw):
        from identity.models import Account

        base = {"courseCode": "TRN-HACCP", "facilitatorRef": Account.objects.get(username="naledi.phiri").reference, "venueId": None,
                "newVenue": "Durban training centre", "mode": "Contact", "cadence": "AdHoc", "start": "2026-10-19",
                "end": "2026-10-20", "capacity": 16, "hours": 0, "notes": ""}
        base.update(kw)
        return base

    def test_the_head_of_department_adds_an_intake_that_can_take_registrations(self):
        self.login(MOKOENA)
        self.assertEqual(self.send("post", "/api/fsa/plan", self.fields()).status_code, 403)
        self.login(PALESA)
        r = self.send("post", "/api/fsa/plan", self.fields(), screen="plan")
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()["data"]
        self.assertEqual((d["state"], d["capacity"], d["venue"]), ("Draft", 16, "Durban training centre"))
        self.assertEqual(d["sessionCount"], 2)  # a two-day block course meets on both days
        self.assertIn("planned as a draft", r.json()["meta"]["audit"]["what"])
        self.assertIn(d["ref"], [i["ref"] for i in self.get("/api/fsa/intakes?course=TRN-HACCP")["data"]])
        past = self.send("post", "/api/fsa/plan", self.fields(start="2026-09-01", end="2026-09-02"))
        self.assertIn("cannot be planned to start in the past", past.json()["blockedBy"][0])

    def test_moving_an_intake_with_learners_needs_a_reason_and_lists_who_to_tell(self):
        self.login(PALESA)
        ref = self.send("post", "/api/fsa/plan", self.fields()).json()["data"]["ref"]
        self.login(MOKOENA)
        self.send("post", "/api/fsa/enrolments", {"blockRef": ref, "consent": True, "names": "Thabo Mokoena", "learnerType": "Public",
                                                  "idType": "SAID", "idNumber": sa_id("900215", 5001), "email": "thabo@example.org"})
        self.login(PALESA)
        moved = self.fields(start="2026-10-26", end="2026-10-27")
        self.assertEqual(self.send("patch", f"/api/fsa/plan/{ref}", moved).json()["error"], "reason_needed")
        r = self.send("patch", f"/api/fsa/plan/{ref}", {**moved, "reason": "Facilitator on leave"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("postponed", r.json()["meta"]["audit"]["what"])
        self.assertEqual(r.json()["meta"]["affected"][0]["email"], "thabo@example.org")
        small = self.send("patch", f"/api/fsa/plan/{ref}", {**moved, "capacity": 0})
        self.assertEqual(small.status_code, 422)
        c = self.send("post", f"/api/fsa/plan/{ref}/cancel", {"reason": "Too few learners"})
        self.assertEqual(c.json()["data"]["state"], "Cancelled")
        self.assertEqual(len(c.json()["meta"]["affected"]), 1)
        self.assertNotIn(ref, [i["ref"] for i in self.get("/api/fsa/intakes?course=TRN-HACCP")["data"]])

    def test_a_started_intake_is_not_replanned(self):
        self.login(PALESA)
        r = self.send("post", "/api/fsa/plan/PLN-11/cancel", {"reason": "x"})
        self.assertEqual(r.json()["error"], "started")



class FacilitatorRegistrations(Api):
    def test_a_renewal_is_recorded_lifts_the_block_and_keeps_the_history(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.login(MOKOENA)
        self.assertEqual(self.send("post", "/api/fsa/facilitators/USR-0008/registrations",
                                   {"registrationType": "Assessor — meat examination", "body": "AGRISETA", "expires": "2029-09-30"}).status_code, 403)
        self.login(PALESA)
        plan = {b["ref"]: b for b in self.get("/api/fsa/plan")["data"]}
        self.assertTrue(plan["PLN-10"]["confirmBlockedBy"])  # William lapsed
        r = self.send("post", "/api/fsa/facilitators/USR-0008/registrations",
                      {"registrationType": "Assessor — meat examination", "body": "AGRISETA", "number": "AGR-123",
                       "issued": "2026-09-01", "expires": "2029-09-30"}, screen="facilitators")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("renewed, valid to 2029-09-30 (was 2026-09-30)", r.json()["meta"]["audit"]["what"])
        up = self.client.post(f"/api/fsa/facilitators/registrations/{r.json()['data']['id']}/certificate",
                              {"file": SimpleUploadedFile("cert.pdf", b"%PDF-1.7 certificate")})
        self.assertEqual(up.status_code, 200, up.content)
        d = self.get("/api/fsa/facilitators/USR-0008")["data"]
        self.assertEqual([x["expires"] for x in d["registrations"]], ["2029-09-30", "2026-09-30"])
        self.assertEqual(d["registrations"][0]["certificate"]["name"], "cert.pdf")
        plan = {b["ref"]: b for b in self.get("/api/fsa/plan")["data"]}
        self.assertEqual(plan["PLN-10"]["confirmBlockedBy"], [])
        expired = self.send("post", "/api/fsa/facilitators/USR-0008/registrations",
                            {"registrationType": "x", "body": "AGRISETA", "expires": "2026-01-01"})
        self.assertEqual(expired.status_code, 422)


class IntakeWarningsFollowTheIntakeDates(Api):
    def test_a_finished_intake_carries_no_warnings(self):
        self.login(PALESA)
        plan = {b["ref"]: b for b in self.get("/api/fsa/plan")["data"]}
        self.assertEqual(plan["PLN-11"]["warnings"], [])  # ran in August; nothing left to act on


class FacilitatorSeesOwnRegistration(Api):
    def test_a_facilitator_sees_only_their_own_registration(self):
        self.login(THANDI)
        rows = self.get("/api/fsa/facilitators")["data"]
        self.assertEqual([r["name"] for r in rows], ["Thandi Ncube"])
        self.assertEqual(self.client.get("/api/fsa/facilitators/USR-0008").status_code, 403)
        self.login(PALESA)
        self.assertGreater(len(self.get("/api/fsa/facilitators")["data"]), 1)



class EmptyRegistersAndLateEntries(Api):
    def test_an_empty_register_is_not_locked_and_a_late_learner_is_added_without_unlocking(self):
        from learners.models import Enrolment

        self.login(THANDI)
        # PLN-06 (SES-0318, running 5 to 16 October): its two learners are registered, not confirmed.
        self.post_clock(30)
        d = self.get("/api/fsa/sessions/SES-0318")["data"]
        self.assertEqual(d["learners"], [])
        self.assertIn("A register is not locked empty", d["captureBlockedBy"][0])
        self.assertEqual(len(d["notOnRoster"]), 2)
        self.assertEqual(self.send("post", "/api/fsa/sessions/SES-0318/attendance", {"marks": {}}).status_code, 409)

    def post_clock(self, days):
        from core.models import DemoClock
        import datetime as dt
        DemoClock.objects.update_or_create(pk=1, defaults={"today": dt.date(2026, 10, 8)})


    def test_a_learner_confirmed_after_the_lock_is_added_as_a_late_entry(self):
        from delivery.models import AttendanceRegister, PlanBlock
        from learners.models import Enrolment, Learner

        block = PlanBlock.objects.get(reference="PLN-11")  # SES-0309, locked in August
        late = Learner.objects.create(names="Late Learner", learner_type="Public")
        Enrolment.objects.create(learner=late, course=block.course, plan_block=block, basis="PerLearner", stage_index=1)
        self.login(PALESA)
        d = self.get("/api/fsa/sessions/SES-0309")["data"]
        row = [l for l in d["learners"] if l["name"] == "Late Learner"][0]
        self.assertIsNone(row["present"])
        no_reason = self.send("post", "/api/fsa/sessions/SES-0309/attendance/late", {"learnerRef": late.reference, "present": True})
        self.assertEqual(no_reason.status_code, 409)
        r = self.send("post", "/api/fsa/sessions/SES-0309/attendance/late",
                      {"learnerRef": late.reference, "present": True, "reason": "Confirmed after the register was captured"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("late entry for Late Learner: present", r.json()["meta"]["audit"]["what"])
        self.assertTrue(AttendanceRegister.objects.filter(session__reference="SES-0309").exists())  # still locked
        again = self.send("post", "/api/fsa/sessions/SES-0309/attendance/late",
                          {"learnerRef": late.reference, "present": False, "reason": "x"})
        self.assertEqual(again.json()["error"], "already_marked")



class IntakeSchedules(Api):
    def intake(self, **kw):
        from identity.models import Account

        base = {"courseCode": "TRN-HACCP", "facilitatorRef": Account.objects.get(username="naledi.phiri").reference, "venueId": None,
                "newVenue": "Durban training centre", "mode": "Online", "cadence": "AdHoc", "capacity": 16, "hours": 0, "notes": ""}
        base.update(kw)
        return self.send("post", "/api/fsa/plan", base, screen="plan")

    def test_a_class_twice_a_week_gets_a_session_for_each_meeting(self):
        self.login(PALESA)
        # Tuesday and Thursday, 3 November to 22 December 2026: fifteen meetings (no public holiday falls on them).
        r = self.intake(schedule="Weekly", weekdays=[1, 3], start="2026-11-03", end="2026-12-22", startsAt="18:00", endsAt="20:00")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["sessionCount"], 15)
        self.assertIn("every Tuesday and Thursday, 18:00–20:00: 15 sessions", r.json()["meta"]["audit"]["what"])
        ref = r.json()["data"]["ref"]
        sessions = [x for x in self.get("/api/fsa/sessions")["data"]["items"] if x["block"] == ref]
        self.assertEqual((sessions[0]["day"], sessions[0]["sequence"], sessions[0]["of"]), ("2026-11-03", 1, 15))
        self.assertEqual(sessions[0]["registerState"], "Not yet delivered")
        # Moving it to Mondays only keeps the plan in step: eight Mondays from 2 November to 21 December.
        moved = self.send("patch", f"/api/fsa/plan/{ref}", {**self.intake_fields(), "schedule": "Weekly", "weekdays": [0],
                                                             "start": "2026-11-02", "end": "2026-12-21"})
        self.assertEqual(moved.json()["data"]["sessionCount"], 8)

    def intake_fields(self):
        from identity.models import Account

        return {"courseCode": "TRN-HACCP", "facilitatorRef": Account.objects.get(username="naledi.phiri").reference, "venueId": None,
                "newVenue": "Durban training centre", "mode": "Online", "cadence": "AdHoc", "capacity": 16, "hours": 0, "notes": ""}

    def test_one_day_and_block_courses(self):
        self.login(PALESA)
        one = self.intake(schedule="Single", start="2026-10-20", end="2026-10-20")
        self.assertEqual(one.json()["data"]["sessionCount"], 1)
        block = self.intake(schedule="Block", start="2026-10-19", end="2026-10-30")  # two working weeks
        self.assertEqual(block.json()["data"]["sessionCount"], 10)
        no_days = self.intake(schedule="Weekly", weekdays=[], start="2026-10-19", end="2026-10-30")
        self.assertIn("Choose the days of the week", no_days.json()["blockedBy"][0])



class UserManagement(Api):
    def test_the_head_of_department_adds_a_facilitator_and_changes_access(self):
        self.login(MOKOENA)
        self.assertEqual(self.client.get("/api/fsa/users").status_code, 403)
        self.login(PALESA)
        self.assertTrue(self.get("/api/fsa/me")["data"]["canManageUsers"])
        r = self.send("post", "/api/fsa/users", {"name": "Lindiwe Dube", "email": "lindiwe@fsa.example", "role": "Facilitator",
                                                 "position": "Facilitator — short courses", "reportsTo": PALESA}, screen="users")
        self.assertEqual(r.status_code, 200, r.content)
        ref, username, password = r.json()["data"]["ref"], r.json()["data"]["username"], r.json()["data"]["password"]
        self.assertEqual(username, "lindiwe.dube")
        self.assertNotIn(password, r.json()["meta"]["audit"]["what"])
        self.client.logout()
        signed = self.client.post("/api/fsa/auth/login", {"username": username, "password": password}, content_type="application/json")
        self.assertEqual(signed.status_code, 200)
        self.login(PALESA)
        moved = self.send("patch", f"/api/fsa/users/{ref}", {"role": "EnquiryHandler"})
        self.assertIn("role Facilitator → Enquiry handler", moved.json()["meta"]["audit"]["what"])
        self.assertIn("access changed", moved.json()["meta"]["audit"]["what"])
        grants = [u for u in self.get("/api/fsa/users")["data"] if u["ref"] == ref][0]["grants"]
        self.assertEqual(grants["demand"], ["write", "all"])
        self.assertEqual(self.send("post", f"/api/fsa/users/{ref}/suspend", {"reason": "Left FSA"}).status_code, 200)
        self.assertEqual(self.send("post", f"/api/fsa/users/{ref}/reinstate").status_code, 200)

    def test_managers_cannot_change_themselves_or_give_restricted_roles(self):
        self.login(PALESA)
        self.assertEqual(self.send("patch", f"/api/fsa/users/{PALESA}", {"role": "Director"}).status_code, 403)
        self.assertEqual(self.send("post", f"/api/fsa/users/{PALESA}/suspend", {"reason": "x"}).status_code, 403)
        self.assertEqual(self.send("post", "/api/fsa/users", {"name": "X Y", "role": "SystemAdministrator", "position": "x"}).status_code, 403)


    def test_directors_manage_users_and_may_appoint_a_director_but_not_an_administrator(self):
        self.login(NICOLE)
        self.assertTrue(self.get("/api/fsa/me")["data"]["canManageUsers"])
        d = self.send("post", "/api/fsa/users", {"name": "New Director", "role": "Director", "position": "GM Operations"})
        self.assertEqual(d.status_code, 200, d.content)
        self.assertEqual(self.send("post", "/api/fsa/users", {"name": "X Y", "role": "SystemAdministrator", "position": "x"}).status_code, 403)
        self.login(THANDI)
        self.assertEqual(self.client.get("/api/fsa/users").status_code, 403)


class AccreditationWorkflow(Api):
    def test_a_renewal_keeps_history_finishes_the_renewal_project_and_clears_the_desk(self):
        self.login(PALESA)
        held = {a["ref"]: a for a in self.get("/api/fsa/accreditations")["data"]["held"]}
        self.assertEqual(held["ACC-0002"]["tone"], "warn")  # SAATCA, expires 2026-11-30: renewal due
        self.assertIn("TRN-IA", [c["code"] for c in held["ACC-0002"]["courses"]])
        self.assertIn("ACC-0002", {i["ref"] for i in self.get("/api/fsa/desk")["data"]["escalated"]})
        r = self.send("post", "/api/fsa/accreditations/ACC-0002/renew", {"number": "SAATCA-TP-77", "granted": "2026-09-08",
                                                                          "expires": "2029-11-30"}, screen="accreditation")
        self.assertEqual(r.status_code, 200, r.content)
        new = r.json()["data"]["ref"]
        detail = self.get(f"/api/fsa/accreditations/{new}")["data"]
        self.assertEqual([h["ref"] for h in detail["history"]], [new, "ACC-0002"])
        self.assertNotIn("ACC-0002", {a["ref"] for a in self.get("/api/fsa/accreditations")["data"]["held"]})
        self.assertNotIn("ACC-0002", {i["ref"] for i in self.get("/api/fsa/desk")["data"]["escalated"]})
        projects = {p["ref"]: p for p in self.get("/api/fsa/accreditations")["data"]["projects"]}
        self.assertEqual((projects["ACC-P03"]["state"], projects["ACC-P03"]["result"]), ("Accredited", new))
        again = self.send("post", "/api/fsa/accreditations/ACC-0002/renew", {"expires": "2030-01-01"})
        self.assertEqual(again.json()["error"], "already_renewed")

    def test_a_new_scope_runs_through_its_steps_to_an_accreditation(self):
        self.login(PALESA)
        start = self.send("post", "/api/fsa/accreditation-projects",
                          {"body": "QCTO", "scope": "Hygiene short course", "owner": MOKOENA, "target": "2027-03-31", "courses": ["TRN-HYG"]})
        self.assertEqual(start.status_code, 200, start.content)
        ref = start.json()["data"]["ref"]
        self.login(THANDI)  # not the owner, not a manager
        self.assertEqual(self.send("post", f"/api/fsa/accreditation-projects/{ref}/step", {}).status_code, 403)
        self.login(MOKOENA)  # the owner moves it on
        from django.core.files.uploadedfile import SimpleUploadedFile

        def attach(n, name="doc.pdf"):
            return self.client.post(f"/api/fsa/accreditation-projects/{ref}/steps/{n}/documents",
                                    {"file": SimpleUploadedFile(name, b"%PDF-1.7 step document")}, HTTP_X_FSA_SCREEN="accreditation")

        bare = self.send("post", f"/api/fsa/accreditation-projects/{ref}/step", {"note": "done"})
        self.assertEqual(bare.json()["error"], "document_needed")  # every step is completed with its document on file
        self.assertIn("scope letter", bare.json()["blockedBy"][0])
        self.assertEqual(attach(5, "visit-confirmation.pdf").status_code, 200)  # filed ahead of its step
        for n in range(1, 6):
            self.assertEqual(attach(n).status_code, 200)
            step = self.send("post", f"/api/fsa/accreditation-projects/{ref}/step", {"note": "done"})
            self.assertEqual(step.status_code, 200, step.content)
        self.assertEqual(step.json()["data"]["plan"][5]["step"], "Accreditation granted")
        self.assertEqual(len(step.json()["data"]["plan"][2]["documents"]), 1)
        self.assertEqual(self.client.get(step.json()["data"]["plan"][2]["documents"][0]["url"]).status_code, 200)
        self.assertEqual(attach(6, "letter.pdf").status_code, 200)
        missing = self.send("post", f"/api/fsa/accreditation-projects/{ref}/step", {})
        self.assertEqual(missing.status_code, 422)
        done = self.send("post", f"/api/fsa/accreditation-projects/{ref}/step", {"number": "QCTO-123", "expires": "2030-03-31"})
        self.assertEqual(done.json()["data"]["state"], "Accredited")
        granted = self.get(f"/api/fsa/accreditations/{done.json()['data']['result']}")["data"]
        self.assertEqual(granted["certificate"]["name"], "letter.pdf")  # the letter on the last step is the certificate
        from courses.models import Course
        self.assertTrue(Course.objects.get(code="TRN-HYG").is_accredited)

    def test_a_lapsed_accreditation_stops_delivery_of_its_courses(self):
        from assurance.models import Accreditation

        Accreditation.objects.filter(reference="ACC-0001").update(expires_on="2026-09-08")  # AgriSETA meat examination lapsed
        self.login(PALESA)
        plan = {b["ref"]: b for b in self.get("/api/fsa/plan")["data"]}
        self.assertTrue(any("Delivery under that scope stops" in r for r in plan["PLN-10"]["confirmBlockedBy"]))
        held = {a["ref"]: a for a in self.get("/api/fsa/accreditations")["data"]["held"]}
        self.assertIn("delivery stopped", held["ACC-0001"]["position"])



class CertificatePdf(Api):
    def test_an_issued_certificate_opens_as_a_pdf_and_downloads(self):
        from learners.models import Certificate

        self.login(PALESA)
        ref = Certificate.objects.first().reference
        view = self.client.get(f"/api/fsa/certificates/{ref}/pdf")
        self.assertEqual(view.status_code, 200)
        self.assertEqual(view["Content-Type"], "application/pdf")
        self.assertTrue(view.content.startswith(b"%PDF"))
        self.assertTrue(view["Content-Disposition"].startswith("inline"))
        self.assertTrue(self.client.get(f"/api/fsa/certificates/{ref}/pdf?download=true")["Content-Disposition"].startswith("attachment"))
        self.login(MOKOENA)
        self.assertEqual(self.client.get(f"/api/fsa/certificates/{ref}/pdf").status_code, 403)


HEIN, WILLIAM = "USR-0004", "USR-0008"


class Assessment(Api):
    """The assessor captures the mark with the marked assessment; someone else moderates it from that evidence."""

    def capture(self, enrolment, mark="72", outcome="Competent", content=b"%PDF-1.7 marked script", name="script.pdf"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        data = {"enrolment": enrolment, "mark": mark, "outcome": outcome, "notes": "Practical observed"}
        if content is not None:
            data["file"] = SimpleUploadedFile(name, content)
        return self.client.post("/api/fsa/results", data, HTTP_X_FSA_SCREEN="results")

    def test_assessor_captures_a_result_with_the_assessment_and_a_moderator_agrees(self):
        self.login(THANDI)
        options = self.get("/api/fsa/results/options")["data"]["intakes"]
        lerato = next(l for i in options for l in i["learners"] if l["enrolment"] == "ENR-0512")
        self.assertEqual(lerato["state"], "ready")
        self.assertEqual(self.capture("ENR-0512", content=None).json()["error"], "invalid")
        self.assertEqual(self.capture("ENR-0512", content=b"MZ not a document").status_code, 422)
        self.assertEqual(self.capture("ENR-0512", mark="140").status_code, 422)
        r = self.capture("ENR-0512")
        self.assertEqual(r.status_code, 200, r.content)
        row = r.json()["data"]
        self.assertEqual((row["mark"], row["outcome"], row["position"]), (72.0, "Competent", "Awaiting moderation"))
        self.assertTrue(row["ownAssessment"])
        view = self.client.get(row["evidence"]["url"])
        self.assertEqual(view.status_code, 200)
        self.assertTrue(b"".join(view.streaming_content).startswith(b"%PDF"))
        self.assertEqual(self.capture("ENR-0512").json()["error"], "awaiting_moderation")
        self.assertEqual(self.send("post", f"/api/fsa/results/{row['ref']}/moderate", {}).status_code, 403)

        self.login(HEIN)
        self.assertEqual(self.client.get(row["evidence"]["url"]).status_code, 200)
        done = self.send("post", f"/api/fsa/results/{row['ref']}/moderate", {"notes": "Script and practical checked"})
        self.assertEqual(done.status_code, 200, done.content)
        self.assertEqual(done.json()["data"]["position"], "Moderated — awaiting certificate")
        self.assertEqual(done.json()["data"]["moderationNotes"], "Script and practical checked")
        self.assertEqual(self.send("post", f"/api/fsa/results/{row['ref']}/moderate", {}).json()["error"], "already_moderated")

    def test_nobody_moderates_their_own_assessment(self):
        self.login(PALESA)
        ref = self.capture("ENR-0512").json()["data"]["ref"]
        r = self.send("post", f"/api/fsa/results/{ref}/moderate", {})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["error"], "own_assessment")

    def test_changing_the_outcome_needs_a_reason_and_not_yet_competent_needs_a_plan(self):
        self.login(HEIN)
        r = self.send("post", "/api/fsa/results/RES-0293/moderate", {"outcome": "NotYetCompetent"})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(len(r.json()["blockedBy"]), 3)  # reason, remediation plan, re-assessment date
        r = self.send("post", "/api/fsa/results/RES-0293/moderate",
                      {"outcome": "NotYetCompetent", "notes": "Hygiene section not answered", "remediation": "Redo the hygiene module",
                       "reassessBy": "2026-09-30"})
        self.assertEqual(r.status_code, 200, r.content)
        row = r.json()["data"]
        self.assertEqual((row["outcome"], row["moderatedOutcome"], row["position"]), ("Competent", "NotYetCompetent", "Moderated — remediation"))
        self.assertIn("2026-09-30", row["remediation"])
        self.assertEqual(Moderation.objects.get(result__reference="RES-0293").notes, "Hygiene section not answered")

    def test_a_learner_moderated_not_yet_competent_is_reassessed_on_a_new_result(self):
        self.login(WILLIAM)
        r = self.capture("ENR-0500", mark="68")
        self.assertEqual(r.status_code, 200, r.content)
        row = r.json()["data"]
        self.assertEqual(row["reassesses"], "RES-0290")
        rows = {x["ref"]: x for x in self.get("/api/fsa/results")["data"]["items"]}
        self.assertEqual(rows["RES-0290"]["reassessedOn"], row["ref"])
        self.assertTrue(rows["RES-0290"]["position"].startswith("Re-assessed on"))
        self.assertEqual(self.capture("ENR-0499").json()["error"], "already_competent")
        self.assertEqual(self.capture("ENR-0001").json()["error"], "not_started")  # PLN-04 starts 2026-09-14

    def test_a_facilitator_captures_only_for_their_own_intakes(self):
        self.login(THANDI)
        self.assertEqual(self.capture("ENR-0500").json()["error"], "not_assessable")
        self.assertEqual(self.client.get("/api/fsa/results/RES-0290/assessment").status_code, 404)


class Placements(Api):
    """University placements: the university's facilitator rule, the checklist, and the twenty-day report."""

    def upload(self, path, name="doc.pdf", content=b"%PDF-1.7 document"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return self.client.post(path, {"file": SimpleUploadedFile(name, content)}, HTTP_X_FSA_SCREEN="partnerships")

    def row(self, ref):
        return next(p for p in self.get("/api/fsa/partnerships")["data"]["items"] if p["ref"] == ref)

    def test_uj_students_need_an_hpcsa_registered_facilitator(self):
        self.login(MOKOENA)
        uj = next(u["ref"] for u in self.get("/api/fsa/universities")["data"] if u["name"] == "University of Johannesburg")
        students = [{"names": "UJ student 1", "studentNumber": "21901"}]
        r = self.send("post", "/api/fsa/partnerships/cohort", {"organisationRef": uj, "blockRef": "PLN-04", "students": students, "consent": True})
        self.assertEqual(r.json()["error"], "facilitator_not_accepted")
        self.assertIn("requires HPCSA-registered facilitators; William holds no HPCSA registration", r.json()["blockedBy"][0])
        ok = self.send("post", "/api/fsa/partnerships/cohort", {"organisationRef": uj, "blockRef": "PLN-08", "students": students, "consent": True})
        self.assertEqual(ok.status_code, 200, ok.content)  # Dr Riaan Steyn is HPCSA registered

    def test_a_rule_set_on_a_university_blocks_confirming_its_intake(self):
        from assurance.placements import requirement_blockers
        from delivery.models import PlanBlock

        self.login(MOKOENA)
        up = next(u for u in self.get("/api/fsa/partnerships")["data"]["universities"] if u["name"] == "University of Pretoria")
        self.assertEqual(self.send("put", f"/api/fsa/universities/{up['ref']}/rule", {"body": "SAATCA"}).status_code, 403)
        self.login(PALESA)
        r = self.send("put", f"/api/fsa/universities/{up['ref']}/rule", {"body": "SAATCA"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("SAATCA", requirement_blockers(PlanBlock.objects.get(reference="PLN-03"))[0])
        step = next(s for s in self.row("PLC-0007")["checklist"] if s["key"] == "facilitator")
        self.assertFalse(step["done"])
        self.send("put", f"/api/fsa/universities/{up['ref']}/rule", {"body": None})
        self.assertEqual(requirement_blockers(PlanBlock.objects.get(reference="PLN-03")), [])

    def test_abattoir_documents_and_confirmation_complete_the_checklist(self):
        self.login(MOKOENA)
        self.assertEqual(self.upload("/api/fsa/placements/PLC-0007/abattoir-documents", content=b"not a file").status_code, 422)
        early = self.send("post", "/api/fsa/placements/PLC-0007/abattoir-confirmed", {"on": "2026-09-01"})
        self.assertEqual(early.json()["error"], "docs_outstanding")
        self.assertEqual(self.upload("/api/fsa/placements/PLC-0007/abattoir-documents", "indemnity.pdf").status_code, 200)
        self.assertEqual(self.send("post", "/api/fsa/placements/PLC-0007/abattoir-confirmed", {"on": "2026-09-02"}).status_code, 200)
        row = self.row("PLC-0007")
        done = {s["key"]: s["done"] for s in row["checklist"]}
        self.assertNotIn("wil", done)  # each student keeps their own WIL book; the hub does not hold it
        self.assertTrue(done["abattoirDocs"] and done["abattoirConfirmed"] and done["students"])
        self.assertFalse(done["marking"] or done["report"])
        self.assertEqual({d["kind"] for d in row["documents"]}, {"Abattoir document"})
        self.assertEqual(self.client.get(row["documents"][0]["url"]).status_code, 200)
        self.login(THANDI)
        self.assertEqual(self.upload("/api/fsa/placements/PLC-0007/abattoir-documents").status_code, 403)

    def test_the_report_is_built_from_the_registers_and_filed_when_submitted(self):
        from identity.models import Account
        from learners.models import Enrolment

        self.login(MOKOENA)
        preview = self.client.get("/api/fsa/placements/PLC-0007/report")
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.content.startswith(b"%PDF"))
        r = self.send("post", "/api/fsa/placements/PLC-0007/report")
        self.assertEqual(r.json()["error"], "not_ready")
        self.assertTrue(any("runs until 2026-09-18" in b for b in r.json()["blockedBy"]))
        self.assertTrue(any("5 not yet marked and moderated" in b for b in r.json()["blockedBy"]))

        riaan, hein = Account.objects.get(reference="USR-0011"), Account.objects.get(reference="USR-0004")
        for e in Enrolment.objects.filter(plan_block__reference="PLN-03"):
            res = Result.objects.create(enrolment=e, assessed_by=riaan, assessed_at=dt.datetime(2026, 9, 18, 10, tzinfo=dt.UTC), mark=70,
                                        outcome="Competent")
            Moderation.objects.create(result=res, moderated_by=hein, moderated_at=dt.datetime(2026, 9, 21, 10, tzinfo=dt.UTC), outcome="Competent")
        DemoClock.objects.update_or_create(pk=1, defaults={"today": dt.date(2026, 9, 30)})
        self.assertEqual(self.row("PLC-0007")["reportBlockedBy"], [])
        done = self.send("post", "/api/fsa/placements/PLC-0007/report")
        self.assertEqual(done.status_code, 200, done.content)
        row = done.json()["data"]
        self.assertTrue(row["position"].startswith("Report submitted"))
        self.assertIn("Placement report", {d["kind"] for d in row["documents"]})
        self.assertEqual(self.send("post", "/api/fsa/placements/PLC-0007/report").json()["error"], "not_ready")


class FacilitatorRegions(Api):
    """Facilitators are assigned regions (provinces and Online); a region with one facilitator is flagged,
    and how each facilitator keeps up with registers, results and moderation is read from the registers."""

    def region(self, name):
        return next(g for g in self.get("/api/fsa/facilitators/cover")["data"]["regions"] if g["region"] == name)

    def test_kzn_has_single_cover_and_an_intake_run_from_outside_is_warned(self):
        self.login(PALESA)
        kzn = self.region("KwaZulu-Natal")
        self.assertEqual(kzn["tone"], "warn")
        self.assertIn("Thandi Ncube only", kzn["position"])
        self.assertTrue(next(i for i in kzn["intakes"] if i["ref"] == "PLN-08")["fromOutside"])  # Dr Riaan Steyn covers North West
        plan = {b["ref"]: b for b in self.get("/api/fsa/plan")["data"]}
        self.assertTrue(any(w["kind"] == "region" and "not KwaZulu-Natal" in w["message"] for w in plan["PLN-08"]["warnings"]))
        self.assertEqual(self.region("Online")["position"], "In order")

    def test_the_training_manager_assigns_several_regions_including_online(self):
        self.login(THANDI)
        self.assertEqual(self.send("put", "/api/fsa/facilitators/USR-0011/regions", {"regions": ["KwaZulu-Natal"]}).status_code, 403)
        self.login(PALESA)
        self.assertEqual(self.send("put", "/api/fsa/facilitators/USR-0011/regions", {"regions": ["Mars"]}).status_code, 422)
        r = self.send("put", "/api/fsa/facilitators/USR-0011/regions", {"regions": ["Online", "KwaZulu-Natal", "North West"]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["regions"], ["KwaZulu-Natal", "North West", "Online"])
        self.assertEqual(self.region("KwaZulu-Natal")["position"], "In order")
        plan = {b["ref"]: b for b in self.get("/api/fsa/plan")["data"]}
        self.assertFalse(any(w["kind"] == "region" for w in plan["PLN-08"]["warnings"]))

    def test_work_indicators_show_outcomes_changed_at_moderation(self):
        self.login(HEIN)
        self.send("post", "/api/fsa/results/RES-0293/moderate",
                  {"outcome": "NotYetCompetent", "notes": "Practical not evidenced", "remediation": "Repeat the practical", "reassessBy": "2026-09-30"})
        self.login(PALESA)
        thandi = next(r for r in self.get("/api/fsa/facilitators")["data"] if r["name"] == "Thandi Ncube")
        moderation = next(i for i in thandi["work"]["items"] if i["key"] == "moderation")
        self.assertIn("changed on RES-0293", moderation["note"])
        self.assertIn(thandi["work"]["position"], ("Needs attention", "Action required"))
        self.assertEqual(self.get("/api/fsa/facilitators/USR-0007")["data"]["work"]["position"], thandi["work"]["position"])


class PrerequisiteAttempts(Api):
    """A new prerequisite test result is captured with the marked test, and every attempt stays on record in order."""

    def capture(self, ref, result, content=b"%PDF-1.7 marked test", name="test.pdf"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        data = {"result": result}
        if content is not None:
            data["file"] = SimpleUploadedFile(name, content)
        return self.client.post(f"/api/fsa/enrolments/{ref}/test", data, HTTP_X_FSA_SCREEN="enrolments")

    def test_each_attempt_is_kept_first_to_latest_with_its_marked_test(self):
        self.login(MOKOENA)
        self.assertEqual(self.capture("ENR-0518", "48", content=None).status_code, 422)  # the marked test is required
        self.assertEqual(self.capture("ENR-0518", "48", name="second.pdf").status_code, 200)
        r = self.capture("ENR-0518", "62", name="third.pdf")
        self.assertEqual(r.status_code, 200, r.content)
        e = r.json()["data"]
        self.assertEqual(e["prerequisiteResult"], 62.0)  # the latest attempt counts
        self.assertEqual([(a["n"], a["result"]) for a in e["testAttempts"]], [(1, 44.0), (2, 48.0), (3, 62.0)])
        self.assertIsNone(e["testAttempts"][0]["file"])  # captured before attempts were kept
        self.assertEqual(e["testAttempts"][1]["file"]["name"], "second.pdf")
        self.assertEqual(self.client.get(e["testAttempts"][1]["file"]["url"]).status_code, 200)
        self.assertNotIn("Prerequisite test result", " ".join(e["gateBlockedBy"]))


class AddUniversity(Api):
    def test_the_training_manager_adds_a_university_with_its_rule(self):
        self.login(MOKOENA)
        self.assertEqual(self.send("post", "/api/fsa/universities", {"name": "University of the Free State"}).status_code, 403)
        self.login(PALESA)
        r = self.send("post", "/api/fsa/universities", {"name": "  University of the   Free State ", "body": "HPCSA"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.json()["data"]["name"], r.json()["data"]["rule"]), ("University of the Free State", "HPCSA"))
        self.assertEqual(self.send("post", "/api/fsa/universities", {"name": "university of the free state"}).json()["error"], "duplicate")
        self.assertIn("University of the Free State", [u["name"] for u in self.get("/api/fsa/universities")["data"]])


class SessionGroups(Api):
    def test_a_session_names_the_university_its_students_come_from(self):
        self.login("USR-0011")  # Dr Riaan Steyn sees his own sessions
        rows = self.get("/api/fsa/sessions")["data"]["items"]
        up = next(r for r in rows if r["block"] == "PLN-03")
        self.assertEqual([(g["name"], g["short"], g["learners"]) for g in up["groups"]], [("University of Pretoria", "UP", 5)])


class ManagementDashboard(Api):
    def test_the_dashboard_reads_throughput_courses_seasons_marketing_and_effectiveness(self):
        self.login(THANDI)
        self.assertEqual(self.client.get("/api/fsa/dashboard").status_code, 403)
        self.login(PALESA)
        d = self.get("/api/fsa/dashboard?months=12")["data"]
        self.assertEqual(len(d["throughput"]["months"]), 12)
        self.assertEqual([f["label"] for f in d["throughput"]["funnel"]], ["Registered", "Confirmed", "Assessed", "Competent", "Certified"])
        pme = next(c for c in d["courses"] if c["course"].startswith("PME 1"))
        self.assertEqual((pme["competent"], pme["nyc"]), (2, 1))  # RES-0288 and RES-0289 competent, RES-0290 not yet
        self.assertEqual(len(d["seasons"]["enquiries"]), 12)
        self.assertGreater(d["marketing"]["funnel"]["enquiries"], 0)
        self.assertIn("Phone", {g["name"] for g in d["marketing"]["byChannel"]})
        self.assertIsNotNone(d["effectiveness"]["enquiries"]["onTime"])
        only = self.get("/api/fsa/dashboard?months=6&course=TRN-HYG")["data"]
        self.assertTrue(all(c["course"] == "Food hygiene and GMP" for c in only["courses"]))
        self.assertEqual(self.client.get("/api/fsa/dashboard?months=7").status_code, 422)



class Campaigns(Api):
    """Marketing records its campaigns; each enquiry says how the person heard about FSA; a campaign's results are
    read from the registers and its evaluation goes back to FSA."""

    def test_an_enquiry_names_its_campaign_and_the_campaign_reports_what_it_brought(self):
        self.login(PALESA)
        bad = self.send("post", "/api/fsa/campaigns", {"name": "", "channel": "Billboard", "starts": "2026-09-10", "ends": "2026-09-01"})
        self.assertEqual(len(bad.json()["blockedBy"]), 3)
        c = self.send("post", "/api/fsa/campaigns", {"name": "Spring meat examiner drive", "channel": "Social media",
                                                     "starts": "2026-09-01", "ends": "2026-09-30", "courses": ["TRN-PME1"], "cost": "5 000"})
        self.assertEqual(c.status_code, 200, c.content)
        ref = c.json()["data"]["ref"]
        self.assertEqual(c.json()["data"]["cost"], "R 5 000.00")
        options = self.get("/api/fsa/campaigns/options")["data"]
        self.assertIn(ref, [x["ref"] for x in options["campaigns"]])
        missing = self.send("post", "/api/fsa/enquiries", {"names": "Sizwe Dube", "channel": "WhatsApp", "topics": ["Costs"],
                                                          "enquiringFor": "Individual", "courseCode": "TRN-PME1", "source": "Campaign"})
        self.assertIn("Choose the campaign that brought them.", missing.json()["blockedBy"])
        e = self.send("post", "/api/fsa/enquiries", {"names": "Sizwe Dube", "channel": "WhatsApp", "topics": ["Costs"], "enquiringFor": "Individual",
                                                    "courseCode": "TRN-PME1", "source": "Campaign", "campaignRef": ref})
        self.assertEqual(e.status_code, 200, e.content)
        self.assertEqual(e.json()["data"]["sourceLabel"], "Campaign: Spring meat examiner drive")
        row = next(x for x in self.get("/api/fsa/campaigns")["data"]["items"] if x["ref"] == ref)
        self.assertEqual((row["results"]["enquiries"], row["results"]["costPerEnquiry"]), (1, "R 5 000.00"))
        self.assertEqual(row["results"]["state"], "Running")
        rec = self.send("patch", f"/api/fsa/campaigns/{ref}", {"recommendations": "Run again before the February intake."})
        self.assertEqual(rec.status_code, 200, rec.content)
        self.assertEqual(rec.json()["data"]["recommendations"], "Run again before the February intake.")
        board = self.get("/api/fsa/dashboard")["data"]["marketing"]
        self.assertIn("A campaign", {g["name"] for g in board["bySource"]})
        self.assertEqual(board["campaigns"][0]["ref"], ref)
        self.login(THANDI)
        self.assertEqual(self.send("post", "/api/fsa/campaigns", {"name": "x"}).status_code, 403)


class CourseEvaluations(Api):
    """Learners evaluate the course through a private link after the intake ends; staff see the scores, not who said what."""

    def test_learners_answer_once_and_the_scores_reach_the_facilitator_and_the_dashboard(self):
        self.login(PALESA)
        reg = self.get("/api/fsa/feedback")["data"]
        pln11 = next(i for i in reg["items"] if i["intake"] == "PLN-11")  # William's PME 1 intake, ended 2026-08-28
        self.assertEqual((pln11["asked"], pln11["answered"]), (3, 0))
        links = [l["link"].rsplit("/", 1)[-1] for l in pln11["learners"]]
        self.client.post("/api/fsa/auth/logout")
        view = self.client.get(f"/api/fsa/public/feedback/{links[0]}")  # no sign-in needed
        self.assertEqual(view.status_code, 200)
        self.assertEqual(view.json()["data"]["facilitator"], "William")
        self.assertEqual(self.client.get("/api/fsa/public/feedback/not-a-token").status_code, 404)
        bad = self.client.post(f"/api/fsa/public/feedback/{links[0]}", {"content": 9}, content_type="application/json")
        self.assertEqual(bad.status_code, 422)
        answer = {"content": 4, "facilitation": 2, "venue": 4, "organisation": 3, "recommend": True, "comments": "Too fast on day two."}
        for t in links:
            self.assertEqual(self.client.post(f"/api/fsa/public/feedback/{t}", answer, content_type="application/json").status_code, 200)
        again = self.client.post(f"/api/fsa/public/feedback/{links[0]}", answer, content_type="application/json")
        self.assertEqual(again.json()["error"], "already_submitted")
        self.login(PALESA)
        pln11 = next(i for i in self.get("/api/fsa/feedback")["data"]["items"] if i["intake"] == "PLN-11")
        self.assertEqual((pln11["answered"], pln11["scores"]["facilitation"], pln11["recommend"]), (3, 2.0, 100))
        self.assertEqual(pln11["comments"], ["Too fast on day two."] * 3)
        william = next(r for r in self.get("/api/fsa/facilitators")["data"] if r["name"] == "William")
        rating = next(i for i in william["work"]["items"] if i["key"] == "feedback")
        self.assertEqual((rating["tone"], rating["note"]), ("bad", "2.0 out of 5 from 3 learners"))
        self.assertEqual(self.get("/api/fsa/dashboard")["data"]["effectiveness"]["feedback"]["answered"], 3)


class SuperAdmin(Api):
    def test_create_superadmin_gives_the_system_administrator_role_and_change_access_everywhere(self):
        from django.core.management import call_command

        from identity.models import Account, Segment

        call_command("create_superadmin", "Test Superadmin", stdout=open("nul" if __import__("os").name == "nt" else "/dev/null", "w"))
        a = Account.objects.get(display_name="Test Superadmin")
        self.assertEqual(a.hub_role, "SystemAdministrator")
        self.assertTrue(all(a.can(code, write=True) for code in Segment.objects.values_list("code", flat=True)))
