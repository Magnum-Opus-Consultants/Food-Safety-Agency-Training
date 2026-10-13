"use client";

// One session's attendance register: captured once and locked, then changed only by audited
// corrections. Opens under the session's row on Sessions & attendance, and on its own page.

import { useState } from "react";
import { Blocked, Loading, Register, SectionHead, Status } from "@/components/ui";
import { useAction, useRegister } from "@/lib/hooks";
import type { SessionRow } from "@/lib/types";

type Learner = { ref: string; name: string; kind: string; present: boolean | null; corrected: boolean; late: boolean };
type Detail = SessionRow & {
  learners: Learner[];
  corrections: { learner: string; present: boolean; reason: string; at: string; by: string }[];
  captureBlockedBy: string[];
  notOnRoster: { enrolment: string; learner: string; stage: string; why: string }[];
  canWrite: boolean;
};

export function SessionPanel({ code: ref }: { code: string }) {
  const q = useRegister<Detail>(`/sessions/${ref}`);
  const [marks, setMarks] = useState<Record<string, boolean>>({});
  const [fix, setFix] = useState<{ learnerRef: string; present: boolean; reason: string; late?: boolean } | null>(null);
  const capture = useAction<{ marks: Record<string, boolean> }>("POST", `/sessions/${ref}/attendance`);
  const correct = useAction<{ learnerRef: string; present: boolean; reason: string }>("POST", `/sessions/${ref}/attendance/correction`);
  const late = useAction<{ learnerRef: string; present: boolean; reason: string }>("POST", `/sessions/${ref}/attendance/late`);

  if (q.error) return <Blocked refusal={q.error} />;
  if (!q.data) return <Loading what="register" />;
  const s = q.data.data;
  const locked = s.registerState === "Locked";
  const marked = Object.keys(marks).length;
  const ready = marked === s.learners.length && s.learners.length > 0;

  return (
    <div className="stack-12">
      <div className="small muted">{s.venue} · {s.facilitator} · {s.start} to {s.end} · {s.mode} · <Status tone={s.tone}>{s.registerState}</Status></div>
      {locked ? <p className="small" style={{ margin: 0 }}>Captured and locked by {s.lockedBy} at {s.lockedAt}. A change is recorded as a correction; a learner confirmed later is added as a late entry.</p> : null}
      {s.notOnRoster.length ? (
        <div className="callout warn">
          <h4>Registered but not on the class list</h4>
          <p className="small">Only confirmed learners are marked. These learners will appear here once they are confirmed on Enrolments:</p>
          <ul className="small" style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {s.notOnRoster.map((n) => <li key={n.enrolment}><b>{n.learner}</b> ({n.enrolment}): {n.why}.</li>)}
          </ul>
        </div>
      ) : null}

      {!locked ? (
        <section className="stack" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <SectionHead title="Capture the register" />
          <Blocked reasons={s.captureBlockedBy} title="The register cannot be captured yet" />
          <Blocked refusal={capture.refusal} />
          <Register rows={s.learners} rowKey={(l) => l.ref}
            columns={[
              { key: "ref", label: "Learner", render: (l) => l.ref, mono: true },
              { key: "name", label: "Name", render: (l) => <b>{l.name}</b> },
              { key: "kind", label: "Type", render: (l) => l.kind },
              { key: "mark", label: "Attendance", render: (l) => (
                <div className="present-toggle" role="group" aria-label={`Attendance for ${l.name}`}>
                  <button className={marks[l.ref] === true ? "on-present" : ""} disabled={!s.canWrite || s.captureBlockedBy.length > 0}
                          onClick={() => setMarks({ ...marks, [l.ref]: true })}>Present</button>
                  <button className={marks[l.ref] === false ? "on-absent" : ""} disabled={!s.canWrite || s.captureBlockedBy.length > 0}
                          onClick={() => setMarks({ ...marks, [l.ref]: false })}>Absent</button>
                </div>
              ) },
            ]} empty="No learners are registered onto this session." />
          <div className="row">
            <button className="btn btn-primary" disabled={!s.canWrite || capture.isPending || s.captureBlockedBy.length > 0}
                    onClick={() => capture.mutate({ marks })}>
              Capture and lock register
            </button>
            <span className="small muted">
              {ready ? "Ready. The register locks on save; any later change is a new audited correction."
                : `${marked} of ${s.learners.length} learners marked. Mark every learner present or absent before saving.`}
            </span>
          </div>
        </section>
      ) : (
        <section style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <SectionHead title="Locked register" />
          <Blocked refusal={correct.refusal ?? late.refusal} />
          <Register rows={s.learners} rowKey={(l) => l.ref} empty="Nobody was confirmed onto this session when the register was captured."
            columns={[
              { key: "ref", label: "Learner", render: (l) => l.ref, mono: true },
              { key: "name", label: "Name", render: (l) => <b>{l.name}</b> },
              { key: "kind", label: "Type", render: (l) => l.kind },
              { key: "present", label: "Attendance", render: (l) => (
                l.present === null ? <Status tone="warn">Not on the register yet</Status>
                  : <Status tone={l.present ? "ok" : "bad"}>{l.present ? "Present" : "Absent"}{l.corrected ? " · corrected" : l.late ? " · late entry" : ""}</Status>
              ) },
              { key: "fix", label: "", render: (l) => !s.canWrite ? null : l.present === null ? (
                <button className="btn btn-sm btn-primary" onClick={() => { late.clear(); setFix({ learnerRef: l.ref, present: true, reason: "", late: true }); }}>Add late entry</button>
              ) : (
                <button className="btn btn-sm" onClick={() => { correct.clear(); setFix({ learnerRef: l.ref, present: !l.present, reason: "" }); }}>Record correction</button>
              ) },
            ]} />
          {fix ? (
            <div className="card" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
              <b>{fix.late ? "Late entry" : "Correction"} for {s.learners.find((l) => l.ref === fix.learnerRef)?.name}: mark {fix.present ? "present" : "absent"}</b>
              {fix.late ? (
                <div className="present-toggle" role="group" aria-label="Attendance">
                  <button className={fix.present ? "on-present" : ""} onClick={() => setFix({ ...fix, present: true })}>Present</button>
                  <button className={!fix.present ? "on-absent" : ""} onClick={() => setFix({ ...fix, present: false })}>Absent</button>
                </div>
              ) : null}
              <div className="field">
                <label htmlFor="reason">{fix.late ? "Why is this learner added after the register was locked?" : "Reason for the correction"}</label>
                <input id="reason" value={fix.reason} onChange={(e) => setFix({ ...fix, reason: e.target.value })}
                       placeholder={fix.late ? "For example: confirmed after the register was captured" : "For example: left site on day 3, supervisor sign-off"} />
              </div>
              <div className="row">
                <button className="btn btn-teal" disabled={correct.isPending || late.isPending}
                        onClick={() => (fix.late ? late : correct).mutate({ learnerRef: fix.learnerRef, present: fix.present, reason: fix.reason },
                          { onSuccess: () => setFix(null) })}>{fix.late ? "Add to the register" : "Save correction"}</button>
                <button className="btn" onClick={() => { setFix(null); correct.clear(); late.clear(); }}>Cancel</button>
              </div>
            </div>
          ) : null}
          {s.corrections.length ? (
            <Register rows={s.corrections} rowKey={(c) => c.at + c.learner} empty=""
              columns={[
                { key: "at", label: "When", render: (c) => c.at, mono: true },
                { key: "l", label: "Learner", render: (c) => c.learner },
                { key: "p", label: "Now", render: (c) => (c.present ? "Present" : "Absent") },
                { key: "r", label: "Reason", render: (c) => c.reason },
                { key: "b", label: "By", render: (c) => c.by },
              ]} />
          ) : null}
        </section>
      )}
    </div>
  );
}
