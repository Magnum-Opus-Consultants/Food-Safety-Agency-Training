"use client";

// The three ways a learner becomes part of the system: from an enquiry (or directly), as a
// corporate group's delegate list, or as a university cohort list. The API enforces every rule;
// these forms only gather the details and render its refusals verbatim.

import { ReactNode, useState } from "react";
import { Blocked, Register as Table, Status } from "@/components/ui";
import { parseList, Row } from "@/lib/csv";
import { useAction, useRegister } from "@/lib/hooks";
import { idTypeOf, saIdProblem } from "@/lib/said";

export type Intake = {
  ref: string; courseCode: string; course: string; gated: boolean; start: string; end: string; venue: string;
  facilitator: string; seats: number; capacity: number; free: number; state: string;
};

function intakeLabel(i: Intake) {
  return `${i.ref} · ${i.start} → ${i.end} · ${i.venue} · ${i.free} of ${i.capacity} seats free${i.state === "Draft" ? " · draft" : ""}`;
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="scrim" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3 className="modal-title">{title}</h3>
          <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function IntakeSelect({ course, value, onChange, need = 1 }: { course?: string; value: string; onChange: (v: string) => void; need?: number }) {
  const q = useRegister<Intake[]>(`/intakes${course ? `?course=${course}` : ""}`);
  const intakes = q.data?.data ?? [];
  return (
    <div className="field">
      <label htmlFor="intake">Intake</label>
      <select id="intake" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{intakes.length ? "Choose an intake from the plan" : course ? "No current intake for this course on the plan" : "Choose a course first"}</option>
        {intakes.map((i) => (
          <option key={i.ref} value={i.ref} disabled={i.free < need}>{intakeLabel(i)}{i.free < need ? " — not enough seats" : ""}</option>
        ))}
      </select>
    </div>
  );
}

function Consent({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{children}</span>
    </label>
  );
}

// --- route 1: an individual ---------------------------------------------------------------

export type Prefill = { enquiryRef?: string; names?: string; email?: string; phone?: string; organisation?: string; courseCode?: string };

export function RegisterLearnerForm({ prefill, onDone }: { prefill?: Prefill; onDone: (enrolmentRef: string) => void }) {
  const courses = useRegister<{ code: string; title: string; gated: boolean }[]>("/courses");
  const [f, setF] = useState({
    names: prefill?.names ?? "", email: prefill?.email ?? "", phone: prefill?.phone ?? "",
    organisation: prefill?.organisation ?? "", learnerType: prefill?.organisation ? "Corporate" : "Public",
    courseCode: prefill?.courseCode ?? "", blockRef: "", prerequisiteResult: "", grade10EvidenceHeld: false, consent: false,
    idType: "SAID", idNumber: "",
  });
  const idHint = f.idType === "SAID" && f.idNumber.trim() ? saIdProblem(f.idNumber) : null;
  const set = (k: string, v: string | boolean) => setF((x) => ({ ...x, [k]: v }));
  const save = useAction<Record<string, unknown>, { ref: string }>("POST", "/enrolments");
  const course = (courses.data?.data ?? []).find((c) => c.code === f.courseCode);

  function submit() {
    save.mutate({
      enquiryRef: prefill?.enquiryRef ?? "", names: f.names, email: f.email, phone: f.phone, organisation: f.organisation,
      learnerType: f.learnerType, blockRef: f.blockRef, consent: f.consent, grade10EvidenceHeld: f.grade10EvidenceHeld,
      idType: f.idType, idNumber: f.idNumber,
      prerequisiteResult: f.prerequisiteResult === "" ? null : Number(f.prerequisiteResult),
    }, { onSuccess: (r) => onDone(r.data.ref) });
  }

  return (
    <div className="stack-12">
      {prefill?.enquiryRef ? <p className="small muted" style={{ margin: 0 }}>From <span className="mono">{prefill.enquiryRef}</span>. On save the enquiry moves to Registered.</p> : null}
      <Blocked refusal={save.refusal} />
      <div className="eyebrow">Learner</div>
      <div className="form-grid">
        <div className="field"><label htmlFor="rl-names">Full name</label><input id="rl-names" value={f.names} onChange={(e) => set("names", e.target.value)} /></div>
        <div className="field"><label htmlFor="rl-type">Learner type</label>
          <select id="rl-type" value={f.learnerType} onChange={(e) => set("learnerType", e.target.value)}>
            <option value="Public">Public applicant</option><option value="Corporate">Corporate delegate</option>
            <option value="University">University student</option><option value="Employee">FSA employee</option>
          </select></div>
        <div className="field"><label htmlFor="rl-org">Organisation {f.learnerType === "Corporate" ? "" : "(optional)"}</label><input id="rl-org" value={f.organisation} onChange={(e) => set("organisation", e.target.value)} /></div>
        <div className="field"><label htmlFor="rl-idtype">Identity document</label>
          <select id="rl-idtype" value={f.idType} onChange={(e) => set("idType", e.target.value)}>
            <option value="SAID">SA ID number</option><option value="Passport">Passport</option>
          </select></div>
        <div className="field"><label htmlFor="rl-id">{f.idType === "SAID" ? "SA ID number" : "Passport number"}{f.learnerType === "University" ? " (optional)" : ""}</label>
          <input id="rl-id" inputMode={f.idType === "SAID" ? "numeric" : "text"} autoComplete="off" value={f.idNumber}
                 onChange={(e) => set("idNumber", e.target.value)} aria-invalid={!!idHint} />
          {idHint ? <span className="small tone-bad">{idHint}</span>
            : <span className="small muted">Encrypted on save; only the last four digits are ever shown.</span>}</div>
        <div className="field"><label htmlFor="rl-email">Email</label><input id="rl-email" type="email" value={f.email} onChange={(e) => set("email", e.target.value)} /></div>
        <div className="field"><label htmlFor="rl-phone">Phone</label><input id="rl-phone" value={f.phone} onChange={(e) => set("phone", e.target.value)} /></div>
      </div>
      <div className="eyebrow">Course and intake</div>
      <div className="form-grid">
        <div className="field"><label htmlFor="rl-course">Course</label>
          <select id="rl-course" value={f.courseCode} onChange={(e) => setF((x) => ({ ...x, courseCode: e.target.value, blockRef: "" }))}>
            <option value="">Choose a course</option>
            {(courses.data?.data ?? []).map((c) => <option key={c.code} value={c.code}>{c.title}</option>)}
          </select></div>
        {f.courseCode ? <IntakeSelect course={f.courseCode} value={f.blockRef} onChange={(v) => set("blockRef", v)} /> : null}
      </div>
      {course?.gated ? (
        <>
          <div className="eyebrow">Entry gate — prerequisite ≥ 50% and Grade 10, both required</div>
          <div className="form-grid">
            <div className="field"><label htmlFor="rl-test">Prerequisite result (%) if written</label>
              <input id="rl-test" inputMode="decimal" value={f.prerequisiteResult} onChange={(e) => set("prerequisiteResult", e.target.value)} /></div>
            <Consent checked={f.grade10EvidenceHeld} onChange={(v) => set("grade10EvidenceHeld", v)}>Grade 10 evidence received</Consent>
          </div>
          <p className="small muted" style={{ margin: 0 }}>The enrolment opens at Applied and cannot advance until both parts of the gate are complete.</p>
        </>
      ) : null}
      <Consent checked={f.consent} onChange={(v) => set("consent", v)}>
        The learner consents to the FSA Academy keeping their personal information for their training record (POPIA).
      </Consent>
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending} onClick={submit}>Register learner</button>
        <span className="small muted">Registering books a seat on the intake and writes an audit entry.</span>
      </div>
    </div>
  );
}

