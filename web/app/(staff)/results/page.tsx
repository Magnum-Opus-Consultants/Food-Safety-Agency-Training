"use client";

import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useAction, useRegister } from "@/lib/hooks";

type Result = {
  ref: string; learner: string; course: string; session: string | null; assessor: string; mark: number; outcome: string;
  moderated: boolean; moderatedBy: string | null; certificate: string | null; position: string; tone: Tone;
  certificateBlockedBy: string[]; remediation: string;
};

export default function Results() {
  const q = useRegister<{ items: Result[]; canModerate: boolean }>("/results");
  const moderate = useAction<{ ref: string }>("POST", (v) => `/results/${v.ref}/moderate`);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { items, canModerate } = q.data.data;
  const waiting = items.filter((r) => !r.moderated);
  return (
    <>
      <Hero
        title="The training official assesses; the training manager moderates every result."
        statement="A result awaiting moderation cannot progress to certification. Evidence is retained two years live, then archived to the NAS."
        stats={[
          { v: String(items.length), l: "Results", c: "On the register" },
          { v: String(waiting.length), l: "Awaiting moderation", c: "Assessed, not yet moderated" },
          { v: String(items.filter((r) => r.moderated && r.outcome === "Competent" && !r.certificate).length), l: "Ready to certify", c: "Moderated competent" },
          { v: String(items.filter((r) => r.outcome !== "Competent").length), l: "Remediation", c: "Not yet competent" },
        ]}
      />
      <Blocked refusal={moderate.refusal} />
      <Register rows={items} rowKey={(r) => r.ref} source={q.data.meta.source as string}
        columns={[
          { key: "ref", label: "Result", render: (r) => r.ref, mono: true },
          { key: "learner", label: "Learner", render: (r) => <b>{r.learner}</b> },
          { key: "course", label: "Course", render: (r) => <>{r.course}<div className="small muted mono">{r.session}</div></> },
          { key: "assessor", label: "Assessor", render: (r) => r.assessor },
          { key: "mark", label: "Mark", render: (r) => `${r.mark}%`, mono: true },
          { key: "outcome", label: "Outcome", render: (r) => (r.outcome === "Competent" ? "Competent" : "Not yet competent") },
          { key: "pos", label: "Position", render: (r) => <Status tone={r.tone}>{r.position}</Status> },
          { key: "act", label: "", render: (r) => (!r.moderated && canModerate ? (
            <button className="btn btn-sm btn-teal" disabled={moderate.isPending} onClick={() => moderate.mutate({ ref: r.ref })}>Record moderation</button>
          ) : null) },
        ]} />
      <AuditTrail />
    </>
  );
}
