"use client";

// Results: the assessor captures the mark and outcome with the marked assessment uploaded; another
// person moderates it from that evidence, agreeing or changing the outcome with a reason. Not yet
// competent gets a remediation plan and a re-assessment date, and the re-assessment is a new result.

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { SearchSelect } from "@/components/SearchSelect";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { ApiError, upload, type Tone } from "@/lib/api";
import { useAction, useFocusRef, useRegister, useScreen } from "@/lib/hooks";

type Attendance = { present: number; of: number; percent: number } | null;
type Result = {
  ref: string; learner: string; learnerRef: string; enrolment: string; course: string; intake: string | null; session: string | null;
  assessor: string; assessedAt: string | null; mark: number; outcome: string;
  moderated: boolean; moderatedOutcome: string | null; moderatedBy: string | null; moderatedAt: string | null; moderationNotes: string;
  certificate: string | null; position: string; tone: Tone; certificateBlockedBy: string[]; remediation: string;
  reassesses: string | null; reassessedOn: string | null; evidence: { ref: string; title: string; url: string } | null;
  attendance: Attendance; ownAssessment: boolean;
};
type Learner = { enrolment: string; learner: string; state: "ready" | "reassess" | "awaiting" | "done" | "notStarted"; note: string; attendance: Attendance };
type Intake = { ref: string; course: string; start: string; learners: Learner[] };

const ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";
const OUTCOME: Record<string, string> = { Competent: "Competent", NotYetCompetent: "Not yet competent" };
const VIEWS: [string, string][] = [["", "All"], ["awaiting", "Awaiting moderation"], ["remediation", "Remediation"], ["moderated", "Moderated"]];

function inView(r: Result, v: string) {
  if (v === "awaiting") return !r.moderated;
  if (v === "remediation") return r.moderated && r.moderatedOutcome === "NotYetCompetent" && !r.reassessedOn;
  if (v === "moderated") return r.moderated;
  return true;
}

const att = (a: Attendance) => (a ? `${a.present} of ${a.of} sessions (${a.percent}%)` : "No register captured yet");