// --- route 2: a corporate group's delegate list --------------------------------------------

export function DelegatesForm({ quote, onDone }: {
  quote: { ref: string; client: string; course: string; courseCode: string; learners: number; registered: number };
  onDone: () => void;
}) {
  const [blockRef, setBlockRef] = useState("");
  const [text, setText] = useState("");
  const [consent, setConsent] = useState(false);
  const save = useAction<Record<string, unknown>>("POST", `/quotations/${quote.ref}/delegates`);
  const rows = parseList(text, ["names", "idNumber", "email", "phone"], {
    names: ["name", "names", "full name", "delegate"], idNumber: ID_ALIASES,
    email: ["email", "e-mail"], phone: ["phone", "cell", "mobile", "telephone"],
  });
  const room = quote.learners - quote.registered;
  return (
    <div className="stack-12">
      <p style={{ margin: 0 }}><b>{quote.client}</b> · {quote.course} · quoted for {quote.learners}, {quote.registered} registered, {room} to add.</p>
      <Blocked refusal={save.refusal} />
      <IntakeSelect course={quote.courseCode} value={blockRef} onChange={setBlockRef} need={Math.max(rows.length, 1)} />
      <div className="field">
        <label htmlFor="dl-list">Delegates — one per line: name, SA ID or passport number, email, phone (or paste from Excel)</label>
        <textarea id="dl-list" rows={6} value={text} onChange={(e) => setText(e.target.value)}
                  placeholder={"Johan Kruger, 8001015009087, johan@chalmar.co.za, 082 555 0101\nNomvula Sithole, A12345678, nomvula@chalmar.co.za"} />
      </div>
      {rows.length ? <Preview rows={rows} columns={[["names", "Name"], ["idNumber", "ID number"], ["email", "Email"], ["phone", "Phone"]]}
                              limit={room} requireId /> : null}
      <Consent checked={consent} onChange={setConsent}>
        {quote.client} has confirmed that each delegate consents to the FSA Academy keeping their personal information (POPIA).
      </Consent>
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending || !rows.length}
                onClick={() => save.mutate({ blockRef, consent, delegates: rows.map((r) => ({ names: r.names ?? "", idNumber: r.idNumber ?? "", idType: idTypeOf(r.idNumber ?? ""),
                  email: r.email ?? "", phone: r.phone ?? "" })) },
                  { onSuccess: onDone })}>
          Register {rows.length || ""} {rows.length === 1 ? "delegate" : "delegates"}
        </button>
        <span className="small muted">All or nothing: if any delegate cannot be registered, none are.</span>
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

const ID_ALIASES = ["id", "id number", "id no", "identity number", "sa id", "said", "passport", "passport number", "id/passport"];

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
      <div className="source">{rows.length} {rows.length === 1 ? "row" : "rows"} read. The API checks them again on save.</div>
    </div>
  );
}
