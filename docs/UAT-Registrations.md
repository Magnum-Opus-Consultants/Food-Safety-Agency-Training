# UAT script: Registrations

**Purpose.** Check the Training Hub against the *Registrations* section of the Holistic Training
Department meeting review, one requirement at a time. Run each test, record **Pass**, **Fail** or
**Not built**, and write what you saw when it differs from *Expected*.

**Where:** http://localhost:3210 (press **Ctrl+F5** first so you have the latest version).
**Sign-in details:** `training-hub/demo-logins.txt`.

| Tester | Date | Build |
| --- | --- | --- |
| | | Training Hub demo, October 2026 |

## Before you start

- **Accounts used**
  - **P. Mokoena** (enquiry handler), who registers learners. Most tests run as this account.
  - **Palesa Mpana** (training manager), for checks on the desk and audit trail.
  - **Thandi Ncube** (facilitator), to confirm a facilitator cannot register learners.
- **Open intakes for the meat examiner courses**
  - **PLN-14** PME 1, 9–20 November 2026, 12 seats.
  - **PLN-16** PME 2, 18–29 January 2027, 12 seats.
  - **PLN-15** Meat examiner (red meat), 23 November – 4 December 2026, 8 seats.
  - **PLN-06** Meat examiner (poultry), 5–16 October 2026, running now.
  - **PLN-10** Game meat examiner, 1–8 December 2026. This one is a draft, because its facilitator's registration has lapsed.
- **Identity numbers.** Use **made-up passport numbers** for test learners: choose *Passport* and type `TEST10001`, `TEST10002` and so on. **Never enter a real person's ID number in a test.**
- **The audit trail.** Every save writes a line to the audit trail at the bottom of the screen you are on. Check it after each test.

---

## Section 1: An enquiry becomes a registration

> *"There needs to be a direct link to the enquire form / registration link - database (CRM) - Quoting systems - then loops back to the consolidated training platform / system"*

### REG-01 · Log a meat examiner enquiry
**Account:** P. Mokoena
1. Open **Demand → Enquiry queue** and press **Log enquiry**.
2. Enter the enquirer `Test Learner One`. Choose the channel **Phone** and the course **PME 1 — primary meat examiner**.
3. Tick **Costs** and **Duration** under *What they asked about*.
4. Press **Log and route**.

**Expected:**
- A new card appears in **New**.
- The card is owned by the person on this week's admin rotation (P. Mokoena).
- The card shows the topic tags *Costs* and *Duration*.
- The audit trail shows a line like *"ENQ-04xx logged from Phone and routed to P. Mokoena"*.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-02 · The required fields are enforced
**Account:** P. Mokoena
1. Press **Log enquiry**. Leave the **Enquirer** name blank, and tick **Other** without describing it.

**Expected:**
- The name box and the *Other* box are outlined in red, each with a message underneath.
- **Log and route** is disabled until both are filled in.
- Organisation, Email and Phone are marked *(optional)*, so leaving them blank is accepted.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-03 · An enquiry cannot be marked Registered without registering a learner
**Account:** P. Mokoena
1. On the card from REG-01, choose **Move to Registered** in the stage list, or drag the card to **Registered**.

**Expected:**
- The card does **not** move.
- A **Register new learner** window opens instead, prefilled with the enquirer's name and course.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-04 · Register the learner from the enquiry
**Account:** P. Mokoena, continuing in the window from REG-03.
1. **Identity document:** choose *Passport* and enter `TEST10001`.
2. **Intake:** choose **PLN-14**. The list shows how many seats are free.
3. Leave *Prerequisite test result* empty, and don't choose a *Grade 10 evidence* file.
4. Press **Register learner** *without* ticking the POPIA consent box.
5. Tick the consent box and press **Register learner** again.

**Expected:**
- **Step 4:** nothing is saved. The consent box is outlined in red with *"The learner's consent is needed before their details can be kept."*
- **Step 5:** the window closes. The card moves to **Registered** and shows *"Registered as ENR-xxxx"*.
- **Enrolments:** the new enrolment is at **Registered** (its first stage, seat reserved). Its Stage column reads *Minimum prerequisites not met*.
- **Training plan:** PLN-14 now shows one more seat booked.

Result: ☐ Pass ☐ Fail Notes: ______________________

---

## Section 2: Minimum prerequisites (test result of 50% or more, and Grade 10)

