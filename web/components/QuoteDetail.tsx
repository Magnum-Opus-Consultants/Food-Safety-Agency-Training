"use client";

// One quotation, opened under its row on the register: who it is for, what was quoted, where it is in
// its life, the enquiry it answers, and the people registered against it.

import { useState } from "react";
import { Blocked, Status } from "@/components/ui";
import { courseOptions, SearchSelect } from "@/components/SearchSelect";
import { useAction, useRegister } from "@/lib/hooks";

type Detail = {
  ref: string; state: string; individual: boolean; client: string; employer: string;
  contact: { names: string; email: string; phone: string };
  course: string; courseCode: string; basis: string; learners: number; value: string; perLearner: string;
  createdAt: string; createdBy: string | null; issued: string | null; followUpDue: string | null; owner: string | null; approval: string;
  enquiry: { ref: string; received: string; stage: string } | null;
  followUps: { at: string; by: string | null; note: string }[];
  delegates: { enrolment: string; learner: string; learnerRef: string; intake: string | null; start: string | null; stage: string }[];
  canEdit: boolean; canApprove: boolean; needsApproval: boolean; valueRands: string; basisCode: string;
};

const LIMIT = 50000;

/** A draft can be changed until it is issued. The head of department can save the changes and approve in one step. */
function EditDraft({ d, onClose }: { d: Detail; onClose: () => void }) {
  const courses = useRegister<{ code: string; title: string }[]>("/courses");
  const save = useAction<Record<string, unknown>>("PATCH", `/quotations/${d.ref}`);
  const [f, setF] = useState({ courseCode: d.courseCode, basis: d.basisCode, learners: String(d.learners), value: d.valueRands });
  const amount = Number(f.value.replace(/[R\s]/g, "").replace(",", "."));
  const n = Number(f.learners);
  const errors: Record<string, string> = {};
  if (!f.courseCode) errors.course = "Choose the course.";
  if (!Number.isInteger(n) || n < 1) errors.learners = "Give the number of learners.";
  if (Number.isNaN(amount) || amount <= 0) errors.value = "Give the value in rand.";
  const blocked = Object.keys(errors).length > 0;
  const body = (approve: boolean) => ({ courseCode: f.courseCode, basis: f.basis, learners: n, value: f.value, approve });
  return (
    <div className="card inset-form">
      <Blocked refusal={save.refusal} />
      <div className="form-grid">
        <div className="field"><label htmlFor={`qe-${d.ref}-course`}>Course</label>
          <SearchSelect id={`qe-${d.ref}-course`} options={courseOptions(courses.data?.data ?? [])} value={f.courseCode}
                        invalid={!!errors.course} onChange={(v) => setF({ ...f, courseCode: v })} /></div>
        <div className="field"><label htmlFor={`qe-${d.ref}-basis`}>Basis</label>
          <select id={`qe-${d.ref}-basis`} value={f.basis} disabled={d.individual} onChange={(e) => setF({ ...f, basis: e.target.value })}>
            <option value="PerGroup">Per group</option><option value="PerLearner">Per learner</option>
          </select></div>
        <div className="field"><label htmlFor={`qe-${d.ref}-n`}>Learners</label>
          <input id={`qe-${d.ref}-n`} inputMode="numeric" value={f.learners} className={errors.learners ? "invalid" : undefined}
                 onChange={(e) => setF({ ...f, learners: e.target.value })} />
          {errors.learners ? <span className="field-error">{errors.learners}</span> : null}</div>
        <div className="field"><label htmlFor={`qe-${d.ref}-v`}>Value (R)</label>
          <input id={`qe-${d.ref}-v`} inputMode="decimal" value={f.value} className={errors.value ? "invalid" : undefined}
                 onChange={(e) => setF({ ...f, value: e.target.value })} />
          {errors.value ? <span className="field-error">{errors.value}</span>
            : amount > LIMIT ? <span className="small tone-warn">Over R 50 000: needs the head of department&rsquo;s approval.</span> : null}</div>
      </div>
      <div className="row">
        {d.canApprove && amount > LIMIT ? (
          <button className="btn btn-primary" disabled={save.isPending || blocked} onClick={() => save.mutate(body(true), { onSuccess: onClose })}>
            Save and approve</button>
        ) : null}
        <button className={`btn${d.canApprove && amount > LIMIT ? "" : " btn-primary"}`} disabled={save.isPending || blocked}
                onClick={() => save.mutate(body(false), { onSuccess: onClose })}>Save changes</button>
        <button className="btn" onClick={onClose}>Cancel</button>
        <span className="small muted">Every change is recorded with its previous value. Once issued, the quotation can no longer be changed.</span>
      </div>
    </div>
  );
}

