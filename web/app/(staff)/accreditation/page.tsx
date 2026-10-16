"use client";

// The accreditation workflow: what the Academy holds (and the courses each covers), renewals with
// their certificates and history, and applications (new scope or renewals) run through six steps with due dates.

import Link from "next/link";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { Modal } from "@/components/registration";
import { SearchSelect } from "@/components/SearchSelect";
import { ACCEPT } from "@/components/Prerequisites";
import { api, ApiError, upload } from "@/lib/api";
import type { Tone } from "@/lib/api";
import { useAction, useRegister, useScreen, useUpload } from "@/lib/hooks";

type Course = { code: string; title: string };
type Held = { ref: string; body: string; bodyCode: string; scope: string; number: string; granted: string | null; expires: string;
  tone: Tone; position: string; courses: Course[]; renewing: { ref: string; step: string }[]; certificate: { name: string; url: string } | null };
type StepDoc = { ref: string; title: string; added: string; url: string };
type Step = { step: string; due: string | null; done: string | null; note: string; late: boolean; hint: string; documents: StepDoc[] };
type Project = { ref: string; body: string; scope: string; owner: string; ownerRef: string; target: string; step: number; steps: string[];
  state: string; position: string; tone: Tone; renews: string | null; result: string | null; courses: Course[]; plan: Step[]; notes: string };
type Data = { held: Held[]; projects: Project[]; canManage: boolean; me: string };
type Options = { bodies: { code: string; name: string }[]; courses: Course[]; people: { ref: string; name: string }[]; steps: string[] };
type Detail = Held & { history: { ref: string; number: string; granted: string | null; expires: string; recorded: string; by: string }[];
  intakes: { ref: string; course: string; start: string; end: string; covered: boolean }[] };

const nice = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" }) : "—");

