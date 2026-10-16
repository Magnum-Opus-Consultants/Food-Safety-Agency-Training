"use client";

// Universities and vet placements: each placement runs from the university's student list, through the documents sent to the abattoir and its confirmation, to marking at the abattoir
// and the report back within twenty days. Open a placement to work its checklist and see the report.

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { CohortImportForm, Modal } from "@/components/registration";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { ApiError, upload, type Tone } from "@/lib/api";
import { useAction, useMe, useRegister, useScreen } from "@/lib/hooks";

type Attendance = { present: number; of: number; percent: number } | null;
type Student = { enrolment: string; learner: string; studentNumber: string; attendance: Attendance; result: string | null; mark: number | null;
  standing: string; moderatedBy: string | null; moderatedOn: string | null; remediation: string; certificate: string | null };
type Step = { key: string; label: string; done: boolean; note: string };
type Doc = { ref: string; kind: string; title: string; added: string; url: string };
type Placement = { ref: string; university: string; universityRef: string; cohort: string; size: number; periodStart: string; periodEnd: string;
  reportDue: string; position: string; tone: Tone; intake: string | null; abattoir: string | null; facilitator: string | null; rule: string | null;
  students: Student[]; checklist: Step[]; documents: Doc[]; reportBlockedBy: string[]; reportPreview: string };
type Uni = { ref: string; name: string; rule: string | null; placements: number };
type Data = { items: Placement[]; universities: Uni[]; bodies: { code: string; name: string }[]; canRun: boolean; canSetRules: boolean };

const ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";
const STANDING_TONE: Record<string, Tone> = { Competent: "ok", "Not yet competent": "warn", "Awaiting moderation": "info", "Not assessed": "na" };

