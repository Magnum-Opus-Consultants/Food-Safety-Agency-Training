"use client";

// Adding a course, editing its details, and changing its entry requirement. A requirement change is
// a new dated version: it applies from the next intake without learners, and the history and the
// edit trail are permanent (the API and the database refuse edits or deletions).

import { useState } from "react";
import { Blocked, Register, Status } from "@/components/ui";
import { useAction, useRegister } from "@/lib/hooks";

type Option = { code: string; name: string };
type Options = { services: Option[]; streams: Option[]; bodies: Option[]; kinds: { code: string; label: string }[];
  courses: { code: string; title: string }[] };
type Version = { version: number; from: string | null; kind: string; label: string; passMark: number | null; priorCourse: string | null;
  description: string; reason: string; by: string; at: string };
export type CourseDetail = {
  code: string; title: string; serviceCode: string; streamCode: string; bodyCode: string | null; days: number; mode: string;
  entryRequirement: string; requirementVersion: number | null; passMark: number | null;
  upcoming: { from: string; label: string; version: number }[];
  versions: Version[]; lockedIntakes: { ref: string; start: string; requirement: string; learners: number }[];
  earliestChange: string; trail: { at: string; what: string; who: string }[]; trailVisible: boolean; canEdit: boolean;
};

type Req = { kind: string; passMark: string; priorCourse: string; description: string };
type Details = { title: string; service: string; stream: string; days: string; mode: string; body: string };

function reqProblems(r: Req, selfCode?: string) {
  const p: Record<string, string> = {};
  if (!r.kind) p.kind = "Choose the kind of entry requirement.";
  if (r.kind === "PrerequisiteAndGrade10") {
    const n = Number(r.passMark);
    if (!r.passMark.trim() || Number.isNaN(n) || n <= 0 || n > 100) p.passMark = "Give the pass mark, a percentage from 1 to 100.";
  }
  if (r.kind === "PriorCourse" && !r.priorCourse) p.priorCourse = "Choose the course they must have passed first.";
  if (r.kind === "PriorCourse" && r.priorCourse && r.priorCourse === selfCode) p.priorCourse = "A course cannot require itself.";
  if (r.kind === "Documented" && !r.description.trim()) p.description = "Describe the document or experience required.";
  return p;
}

function detailProblems(d: Details) {
  const p: Record<string, string> = {};
  if (!d.title.trim()) p.title = "Give the course title.";
  if (!d.service) p.service = "Choose the service.";
  if (!d.stream) p.stream = "Choose the planner stream.";
  const n = Number(d.days);
  if (!d.days.trim() || !Number.isInteger(n) || n < 1 || n > 365) p.days = "Give the duration in whole days, 1 to 365.";
  if (!d.mode.trim()) p.mode = "Describe the delivery.";
  return p;
}

const Err = ({ m }: { m?: string }) => (m ? <span className="field-error">{m}</span> : null);

function RequirementFields({ id, r, set, opts, errors, selfCode }: {
  id: string; r: Req; set: (r: Req) => void; opts: Options; errors: Record<string, string>; selfCode?: string;
}) {
  return (
    <div className="form-grid">
      <div className="field"><label htmlFor={`${id}-kind`}>Entry requirement</label>
        <select id={`${id}-kind`} value={r.kind} className={errors.kind ? "invalid" : undefined} onChange={(e) => set({ ...r, kind: e.target.value })}>
          <option value="">Choose…</option>
          {opts.kinds.map((k) => <option key={k.code} value={k.code}>{k.code === "PrerequisiteAndGrade10" ? "Prerequisite test and Grade 10" : k.label}</option>)}
        </select><Err m={errors.kind} /></div>
      {r.kind === "PrerequisiteAndGrade10" ? (
        <div className="field"><label htmlFor={`${id}-mark`}>Pass mark for the test (%)</label>
          <input id={`${id}-mark`} inputMode="decimal" value={r.passMark} className={errors.passMark ? "invalid" : undefined}
                 onChange={(e) => set({ ...r, passMark: e.target.value })} />
          {errors.passMark ? <Err m={errors.passMark} /> : <span className="small muted">Grade 10 evidence is required as well.</span>}</div>
      ) : null}
      {r.kind === "PriorCourse" ? (
        <div className="field"><label htmlFor={`${id}-prior`}>Must have passed</label>
          <select id={`${id}-prior`} value={r.priorCourse} className={errors.priorCourse ? "invalid" : undefined}
                  onChange={(e) => set({ ...r, priorCourse: e.target.value })}>
            <option value="">Choose a course…</option>
            {opts.courses.filter((c) => c.code !== selfCode).map((c) => <option key={c.code} value={c.code}>{c.title}</option>)}
          </select>
          {errors.priorCourse ? <Err m={errors.priorCourse} /> : <span className="small muted">A moderated competent result on that course.</span>}</div>
      ) : null}
      {r.kind === "Documented" ? (
        <div className="field"><label htmlFor={`${id}-desc`}>Document or experience required</label>
          <input id={`${id}-desc`} value={r.description} placeholder="e.g. Two years industry experience" className={errors.description ? "invalid" : undefined}
                 onChange={(e) => set({ ...r, description: e.target.value })} /><Err m={errors.description} /></div>
      ) : null}
    </div>
  );
}