export default function Results() {
  const q = useRegister<{ items: Result[]; canModerate: boolean; canCapture: boolean }>("/results");
  const focus = useFocusRef();
  const [open, setOpen] = useState<string | null>(null);
  const [capturing, setCapturing] = useState<string | null>(null); // "" for a new capture, or an enrolment to re-assess
  const [done, setDone] = useState("");
  const [view, setView] = useState("");
  const [course, setCourse] = useState("");
  const [search, setSearch] = useState("");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { items, canModerate, canCapture } = q.data.data;
  const shown = open ?? focus;
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const rows = items.filter((r) => inView(r, view)).filter((r) => !course || r.course === course)
    .filter((r) => words.every((w) => `${r.learner} ${r.course} ${r.ref} ${r.assessor} ${r.intake ?? ""}`.toLowerCase().includes(w)));
  const courses = Array.from(new Set(items.map((r) => r.course))).sort();

  return (
    <>
      <Hero
        stats={[
          { v: String(items.length), l: "Results", c: "On the register" },
          { v: String(items.filter((r) => !r.moderated).length), l: "Awaiting moderation", c: "Assessed, not yet moderated" },
          { v: String(items.filter((r) => r.moderatedOutcome === "Competent" && !r.certificate).length), l: "Ready to certify", c: "Moderated competent" },
          { v: String(items.filter((r) => inView(r, "remediation")).length), l: "Remediation", c: "Moderated not yet competent, not re-assessed" },
        ]}
      />
      {done ? <div className="callout ok" role="status"><p><b>Saved.</b> {done}</p></div> : null}
      <SectionHead title="Results">
        {canCapture && capturing !== "" ? (
          <button className="btn btn-primary" onClick={() => { setCapturing(""); setDone(""); }}>
            <i className="fas fa-plus" aria-hidden /> Capture a result</button>
        ) : null}
      </SectionHead>
      {capturing === "" ? (
        <div className="card stack-12">
          <h3 style={{ margin: 0 }}>Capture a result</h3>
          <CaptureForm preset="" onCancel={() => setCapturing(null)}
                       onDone={(ref, what) => { setCapturing(null); setDone(what); setOpen(ref); }} />
        </div>
      ) : null}
      <div className="card week-bar">
        <div className="seg" role="group" aria-label="Show">
          {VIEWS.map(([v, l]) => (
            <button key={l} className={view === v ? "on" : undefined} aria-pressed={view === v} onClick={() => setView(v)}>
              {l} <span className="seg-n">{items.filter((r) => inView(r, v)).length}</span></button>
          ))}
        </div>
        <select aria-label="Course" className="bar-select" value={course} onChange={(e) => setCourse(e.target.value)}>
          <option value="">Any course</option>{courses.map((c) => <option key={c}>{c}</option>)}
        </select>
        <div className="week-search">
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search results"
                 placeholder="Search: student, course, result (RES-…), assessor or intake" />
        </div>
        <span className="small muted">{rows.length} of {items.length}</span>
      </div>
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string} empty="Nothing matches these filters."
        onRow={(r) => setOpen(r.ref === shown ? "" : r.ref)}
        expanded={(r) => (r.ref !== shown ? null : (
          <Detail r={r} canModerate={canModerate} canCapture={canCapture} reassessing={capturing === r.enrolment}
                  onReassess={() => { setCapturing(r.enrolment); setDone(""); }} onCancel={() => setCapturing(null)}
                  onDone={(ref, what) => { setCapturing(null); setDone(what); setOpen(ref); }} />
        ))}
        columns={[
          { key: "ref", label: "Result", render: (r) => <>{r.ref}<div className="small muted">{r.assessedAt}</div></>, mono: true },
          { key: "learner", label: "Learner", render: (r) => <b>{r.learner}</b> },
          { key: "course", label: "Course", render: (r) => <>{r.course}<div className="small muted mono">{r.intake}</div></> },
          { key: "assessor", label: "Assessor", render: (r) => r.assessor },
          { key: "mark", label: "Mark", render: (r) => `${r.mark}%`, mono: true },
          { key: "outcome", label: "Outcome", render: (r) => (
            <>{OUTCOME[r.outcome]}{r.moderated && r.moderatedOutcome !== r.outcome
              ? <div className="small muted">Moderated: {OUTCOME[r.moderatedOutcome!]}</div> : null}</>) },
          { key: "evidence", label: "Assessment", render: (r) => r.evidence ? (
            <a className="btn btn-sm" href={r.evidence.url} target="_blank" rel="noopener" onClick={(e) => e.stopPropagation()}>
              <i className="fas fa-file-lines" aria-hidden /> View</a>) : <span className="small muted">Not uploaded</span> },
          { key: "pos", label: "Position", render: (r) => <Status tone={r.tone}>{r.position}</Status> },
        ]} />
      <AuditTrail />
    </>
  );
}

