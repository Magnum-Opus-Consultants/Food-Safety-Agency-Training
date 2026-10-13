"use client";

import { useMemo, useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register } from "@/components/ui";
import { useRegister } from "@/lib/hooks";

type Learner = { ref: string; name: string; type: string; organisation: string; hrLinked: boolean; enrolments: string[];
  enrolmentItems: { ref: string; course: string; courseCode: string; stage: string; intakeRef: string | null }[];
  idNumber: string; studentNumber: string };

type Filter = { q: string; type: string; organisation: string; course: string; stage: string; identity: string; hr: string };
const NO_FILTER: Filter = { q: "", type: "", organisation: "", course: "", stage: "", identity: "", hr: "" };
const STAGES = ["Registered", "Confirmed", "In training", "Completed"];

function matches(r: Learner, f: Filter) {
  const q = f.q.trim().toLowerCase();
  if (q) {
    const hay = [r.name, r.ref, r.organisation, r.studentNumber,
      ...r.enrolmentItems.flatMap((e) => [e.ref, e.course, e.intakeRef ?? ""])];
    if (!hay.some((v) => v.toLowerCase().includes(q))) return false;
  }
  if (f.type && r.type !== f.type) return false;
  if (f.organisation === "-" ? r.organisation : f.organisation && r.organisation !== f.organisation) return false;
  if (f.course === "-" ? r.enrolmentItems.length : f.course && !r.enrolmentItems.some((e) => e.courseCode === f.course)) return false;
  if (f.stage && !r.enrolmentItems.some((e) => e.stage === f.stage && (!f.course || f.course === "-" || e.courseCode === f.course))) return false;
  if (f.identity === "captured" && r.idNumber === "Not captured") return false;
  if (f.identity === "missing" && r.idNumber !== "Not captured") return false;
  if (f.hr === "linked" && !r.hrLinked) return false;
  if (f.hr === "unlinked" && r.hrLinked) return false;
  return true;
}