> *"Entry assessment to verify if the student / enquire are capable to apply for the course = called a Prerequisite Test Pass with 50 % minimum of grade 10 · Have to have Evidence of latest qualifications · This is linked to all meat examiners"*

**Before you start:** have two files ready on your computer: any small **PDF** (it stands in for a Grade 10 report), and a file that is *not* a document, for example a `.txt` or `.docx`.

### REG-05 · Missing prerequisites block the enrolment, and are named
**Account:** P. Mokoena
1. Open **Learners → Enrolments** and click the enrolment from REG-04.

**Expected:**
- The **Minimum prerequisites** panel shows *Prerequisite test result: Not captured* and *Grade 10 evidence: Not uploaded*.
- **Confirm — prerequisites met** is greyed out, with *"Available once both minimum prerequisites are met."*

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-06 · A result below 50% does not meet the minimum
**Account:** P. Mokoena
1. In the same enrolment, type `44` in the test result box and press **Save**.
2. Under Grade 10 evidence press **Upload** and choose the PDF.

**Expected:**
- The test result shows *44% · below 50%*.
- Grade 10 evidence shows the file name as a link, with *"Uploaded … by P. Mokoena"*. Clicking the link opens the PDF in a new tab.
- The Stage column now reads *Test result below 50%*. **Confirm** stays greyed out.
- **Audit trail:** *"ENR-xxxx Grade 10 evidence uploaded — (file name)"*.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-07 · Only documents are accepted, and Delete removes the file
**Account:** P. Mokoena
1. Press **Replace** and choose the `.txt` or `.docx` file.
2. Press **Delete**, then **Keep** when asked *"Delete this file?"*.
3. Press **Delete** again, and this time confirm with **Delete**.
4. Press **Upload** and choose the PDF again.

**Expected:**
- **Step 1:** refused with *"That file type is not accepted. Upload a PDF, or a photo or scan as JPG or PNG."* The PDF stays on file.
- **Step 2:** nothing changes.
- **Step 3:** the file is gone, and Grade 10 evidence shows *Not uploaded*. The audit trail records the deletion.
- **Step 4:** the PDF is back on file.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-08 · A pass of 50% with Grade 10 evidence lets the enrolment advance
**Account:** P. Mokoena
1. Type `50` in the test result box and press **Save**.
2. Press **Confirm — prerequisites met**.

**Expected:**
- **Step 1:** the test result shows *50% · met*, and **Confirm** becomes available.
- **Step 2:** the enrolment moves to **Confirmed**. The panel says the prerequisites are verified and can no longer change; **Upload**, **Replace** and **Delete** are gone, but the file link still opens.
- The **Enrolments** badge in the sidebar goes down by one.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-09 · Both prerequisites are required, not either
**Account:** P. Mokoena
1. Register another learner from **Enrolments → Register new learner**:
   - course **Meat examiner — red meat**, intake **PLN-15**;
   - passport `TEST10002`;
   - prerequisite test result `78`;
   - no Grade 10 file chosen;
   - consent ticked.
2. Open the new enrolment.

**Expected:**
- The test result shows *78% · met*, but Grade 10 evidence shows *Not uploaded*.
- The Stage column reads *Grade 10 evidence outstanding*, and **Confirm** is greyed out even though the score is high.

3. Without opening the enrolment, press **Upload** in its **Grade 10** column and choose the PDF.

**Expected:**
- The Grade 10 column changes to **View file**, which opens the PDF.
- The Stage column changes to *Registered*, and when the enrolment is opened **Confirm** is available.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-10 · The Grade 10 document can be attached while registering
**Account:** P. Mokoena
1. Register a learner on **Meat examiner — poultry** (any intake with free seats), with passport `TEST10004`, a test result of `65`, the PDF chosen under *Grade 10 evidence*, and consent ticked.

**Expected:**
- The button briefly reads *"Uploading Grade 10 evidence…"*, then the window closes and the new enrolment opens.
- Both prerequisites show as met, and **Confirm** is available.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-10a · A result below 50% cannot be registered
**Account:** P. Mokoena
1. Start registering a learner on **PME 1 — primary meat examiner**, passport `TEST10005`, consent ticked, and type `30` as the prerequisite test result.
2. Press **Register learner**.
3. Clear the result and press **Register learner** again.