function Detail({ r, canModerate, canCapture, reassessing, onReassess, onCancel, onDone }: {
  r: Result; canModerate: boolean; canCapture: boolean; reassessing: boolean;
  onReassess: () => void; onCancel: () => void; onDone: (ref: string, what: string) => void;
}) {
  return (
    <div className="stack-12">
      <dl className="facts">
        <div><dt>Assessed</dt><dd>{r.assessor}, {r.assessedAt} · {r.mark}% · {OUTCOME[r.outcome]}</dd></div>
        <div><dt>Attendance</dt><dd>{att(r.attendance)}</dd></div>
        {r.reassesses ? <div><dt>Re-assessment of</dt><dd className="mono">{r.reassesses}</dd></div> : null}
        {r.moderated ? (
          <div><dt>Moderated</dt><dd>{r.moderatedBy}, {r.moderatedAt} · {r.moderatedOutcome === r.outcome ? "agreed" : "outcome changed"}: {OUTCOME[r.moderatedOutcome!]}
            {r.moderationNotes ? <> — {r.moderationNotes}</> : null}</dd></div>
        ) : null}
        {r.remediation ? <div><dt>Remediation</dt><dd>{r.remediation}</dd></div> : null}
        {r.reassessedOn ? <div><dt>Re-assessed on</dt><dd className="mono">{r.reassessedOn}</dd></div> : null}
      </dl>
      {r.evidence ? (
        <>
          <div className="row">
            <a className="btn btn-sm" href={`${r.evidence.url}?download=true`}><i className="fas fa-download" aria-hidden /> Download</a>
            <span className="small muted">{r.evidence.title} · {r.evidence.ref}</span>
          </div>
          <iframe className="cert-frame" src={r.evidence.url} title={`Assessment for ${r.ref}`} />
        </>
      ) : <p className="small muted" style={{ margin: 0 }}>No marked assessment was uploaded for this result (captured before uploads were required).</p>}
      {!r.moderated && r.ownAssessment ? <ReplaceAssessment r={r} /> : null}
      {!r.moderated ? (
        r.ownAssessment ? <p className="small muted" style={{ margin: 0 }}>You assessed this result, so another person moderates it.</p>
          : canModerate ? <ModerateForm r={r} />
          : <p className="small muted" style={{ margin: 0 }}>Awaiting moderation by the training manager or a moderator.</p>
      ) : null}
      {r.moderated && r.moderatedOutcome === "NotYetCompetent" && !r.reassessedOn && canCapture ? (reassessing ? (
        <div className="card stack-12" style={{ background: "var(--aps-zebra)" }}>
          <b>Capture the re-assessment for {r.learner}</b>
          <CaptureForm preset={r.enrolment} onCancel={onCancel} onDone={onDone} />
        </div>
      ) : (
        <div className="row">
          <button className="btn btn-primary" onClick={onReassess}>Capture the re-assessment</button>
          <span className="small muted">A new result, with its own assessment and moderation. This one stays on record.</span>
        </div>
      )) : null}
    </div>
  );
}

function ModerateForm({ r }: { r: Result }) {
  const moderate = useAction<{ ref: string; outcome: string; notes: string; remediation: string; reassessBy: string | null }>(
    "POST", (v) => `/results/${v.ref}/moderate`);
  const [decision, setDecision] = useState<"agree" | "change">("agree");
  const [notes, setNotes] = useState("");
  const [remediation, setRemediation] = useState("");
  const [by, setBy] = useState("");
  const [tried, setTried] = useState(false);
  const final = decision === "agree" ? r.outcome : r.outcome === "Competent" ? "NotYetCompetent" : "Competent";
  const nyc = final === "NotYetCompetent";
  const p: Record<string, string> = {};
  if (decision === "change" && !notes.trim()) p.notes = "Give the reason for changing the outcome.";
  if (nyc && !remediation.trim()) p.remediation = "Record what the learner must do before re-assessment.";
  if (nyc && !by) p.by = "Give the re-assessment date.";
  const e = tried ? p : {};
  function save() {
    setTried(true);
    if (Object.keys(p).length) return;
    moderate.mutate({ ref: r.ref, outcome: final, notes, remediation: nyc ? remediation : "", reassessBy: nyc ? by : null });
  }
  return (
    <div className="card stack-12" style={{ background: "var(--aps-zebra)" }}>
      <b>Moderate {r.ref}</b>
      <p className="small muted" style={{ margin: 0 }}>
        Check the marked assessment against the mark ({r.mark}%) and the assessor&apos;s outcome ({OUTCOME[r.outcome].toLowerCase()}), with attendance: {att(r.attendance)}.
      </p>
      <Blocked refusal={moderate.refusal} />
      <div className="seg" role="group" aria-label="Decision">
        <button className={decision === "agree" ? "on" : undefined} aria-pressed={decision === "agree"} onClick={() => setDecision("agree")}>
          Agree: {OUTCOME[r.outcome].toLowerCase()}</button>
        <button className={decision === "change" ? "on" : undefined} aria-pressed={decision === "change"} onClick={() => setDecision("change")}>
          Change to {OUTCOME[r.outcome === "Competent" ? "NotYetCompetent" : "Competent"].toLowerCase()}</button>
      </div>
      <div className="field"><label htmlFor={`mn-${r.ref}`}>{decision === "change" ? "Reason for changing the outcome" : <>Moderation notes <span className="optional">(optional)</span></>}</label>
        <textarea id={`mn-${r.ref}`} rows={2} value={notes} className={e.notes ? "invalid" : undefined} onChange={(x) => setNotes(x.target.value)} />
        {e.notes ? <span className="field-error">{e.notes}</span> : null}</div>
      {nyc ? (
        <div className="form-grid">
          <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor={`mr-${r.ref}`}>Remediation plan</label>
            <textarea id={`mr-${r.ref}`} rows={2} value={remediation} className={e.remediation ? "invalid" : undefined}
                      placeholder="e.g. Repeat the hygiene module and the practical on the line" onChange={(x) => setRemediation(x.target.value)} />
            {e.remediation ? <span className="field-error">{e.remediation}</span> : null}</div>
          <div className="field"><label htmlFor={`mb-${r.ref}`}>Re-assess by</label>
            <input id={`mb-${r.ref}`} type="date" value={by} className={e.by ? "invalid" : undefined} onChange={(x) => setBy(x.target.value)} />
            {e.by ? <span className="field-error">{e.by}</span> : null}</div>
        </div>
      ) : null}
      <div className="row">
        <button className="btn btn-primary" disabled={moderate.isPending} onClick={save}>
          {moderate.isPending ? "Saving…" : decision === "agree" ? "Record moderation: agree" : "Record moderation: outcome changed"}</button>
        <span className="small muted">Final once recorded. {final === "Competent" ? "Competent goes to certification." : ""}</span>
      </div>
    </div>
  );
}

