"use client";

// Certification: every result that has or could have a certificate, in one register. Filter by
// issued or not, search by student, and open a row underneath: an issued certificate opens as a PDF
// (view or download); one not yet issued shows why, or can be issued.

import { useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { useAction, useRegister } from "@/lib/hooks";
import type { Tone } from "@/lib/api";

type Issued = { ref: string; result: string; learner: string; learnerRef: string; enrolment: string; course: string; mark: number;
  issuedAt: string; issuedBy: string; verificationCode: string; depositoryRef: string | null; revoked: boolean; pdf: string };
type Candidate = { ref: string; learner: string; course: string; mark: number; position: string; tone: Tone; certificateBlockedBy: string[] };
type Row = { key: string; result: string; learner: string; course: string; mark: number; issued: Issued | null; candidate: Candidate | null };

const VIEWS: [string, string][] = [["", "All"], ["ready", "Ready to issue"], ["not", "Not issued"], ["issued", "Issued"]];

export default function Certification() {
  const q = useRegister<{ issued: Issued[]; candidates: Candidate[]; canIssue: boolean }>("/certificates");
  const issue = useAction<{ resultRef: string }, Issued>("POST", "/certificates");
  const [open, setOpen] = useState<string | null>(null);
  const [view, setView] = useState("");
  const [course, setCourse] = useState("");
  const [search, setSearch] = useState("");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { issued, candidates, canIssue } = q.data.data;
  const all: Row[] = [
    ...candidates.map((c) => ({ key: c.ref, result: c.ref, learner: c.learner, course: c.course, mark: c.mark, issued: null, candidate: c })),
    ...issued.map((c) => ({ key: c.ref, result: c.result, learner: c.learner, course: c.course, mark: c.mark, issued: c, candidate: null })),
  ];
  const ready = (r: Row) => !!r.candidate && r.candidate.certificateBlockedBy.length === 0;
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const rows = all
    .filter((r) => !view || (view === "issued" ? !!r.issued : view === "not" ? !r.issued : ready(r)))
    .filter((r) => !course || r.course === course)
    .filter((r) => words.every((w) => `${r.learner} ${r.course} ${r.result} ${r.issued?.ref ?? ""} ${r.issued?.learnerRef ?? ""}`.toLowerCase().includes(w)));
  const courses = Array.from(new Set(all.map((r) => r.course))).sort();
  const count = (v: string) => all.filter((r) => !v || (v === "issued" ? !!r.issued : v === "not" ? !r.issued : ready(r))).length;

  return (
    <>
      <Hero
        stats={[
          { v: String(issued.length), l: "Issued", c: "Certificates on the register" },
          { v: String(candidates.filter((c) => c.certificateBlockedBy.length === 0).length), l: "Ready to issue", c: "Moderated competent" },
          { v: String(candidates.filter((c) => c.certificateBlockedBy.length > 0).length), l: "Not issuable yet", c: "Unmoderated or not yet competent" },
          { v: "10", l: "Working days", c: "Issue standard after moderation" },
        ]}
      />
      <Blocked refusal={issue.refusal} />
      <SectionHead title="Certificates" />
      <div className="card week-bar">
        <div className="seg" role="group" aria-label="Show">
          {VIEWS.map(([v, l]) => (
            <button key={l} className={view === v ? "on" : undefined} aria-pressed={view === v} onClick={() => setView(v)}>
              {l} <span className="seg-n">{count(v)}</span></button>
          ))}
        </div>
        <select aria-label="Course" className="bar-select" value={course} onChange={(e) => setCourse(e.target.value)}>
          <option value="">Any course</option>{courses.map((c) => <option key={c}>{c}</option>)}
        </select>
        <div className="week-search">
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search certificates"
                 placeholder="Search: student, course, result (RES-…) or certificate (CERT-…)" />
        </div>
        <span className="small muted">{rows.length} of {all.length}</span>
      </div>
      <Register rows={rows} rowKey={(r) => r.key} empty="Nothing matches these filters."
        onRow={(r) => { setOpen(r.key === open ? null : r.key); issue.clear(); }}
        expanded={(r) => (r.key !== open ? null : r.issued ? (
          <div className="stack-12">
            <div className="row">
              <a className="btn btn-sm btn-primary" href={r.issued.pdf} target="_blank" rel="noopener"><i className="fas fa-file-pdf" aria-hidden /> View PDF</a>
              <a className="btn btn-sm" href={`${r.issued.pdf}?download=true`}><i className="fas fa-download" aria-hidden /> Download PDF</a>
              <span className="small muted">Verification code {r.issued.verificationCode} · filed to the depository as {r.issued.depositoryRef ?? "—"}</span>
            </div>
            <iframe className="cert-frame" src={r.issued.pdf} title={`Certificate ${r.issued.ref}`} />
          </div>
        ) : r.candidate ? (
          <div className="stack-12">
            <div className="small muted">{r.result} · {r.course} · mark {r.mark}%</div>
            {r.candidate.certificateBlockedBy.length ? (
              <Blocked reasons={r.candidate.certificateBlockedBy} title="Not issuable yet" />
            ) : canIssue ? (
              <div className="row">
                <button className="btn btn-primary" disabled={issue.isPending}
                        onClick={() => issue.mutate({ resultRef: r.result }, { onSuccess: (x) => setOpen(x.data.ref) })}>Issue certificate</button>
                <span className="small muted">Signed by you as training manager and filed to the depository. The PDF is ready straight after.</span>
              </div>
            ) : <p className="small muted" style={{ margin: 0 }}>Moderated competent: the training manager signs and issues it.</p>}
          </div>
        ) : null)}
        columns={[
          { key: "ref", label: "Reference", render: (r) => <>{r.issued ? r.issued.ref : r.result}<div className="small muted">{r.issued ? r.result : ""}</div></>, mono: true },
          { key: "learner", label: "Student", render: (r) => <b>{r.learner}</b> },
          { key: "course", label: "Course", render: (r) => r.course },
          { key: "mark", label: "Mark", render: (r) => `${r.mark}%`, mono: true },
          { key: "state", label: "Certificate", render: (r) => r.issued ? (
            <><Status tone={r.issued.revoked ? "bad" : "ok"}>{r.issued.revoked ? "Revoked" : "Issued"}</Status><div className="small muted">{r.issued.issuedAt} · {r.issued.issuedBy}</div></>
          ) : <Status tone={r.candidate!.certificateBlockedBy.length ? r.candidate!.tone : "info"}>{r.candidate!.certificateBlockedBy.length ? r.candidate!.position : "Ready to issue"}</Status> },
          { key: "act", label: "", render: (r) => r.issued ? (
            <a className="btn btn-sm" href={r.issued.pdf} target="_blank" rel="noopener" onClick={(e) => e.stopPropagation()}>
              <i className="fas fa-file-pdf" aria-hidden /> PDF</a>
          ) : null },
        ]} />
      <AuditTrail />
    </>
  );
}
