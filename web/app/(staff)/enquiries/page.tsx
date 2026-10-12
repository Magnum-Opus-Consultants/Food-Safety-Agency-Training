"use client";

import { useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, SectionHead, Stat, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useAction, useMe, useRegister } from "@/lib/hooks";
import { Modal, RegisterLearnerForm } from "@/components/registration";

type Enquiry = {
  ref: string; name: string; org: string; course: string; kind: string; channel: string; workingDaysOpen: number;
  stageIndex: number; stage: string; owner: string | null; tone: Tone; stale: boolean;
  courseCode: string; email: string; phone: string; enrolment: string | null;
};

const REGISTERED = 3;

const CHANNELS = [["Phone", "Phone"], ["Email", "Email"], ["WhatsApp", "WhatsApp"], ["DirectLine", "Her direct line"]];

export default function EnquiryQueue() {
  const q = useRegister<{ stages: string[]; items: Enquiry[]; stats: Stat[] }>("/enquiries");
  const courses = useRegister<{ code: string; title: string }[]>("/courses");
  const me = useMe();
  const move = useAction<{ ref: string; stageIndex: number }>("PATCH", (v) => `/enquiries/${v.ref}/stage`);
  const log = useAction<Record<string, string>>("POST", "/enquiries");
  const [drag, setDrag] = useState<string | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [registering, setRegistering] = useState<Enquiry | null>(null);

  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="enquiry queue" />;
  const { stages, items, stats } = q.data.data;
  const canWrite = me.data?.data.writes.includes("demand") ?? false;
  const enquiries = items.filter((e) => e.kind === "Enquiry");

  function drop(stageIndex: number) {
    const ref = drag;
    setDrag(null);
    setOver(null);
    const card = enquiries.find((e) => e.ref === ref);
    if (card && card.stageIndex !== stageIndex) toStage(card, stageIndex);
  }

  // Registered means a learner exists: moving there opens the registration instead of moving the card.
  function toStage(card: Enquiry, stageIndex: number) {
    if (stageIndex === REGISTERED && !card.enrolment) {
      move.clear();
      setRegistering(card);
    } else move.mutate({ ref: card.ref, stageIndex });
  }

  return (
    <>
      <Hero
        title="A shared queue, not an individual's inbox."
        statement="Enquiries arrive by phone, email and WhatsApp and route to the admin rotation; her direct line reaches her first. Drag a card to change its stage. The two-working-day response clock stops on first response."
        stats={stats}
      />
      <Blocked refusal={move.refusal ?? log.refusal} />
      <SectionHead title="Enquiry board">
        {canWrite ? <button className="btn btn-teal" onClick={() => setForm(form ? null : { channel: "Phone", kind: "Enquiry" })}>Log enquiry</button> : null}
      </SectionHead>
      {form ? (
        <div className="card" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="form-grid">
            <div className="field"><label htmlFor="n">Enquirer</label><input id="n" value={form.names ?? ""} onChange={(e) => setForm({ ...form, names: e.target.value })} /></div>
            <div className="field"><label htmlFor="o">Organisation</label><input id="o" value={form.organisation ?? ""} onChange={(e) => setForm({ ...form, organisation: e.target.value })} /></div>
            <div className="field"><label htmlFor="c">Channel</label>
              <select id="c" value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
                {CHANNELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></div>
            <div className="field"><label htmlFor="k">Kind</label>
              <select id="k" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option>Enquiry</option><option>Complaint</option><option>Opportunity</option>
              </select></div>
            <div className="field"><label htmlFor="cc">Course</label>
              <select id="cc" value={form.courseCode ?? ""} onChange={(e) => setForm({ ...form, courseCode: e.target.value })}>
                <option value="">Not a catalogue course</option>
                {(courses.data?.data ?? []).map((c) => <option key={c.code} value={c.code}>{c.title}</option>)}
              </select></div>
            <div className="field"><label htmlFor="i">What they asked about</label><input id="i" value={form.interest ?? ""} onChange={(e) => setForm({ ...form, interest: e.target.value })} /></div>
          </div>
          <div className="row">
            <button className="btn btn-primary" disabled={log.isPending} onClick={() => log.mutate(form, { onSuccess: () => setForm(null) })}>Log and route</button>
            <button className="btn" onClick={() => setForm(null)}>Cancel</button>
            <span className="small muted">Complaints and opportunities go straight to the head of department&apos;s desk.</span>
          </div>
        </div>
      ) : null}
      <div className="board">
        {stages.map((stage, i) => {
          const cards = enquiries.filter((e) => e.stageIndex === i);
          return (
            <div key={stage} className={`col${over === i && drag ? " over" : ""}`}
                 onDragOver={(e) => { if (canWrite) { e.preventDefault(); setOver(i); } }}
                 onDragLeave={() => setOver(null)} onDrop={(e) => { e.preventDefault(); drop(i); }}>
              <div className="col-head"><span>{stage}</span><span className="mono">{cards.length}</span></div>
              {cards.map((e) => (
                <div key={e.ref} className={`kcard${drag === e.ref ? " dragging" : ""}`} draggable={canWrite}
                     onDragStart={(ev) => { setDrag(e.ref); ev.dataTransfer.setData("text/plain", e.ref); ev.dataTransfer.effectAllowed = "move"; }}
                     onDragEnd={() => { setDrag(null); setOver(null); }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span className="mono small">{e.ref}</span>
                    {e.stale ? <Status tone="bad">Over two days</Status> : !e.owner ? <Status tone="bad">Unassigned</Status> : null}
                  </div>
                  <b>{e.name}</b>
                  <span>{e.org}</span>
                  <span>{e.course}</span>
                  <span className="mono">{e.workingDaysOpen} working {e.workingDaysOpen === 1 ? "day" : "days"} · {e.channel}</span>
                  <span>Owner: {e.owner ?? "unassigned"}</span>
                  {e.enrolment ? <span>Registered as <span className="mono">{e.enrolment}</span></span> : null}
                  {canWrite && !e.enrolment && e.stageIndex < REGISTERED ? (
                    <button className="btn btn-sm" onClick={() => { move.clear(); setRegistering(e); }}>Register learner</button>
                  ) : null}
                  {canWrite ? (
                    <select aria-label={`Move ${e.ref}`} value={e.stageIndex} className="small"
                            onChange={(ev) => toStage(e, Number(ev.target.value))}>
                      {stages.map((s, si) => <option key={s} value={si}>{si === e.stageIndex ? `Stage: ${s}` : `Move to ${s}`}</option>)}
                    </select>
                  ) : null}
                </div>
              ))}
            </div>
          );
        })}
      </div>
      <div className="source">Source: {q.data.meta.source as string}. Complaints and opportunities are listed on the head of department&apos;s desk.</div>
      {registering ? (
        <Modal title={`Register a learner from ${registering.ref}`} onClose={() => setRegistering(null)}>
          <RegisterLearnerForm
            prefill={{ enquiryRef: registering.ref, names: registering.name === "Training desk" ? "" : registering.name,
                       email: registering.email, phone: registering.phone, organisation: registering.org,
                       courseCode: registering.courseCode }}
            onDone={() => setRegistering(null)} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