function ReplaceAssessment({ r }: { r: Result }) {
  const qc = useQueryClient();
  const screen = useScreen();
  const [refusal, setRefusal] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  async function send(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setRefusal(null);
    try {
      await upload(`/results/${r.ref}/assessment`, file, screen);
      await qc.invalidateQueries();
    } catch (err) {
      if (err instanceof ApiError) setRefusal(err);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack-12">
      <Blocked refusal={refusal} />
      <div className="field" style={{ maxWidth: 420 }}>
        <label htmlFor={`ra-${r.ref}`}>{r.evidence ? "Replace the assessment" : "Upload the assessment"} <span className="optional">(until it is moderated)</span></label>
        <input id={`ra-${r.ref}`} type="file" accept={ACCEPT} disabled={busy} onChange={(x) => send(x.target.files?.[0])} />
      </div>
    </div>
  );
}

function CaptureForm({ preset, onDone, onCancel }: { preset: string; onDone: (ref: string, what: string) => void; onCancel: () => void }) {
  const opts = useRegister<{ intakes: Intake[] }>("/results/options");
  const qc = useQueryClient();
  const screen = useScreen();
  const presetIntake = preset ? opts.data?.data.intakes.find((i) => i.learners.some((l) => l.enrolment === preset))?.ref ?? "" : "";
  const [intake, setIntake] = useState<string | null>(null);
  const [f, setF] = useState({ enrolment: preset, mark: "", outcome: "", notes: "" });
  const [file, setFile] = useState<File | null>(null);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<ApiError | null>(null);
  if (opts.error) return <Blocked refusal={opts.error} />;
  if (!opts.data) return <p className="muted">Loading…</p>;
  const intakes = opts.data.data.intakes;
  const chosenIntake = intakes.find((i) => i.ref === (intake ?? presetIntake));
  const learners = chosenIntake?.learners ?? [];
  const open = learners.filter((l) => l.state === "ready" || l.state === "reassess");
  const learner = learners.find((l) => l.enrolment === f.enrolment);
  const markN = Number(f.mark);
  const p: Record<string, string> = {};
  if (!chosenIntake) p.intake = "Choose the intake.";
  if (!learner) p.enrolment = "Choose the learner.";
  if (f.mark === "" || Number.isNaN(markN) || markN < 0 || markN > 100) p.mark = "A percentage from 0 to 100.";
  if (!f.outcome) p.outcome = "Choose the outcome.";
  if (!file) p.file = "Upload the marked assessment.";
  else if (file.size > 5 * 1048576) p.file = "The file is larger than 5 MB.";
  const e = tried ? p : {};
  async function save() {
    setTried(true);
    if (Object.keys(p).length) return;
    setBusy(true);
    setRefusal(null);
    try {
      const r = await upload<{ ref: string }>("/results", file, screen, { enrolment: f.enrolment, mark: f.mark, outcome: f.outcome, notes: f.notes });
      await qc.invalidateQueries();
      onDone(r.data.ref, r.meta.audit?.what ?? "");
    } catch (err) {
      if (err instanceof ApiError) setRefusal(err);
    } finally {
      setBusy(false);
    }
  }
  if (!intakes.length) return (
    <><p className="muted" style={{ margin: 0 }}>No confirmed learners on your intakes to assess.</p>
      <div className="row"><button className="btn" onClick={onCancel}>Close</button></div></>
  );
  return (
    <div className="stack-12">
      <Blocked refusal={refusal} />
      {preset ? null : <div className="form-grid">
        <div className="field"><label htmlFor="cr-intake">Intake</label>
          <SearchSelect id="cr-intake" value={chosenIntake?.ref ?? ""} invalid={!!e.intake} placeholder="Type the course or intake…"
            options={intakes.map((i) => ({ value: i.ref, label: `${i.ref} · ${i.course}`, hint: `Starts ${i.start}` }))}
            onChange={(v) => { setIntake(v); setF({ ...f, enrolment: "" }); }} />
          {e.intake ? <span className="field-error">{e.intake}</span> : null}</div>
        <div className="field"><label htmlFor="cr-learner">Learner</label>
          <SearchSelect id="cr-learner" value={learner ? f.enrolment : ""} invalid={!!e.enrolment} disabled={!chosenIntake}
            placeholder={chosenIntake ? "Type the learner's name…" : "Choose the intake first"}
            emptyText="No learner on this intake is waiting to be assessed"
            options={open.map((l) => ({ value: l.enrolment, label: l.learner, hint: l.note }))}
            onChange={(v) => setF({ ...f, enrolment: v })} />
          {e.enrolment ? <span className="field-error">{e.enrolment}</span> : null}
          {chosenIntake && open.length < learners.length ? (
            <span className="small muted">{learners.length - open.length} not listed: {learners.filter((l) => !open.includes(l)).map((l) => `${l.learner} (${l.note.charAt(0).toLowerCase()}${l.note.slice(1)})`).join("; ")}</span>
          ) : null}</div>
      </div>}
      {learner ? <p className="small muted" style={{ margin: 0 }}>{preset ? <><b>{learner.learner}</b> · {chosenIntake?.ref} · </> : null}{learner.note} · attendance: {att(learner.attendance)}</p> : null}
      <div className="form-grid">
        <div className="field"><label htmlFor="cr-mark">Mark (%)</label>
          <input id="cr-mark" type="number" min={0} max={100} step="0.5" value={f.mark} className={e.mark ? "invalid" : undefined}
                 onChange={(x) => setF({ ...f, mark: x.target.value })} />
          {e.mark ? <span className="field-error">{e.mark}</span> : null}</div>
        <div className="field"><label>Outcome</label>
          <div className="seg" role="group" aria-label="Outcome">
            {Object.entries(OUTCOME).map(([v, l]) => (
              <button key={v} type="button" className={f.outcome === v ? "on" : undefined} aria-pressed={f.outcome === v}
                      onClick={() => setF({ ...f, outcome: v })}>{l}</button>
            ))}
          </div>
          {e.outcome ? <span className="field-error">{e.outcome}</span> : null}</div>
        <div className="field"><label htmlFor="cr-file">Marked assessment <span className="optional">(PDF, JPG or PNG, up to 5 MB)</span></label>
          <input id="cr-file" type="file" accept={ACCEPT} className={e.file ? "invalid" : undefined} onChange={(x) => setFile(x.target.files?.[0] ?? null)} />
          {e.file ? <span className="field-error">{e.file}</span> : null}</div>
      </div>
      <div className="field"><label htmlFor="cr-notes">Assessor&apos;s notes <span className="optional">(optional)</span></label>
        <textarea id="cr-notes" rows={2} value={f.notes} onChange={(x) => setF({ ...f, notes: x.target.value })} /></div>
      <div className="row">
        <button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save result"}</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
        <span className="small muted">Goes to moderation next. Someone other than you moderates it.</span>
      </div>
    </div>
  );
}