export default function Partnerships() {
  const q = useRegister<Data>("/partnerships");
  const me = useMe();
  const [open, setOpen] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [done, setDone] = useState("");
  const [search, setSearch] = useState("");
  const [addingUni, setAddingUni] = useState(false);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { items, universities, bodies, canRun, canSetRules } = q.data.data;
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const rows = items.filter((p) => words.every((w) => `${p.university} ${p.cohort} ${p.ref} ${p.abattoir ?? ""} ${p.intake ?? ""}`.toLowerCase().includes(w)));
  return (
    <>
      <Hero
        stats={[
          { v: String(items.length), l: "Placements", c: "On the register" },
          { v: String(items.filter((r) => r.tone === "bad").length), l: "Action required", c: "Report overdue, or facilitator not accepted" },
          { v: String(items.filter((r) => r.tone === "warn").length), l: "Needs attention", c: "Report due within five days" },
          { v: String(universities.length), l: "University partners", c: universities.filter((u) => u.rule).map((u) => `${u.name.replace("University of ", "")}: ${u.rule}`).join(" · ") || "No facilitator rules set" },
        ]}
      />
      {done ? <div className="callout ok" role="status"><p><b>Saved.</b> {done}</p></div> : null}
      <SectionHead title="Placements">
        {me.data?.data.writes.includes("learners") ? (
          <button className="btn btn-teal" onClick={() => { setDone(""); setImporting(true); }}>Import cohort list</button>
        ) : null}
      </SectionHead>
      <div className="card week-bar">
        <div className="week-search">
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search placements"
                 placeholder="Search: university, cohort, abattoir, placement (PLC-…) or intake" />
        </div>
        <span className="small muted">{rows.length} of {items.length}</span>
      </div>
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string} empty="No placements match."
        onRow={(r) => setOpen(r.ref === open ? null : r.ref)}
        expanded={(r) => (r.ref !== open ? null : <Detail p={r} canRun={canRun} onDone={setDone} />)}
        columns={[
          { key: "ref", label: "Placement", render: (r) => r.ref, mono: true },
          { key: "uni", label: "University", render: (r) => <><b>{r.university}</b>{r.rule ? <div className="small muted">{r.rule}-registered facilitators only</div> : null}</> },
          { key: "cohort", label: "Cohort", render: (r) => <>{r.cohort}<div className="small muted">{r.students.length || r.size} students</div></> },
          { key: "abattoir", label: "Abattoir", render: (r) => r.abattoir ? <>{r.abattoir}<div className="small muted mono">{r.intake}</div></> : <span className="small muted">No intake linked</span> },
          { key: "steps", label: "Checklist", render: (r) => `${r.checklist.filter((s) => s.done).length} of ${r.checklist.length}`, mono: true },
          { key: "due", label: "Report due", render: (r) => r.reportDue, mono: true },
          { key: "pos", label: "Position", render: (r) => <Status tone={r.tone}>{r.position}</Status> },
        ]} />

      <SectionHead title="University rules">
        {canSetRules && !addingUni ? <button className="btn btn-teal" onClick={() => setAddingUni(true)}>Add university</button> : null}
      </SectionHead>
      {addingUni ? (
        <div className="card inset-form"><AddUniversity bodies={bodies} onCancel={() => setAddingUni(false)}
          onDone={(m) => { setAddingUni(false); setDone(m); }} /></div>
      ) : null}
      <Register rows={universities} rowKey={(u) => u.ref}
        columns={[
          { key: "name", label: "University", render: (u) => <b>{u.name}</b> },
          { key: "n", label: "Placements", render: (u) => String(u.placements), mono: true },
          { key: "rule", label: "Facilitators must be registered with", render: (u) => canSetRules
            ? <RuleSelect uni={u} bodies={bodies} onDone={setDone} />
            : (u.rule ?? <span className="muted">No rule</span>) },
        ]} />

      {importing ? (
        <Modal title="Import a university cohort list" onClose={() => setImporting(false)}>
          <CohortImportForm onDone={(msg) => { setImporting(false); setDone(msg); }} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}

function AddUniversity({ bodies, onDone, onCancel }: { bodies: { code: string; name: string }[]; onDone: (m: string) => void; onCancel: () => void }) {
  const add = useAction<{ name: string; body: string | null }>("POST", "/universities");
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [tried, setTried] = useState(false);
  const problem = name.trim().length < 3 ? "Give the university's full name." : "";
  return (
    <div className="stack-12">
      <Blocked refusal={add.refusal} />
      <div className="form-grid">
        <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor="uni-name">University</label>
          <input id="uni-name" value={name} className={tried && problem ? "invalid" : undefined} placeholder="e.g. University of the Free State"
                 onChange={(x) => setName(x.target.value)} />
          {tried && problem ? <span className="field-error">{problem}</span> : null}</div>
        <div className="field"><label htmlFor="uni-body">Facilitators must be registered with <span className="optional">(optional)</span></label>
          <select id="uni-body" value={body} onChange={(x) => setBody(x.target.value)}>
            <option value="">No rule</option>{bodies.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
          </select></div>
      </div>
      <div className="row">
        <button className="btn btn-primary" disabled={add.isPending} onClick={() => {
          setTried(true);
          if (!problem) add.mutate({ name, body: body || null }, { onSuccess: (r) => onDone(r.meta.audit?.what ?? "") });
        }}>{add.isPending ? "Saving…" : "Add university"}</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
        <span className="small muted">It can then be chosen when importing a cohort list.</span>
      </div>
    </div>
  );
}

function RuleSelect({ uni, bodies, onDone }: { uni: Uni; bodies: { code: string; name: string }[]; onDone: (m: string) => void }) {
  const set = useAction<{ body: string | null }>("PUT", `/universities/${uni.ref}/rule`);
  return (
    <div className="row">
      <select aria-label={`Rule for ${uni.name}`} className="bar-select" value={uni.rule ?? ""} disabled={set.isPending}
              onChange={(e) => set.mutate({ body: e.target.value || null }, { onSuccess: (x) => onDone(x.meta.audit?.what ?? "") })}>
        <option value="">No rule</option>
        {bodies.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
      </select>
      <Blocked refusal={set.refusal} />
    </div>
  );
}

function Detail({ p, canRun, onDone }: { p: Placement; canRun: boolean; onDone: (m: string) => void }) {
  const qc = useQueryClient();
  const screen = useScreen();
  const [refusal, setRefusal] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState("");
  const [confirmedOn, setConfirmedOn] = useState("");
  const confirm = useAction<{ on: string }>("POST", `/placements/${p.ref}/abattoir-confirmed`);
  const submit = useAction<Record<string, never>>("POST", `/placements/${p.ref}/report`);
  async function send(path: string, file: File | undefined) {
    if (!file) return;
    setBusy(path);
    setRefusal(null);
    try {
      const r = await upload(path, file, screen);
      await qc.invalidateQueries();
      onDone(r.meta.audit?.what ?? "");
    } catch (err) {
      if (err instanceof ApiError) setRefusal(err);
    } finally {
      setBusy("");
    }
  }
  const step = (key: string) => p.checklist.find((s) => s.key === key)!;
  const action = (key: string) => {
    if (!canRun) return null;
    if (key === "abattoirDocs" && p.intake) return (
      <label className="btn btn-sm"><i className="fas fa-upload" aria-hidden /> Add a document
        <input type="file" accept={ACCEPT} hidden disabled={!!busy} onChange={(x) => send(`/placements/${p.ref}/abattoir-documents`, x.target.files?.[0])} /></label>);
    if (key === "abattoirConfirmed" && !step(key).done && step("abattoirDocs").done) return (
      <span className="row">
        <input type="date" aria-label="Date the abattoir confirmed" value={confirmedOn} onChange={(x) => setConfirmedOn(x.target.value)} />
        <button className="btn btn-sm" disabled={!confirmedOn || confirm.isPending}
                onClick={() => confirm.mutate({ on: confirmedOn }, { onSuccess: (x) => onDone(x.meta.audit?.what ?? "") })}>Record</button>
      </span>);
    return null;
  };
  return (
    <div className="stack-12">
      <Blocked refusal={refusal ?? confirm.refusal ?? submit.refusal} />
      <dl className="facts">
        <div><dt>Period</dt><dd>{p.periodStart} to {p.periodEnd} · report due {p.reportDue}</dd></div>
        <div><dt>Abattoir</dt><dd>{p.abattoir ? `${p.abattoir} · ${p.intake}` : "No intake linked yet"}</dd></div>
        <div><dt>Facilitator</dt><dd>{p.facilitator ?? "—"}{p.rule ? ` · ${p.university} requires ${p.rule} registration` : ""}</dd></div>
      </dl>

      <b>Checklist</b>
      <table className="plain-table">
        <tbody>
          {p.checklist.map((s) => (
            <tr key={s.key}>
              <td style={{ width: 28 }}><i className={s.done ? "fas fa-circle-check" : "far fa-circle"} style={{ color: s.done ? "var(--ok)" : "var(--aps-faint)" }}
                     aria-label={s.done ? "Done" : "Outstanding"} /></td>
              <td><b>{s.label}</b><div className="small muted">{s.note}</div></td>
              <td style={{ textAlign: "right" }}>{action(s.key)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <b>Students</b>
      {p.students.length ? (
        <table className="plain-table">
          <thead><tr><th>Student</th><th>Student no.</th><th>Attendance</th><th>Mark</th><th>Outcome</th><th>Moderated</th></tr></thead>
          <tbody>
            {p.students.map((s) => (
              <tr key={s.enrolment}>
                <td><b>{s.learner}</b></td>
                <td className="mono">{s.studentNumber || "—"}</td>
                <td>{s.attendance ? `${s.attendance.present} of ${s.attendance.of} (${s.attendance.percent}%)` : "—"}</td>
                <td className="mono">{s.mark !== null ? `${s.mark}%` : "—"}</td>
                <td><Status tone={STANDING_TONE[s.standing] ?? "na"}>{s.standing}</Status></td>
                <td className="small">{s.moderatedBy ? `${s.moderatedBy}, ${s.moderatedOn}` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <p className="small muted" style={{ margin: 0 }}>No students yet. Import the university&apos;s student list.</p>}

      {p.documents.length ? (
        <>
          <b>Documents</b>
          <div className="stack-12">
            {p.documents.map((d) => (
              <div key={d.ref} className="row">
                <a className="btn btn-sm" href={d.url} target="_blank" rel="noopener"><i className="fas fa-file-lines" aria-hidden /> View</a>
                <span><b>{d.kind}</b> · {d.title} <span className="small muted">· {d.added} · {d.ref}</span></span>
              </div>
            ))}
          </div>
        </>
      ) : null}

      <b>Report to {p.university}</b>
      <div className="row">
        <a className="btn btn-sm" href={`${p.reportPreview}?download=true`}><i className="fas fa-download" aria-hidden /> Download PDF</a>
        {canRun && !step("report").done ? (
          p.reportBlockedBy.length ? null : (
            <button className="btn btn-sm btn-primary" disabled={submit.isPending}
                    onClick={() => submit.mutate({}, { onSuccess: (x) => onDone(x.meta.audit?.what ?? "") })}>Submit report</button>
          )
        ) : null}
        <span className="small muted">{step("report").done ? "The submitted copy, as filed." : "Built from the registers as they stand. Submitting files this copy."}</span>
      </div>
      {!step("report").done && p.reportBlockedBy.length ? <Blocked reasons={p.reportBlockedBy} title="Not ready to submit" /> : null}
      <iframe className="cert-frame" src={p.reportPreview} title={`Report for ${p.ref}`} />
    </div>
  );
}
