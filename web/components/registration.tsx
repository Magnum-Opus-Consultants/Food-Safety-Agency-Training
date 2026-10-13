"use client";

// The three ways a learner becomes part of the system: from an enquiry (or directly), as a
// corporate group's delegate list, or as a university cohort list. The API enforces every rule;
// these forms only gather the details and render its refusals verbatim.

import { ReactNode, useState } from "react";
import { Blocked, Register as Table, Status } from "@/components/ui";
import { parseList, Row } from "@/lib/csv";
import { useAction, useRegister } from "@/lib/hooks";
import { idTypeOf, saIdProblem } from "@/lib/said";
import { PhoneInput } from "@/components/PhoneInput";
import { ACCEPT } from "@/components/Prerequisites";
import { upload } from "@/lib/api";
import { courseOptions, SearchSelect } from "@/components/SearchSelect";

export type Intake = {
  ref: string; courseCode: string; course: string; gated: boolean; passMark: number | null; requirement: string; start: string; end: string; venue: string;
  facilitator: string; seats: number; capacity: number; free: number; state: string;
};

function intakeLabel(i: Intake) {
  return `${i.ref} · ${i.start} to ${i.end} · ${i.venue} · ${i.free} of ${i.capacity} seats free${i.state === "Draft" ? " · draft" : ""}`;
}