**Expected:**
- **Step 1:** as soon as `30` is typed, the box turns red with *"30% is below the 50% minimum, so the learner cannot be registered on this course…"*.
- **Step 2:** nothing is saved and no seat is taken.
- **Step 3:** the learner registers (stage **Registered**), with *Test result not captured*, ready to write the test.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-11 · Minimum prerequisites apply to every meat examiner course
**Account:** P. Mokoena
1. Open **Courses → Course catalogue**.

**Expected:**
- **PME 1**, **Meat examiner — red meat**, **Meat examiner — poultry** and **Game meat examiner** show the entry requirement *"Prerequisite test ≥ 50% and Grade 10"*.
- **PME 2** shows *"PME 1 competent"*.
- HACCP awareness and Food hygiene show *None*.
- The other short courses show their own requirement, for example *"Registered classifier"*.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-11a · PME 2 needs a PME 1 pass
> *"PME level 1 & 2"*

**Account:** P. Mokoena
1. Register a new learner on **PME 2 — primary meat examiner**, intake **PLN-16**, with passport `TEST10003` and consent ticked.
2. Open the enrolment.

**Expected:**
- A *Minimum prerequisites — outstanding* box names *"No moderated competent result on file for PME 1 — primary meat examiner"*, and **Confirm** is greyed out.

Result: ☐ Pass ☐ Fail Notes: ______________________

---

## Section 3: Corporate groups register on behalf of their people

> *"Registration can also be considered by corporate groups to register on behalf of a group of people"*

### REG-11b · Add a new corporate client and quote them
**Account:** P. Mokoena
1. Open **Demand → Quotes & corporate accounts** and press **New quotation**.
2. Under *Company* choose **+ Add a new client**. Enter `Test Abattoir (UAT)`, contact person `Test Contact`, phone `082 555 0199`.
3. Choose course **HACCP awareness**, basis **Per group**, `4` learners, value `16 800`, and press **Save and issue**.
4. Repeat with a value of `60 000`.

**Expected:**
- **Step 3:** the quotation appears at the top of the register as *Issued*, with a follow-up date fourteen days on, and **Add delegates** is available.
- **Step 4:** the button reads **Save for approval**. The quotation is saved as a *Draft* showing **Approval needed**, with no **Issue** button. Signed in as **Palesa Mpana**, an **Approve** button appears; after approving, P. Mokoena can **Issue** it.
- Trying to add `Test Abattoir (UAT)` as a new client again is refused: *"already a client: choose it from the list"*.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-12 · Register a delegate list against a group quotation
**Account:** P. Mokoena
1. Open **Demand → Quotes & corporate accounts**. Find **QTE-0221** (Rainbow, Hammarsdale, poultry, quoted for 16, R 68 400).
2. Press **Add delegates** and choose intake **PLN-06**.
3. Fill in one row per delegate (ID type **Passport**):

   | Full name | Passport number | Email |
   |---|---|---|
   | Test Delegate A | `TEST20001` | a@example.org |
   | Test Delegate B | `TEST20002` | |
   | Test Delegate C | `TEST20003` | |

   (Rows can also be pasted from Excel into the first name box, or loaded from a CSV file.)
4. Tick the consent confirmation and press **Register 3 delegates**.

**Expected:**
- No row is highlighted red before you save.
- After saving, QTE-0221 shows **Registered 3 / 16**.
- Its status still reads **Approval needed**, because R 68 400 is over the R 50 000 line and the head of department has not approved it.
  **Question for the department:** should registering delegates be blocked until a quotation over R 50 000 is approved? At present it is not.
- **Enrolments:** three new *Corporate* enrolments at **Registered**, linked to Rainbow.
- **Audit trail:** *"3 delegates of Rainbow, Hammarsdale registered on PLN-06 against QTE-0221 — quotation accepted"*.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-13 · The group cannot go over the number quoted or the seats free
**Account:** P. Mokoena
1. On **QTE-0221**, press **Add delegates**, choose **PLN-06**, then paste **14** more delegates from Excel (passports `TEST20004` to `TEST20017`) into the first name box.

**Expected:**
- **Add row** is greyed out once 13 rows exist, and pressing **Register** names the problem: *"QTE-0221 has room for 13 more; 14 are entered."* Nothing is saved.
- PLN-06 only has a few seats left, so the intake list also marks it *not enough seats* for 14.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-14 · The same person sent twice is one learner, not two
**Account:** P. Mokoena
1. Register a learner from **Enrolments → Register new learner**: course **Meat examiner — red meat**, intake **PLN-15**, passport **`TEST20001`** (the same as *Test Delegate A*), name typed differently as `T. Delegate A`.
2. Open **Learners → Learner directory**.

