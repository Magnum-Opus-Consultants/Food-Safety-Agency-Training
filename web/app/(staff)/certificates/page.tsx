"use client";

import { useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { useAction, useRegister } from "@/lib/hooks";
import type { Tone } from "@/lib/api";

type Issued = { ref: string; result: string; learner: string; course: string; mark: number; issuedAt: string; issuedBy: string; verificationCode: string; depositoryRef: string | null };
type Candidate = { ref: string; learner: string; course: string; mark: number; position: string; tone: Tone; certificateBlockedBy: string[] };

export default function Certification() {
  const q = useRegister<{ issued: Issued[]; candidates: Candidate[]; canIssue: boolean }>("/certificates");
  const issue = useAction<{ resultRef: string }, Issued>("POST", "/certificates");
  const [preview, setPreview] = useState<string | null>(null);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { issued, candidates, canIssue } = q.data.data;
  return (
    <>
      <Hero
        title="A certificate may only be issued after moderation, and is signed by the training manager."
        statement="Issue files the certificate to the depository with a reference and writes an audit entry. The API refuses an unmoderated result and the screen explains the refusal."
        stats={[
          { v: String(issued.length), l: "Issued", c: "Certification register" },
          { v: String(candidates.filter((c) => c.certificateBlockedBy.length === 0).length), l: "Ready to issue", c: "Moderated competent" },
          { v: String(candidates.filter((c) => c.certificateBlockedBy.length > 0).length), l: "Not issuable", c: "Unmoderated or not yet competent" },
          { v: "10", l: "Working days", c: "Issue standard after moderation" },
        ]}
      />
      <Blocked refusal={issue.refusal} />
      <SectionHead title="Results without a certificate" />
      <Register rows={candidates} rowKey={(c) => c.ref}
        columns={[
          { key: "ref", label: "Result", render: (c) => c.ref, mono: true },
          { key: "learner", label: "Learner", render: (c) => <b>{c.learner}</b> },
          { key: "course", label: "Course", render: (c) => c.course },
          { key: "mark", label: "Mark", render: (c) => `${c.mark}%`, mono: true },
          { key: "pos", label: "Position", render: (c) => <Status tone={c.tone}>{c.position}</Status> },
          { key: "act", label: "", render: (c) => canIssue ? (
            // Deliberately not disabled for unmoderated results: the API's refusal names why (rule 2).
            <button className="btn btn-sm" disabled={issue.isPending}
                    onClick={() => issue.mutate({ resultRef: c.ref }, { onSuccess: (r) => setPreview(r.data.ref) })}>Issue certificate</button>
          ) : null },
        ]} />
      <SectionHead title="Certification register" />
      <Register rows={issued} rowKey={(c) => c.ref} onRow={(c) => setPreview(c.ref === preview ? null : c.ref)}
        expanded={(c) => (c.ref === preview ? (
          <div className="cert">
            <span className="eyebrow">FSA Academy · Certificate of competence</span>
            <h2>{c.learner}</h2>
            <p style={{ margin: 0 }}>has been found competent in</p>
            <b>{c.course}</b>
            <p className="small muted" style={{ margin: 0 }}>{c.ref} · issued {c.issuedAt} · verification {c.verificationCode}</p>
            <p className="small muted" style={{ margin: 0 }}>Signed by {c.issuedBy}, training manager. Filed to the depository as {c.depositoryRef}.</p>
          </div>
        ) : null)}
        columns={[
          { key: "ref", label: "Certificate", render: (c) => c.ref, mono: true },
          { key: "learner", label: "Learner", render: (c) => <b>{c.learner}</b> },
          { key: "course", label: "Course", render: (c) => c.course },
          { key: "at", label: "Issued", render: (c) => c.issuedAt, mono: true },
          { key: "by", label: "Signed by", render: (c) => c.issuedBy },
          { key: "doc", label: "Depository", render: (c) => c.depositoryRef ?? "—", mono: true },
        ]} />
      <AuditTrail />
    </>
  );
}