const STEPS = ["Draft", "Issued", "Accepted"];

export function QuoteDetail({ code, edit = false }: { code: string; edit?: boolean }) {
  const q = useRegister<Detail>(`/quotations/${code}`);
  if (q.error) return <Blocked refusal={q.error} />;
  if (!q.data) return <p className="muted">Loading…</p>;
  const d = q.data.data;
  return <QuoteBody key={String(edit)} d={d} startEditing={edit && d.canEdit} />;
}

function QuoteBody({ d, startEditing }: { d: Detail; startEditing: boolean }) {
  const [editing, setEditing] = useState(startEditing);
  const step = STEPS.indexOf(d.state);
  const row = (label: string, value: React.ReactNode) => (
    <div className="qd-row"><span className="qd-label">{label}</span><span>{value || "—"}</span></div>
  );
  return (
    <div className="stack-12">
      {step >= 0 ? (
        <div className="stage-rail">{STEPS.map((s, i) => (
          <div key={s} className={i < step ? "done" : i === step ? "now" : ""}><i aria-hidden /><span>{s}</span></div>
        ))}</div>
      ) : <Status tone="bad">{d.state}</Status>}
      {d.canEdit && !editing ? (
        <div className="row">
          <button className="btn btn-sm" onClick={() => setEditing(true)}><i className="fas fa-pen" aria-hidden /> Edit quotation</button>
          {d.needsApproval && d.canApprove ? <span className="small muted">You can change the quotation, then approve it in the same step.</span> : null}
        </div>
      ) : null}
      {editing ? <EditDraft d={d} onClose={() => setEditing(false)} /> : null}
      <div className="account-detail">
        <section>
          <div className="eyebrow">{d.individual ? "Quoted to" : "Client"}</div>
          {row(d.individual ? "Person" : "Company", <b>{d.client}</b>)}
          {d.individual && d.employer ? row("Employer", `${d.employer} (not billed)`) : null}
          {row("Contact", d.contact.names)}
          {row("Email", d.contact.email ? <a href={`mailto:${d.contact.email}`}>{d.contact.email}</a> : "")}
          {row("Phone", d.contact.phone)}
        </section>
        <section>
          <div className="eyebrow">Quoted</div>
          {row("Course", <>{d.course} <span className="mono muted small">{d.courseCode}</span></>)}
          {row("Basis", d.basis)}
          {row("Learners", d.learners)}
          {row("Value", <b className="mono">{d.value}</b>)}
          {row("Per learner", <span className="mono">{d.perLearner}</span>)}
        </section>
        <section>
          <div className="eyebrow">Life of the quotation</div>
          {row("Created", `${d.createdAt}${d.createdBy ? ` by ${d.createdBy}` : ""}`)}
          {row("Approval", d.approval)}
          {row("Issued", d.issued ?? "Not yet: still a draft")}
          {row("Follow-up due", d.followUpDue)}
          {row("Owner", d.owner ?? "Unassigned")}
          {row("Enquiry", d.enquiry ? <><span className="mono">{d.enquiry.ref}</span> · received {d.enquiry.received} · {d.enquiry.stage}</> : "Not from an enquiry")}
        </section>
      </div>
      <div>
        <div className="eyebrow">Follow-ups</div>
        {d.followUps.length ? d.followUps.map((f, i) => (
          <div key={i} className="small"><span className="mono">{f.at}</span> · {f.note}{f.by ? ` · ${f.by}` : ""}</div>
        )) : <p className="small muted" style={{ margin: 0 }}>None recorded.</p>}
      </div>
      <div>
        <div className="eyebrow">{d.individual ? "Registration" : "Delegates registered"} · {d.delegates.length} of {d.learners}</div>
        {d.delegates.length ? (
          <table className="plain-table">
            <thead><tr><th>Enrolment</th><th>Learner</th><th>Intake</th><th>Stage</th></tr></thead>
            <tbody>
              {d.delegates.map((x) => (
                <tr key={x.enrolment}>
                  <td className="mono">{x.enrolment}</td>
                  <td>{x.learner} <span className="mono muted small">{x.learnerRef}</span></td>
                  <td className="mono">{x.intake ? `${x.intake} · ${x.start}` : "—"}</td>
                  <td>{x.stage}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="small muted" style={{ margin: 0 }}>Nobody registered yet.</p>}
      </div>
    </div>
  );
}