function CoursePicks({ all, value, onChange }: { all: Course[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="day-picks" role="group" aria-label="Courses covered">
      {all.map((c) => (
        <button key={c.code} type="button" className={value.includes(c.code) ? "on" : undefined} aria-pressed={value.includes(c.code)}
                onClick={() => onChange(value.includes(c.code) ? value.filter((x) => x !== c.code) : [...value, c.code])}>{c.title}</button>
      ))}
    </div>
  );
}

/** Renew a held accreditation (or record one already held), with its certificate, in one step. */
function HeldForm({ renew, onDone, onCancel }: { renew?: Held; onDone: (what: string) => void; onCancel: () => void }) {
  const opts = useRegister<Options>("/accreditations/options");
  const qc = useQueryClient();
  const screen = useScreen();
  const [f, setF] = useState({ body: renew?.bodyCode ?? "", scope: renew?.scope ?? "", number: renew?.number ?? "", granted: "", expires: "",
    courses: renew?.courses.map((c) => c.code) ?? [] as string[] });
  const [file, setFile] = useState<File | null>(null);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<ApiError | null>(null);
  if (!opts.data) return <p className="muted">Loading…</p>;
  const p: Record<string, string> = {};
  if (!renew && !f.body) p.body = "Choose the body.";
  if (!renew && !f.scope.trim()) p.scope = "Describe the scope.";
  if (!f.expires) p.expires = "Give the expiry date.";
  else if (renew && f.expires <= renew.expires) p.expires = `Must be after the current expiry (${renew.expires}).`;
  else if (f.granted && f.expires <= f.granted) p.expires = "Must be after the date granted.";
  const e = tried ? p : {};
  async function save() {
    setTried(true);
    if (Object.keys(p).length) return;
    setBusy(true);
    setRefusal(null);
    try {
      const body = { ...f, granted: f.granted || null, expires: f.expires };
      const r = renew ? await api<{ ref: string }>(`/accreditations/${renew.ref}/renew`, { method: "POST", screen, body })
        : await api<{ ref: string }>("/accreditations", { method: "POST", screen, body });
      if (file) await upload(`/accreditations/${r.data.ref}/certificate`, file, screen);
      await qc.invalidateQueries();
      onDone(r.meta.audit?.what ?? "");
    } catch (err) {
      if (err instanceof ApiError) setRefusal(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack-12">
      <Blocked refusal={refusal} />
      <div className="form-grid cols-4">
        {!renew ? (
          <>
            <div className="field"><label htmlFor="ah-body">Body</label>
              <select id="ah-body" value={f.body} className={e.body ? "invalid" : undefined} onChange={(x) => setF({ ...f, body: x.target.value })}>
                <option value="">Choose…</option>{opts.data.data.bodies.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
              </select>{e.body ? <span className="field-error">{e.body}</span> : null}</div>
            <div className="field" style={{ gridColumn: "span 3" }}><label htmlFor="ah-scope">Scope</label>
              <input id="ah-scope" value={f.scope} className={e.scope ? "invalid" : undefined} placeholder="e.g. Meat examination — red meat, poultry and game"
                     onChange={(x) => setF({ ...f, scope: x.target.value })} />{e.scope ? <span className="field-error">{e.scope}</span> : null}</div>
          </>
        ) : null}
        <div className="field"><label htmlFor="ah-no">Accreditation number <span className="optional">(optional)</span></label>
          <input id="ah-no" value={f.number} onChange={(x) => setF({ ...f, number: x.target.value })} /></div>
        <div className="field"><label htmlFor="ah-g">Granted <span className="optional">(optional)</span></label>
          <input id="ah-g" type="date" value={f.granted} onChange={(x) => setF({ ...f, granted: x.target.value })} /></div>
        <div className="field"><label htmlFor="ah-e">{renew ? "New expiry" : "Expires"}</label>
          <input id="ah-e" type="date" value={f.expires} className={e.expires ? "invalid" : undefined} onChange={(x) => setF({ ...f, expires: x.target.value })} />
          {e.expires ? <span className="field-error">{e.expires}</span> : null}</div>
        <div className="field"><label htmlFor="ah-file">Certificate <span className="optional">(PDF, JPG or PNG)</span></label>
          <input id="ah-file" type="file" accept={ACCEPT} onChange={(x) => setFile(x.target.files?.[0] ?? null)} /></div>
      </div>
      {!renew ? (
        <div className="field"><label>Courses it covers</label>
          <CoursePicks all={opts.data.data.courses} value={f.courses} onChange={(v) => setF({ ...f, courses: v })} /></div>
      ) : null}
      <div className="row">
        <button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? "Saving…" : renew ? "Record renewal" : "Record accreditation"}</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
        {renew ? <span className="small muted">The current record stays in the history; its courses carry over.</span> : null}
      </div>
    </div>
  );
}

function HeldPanel({ code, canManage, onDone }: { code: string; canManage: boolean; onDone: (w: string) => void }) {
  const q = useRegister<Detail>(`/accreditations/${code}`);
  const opts = useRegister<Options>("/accreditations/options");
  const courses = useAction<{ courses: string[] }>("PUT", `/accreditations/${code}/courses`);
  const [mode, setMode] = useState<"" | "renew" | "courses">("");
  const [picked, setPicked] = useState<string[] | null>(null);
  if (q.error) return <Blocked refusal={q.error} />;
  if (!q.data) return <p className="muted">Loading…</p>;
  const d = q.data.data;
  const sel = picked ?? d.courses.map((c) => c.code);
  return (
    <div className="stack-12">
      <div className="fac-summary">
        <div><span className="qd-label">Body</span><b>{d.body}</b><span className="small muted">{d.number ? `No. ${d.number}` : "No number recorded"}</span></div>
        <div><span className="qd-label">Valid</span><b>{nice(d.granted)} to {nice(d.expires)}</b><Status tone={d.tone}>{d.position}</Status></div>
        <div><span className="qd-label">Certificate</span>
          {d.certificate ? <a href={d.certificate.url} target="_blank" rel="noopener"><i className="fas fa-file-pdf" aria-hidden /> {d.certificate.name}</a>
            : <span className="small tone-warn">None on file</span>}</div>
        {canManage && !mode ? (
          <div className="fac-act" style={{ flexDirection: "row", gap: 8 }}>
            <button className="btn btn-sm btn-primary" onClick={() => setMode("renew")}><i className="fas fa-rotate" aria-hidden /> Record renewal</button>
            <button className="btn btn-sm" onClick={() => setMode("courses")}>Courses covered</button>
          </div>
        ) : null}
      </div>
      {d.renewing.length ? <p className="small" style={{ margin: 0 }}>Renewal under way: {d.renewing.map((r) => `${r.ref} (${r.step})`).join(", ")}. Recording the renewal here finishes it.</p> : null}
      {mode === "renew" ? <div className="card inset-form"><HeldForm renew={d} onCancel={() => setMode("")} onDone={(w) => { setMode(""); onDone(w); }} /></div> : null}
      {mode === "courses" && opts.data ? (
        <div className="card inset-form">
          <Blocked refusal={courses.refusal} />
          <CoursePicks all={opts.data.data.courses} value={sel} onChange={setPicked} />
          <div className="row">
            <button className="btn btn-primary" disabled={courses.isPending} onClick={() => courses.mutate({ courses: sel },
              { onSuccess: (r) => { setMode(""); setPicked(null); onDone(r.meta.audit?.what ?? ""); } })}>Save courses</button>
            <button className="btn" onClick={() => { setMode(""); setPicked(null); }}>Cancel</button>
          </div>
        </div>
      ) : null}
      <div className="fac-cols">
        <section>
          <div className="eyebrow">Courses covered · {d.courses.length}</div>
          {d.courses.length ? d.courses.map((c) => <div key={c.code} className="small">{c.title} <span className="muted">{c.code}</span></div>)
            : <p className="small muted" style={{ margin: 0 }}>No course linked yet.</p>}
          <div className="eyebrow" style={{ marginTop: 12 }}>Intakes that depend on it</div>
          {d.intakes.length ? (
            <table className="plain-table">
              <thead><tr><th>Intake</th><th>Course</th><th>Dates</th><th /></tr></thead>
              <tbody>{d.intakes.map((b) => (
                <tr key={b.ref}><td><Link href={`/plan?focus=${b.ref}`}>{b.ref}</Link></td><td>{b.course}</td><td>{b.start} to {b.end}</td>
                  <td>{b.covered ? <Status tone="ok">Covered</Status> : <Status tone="bad">Not covered</Status>}</td></tr>
              ))}</tbody>
            </table>
          ) : <p className="small muted" style={{ margin: 0 }}>No upcoming intakes.</p>}
        </section>
        <section>
          <div className="eyebrow">History</div>
          <ul className="fac-history">
            {d.history.map((h, i) => (
              <li key={h.ref} className={i === 0 ? "now" : ""}>
                <b>{h.ref}</b> <span className="small muted">{h.number ? `· No. ${h.number}` : ""}</span>
                <div className="small">{nice(h.granted)} to {nice(h.expires)}</div>
                <div className="small muted">Recorded by {h.by}, {h.recorded}</div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

function ProjectForm({ onDone, onCancel, held }: { onDone: (w: string) => void; onCancel: () => void; held: Held[] }) {
  const opts = useRegister<Options>("/accreditations/options");
  const save = useAction<Record<string, unknown>>("POST", "/accreditation-projects");
  const [f, setF] = useState({ body: "", scope: "", owner: "", target: "", renews: "", courses: [] as string[] });
  const [tried, setTried] = useState(false);
  if (!opts.data) return <p className="muted">Loading…</p>;
  const today = new Date().toISOString().slice(0, 10);
  const p: Record<string, string> = {};
  if (!f.body) p.body = "Choose the body.";
  if (!f.scope.trim()) p.scope = "Describe the scope sought.";
  if (!f.owner) p.owner = "Choose who runs it.";
  if (!f.target || f.target <= today) p.target = "Give a target date in the future.";
  const e = tried ? p : {};
  return (
    <div className="stack-12">
      <Blocked refusal={save.refusal} />
      <div className="form-grid cols-4">
        <div className="field"><label htmlFor="ap-body">Body</label>
          <select id="ap-body" value={f.body} className={e.body ? "invalid" : undefined} onChange={(x) => setF({ ...f, body: x.target.value })}>
            <option value="">Choose…</option>{opts.data.data.bodies.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
          </select>{e.body ? <span className="field-error">{e.body}</span> : null}</div>
        <div className="field" style={{ gridColumn: "span 3" }}><label htmlFor="ap-scope">Scope sought</label>
          <input id="ap-scope" value={f.scope} className={e.scope ? "invalid" : undefined} placeholder="e.g. Extension of scope — game meat examination"
                 onChange={(x) => setF({ ...f, scope: x.target.value })} />{e.scope ? <span className="field-error">{e.scope}</span> : null}</div>
        <div className="field"><label htmlFor="ap-owner">Run by</label>
          <SearchSelect id="ap-owner" value={f.owner} invalid={!!e.owner} onChange={(v) => setF({ ...f, owner: v })} placeholder="Type to search people…"
                        options={opts.data.data.people.map((x) => ({ value: x.ref, label: x.name }))} />
          {e.owner ? <span className="field-error">{e.owner}</span> : null}</div>
        <div className="field"><label htmlFor="ap-target">Target date</label>
          <input id="ap-target" type="date" min={today} value={f.target} className={e.target ? "invalid" : undefined} onChange={(x) => setF({ ...f, target: x.target.value })} />
          {e.target ? <span className="field-error">{e.target}</span> : null}</div>
        <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor="ap-renews">Renews <span className="optional">(optional)</span></label>
          <select id="ap-renews" value={f.renews} onChange={(x) => {
            const h = held.find((y) => y.ref === x.target.value);
            setF({ ...f, renews: x.target.value, body: h?.bodyCode ?? f.body, scope: h ? `Renewal — ${h.scope}` : f.scope, courses: h ? h.courses.map((c) => c.code) : f.courses });
          }}>
            <option value="">No: new scope</option>{held.map((h) => <option key={h.ref} value={h.ref}>{h.ref} · {h.body} · {h.scope}</option>)}
          </select></div>
      </div>
      <div className="field"><label>Courses it will cover</label>
        <CoursePicks all={opts.data.data.courses} value={f.courses} onChange={(v) => setF({ ...f, courses: v })} /></div>
      <p className="small muted" style={{ margin: 0 }}>The six steps ({opts.data.data.steps.join(" → ")}) get due dates spread evenly up to the target; adjust them on the application after starting.</p>
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending} onClick={() => {
          setTried(true);
          if (Object.keys(p).length) return;
          save.mutate(f, { onSuccess: (r) => onDone(r.meta.audit?.what ?? "") });
        }}>Start application</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

/** File a document against a step of an application. */
function StepUpload({ app, n, first, onDone }: { app: string; n: number; first: boolean; onDone: (w: string) => void }) {
  const send = useUpload((ref) => `/accreditation-projects/${ref}/steps/${n}/documents`);
  return (
    <label className="btn btn-sm" style={{ cursor: "pointer", marginTop: first ? 0 : 4 }}>
      <i className="fas fa-upload" aria-hidden /> {send.isPending ? "Uploading…" : first ? "Upload" : "Add another"}
      <input type="file" accept={ACCEPT} hidden onChange={(e) => {
        const f = e.target.files?.[0];
        if (f) send.mutate({ ref: app, file: f }, { onSuccess: (r) => onDone(r.meta.audit?.what ?? "") });
        e.target.value = "";
      }} />
      {send.refusal ? <span className="field-error"> {send.refusal.blockedBy[0] ?? send.refusal.message}</span> : null}
    </label>
  );
}

function ProjectPanel({ p, canManage, me, onDone }: { p: Project; canManage: boolean; me: string; onDone: (w: string) => void }) {
  const step = useAction<Record<string, unknown>>("POST", `/accreditation-projects/${p.ref}/step`);
  const replan = useAction<Record<string, unknown>>("PATCH", `/accreditation-projects/${p.ref}`);
  const withdraw = useAction<{ reason: string }>("POST", `/accreditation-projects/${p.ref}/withdraw`);
  const [note, setNote] = useState("");
  const [grant, setGrant] = useState({ number: "", granted: "", expires: "" });
  const [due, setDue] = useState<string[] | null>(null);
  const [reason, setReason] = useState("");
  const [withdrawing, setWithdrawing] = useState(false);
  const active = p.state === "Active";
  const canMove = active && (canManage || p.ownerRef === me);
  const last = p.step === p.steps.length - 1;
  const current = p.plan[p.step];
  const hasDoc = !!current && current.documents.length > 0;
  const dates = due ?? p.plan.map((s) => s.due ?? "");
  const refusal = step.refusal ?? replan.refusal ?? withdraw.refusal;
  return (
    <div className="stack-12">
      <Blocked refusal={refusal} />
      <table className="plain-table">
        <thead><tr><th>Step</th><th>Due</th><th>Done</th><th>Documents</th><th>Note</th></tr></thead>
        <tbody>
          {p.plan.map((s, i) => (
            <tr key={s.step} className={i === p.step && active ? "step-now" : undefined}>
              <td><b>{i + 1}. {s.step}</b>{i === p.step && active ? <span className="for-tag co">Now</span> : null}</td>
              <td>{canManage && active && due !== null && i >= p.step
                ? <input type="date" aria-label={`${s.step} due`} value={dates[i]} onChange={(x) => setDue(dates.map((d, j) => (j === i ? x.target.value : d)))} />
                : <>{nice(s.due)}{s.late ? <> <Status tone="bad">Late</Status></> : null}</>}</td>
              <td>{s.done ? nice(s.done) : "—"}</td>
              <td className="small">
                {s.documents.map((d) => (
                  <div key={d.ref}><a href={d.url} target="_blank" rel="noopener"><i className="fas fa-file-lines" aria-hidden /> {d.title}</a></div>
                ))}
                {(canManage || p.ownerRef === me) && p.state !== "Withdrawn"
                  ? <StepUpload app={p.ref} n={i + 1} onDone={onDone} first={!s.documents.length} />
                  : !s.documents.length ? "—" : null}
              </td>
              <td className="small">{s.note || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {due !== null ? (
        <div className="row">
          <button className="btn btn-primary" disabled={replan.isPending} onClick={() => replan.mutate({ due: dates }, { onSuccess: (r) => { setDue(null); onDone(r.meta.audit?.what ?? ""); } })}>Save due dates</button>
          <button className="btn" onClick={() => setDue(null)}>Cancel</button>
        </div>
      ) : null}
      {canMove ? (
        <div className="card inset-form">
          <b>Complete “{p.steps[p.step]}”</b>
          {!hasDoc ? <p className="small tone-warn" style={{ margin: 0 }}>Attach the document first: {current?.hint}.</p> : null}
          {last ? (
            <div className="form-grid cols-4">
              <div className="field"><label htmlFor={`pg-n-${p.ref}`}>Accreditation number <span className="optional">(optional)</span></label>
                <input id={`pg-n-${p.ref}`} value={grant.number} onChange={(x) => setGrant({ ...grant, number: x.target.value })} /></div>
              <div className="field"><label htmlFor={`pg-g-${p.ref}`}>Granted</label>
                <input id={`pg-g-${p.ref}`} type="date" value={grant.granted} onChange={(x) => setGrant({ ...grant, granted: x.target.value })} /></div>
              <div className="field"><label htmlFor={`pg-e-${p.ref}`}>Expires</label>
                <input id={`pg-e-${p.ref}`} type="date" value={grant.expires} onChange={(x) => setGrant({ ...grant, expires: x.target.value })} /></div>
            </div>
          ) : null}
          <div className="field"><label htmlFor={`pn-${p.ref}`}>Note <span className="optional">(optional)</span></label>
            <input id={`pn-${p.ref}`} value={note} placeholder={last ? "e.g. Letter of accreditation received" : "e.g. Signed off by the training manager"}
                   onChange={(x) => setNote(x.target.value)} /></div>
          <div className="row">
            <button className="btn btn-primary" disabled={step.isPending || !hasDoc || (last && !grant.expires)}
                    onClick={() => step.mutate({ note, ...(last ? { number: grant.number, granted: grant.granted || null, expires: grant.expires } : {}) },
                      { onSuccess: (r) => { setNote(""); onDone(r.meta.audit?.what ?? ""); } })}>
              {last ? "Record accreditation" : `Mark “${p.steps[p.step]}” complete`}</button>
            {canManage && due === null ? <button className="btn" onClick={() => setDue(p.plan.map((s) => s.due ?? ""))}>Change due dates</button> : null}
            <span className="spacer" />
            {canManage && !withdrawing ? <button className="btn btn-ghost-danger" onClick={() => setWithdrawing(true)}>Withdraw application</button> : null}
          </div>
        </div>
      ) : null}
      {withdrawing ? (
        <div className="card inset-form">
          <div className="field"><label htmlFor={`pw-${p.ref}`}>Why is {p.ref} being withdrawn?</label>
            <input id={`pw-${p.ref}`} value={reason} onChange={(x) => setReason(x.target.value)} /></div>
          <div className="row">
            <button className="btn btn-danger" disabled={!reason.trim() || withdraw.isPending}
                    onClick={() => withdraw.mutate({ reason }, { onSuccess: (r) => { setWithdrawing(false); onDone(r.meta.audit?.what ?? ""); } })}>Withdraw</button>
            <button className="btn" onClick={() => setWithdrawing(false)}>Keep it</button>
          </div>
        </div>
      ) : null}
      <p className="small muted" style={{ margin: 0 }}>
        Covers: {p.courses.map((c) => c.title).join(", ") || "no course linked"}{p.renews ? ` · renews ${p.renews}` : ""}{p.result ? ` · produced ${p.result}` : ""}
      </p>
    </div>
  );
}

export default function Accreditation() {
  const q = useRegister<Data>("/accreditations");
  const [openHeld, setOpenHeld] = useState<string | null>(null);
  const [openProject, setOpenProject] = useState<string | null>(null);
  const [adding, setAdding] = useState<"" | "held" | "project">("");
  const [notice, setNotice] = useState("");
  const [showClosed, setShowClosed] = useState(false);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { held, projects, canManage, me } = q.data.data;
  const say = (w: string) => { setNotice(w); setAdding(""); window.setTimeout(() => setNotice(""), 10000); };
  const shownProjects = projects.filter((p) => showClosed || p.state === "Active");
  return (
    <>
      <Hero
        stats={[
          { v: String(held.length), l: "Held", c: "Accreditations in force" },
          { v: String(held.filter((h) => h.tone !== "ok").length), l: "Renewals due", c: "Within ninety days, or lapsed" },
          { v: String(projects.filter((p) => p.state === "Active").length), l: "Applications", c: "New scope and renewals under way" },
          { v: String(projects.filter((p) => p.state === "Active" && p.tone === "bad").length), l: "Steps overdue", c: "Past their due date" },
        ]}
      />
      {notice ? <div className="callout ok" role="status"><p><b>Saved.</b> {notice}</p></div> : null}
      <SectionHead title="Accreditations held">
        {canManage ? <button className="btn btn-teal" onClick={() => setAdding("held")}>Record an accreditation</button> : null}
      </SectionHead>
      <Register rows={held} rowKey={(h) => h.ref} onRow={(h) => setOpenHeld(h.ref === openHeld ? null : h.ref)}
        expanded={(h) => (h.ref === openHeld ? <HeldPanel code={h.ref} canManage={canManage} onDone={say} /> : null)}
        columns={[
          { key: "ref", label: "Reference", render: (h) => h.ref, mono: true },
          { key: "body", label: "Body", render: (h) => <b>{h.body}</b> },
          { key: "scope", label: "Scope", render: (h) => <>{h.scope}<div className="small muted">{h.courses.length} {h.courses.length === 1 ? "course" : "courses"} covered</div></> },
          { key: "exp", label: "Expires", render: (h) => h.expires, mono: true },
          { key: "pos", label: "Position", render: (h) => <Status tone={h.tone}>{h.position}</Status> },
        ]} />
      <SectionHead title="Applications — new scope and renewals">
        <div className="row">
          <label className="small" style={{ color: "#fff" }}><input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} /> Show finished and withdrawn</label>
          {canManage ? <button className="btn btn-teal" onClick={() => setAdding("project")}>Start an application</button> : null}
        </div>
      </SectionHead>
      <Register rows={shownProjects} rowKey={(p) => p.ref} empty="No application under way." onRow={(p) => setOpenProject(p.ref === openProject ? null : p.ref)}
        expanded={(p) => (p.ref === openProject ? <ProjectPanel key={JSON.stringify(p)} p={p} canManage={canManage} me={me} onDone={say} /> : null)}
        columns={[
          { key: "ref", label: "Application", render: (p) => p.ref, mono: true },
          { key: "scope", label: "Scope", render: (p) => <><b>{p.body}</b> · {p.scope}</> },
          { key: "rail", label: "Progress", render: (p) => (
            <div style={{ minWidth: 220 }}>
              <div className="rail-steps" aria-hidden>{p.steps.map((s, i) => <i key={s} className={p.state === "Accredited" || i < p.step ? "done" : i === p.step ? "now" : ""} />)}</div>
              <div className="small muted">Step {Math.min(p.step + 1, p.steps.length)} of {p.steps.length}: {p.steps[p.step]}</div>
            </div>
          ) },
          { key: "owner", label: "Run by", render: (p) => p.owner },
          { key: "target", label: "Target", render: (p) => p.target, mono: true },
          { key: "pos", label: "Position", render: (p) => <Status tone={p.tone}>{p.position}</Status> },
        ]} />
      {adding === "held" ? (
        <Modal title="Record an accreditation" onClose={() => setAdding("")} wide>
          <HeldForm onDone={say} onCancel={() => setAdding("")} />
        </Modal>
      ) : null}
      {adding === "project" ? (
        <Modal title="Start an accreditation application" onClose={() => setAdding("")} wide>
          <ProjectForm held={held} onDone={say} onCancel={() => setAdding("")} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