export function Modal({ title, onClose, children, wide = false }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div className="scrim" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className={`modal${wide ? " modal-wide" : ""}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3 className="modal-title">{title}</h3>
          <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function IntakeSelect({ course, value, onChange, need = 1, error }: { course?: string; value: string; onChange: (v: string) => void; need?: number; error?: string }) {
  const q = useRegister<Intake[]>(`/intakes${course ? `?course=${course}` : ""}`);
  const intakes = q.data?.data ?? [];
  return (
    <div className="field">
      <label htmlFor="intake">Intake</label>
      <select id="intake" value={value} onChange={(e) => onChange(e.target.value)} className={error ? "invalid" : undefined} aria-invalid={!!error}>
        <option value="">{intakes.length ? "Choose an intake from the plan" : course ? "No current intake for this course on the plan" : "Choose a course first"}</option>
        {intakes.map((i) => (
          <option key={i.ref} value={i.ref} disabled={i.free < need}>{intakeLabel(i)}{i.free < need ? " — not enough seats" : ""}</option>
        ))}
      </select>
      {error ? <span className="field-error">{error}</span> : null}
    </div>
  );
}

function Consent({ checked, onChange, children, error }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; error?: string }) {
  return (
    <div>
      <label className={`check${error ? " invalid" : ""}`}>
        <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} aria-invalid={!!error} />
        <span>{children}</span>
      </label>
      {error ? <span className="field-error">{error}</span> : null}
    </div>
  );
}

// --- route 1: an individual ---------------------------------------------------------------

export type Prefill = { enquiryRef?: string; names?: string; email?: string; phone?: string; organisation?: string; courseCode?: string;
  learnerType?: string };

export function RegisterLearnerForm({ prefill, onDone }: { prefill?: Prefill; onDone: (enrolmentRef: string) => void }) {
  const courses = useRegister<{ code: string; title: string; gated: boolean; passMark: number | null }[]>("/courses");
  const [f, setF] = useState({
    names: prefill?.names ?? "", email: prefill?.email ?? "", phone: prefill?.phone ?? "",
    organisation: prefill?.organisation ?? "", learnerType: prefill?.learnerType ?? (prefill?.organisation ? "Corporate" : "Public"),
    courseCode: prefill?.courseCode ?? "", blockRef: "", prerequisiteResult: "", consent: false,
    idType: "SAID", idNumber: "",
  });
  const [tried, setTried] = useState(false);
  const [grade10, setGrade10] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const set = (k: string, v: string | boolean) => setF((x) => ({ ...x, [k]: v }));
  const save = useAction<Record<string, unknown>, { ref: string }>("POST", "/enrolments");
  const courseRow = (courses.data?.data ?? []).find((c) => c.code === f.courseCode);
  // The requirement that applies is the one in force for the chosen intake (it can differ from today's
  // when a change is scheduled); before an intake is chosen, the course's current one.
  const intakes = useRegister<Intake[]>(`/intakes${f.courseCode ? `?course=${f.courseCode}` : ""}`, !!f.courseCode);
  const intake = (intakes.data?.data ?? []).find((i) => i.ref === f.blockRef);
  const course = courseRow ? { ...courseRow, gated: intake ? intake.gated : courseRow.gated,
                               passMark: (intake ? intake.passMark : courseRow.passMark) ?? 50 } : undefined;

  // Problems are worked out on every render, but only shown once a save has been tried, so the
  // learner's fields are not marked red while they are still being filled in. A format problem
  // with the ID shows as soon as it is typed.
  const idNumber = f.idNumber.trim();
  const idFormat = !idNumber ? null
    : f.idType === "SAID" ? saIdProblem(idNumber)
    : /^[A-Za-z0-9]{6,12}$/.test(idNumber.replace(/[\s-]/g, "")) ? null : "A passport number is 6 to 12 letters and digits.";
  const problems: Record<string, string> = {};
  if (!f.names.trim()) problems.names = "Enter the learner's full name.";
  if (f.learnerType === "Corporate" && !f.organisation.trim()) problems.organisation = "A corporate delegate needs their organisation.";
  if (idFormat) problems.idNumber = idFormat;
  else if (!idNumber && f.learnerType !== "University")
    problems.idNumber = `Enter the ${f.idType === "SAID" ? "SA ID" : "passport"} number. It is how the Academy tells two people of the same name apart.`;
  if (f.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim())) problems.email = "This does not look like an email address.";
  if (!f.courseCode) problems.courseCode = "Choose the course.";
  else if (!f.blockRef) problems.blockRef = "Choose an intake from the plan.";
  if (grade10 && grade10.size > 5 * 1024 * 1024) problems.grade10 = "The file is larger than 5 MB.";
  const prereq = f.prerequisiteResult.trim();
  const prereqProblem = !prereq ? null
    : Number.isNaN(Number(prereq)) || Number(prereq) < 0 || Number(prereq) > 100 ? "Enter a percentage from 0 to 100."
    : course?.gated && Number(prereq) < course.passMark
      ? `${Number(prereq)}% is below the ${course.passMark}% minimum, so the learner cannot be registered on this ${intake ? "intake" : "course"}. Leave it blank if they will write or rewrite the test.`
      : null;
  if (prereqProblem) problems.prerequisiteResult = prereqProblem;
  if (!f.consent) problems.consent = "The learner's consent is needed before their details can be kept.";
  // A wrong ID format or a result below the minimum shows as soon as it is typed.
  const err = (k: string) => (k === "idNumber" && idFormat) || (k === "prerequisiteResult" && prereqProblem) || tried ? problems[k] : undefined;

  function submit() {
    setTried(true);
    if (Object.keys(problems).length) { save.clear(); return; }
    save.mutate({
      enquiryRef: prefill?.enquiryRef ?? "", names: f.names, email: f.email, phone: f.phone, organisation: f.organisation,
      learnerType: f.learnerType, blockRef: f.blockRef, consent: f.consent,
      idType: f.idType, idNumber: f.idNumber,
      prerequisiteResult: f.prerequisiteResult === "" ? null : Number(f.prerequisiteResult),
    }, { onSuccess: async (r) => {
      // The Grade 10 document belongs to the enrolment, so it goes up once the enrolment exists. If the
      // upload fails the enrolment still stands and opens with the document marked as not uploaded.
      if (grade10 && course?.gated) {
        setUploading(true);
        try { await upload(`/enrolments/${r.data.ref}/grade10`, grade10, "enrolments"); } catch { /* retried from the enrolment */ }
        setUploading(false);
      }
      onDone(r.data.ref);
    } });
  }

  return (
    <div className="stack-12">
      {prefill?.enquiryRef ? <p className="small muted" style={{ margin: 0 }}>From <span className="mono">{prefill.enquiryRef}</span>. On save the enquiry moves to Registered.</p> : null}
      <Blocked refusal={save.refusal} />
      <div className="eyebrow">Learner</div>
      <div className="form-grid">
        <div className="field"><label htmlFor="rl-names">Full name</label><input id="rl-names" className={err("names") ? "invalid" : undefined} aria-invalid={!!err("names")} value={f.names} onChange={(e) => set("names", e.target.value)} />
          {err("names") ? <span className="field-error">{err("names")}</span> : null}</div>
        <div className="field"><label htmlFor="rl-type">Learner type</label>
          <select id="rl-type" value={f.learnerType} onChange={(e) => set("learnerType", e.target.value)}>
            <option value="Public">Public applicant</option><option value="Corporate">Corporate delegate</option>
            <option value="University">University student</option><option value="Employee">FSA employee</option>
          </select></div>
        <div className="field"><label htmlFor="rl-org">Organisation {f.learnerType === "Corporate" ? "" : <span className="optional">(optional)</span>}</label><input id="rl-org" className={err("organisation") ? "invalid" : undefined} aria-invalid={!!err("organisation")} value={f.organisation} onChange={(e) => set("organisation", e.target.value)} />
          {err("organisation") ? <span className="field-error">{err("organisation")}</span> : null}</div>
        <div className="field"><label htmlFor="rl-idtype">Identity document</label>
          <select id="rl-idtype" value={f.idType} onChange={(e) => set("idType", e.target.value)}>
            <option value="SAID">SA ID number</option><option value="Passport">Passport</option>
          </select></div>
        <div className="field"><label htmlFor="rl-id">{f.idType === "SAID" ? "SA ID number" : "Passport number"}{f.learnerType === "University" ? " (optional)" : ""}</label>
          <input id="rl-id" inputMode={f.idType === "SAID" ? "numeric" : "text"} autoComplete="off" value={f.idNumber}
                 className={err("idNumber") ? "invalid" : undefined} onChange={(e) => set("idNumber", e.target.value)} aria-invalid={!!err("idNumber")} />
          {err("idNumber") ? <span className="field-error">{err("idNumber")}</span>
            : <span className="small muted">Encrypted on save; only the last four digits are ever shown.</span>}</div>
        <div className="field"><label htmlFor="rl-email">Email <span className="optional">(optional)</span></label><input id="rl-email" type="email" className={err("email") ? "invalid" : undefined} aria-invalid={!!err("email")} value={f.email} onChange={(e) => set("email", e.target.value)} />
          {err("email") ? <span className="field-error">{err("email")}</span> : null}</div>
        <div className="field"><label htmlFor="rl-phone">Phone <span className="optional">(optional)</span></label><PhoneInput id="rl-phone" value={f.phone} onChange={(v) => set("phone", v)} /></div>
      </div>
      <div className="eyebrow">Course and intake</div>
      <div className="form-grid">
        <div className="field"><label htmlFor="rl-course">Course</label>
          <SearchSelect id="rl-course" options={courseOptions(courses.data?.data ?? [])} value={f.courseCode} invalid={!!err("courseCode")}
                        placeholder="Type to search courses…" emptyText="No course matches"
                        onChange={(v) => setF((x) => ({ ...x, courseCode: v, blockRef: "" }))} />
          {err("courseCode") ? <span className="field-error">{err("courseCode")}</span> : null}</div>
        {f.courseCode ? <IntakeSelect course={f.courseCode} value={f.blockRef} onChange={(v) => set("blockRef", v)} error={err("blockRef")} /> : null}
      </div>
      {course?.gated ? (
        <>
          <div className="eyebrow">Minimum prerequisites — test result of {course.passMark}% or more and Grade 10, both required</div>
          <div className="form-grid">
            <div className="field"><label htmlFor="rl-test">Prerequisite test result (%) <span className="optional">(if written)</span></label>
              <input id="rl-test" inputMode="decimal" className={err("prerequisiteResult") ? "invalid" : undefined} value={f.prerequisiteResult}
                     onChange={(e) => set("prerequisiteResult", e.target.value)} />
              {err("prerequisiteResult") ? <span className="field-error">{err("prerequisiteResult")}</span> : null}</div>
            <div className="field"><label htmlFor="rl-g10">Grade 10 evidence <span className="optional">(if received)</span></label>
              <input id="rl-g10" type="file" accept={ACCEPT} className={err("grade10") ? "invalid" : undefined}
                     onChange={(e) => setGrade10(e.target.files?.[0] ?? null)} />
              {err("grade10") ? <span className="field-error">{err("grade10")}</span>
                : <span className="small muted">Report or certificate · PDF, JPG or PNG, up to 5 MB</span>}</div>
          </div>
          <p className="small muted" style={{ margin: 0 }}>The learner is registered and their seat reserved now; the enrolment cannot advance until both minimum prerequisites are met.</p>
        </>
      ) : null}
      <Consent checked={f.consent} onChange={(v) => set("consent", v)} error={err("consent")}>
        The learner consents to the FSA Academy keeping their personal information for their training record (POPIA).
      </Consent>
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending || uploading} onClick={submit}>{uploading ? "Uploading Grade 10 evidence…" : "Register learner"}</button>
        <span className="small muted">Registering books a seat on the intake and writes an audit entry.</span>
      </div>
    </div>
  );
}

// --- route 2: a corporate group's delegate list --------------------------------------------

type DelegateRow = { names: string; idType: "SAID" | "Passport"; idNumber: string; email: string; phone: string };
const blankDelegate = (): DelegateRow => ({ names: "", idType: "SAID", idNumber: "", email: "", phone: "" });
const filled = (r: DelegateRow) => Boolean(r.names.trim() || r.idNumber.trim() || r.email.trim() || r.phone.trim());

function delegateProblems(r: DelegateRow): Partial<Record<keyof DelegateRow, string>> {
  const p: Partial<Record<keyof DelegateRow, string>> = {};
  if (!r.names.trim()) p.names = "Name missing";
  const id = r.idNumber.trim();
  if (!id) p.idNumber = "ID or passport missing";
  else if (/^\d+(\.\d+)?e\+\d+$/i.test(id)) p.idNumber = "Excel shortened this number: format the column as Text and save again";
  else if (r.idType === "SAID") { const why = saIdProblem(id); if (why) p.idNumber = why; }
  else if (!/^[A-Za-z0-9]{6,12}$/.test(id.replace(/[\s-]/g, ""))) p.idNumber = "6 to 12 letters and digits";
  if (r.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(r.email.trim())) p.email = "Not an email address";
  return p;
}

export function DelegatesForm({ quote, onDone }: {
  quote: { ref: string; client: string; course: string; courseCode: string; learners: number; registered: number };
  onDone: () => void;
}) {
  const room = quote.learners - quote.registered;
  const [blockRef, setBlockRef] = useState("");
  const [rows, setRows] = useState<DelegateRow[]>(() => Array.from({ length: Math.max(1, Math.min(3, room)) }, blankDelegate));
  const [consent, setConsent] = useState(false);
  const [tried, setTried] = useState(false);
  const save = useAction<Record<string, unknown>>("POST", `/quotations/${quote.ref}/delegates`);
  const used = rows.filter(filled);
  const problems = rows.map((r) => (filled(r) ? delegateProblems(r) : {}));
  const bad = problems.filter((p) => Object.keys(p).length).length;
  // A row's problems show once something is typed in that cell, or for every row after a save attempt.
  const show = (i: number, k: keyof DelegateRow) => (tried || rows[i][k] !== "" ? problems[i][k] : undefined);
  const sheetProblems: string[] = [];
  if (!blockRef) sheetProblems.push("Choose the intake.");
  if (!used.length) sheetProblems.push("Enter at least one delegate.");
  if (used.length > room) sheetProblems.push(`${quote.ref} has room for ${room} more; ${used.length} are entered.`);
  if (bad) sheetProblems.push(`${bad} ${bad === 1 ? "row needs" : "rows need"} fixing (highlighted).`);
  if (!consent) sheetProblems.push("Confirm the client has the delegates' consent.");

  const set = (i: number, k: keyof DelegateRow, v: string) =>
    setRows((rs) => rs.map((r, j) => (j !== i ? r : { ...r, [k]: v, ...(k === "idNumber" && v.trim() ? { idType: idTypeOf(v) } : {}) })));

  function fillFrom(i: number, text: string) {
    const list: DelegateRow[] = parseList(text, ["names", "idNumber", "email", "phone"], {
      names: ["name", "names", "full name", "delegate"], idNumber: ID_ALIASES,
      email: ["email", "e-mail"], phone: ["phone", "cell", "mobile", "telephone"],
    }).map((r) => ({ names: r.names ?? "", idNumber: r.idNumber ?? "", idType: idTypeOf(r.idNumber ?? ""), email: r.email ?? "", phone: r.phone ?? "" }));
    setRows((rs) => {
      const next = [...rs];
      list.forEach((r, k) => { next[i + k] = r; });
      return Array.from(next, (r) => r ?? blankDelegate());
    });
  }

  // Pasting several lines (copied from Excel or a CSV) fills the rows from this one down.
  function paste(i: number, e: React.ClipboardEvent<HTMLInputElement>) {
    const text = e.clipboardData.getData("text");
    if (!/[\t\n]/.test(text.trim())) return;
    e.preventDefault();
    fillFrom(i, text);
  }

  const firstEmpty = () => { const i = rows.findIndex((r) => !filled(r)); return i === -1 ? rows.length : i; };
  const cell = (i: number, k: "names" | "idNumber" | "email", label: string, extra = "") => (
    <td>
      <input aria-label={`Delegate ${i + 1} ${label}`} value={rows[i][k]} type={k === "email" ? "email" : "text"} autoComplete="off"
             className={`${extra}${show(i, k) ? " invalid" : ""}`.trim() || undefined}
             onChange={(e) => set(i, k, e.target.value)} onPaste={k === "email" ? undefined : (e) => paste(i, e)} />
      {show(i, k) ? <span className="field-error">{show(i, k)}</span> : null}
    </td>
  );

  return (
    <div className="stack-12">
      <p style={{ margin: 0 }}><b>{quote.client}</b> · {quote.course} · quoted for {quote.learners}, {quote.registered} registered, {room} to add.</p>
      <Blocked refusal={save.refusal} />
      <IntakeSelect course={quote.courseCode} value={blockRef} onChange={setBlockRef} need={Math.max(used.length, 1)}
                    error={tried && !blockRef ? "Choose the intake." : undefined} />
      <div className="field">
        <label>Delegates: one row per person</label>
        <div className="sheet-wrap">
          <table className="sheet">
            <thead>
              <tr><th>#</th><th>Full name</th><th>ID type</th><th>SA ID or passport number</th>
                <th>Email <span className="optional">(optional)</span></th><th>Phone <span className="optional">(optional)</span></th><th /></tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i}>
                  <td className="mono small muted">{i + 1}</td>
                  {cell(i, "names", "name")}
                  <td>
                    <select aria-label={`Delegate ${i + 1} ID type`} value={r.idType} onChange={(e) => set(i, "idType", e.target.value)}>
                      <option value="SAID">SA ID</option><option value="Passport">Passport</option>
                    </select>
                  </td>
                  {cell(i, "idNumber", "ID number", "mono")}
                  {cell(i, "email", "email")}
                  <td><input aria-label={`Delegate ${i + 1} phone`} value={r.phone} placeholder="082 555 0101" onChange={(e) => set(i, "phone", e.target.value)} /></td>
                  <td>
                    <button className="btn btn-sm btn-ghost-danger" aria-label={`Remove row ${i + 1}`} title="Remove this row"
                            onClick={() => setRows((rs) => (rs.length > 1 ? rs.filter((_, j) => j !== i) : [blankDelegate()]))}>
                      <i className="fas fa-times" aria-hidden />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="row">
          <button className="btn btn-sm" disabled={rows.length >= room} onClick={() => setRows((rs) => [...rs, blankDelegate()])}>
            <i className="fas fa-plus" aria-hidden /> Add row
          </button>
          <button className="btn btn-sm" onClick={() => downloadTemplate(`${quote.ref}-delegates.csv`)}>
            <i className="fas fa-download" aria-hidden /> Download template
          </button>
          <label className="btn btn-sm" style={{ cursor: "pointer" }}>
            <i className="fas fa-file-csv" aria-hidden /> Load from a CSV file
            <input type="file" accept=".csv,text/csv,text/plain" hidden onChange={async (e) => {
              const f = e.target.files?.[0];
              if (f) fillFrom(firstEmpty(), await f.text());
              e.target.value = "";
            }} />
          </label>
          <span className="small muted">
            Or copy rows from Excel and paste them into the first empty name box. {used.length} entered · {Math.max(room - used.length, 0)} more allowed.
          </span>
        </div>
      </div>
      <Consent checked={consent} onChange={setConsent} error={tried && !consent ? "The client's confirmation of consent is needed." : undefined}>
        {quote.client} has confirmed that each delegate consents to the FSA Academy keeping their personal information (POPIA).
      </Consent>
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending}
                onClick={() => {
                  setTried(true);
                  if (sheetProblems.length) { save.clear(); return; }
                  save.mutate({ blockRef, consent, delegates: used.map((r) => ({ names: r.names.trim(), idNumber: r.idNumber.trim(),
                    idType: r.idType, email: r.email.trim(), phone: r.phone.trim() })) }, { onSuccess: onDone });
                }}>
          Register {used.length || ""} {used.length === 1 ? "delegate" : "delegates"}
        </button>
        <span className="small muted">
          {tried && sheetProblems.length ? <span className="tone-bad">{sheetProblems.join(" ")}</span>
            : "All or nothing: if any delegate cannot be registered, none are."}
        </span>
      </div>
    </div>
  );
}

// --- route 3: a university cohort list ------------------------------------------------------

export function CohortImportForm({ onDone }: { onDone: (msg: string) => void }) {
  const unis = useRegister<{ ref: string; name: string }[]>("/universities");
  const [org, setOrg] = useState("");
  const [blockRef, setBlockRef] = useState("");
  const [text, setText] = useState("");
  const [consent, setConsent] = useState(false);
  const save = useAction<Record<string, unknown>, { imported: number; skipped: number; placement: string }>("POST", "/partnerships/cohort");
  const rows = parseList(text, ["names", "studentNumber", "email", "idNumber"], {
    idNumber: ID_ALIASES,
    names: ["name", "names", "student", "full name", "student name"],
    studentNumber: ["student number", "student no", "student_number", "number", "id", "studentnumber"],
    email: ["email", "e-mail"],
  });

  async function readFile(file: File) {
    setText(await file.text());
  }

  return (
    <div className="stack-12">
      <Blocked refusal={save.refusal} />
      <div className="form-grid">
        <div className="field"><label htmlFor="co-uni">University</label>
          <select id="co-uni" value={org} onChange={(e) => setOrg(e.target.value)}>
            <option value="">Choose the university</option>
            {(unis.data?.data ?? []).map((u) => <option key={u.ref} value={u.ref}>{u.name}</option>)}
          </select></div>
        <IntakeSelect course="TRN-VET" value={blockRef} onChange={setBlockRef} need={Math.max(rows.length, 1)} />
      </div>
      <div className="field">
        <label htmlFor="co-file">Student list (CSV from the university)</label>
        <input id="co-file" type="file" accept=".csv,text/csv,text/plain" onChange={(e) => e.target.files?.[0] && readFile(e.target.files[0])} />
      </div>
      <div className="field">
        <label htmlFor="co-list">Or paste it — one per line: name, student number, email, ID number (optional)</label>
        <textarea id="co-list" rows={6} value={text} onChange={(e) => setText(e.target.value)}
                  placeholder={"Name,Student number,Email\nT. Mokoena,219004512,219004512@student.uj.ac.za"} />
      </div>
      {rows.length ? <Preview rows={rows} columns={[["names", "Name"], ["studentNumber", "Student number"], ["email", "Email"]]} required="studentNumber" /> : null}
      <Consent checked={consent} onChange={setConsent}>
        The students on this list are covered by the university placement agreement, including consent to keep their training record (POPIA).
      </Consent>
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending || !rows.length}
                onClick={() => save.mutate({ organisationRef: org, blockRef, consent,
                  students: rows.map((r) => ({ names: r.names ?? "", studentNumber: r.studentNumber ?? "", email: r.email ?? "",
                    idNumber: r.idNumber ?? "", idType: idTypeOf(r.idNumber ?? "") })) },
                  { onSuccess: (r) => onDone(`${r.data.imported} imported onto ${blockRef}${r.data.skipped ? `, ${r.data.skipped} already enrolled and skipped` : ""} — ${r.data.placement}.`) })}>
          Import {rows.length || ""} {rows.length === 1 ? "student" : "students"}
        </button>
        <span className="small muted">Students already on the intake are matched by student number and skipped.</span>
      </div>
    </div>
  );
}

const ID_ALIASES = ["id", "id number", "id no", "identity number", "sa id", "said", "passport", "passport number", "id/passport",
  "id or passport", "id or passport number", "sa id or passport number", "sa id / passport", "id / passport number"];

// The delegate list template: the header row the form reads, ready to fill in Excel and save as CSV.
const DELEGATE_TEMPLATE = "Full name,SA ID or passport number,Email,Phone\r\n";

function downloadTemplate(name: string) {
  const blob = new Blob([DELEGATE_TEMPLATE], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function idCheck(raw: string | undefined, required: boolean): string | null {
  const v = (raw ?? "").trim();
  if (!v) return required ? "ID missing" : null;
  if (idTypeOf(v) === "SAID") return saIdProblem(v) ? "ID invalid" : null;
  return /^[A-Za-z0-9]{6,12}$/.test(v.replace(/[\s-]/g, "")) ? null : "ID invalid";
}

function Preview({ rows, columns, limit, required, requireId = false }: {
  rows: Row[]; columns: [string, string][]; limit?: number; required?: string; requireId?: boolean;
}) {
  return (
    <div>
      <Table rows={rows.map((r, i) => ({ ...r, _i: String(i + 1) }))} rowKey={(r) => r._i}
        columns={[
          { key: "_i", label: "#", render: (r) => r._i, mono: true },
          ...columns.map(([k, label]) => ({ key: k, label, render: (r: Row) => r[k] || <span className="muted">—</span> })),
          { key: "_s", label: "Check", render: (r: Row & { _i: string }) => {
            if (!r.names) return <Status tone="bad">Name missing</Status>;
            if (required && !r[required]) return <Status tone="bad">Number missing</Status>;
            const idProblem = idCheck(r.idNumber, requireId);
            if (idProblem) return <Status tone="bad">{idProblem}</Status>;
            if (limit !== undefined && Number(r._i) > limit) return <Status tone="bad">Over the quote</Status>;
            return <Status tone="ok">Ready</Status>;
          } },
        ]} />
    </div>
  );
}