**Expected:**
- The audit line says *"existing learner matched on ID number"*.
- The directory shows **one** record for Test Delegate A, with two enrolments.
- The identity shows only **Passport •••• 0001**. The full number appears nowhere.

Result: ☐ Pass ☐ Fail Notes: ______________________

---

## Section 4: Clean records and access

> *"Start mapping the process of registration to have our head office … cleaned"*

### REG-15 · Invalid ID numbers are caught
**Account:** P. Mokoena
1. Start **Register new learner**. Choose *SA ID number* and type `8001015009088`. This number has a deliberate wrong check digit.

**Expected:**
- A red message appears under the field before you save: *"The check digit does not match; check for a mistyped digit."*
- If you try to save anyway, the server refuses with the same reason.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-16 · Phone numbers are stored with their country code
**Account:** P. Mokoena
1. Open the enquiry from REG-01 (**Edit** on its card). Choose phone country **NA +264**, type `081 234 5678` and press **Save changes**.
2. Open the enquiry again.

**Expected:**
- The audit line reads *"phone — → +264 812345678"*: the leading 0 is dropped and the country code is kept.
- Reopened, it shows **NA +264** and `812345678`.
- Choosing **ZA +27** and typing `082 555 0101` saves as **+27 825550101**.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-17 · Only the right roles can register
**Account:** Thandi Ncube (facilitator)
1. Sign in as Thandi Ncube and look for **Enquiry queue**, **Enrolments** and **Quotes**.

**Expected:**
- She has no **Register new learner**, **Log enquiry** or **Add delegates** buttons.
- **Demand** and **Enrolments** are not in her sidebar.
- Typing the address directly (for example `/enrolments`) shows that her role does not have access.

Result: ☐ Pass ☐ Fail Notes: ______________________

### REG-18 · Every registration is in the audit trail
**Account:** Palesa Mpana
1. Read the audit trail at the bottom of **Enquiry queue** (registrations made from an enquiry, REG-04), **Enrolments** (REG-09, REG-10, REG-14, and the uploads and deletion in REG-06 and REG-07) and **Quotes** (REG-12).

**Expected:**
- One line for each registration, showing who did it and when.
- No ID or passport number appears in any line.

Result: ☐ Pass ☐ Fail Notes: ______________________

---

## Section 5: Requirements not yet built

Mark these **Not built** and add comments. They are listed so that nothing in the meeting note is missed.

| # | Requirement from the meeting review | Status today | Comment |
| --- | --- | --- | --- |
| REG-19 | *"There is a form for Meat Examiners registration but no link to database"*: a public online registration form | **Not built.** Staff register people inside the hub. A public form where applicants register themselves, upload documents and consent has not been built. | |
| REG-20 | *"… Quoting systems …"*: create a quote from an enquiry, priced from course fees | **Partly built** (REG-11b): quotations are created with a new or existing client, issued, and approved over R 50 000. The value is typed in: courses have no fees yet, and a quote is not yet started from an enquiry card. | |
| REG-21 | *"Have to have Evidence of latest qualifications"*: upload the document | **Built for Grade 10** (REG-06 to REG-10): the document is uploaded to the enrolment and kept in the evidence library. Other qualifications have no upload yet. | |
| REG-22 | Register an **existing** learner onto a new course, for example a PME 1 graduate onto PME 2, by choosing them from the learner directory | **Partly built.** The server supports it, but there is no screen for it yet. The workaround is to register the person again with the same ID or passport number, and they are matched. | |
| REG-23 | *"… then loops back to the consolidated training platform"*: the link to IMI and the consolidated learner view | **Not built.** This is an integration, which was out of scope for now. | |
| REG-24 | *"… head office … cleaned"*: clean the existing learner records | **Partly built.** New duplicates are prevented by ID matching. Records captured earlier without an ID are matched once by name and organisation. No bulk clean-up exists. | |

---

## Sign-off

| | Name | Signature | Date |
| --- | --- | --- | --- |
| Tested by | | | |
| Reviewed by (head of department) | | | |

**After testing:** the test learners, enrolments and delegates stay in the demo. To return the demo to its starting data, an administrator runs `python manage.py reset_demo`. That also deletes anything else entered since the last reset, so agree this with the department first.