export default function LearnerDirectory() {
  const q = useRegister<Learner[]>("/learners");
  const [filter, setFilter] = useState(NO_FILTER);
  const setF = (k: keyof Filter, v: string) => setFilter((x) => ({ ...x, [k]: v }));
  // The ID search goes to the API: numbers are stored encrypted, so only the server can match one.
  const [idText, setIdText] = useState("");
  const [idQuery, setIdQuery] = useState("");
  const byId = useRegister<Learner[]>(`/learners?idNumber=${encodeURIComponent(idQuery)}`, !!idQuery);

  const all = q.data?.data;
  const options = useMemo(() => {
    const rows = all ?? [];
    const orgs = [...new Set(rows.map((r) => r.organisation).filter(Boolean))].sort();
    const courses = [...new Map(rows.flatMap((r) => r.enrolmentItems).map((e) => [e.courseCode, e.course])).entries()]
      .sort((a, b) => a[1].localeCompare(b[1]));
    return { orgs, courses };
  }, [all]);

  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const everything = q.data.data;
  const idMode = !!idQuery;
  const rows = idMode ? byId.data?.data ?? [] : everything.filter((r) => matches(r, filter));
  const filtered = Object.values(filter).some(Boolean);
  const count = (t: string) => String(everything.filter((r) => r.type === t).length);

  return (
    <>
      <Hero
        title="One person across both hubs where the learner is an FSA employee."
        statement="A learner may be a public applicant, a corporate delegate, a university student, or an employee whose development plan commissioned the course. Employees link to the HR directory rather than being duplicated."
        stats={[
          { v: count("Public"), l: "Public", c: "Individual applicants" },
          { v: count("Corporate"), l: "Corporate", c: "Delegates of a client" },
          { v: count("University"), l: "University", c: "Placement students" },
          { v: count("Employee"), l: "Employee", c: "Linked to the HR directory" },
        ]}
      />
      <section className="card filter-bar" aria-label="Search and filter learners">
        <div className="field filter-search"><label htmlFor="lf-q">Search</label>
          <input id="lf-q" type="search" value={filter.q} disabled={idMode} onChange={(e) => setF("q", e.target.value)}
                 placeholder="Name, learner (LRN-0019), organisation, student number, enrolment or intake" /></div>
        <div className="field"><label htmlFor="lf-type">Type</label>
          <select id="lf-type" value={filter.type} disabled={idMode} onChange={(e) => setF("type", e.target.value)}>
            <option value="">All types</option><option value="Public">Public</option><option value="Corporate">Corporate</option>
            <option value="University">University</option><option value="Employee">Employee</option>
          </select></div>
        <div className="field"><label htmlFor="lf-org">Organisation</label>
          <select id="lf-org" value={filter.organisation} disabled={idMode} onChange={(e) => setF("organisation", e.target.value)}>
            <option value="">All organisations</option><option value="-">No organisation</option>
            {options.orgs.map((o) => <option key={o} value={o}>{o}</option>)}
          </select></div>
        <div className="field"><label htmlFor="lf-course">Course</label>
          <select id="lf-course" value={filter.course} disabled={idMode} onChange={(e) => setF("course", e.target.value)}>
            <option value="">All courses</option><option value="-">Not enrolled on any course</option>
            {options.courses.map(([code, title]) => <option key={code} value={code}>{title}</option>)}
          </select></div>
        <div className="field"><label htmlFor="lf-stage">Enrolment stage</label>
          <select id="lf-stage" value={filter.stage} disabled={idMode} onChange={(e) => setF("stage", e.target.value)}>
            <option value="">Any stage</option>
            {STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select></div>
        <div className="field"><label htmlFor="lf-id">Identity</label>
          <select id="lf-id" value={filter.identity} disabled={idMode} onChange={(e) => setF("identity", e.target.value)}>
            <option value="">Any</option><option value="captured">ID or passport captured</option><option value="missing">Not captured</option>
          </select></div>
        <div className="field"><label htmlFor="lf-hr">HR directory</label>
          <select id="lf-hr" value={filter.hr} disabled={idMode} onChange={(e) => setF("hr", e.target.value)}>
            <option value="">Any</option><option value="linked">Linked</option><option value="unlinked">Not linked</option>
          </select></div>
        <form className="field id-find" onSubmit={(e) => { e.preventDefault(); setIdQuery(idText.trim()); }}>
          <label htmlFor="lf-idnum">Find by SA ID or passport number</label>
          <div className="row" style={{ flexWrap: "nowrap" }}>
            <input id="lf-idnum" autoComplete="off" value={idText} onChange={(e) => setIdText(e.target.value)} placeholder="Full number" />
            <button className="btn" type="submit" disabled={!idText.trim()}>Find</button>
          </div>
        </form>
        <div className="filter-foot">
          {idMode ? (
            <>
              <span className="small muted">{byId.isFetching ? "Looking up the number…"
                : byId.error ? "" : rows.length ? "The learner holding that number:" : "No learner holds that number."}</span>
              <button className="btn btn-sm" onClick={() => { setIdQuery(""); setIdText(""); }}>Back to the full directory</button>
            </>
          ) : (
            <>
              <span className="small muted">Showing {rows.length} of {everything.length} {everything.length === 1 ? "learner" : "learners"}</span>
              {filtered ? <button className="btn btn-sm" onClick={() => setFilter(NO_FILTER)}>Clear filters</button> : null}
            </>
          )}
        </div>
      </section>
      {idMode && byId.error ? <Blocked refusal={byId.error} /> : null}
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string}
        empty={idMode ? (byId.isFetching ? "Looking up…" : "No learner holds that number.") : filtered ? "No learner matches these filters." : undefined}
        columns={[
          { key: "ref", label: "Learner", render: (r) => r.ref, mono: true },
          { key: "name", label: "Name", render: (r) => <b>{r.name}</b> },
          { key: "type", label: "Type", render: (r) => r.type },
          { key: "org", label: "Organisation", render: (r) => r.organisation || "—" },
          { key: "id", label: "Identity", render: (r) => <span className={r.idNumber === "Not captured" ? "muted small" : "mono"}>{r.idNumber}</span> },
          { key: "hr", label: "HR directory", render: (r) => (r.hrLinked ? "Linked" : "—") },
          { key: "enr", label: "Enrolments", render: (r) => r.enrolments.map((e) => <div key={e} className="small">{e}</div>) },
        ]} />
      <AuditTrail />
    </>
  );
}
