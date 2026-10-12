"use client";

import { useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { useAction, useMe, useRegister } from "@/lib/hooks";
import { Modal, RegisterLearnerForm } from "@/components/registration";

type Enrolment = {
  ref: string; learner: string; course: string; gated: boolean; intake: string | null; stageIndex: number; stage: string;
  prerequisiteResult: number | null; grade10: boolean; basis: string; gateBlockedBy: string[]; advanceBlockedBy: string[];
  owner: string | null;
};

export default function Enrolments() {
  const q = useRegister<{ stages: string[]; items: Enrolment[]; counts: number[] }>("/enrolments");
  const me = useMe();
  const advance = useAction<{ ref: string }>("PATCH", (v) => `/enrolments/${v.ref}/stage`);
  const gate = useAction<{ ref: string; prerequisiteResult?: number; grade10EvidenceHeld?: boolean }>(
    "PATCH", (v) => `/enrolments/${v.ref}/gate`);
  const [open, setOpen] = useState<string | null>(null);
  const [score, setScore] = useState("");
  const [registering, setRegistering] = useState(false);

  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { stages, items, counts } = q.data.data;
  const canWrite = me.data?.data.writes.includes("learners") ?? false;
  const selected = items.find((e) => e.ref === open);
  const refusal = advance.refusal ?? gate.refusal;

  return (
    <>
      <Hero
        title="The entry gate is a prerequisite test of 50% or better and evidence of Grade 10. Both, not either."
        statement="An enrolment cannot advance while either part is outstanding, and the screen names which one."
        stats={stages.map((s, i) => ({ v: String(counts[i]), l: s, c: i === 0 ? "At the entry gate" : undefined }))}
      />
      <SectionHead title="Enrolment register">
        {canWrite ? <button className="btn btn-teal" onClick={() => setRegistering(true)}>Register a learner</button> : null}
      </SectionHead>
      <Register rows={items} rowKey={(e) => e.ref} source={q.data.meta.source as string}
        onRow={(e) => { setOpen(e.ref === open ? null : e.ref); advance.clear(); gate.clear(); setScore(""); }}
        columns={[
          { key: "ref", label: "Enrolment", render: (e) => e.ref, mono: true },
          { key: "learner", label: "Learner", render: (e) => <b>{e.learner}</b> },
          { key: "course", label: "Course", render: (e) => e.course },
          { key: "intake", label: "Intake", render: (e) => e.intake ?? "—", mono: true },
          { key: "test", label: "Test", render: (e) => (e.gated ? (e.prerequisiteResult === null ? "—" : `${e.prerequisiteResult}%`) : "n/a"), mono: true },
          { key: "g10", label: "Grade 10", render: (e) => (e.gated ? (e.grade10 ? "Held" : "Outstanding") : "n/a") },
          { key: "stage", label: "Stage", render: (e) => (
            <Status tone={e.gateBlockedBy.length ? "bad" : e.stageIndex === 4 ? "ok" : "info"}>{e.gateBlockedBy.length ? "Gate incomplete" : e.stage}</Status>
          ) },
        ]} />
      {selected ? (
        <section className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="row"><span className="mono">{selected.ref}</span><b>{selected.learner}</b><span className="muted">· {selected.course}</span>
            <span className="spacer" /><button className="btn btn-sm" onClick={() => setOpen(null)}>Close</button></div>
          <div className="row small muted">Stage {selected.stageIndex + 1} of 5 · {selected.stage} · {selected.basis} · owner {selected.owner ?? "unassigned"}</div>
          <div className="rail-steps" aria-hidden>{stages.map((s, i) => <i key={s} className={i < selected.stageIndex ? "done" : i === selected.stageIndex ? "now" : ""} />)}</div>
          {selected.gateBlockedBy.length ? <Blocked reasons={selected.gateBlockedBy} title="Entry gate — outstanding" /> : null}
          <Blocked refusal={refusal} />
          {canWrite && selected.stageIndex === 0 && selected.gated ? (
            <div className="row">
              <div className="field" style={{ width: 170 }}>
                <label htmlFor="score">Prerequisite result (%)</label>
                <input id="score" inputMode="decimal" value={score} onChange={(e) => setScore(e.target.value)} placeholder={selected.prerequisiteResult?.toString() ?? ""} />
              </div>
              <button className="btn" disabled={!score || gate.isPending} onClick={() => gate.mutate({ ref: selected.ref, prerequisiteResult: Number(score) }, { onSuccess: () => setScore("") })}>Capture result</button>
              <button className="btn" disabled={gate.isPending} onClick={() => gate.mutate({ ref: selected.ref, grade10EvidenceHeld: !selected.grade10 })}>
                {selected.grade10 ? "Withdraw Grade 10 evidence" : "File Grade 10 evidence"}
              </button>
            </div>
          ) : null}
          {canWrite && selected.stageIndex < 4 ? (
            <div className="row">
              <button className="btn btn-primary" disabled={advance.isPending} onClick={() => advance.mutate({ ref: selected.ref })}>
                Advance to {stages[selected.stageIndex + 1].toLowerCase()}
              </button>
              <span className="small muted">If the gate is incomplete the refusal names what is outstanding.</span>
            </div>
          ) : null}
        </section>
      ) : null}
      {registering ? (
        <Modal title="Register a learner" onClose={() => setRegistering(false)}>
          <RegisterLearnerForm onDone={(ref) => { setRegistering(false); setOpen(ref); }} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