function DetailFields({ id, d, set, opts, errors }: { id: string; d: Details; set: (d: Details) => void; opts: Options; errors: Record<string, string> }) {
  const f = (k: keyof Details, label: string, input: React.ReactNode) => (
    <div className="field"><label htmlFor={`${id}-${k}`}>{label}</label>{input}<Err m={errors[k]} /></div>
  );
  const cls = (k: string) => (errors[k] ? "invalid" : undefined);
  return (
    <div className="form-grid">
      {f("title", "Course title", <input id={`${id}-title`} value={d.title} className={cls("title")} onChange={(e) => set({ ...d, title: e.target.value })} />)}
      {f("service", "Service supported", (
        <select id={`${id}-service`} value={d.service} className={cls("service")} onChange={(e) => set({ ...d, service: e.target.value })}>
          <option value="">Choose…</option>{opts.services.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
        </select>))}
      {f("stream", "Planner stream", (
        <select id={`${id}-stream`} value={d.stream} className={cls("stream")} onChange={(e) => set({ ...d, stream: e.target.value })}>
          <option value="">Choose…</option>{opts.streams.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
        </select>))}
      {f("days", "Duration (days)", <input id={`${id}-days`} inputMode="numeric" value={d.days} className={cls("days")} onChange={(e) => set({ ...d, days: e.target.value })} />)}
      {f("mode", "Delivery", <input id={`${id}-mode`} value={d.mode} placeholder="e.g. Contact and workplace" className={cls("mode")} onChange={(e) => set({ ...d, mode: e.target.value })} />)}
      {f("body", "Accreditation", (
        <select id={`${id}-body`} value={d.body} onChange={(e) => set({ ...d, body: e.target.value })}>
          <option value="">Not accredited</option>{opts.bodies.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
        </select>))}
    </div>
  );
}

function reqBody(r: Req) {
  return { kind: r.kind, passMark: r.kind === "PrerequisiteAndGrade10" ? Number(r.passMark) : null,
           priorCourse: r.kind === "PriorCourse" ? r.priorCourse : "", description: r.kind === "Documented" ? r.description : "" };
}

// --- add a course ---------------------------------------------------------------------------

export function AddCourseForm({ onDone }: { onDone: (code: string, what: string) => void }) {
  const opts = useRegister<Options>("/courses/options");
  const save = useAction<Record<string, unknown>, { code: string }>("POST", "/courses");
  const [code, setCode] = useState("TRN-");
  const [d, setD] = useState<Details>({ title: "", service: "", stream: "", days: "", mode: "", body: "" });
  const [r, setR] = useState<Req>({ kind: "", passMark: "50", priorCourse: "", description: "" });
  const [tried, setTried] = useState(false);
  if (!opts.data) return <p className="muted">Loading…</p>;
  const codeProblem = /^TRN-[A-Z0-9]{2,12}$/.test(code.trim().toUpperCase()) ? null : "TRN- followed by 2 to 12 capital letters or digits, e.g. TRN-PME3.";
  const all = { ...detailProblems(d), ...reqProblems(r, code.trim().toUpperCase()), ...(codeProblem ? { code: codeProblem } : {}) };
  const errors = tried ? all : {};
  return (
    <div className="stack-12">
      <Blocked refusal={save.refusal} />
      <div className="form-grid">
        <div className="field"><label htmlFor="nc-code">Course code</label>
          <input id="nc-code" value={code} className={errors.code ? "invalid" : undefined} onChange={(e) => setCode(e.target.value.toUpperCase())} />
          {errors.code ? <Err m={errors.code} /> : <span className="small muted">Permanent: a code is never changed or reused.</span>}</div>
      </div>
      <DetailFields id="nc" d={d} set={setD} opts={opts.data.data} errors={errors} />
      <div className="eyebrow">Minimum prerequisites</div>
      <RequirementFields id="nc" r={r} set={setR} opts={opts.data.data} errors={errors} selfCode={code.trim().toUpperCase()} />
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending} onClick={() => {
          setTried(true);
          if (Object.keys(all).length) return;
          save.mutate({ code: code.trim().toUpperCase(), ...d, days: Number(d.days), ...reqBody(r) },
            { onSuccess: (res) => onDone(res.data.code, res.meta.audit?.what ?? "") });
        }}>Add course</button>
        <span className="small muted">Recorded in the course&apos;s permanent edit trail.</span>
      </div>
    </div>
  );
}

// --- one course, opened under its row --------------------------------------------------------

export function CourseDetailPanel({ code }: { code: string }) {
  const q = useRegister<CourseDetail>(`/courses/${code}`);
  const opts = useRegister<Options>("/courses/options");
  const [mode, setMode] = useState<"" | "details" | "requirement">("");
  if (q.error) return <Blocked refusal={q.error} />;
  if (!q.data || !opts.data) return <p className="muted">Loading…</p>;
  const c = q.data.data;
  return (
    <div className="stack-12">
      <div className="course-req">
        <div>
          <div className="small muted">Entry requirement now{c.requirementVersion ? ` · version ${c.requirementVersion}` : ""}</div>
          <b>{c.entryRequirement}</b>
        </div>
        {c.upcoming.map((u) => (
          <div key={u.version}><div className="small muted">From {u.from} · version {u.version}</div><b>{u.label}</b> <Status tone="warn">Scheduled</Status></div>
        ))}
        {c.canEdit && !mode ? (
          <div className="row" style={{ marginLeft: "auto" }}>
            <button className="btn btn-sm" onClick={() => setMode("details")}><i className="fas fa-pen" aria-hidden /> Edit details</button>
            <button className="btn btn-sm" onClick={() => setMode("requirement")}><i className="fas fa-list-check" aria-hidden /> Change entry requirement</button>
          </div>
        ) : null}
      </div>
      {c.lockedIntakes.length ? (
        <p className="small muted" style={{ margin: 0 }}>
          <i className="fas fa-lock" aria-hidden /> Fixed for learners already registered:{" "}
          {c.lockedIntakes.map((b) => `${b.ref} (starts ${b.start}, ${b.learners} ${b.learners === 1 ? "learner" : "learners"}, ${b.requirement})`).join("; ")}.
        </p>
      ) : null}
      {mode === "details" ? <EditDetails c={c} opts={opts.data.data} onClose={() => setMode("")} /> : null}
      {mode === "requirement" ? <ChangeRequirement c={c} opts={opts.data.data} onClose={() => setMode("")} /> : null}

      <div className="eyebrow">Entry requirement history</div>
      <Register rows={c.versions} rowKey={(v) => String(v.version)}
        columns={[
          { key: "v", label: "Version", render: (v) => v.version, mono: true },
          { key: "from", label: "Applies to intakes starting", render: (v) => v.from ?? "Initiation", mono: true },
          { key: "req", label: "Requirement", render: (v) => <b>{v.label}</b> },
          { key: "why", label: "Reason", render: (v) => v.reason },
          { key: "by", label: "Recorded", render: (v) => <span className="small">{v.by} · {v.at}</span> },
        ]} />
      {c.trailVisible ? (<>
      <div className="eyebrow">Edit trail <span className="muted" style={{ textTransform: "none", letterSpacing: 0 }}>· permanent, cannot be edited or deleted</span></div>
      {c.trail.length ? (
        <div className="audit">
          {c.trail.map((a, i) => (
            <div className="audit-row" key={`${a.at}-${i}`}><span className="when">{a.at}</span><span>{a.what}</span><span className="who">{a.who}</span></div>
          ))}
        </div>
      ) : <p className="small muted" style={{ margin: 0 }}>No edits since the catalogue was loaded.</p>}
      </>) : null}
    </div>
  );
}

function EditDetails({ c, opts, onClose }: { c: CourseDetail; opts: Options; onClose: () => void }) {
  const save = useAction<Record<string, unknown>>("PATCH", `/courses/${c.code}`);
  const [d, setD] = useState<Details>({ title: c.title, service: c.serviceCode, stream: c.streamCode, days: String(c.days), mode: c.mode, body: c.bodyCode ?? "" });
  const errors = detailProblems(d);
  return (
    <div className="card inset-form">
      <Blocked refusal={save.refusal} />
      <DetailFields id={`ed-${c.code}`} d={d} set={setD} opts={opts} errors={errors} />
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending || Object.keys(errors).length > 0}
                onClick={() => save.mutate({ ...d, days: Number(d.days) }, { onSuccess: onClose })}>Save details</button>
        <button className="btn" onClick={onClose}>Cancel</button>
        <span className="small muted">The course code {c.code} does not change.</span>
      </div>
    </div>
  );
}

function ChangeRequirement({ c, opts, onClose }: { c: CourseDetail; opts: Options; onClose: () => void }) {
  const save = useAction<Record<string, unknown>>("POST", `/courses/${c.code}/requirements`);
  const now = c.versions.find((v) => v.version === c.requirementVersion);
  const [r, setR] = useState<Req>({ kind: now?.kind ?? "", passMark: now?.passMark != null ? String(now.passMark) : "50",
    priorCourse: now?.priorCourse ?? "", description: now?.description ?? "" });
  const [from, setFrom] = useState(c.earliestChange);
  const [reason, setReason] = useState("");
  const [tried, setTried] = useState(false);
  const all = { ...reqProblems(r, c.code), ...(from < c.earliestChange ? { from: `The earliest date is ${c.earliestChange}.` } : {}),
                ...(reason.trim() ? {} : { reason: "Give the reason, for example the regulation or decision." }) };
  const errors = tried ? all : {};
  return (
    <div className="card inset-form">
      <Blocked refusal={save.refusal} />
      <RequirementFields id={`cr-${c.code}`} r={r} set={setR} opts={opts} errors={errors} selfCode={c.code} />
      <div className="form-grid">
        <div className="field"><label htmlFor={`cr-${c.code}-from`}>Applies to intakes starting from</label>
          <input id={`cr-${c.code}-from`} type="date" value={from} min={c.earliestChange} className={errors.from ? "invalid" : undefined}
                 onChange={(e) => setFrom(e.target.value)} />
          {errors.from ? <Err m={errors.from} /> : <span className="small muted">Earliest {c.earliestChange}: intakes with learners keep their requirement.</span>}</div>
        <div className="field"><label htmlFor={`cr-${c.code}-why`}>Reason for the change</label>
          <input id={`cr-${c.code}-why`} value={reason} placeholder="e.g. Regulation or committee decision" className={errors.reason ? "invalid" : undefined}
                 onChange={(e) => setReason(e.target.value)} /><Err m={errors.reason} /></div>
      </div>
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending} onClick={() => {
          setTried(true);
          if (Object.keys(all).length) return;
          save.mutate({ ...reqBody(r), effectiveFrom: from, reason }, { onSuccess: onClose });
        }}>Save as version {Math.max(0, ...c.versions.map((v) => v.version)) + 1}</button>
        <button className="btn" onClick={onClose}>Cancel</button>
        <span className="small muted">The current version stays in the history; nothing is overwritten.</span>
      </div>
    </div>
  );
}
