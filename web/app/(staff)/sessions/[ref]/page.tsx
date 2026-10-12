"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { AuditTrail, Blocked, LoadError, Loading, PageHeader, Register, SectionHead, Status } from "@/components/ui";
import { useAction, useRegister } from "@/lib/hooks";
import type { SessionRow } from "@/lib/types";

type Learner = { ref: string; name: string; kind: string; present: boolean | null; corrected: boolean };
type Detail = SessionRow & {
  learners: Learner[];
  corrections: { learner: string; present: boolean; reason: string; at: string; by: string }[];
  captureBlockedBy: string[];
  canWrite: boolean;
};

export default function SessionRegister() {
  const { ref } = useParams<{ ref: string }>();
  const q = useRegister<Detail>(`/sessions/${ref}`);
  const [marks, setMarks] = useState<Record<string, boolean>>({});
  const [fix, setFix] = useState<{ learnerRef: string; present: boolean; reason: string } | null>(null);
  const capture = useAction<{ marks: Record<string, boolean> }>("POST", `/sessions/${ref}/attendance`);
  const correct = useAction<{ learnerRef: string; present: boolean; reason: string }>("POST", `/sessions/${ref}/attendance/correction`);

  if (q.error) return <><LoadError error={q.error} /><Link href="/sessions">Back to sessions</Link></>;
  if (!q.data) return <Loading what="register" />;
  const s = q.data.data;
  const locked = s.registerState === "Locked";
  const marked = Object.keys(marks).length;
  const ready = marked === s.learners.length && s.learners.length > 0;

  return (
    <>
      <div className="row"><Link href="/sessions" className="small"><i className="fas fa-arrow-left" aria-hidden /> All sessions</Link></div>
      <PageHeader lead={`${s.ref} · ${s.course}`} statement={`${s.venue} · ${s.facilitator} · ${s.start} → ${s.end}`} />
      <section className="card hero">
        <div className="row"><span className="mono">{s.ref}</span><Status tone={s.tone}>{s.registerState}</Status></div>
        <h2>{s.course}</h2>
        <p className="muted">{s.venue} · {s.facilitator} · <span className="mono">{s.start} → {s.end}</span> · {s.mode}</p>
        {locked ? <p>Captured and locked by {s.lockedBy} at <span className="mono">{s.lockedAt}</span>. A change is recorded as a correction.</p> : null}
      </section>

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
          <Blocked refusal={correct.refusal} />
          <Register rows={s.learners} rowKey={(l) => l.ref}
            columns={[
              { key: "ref", label: "Learner", render: (l) => l.ref, mono: true },
              { key: "name", label: "Name", render: (l) => <b>{l.name}</b> },
              { key: "kind", label: "Type", render: (l) => l.kind },
              { key: "present", label: "Attendance", render: (l) => (
                <Status tone={l.present ? "ok" : "bad"}>{l.present ? "Present" : "Absent"}{l.corrected ? " · corrected" : ""}</Status>
              ) },
              { key: "fix", label: "", render: (l) => s.canWrite ? (
                <button className="btn btn-sm" onClick={() => setFix({ learnerRef: l.ref, present: !l.present, reason: "" })}>Record correction</button>
              ) : null },
            ]} />
          {fix ? (
            <div className="card" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
              <b>Correction for {s.learners.find((l) => l.ref === fix.learnerRef)?.name}: mark {fix.present ? "present" : "absent"}</b>
              <div className="field">
                <label htmlFor="reason">Reason for the correction</label>
                <input id="reason" value={fix.reason} onChange={(e) => setFix({ ...fix, reason: e.target.value })}
                       placeholder="For example: left site on day 3, supervisor sign-off" />
              </div>
              <div className="row">
                <button className="btn btn-teal" disabled={correct.isPending}
                        onClick={() => correct.mutate(fix, { onSuccess: () => setFix(null) })}>Save correction</button>
                <button className="btn" onClick={() => { setFix(null); correct.clear(); }}>Cancel</button>
              </div>
            </div>
          ) : null}
          {s.corrections.length ? (
            <Register rows={s.corrections} rowKey={(c) => c.at + c.learner} source="Corrections are new entries; the original capture is never edited"
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
      <AuditTrail screen="sessions" />
    </>
  );
}
