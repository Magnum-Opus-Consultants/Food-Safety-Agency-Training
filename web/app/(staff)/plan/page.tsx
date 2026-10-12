"use client";

import { useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, Status } from "@/components/ui";
import { useAction, useMe, useRegister } from "@/lib/hooks";
import type { Block } from "@/lib/types";

// Demo depth: the plan as a register with derived warnings and the confirm hard block.
// The year / month / week horizons and the block editor are phase 3 (the department's constraint).
export default function TrainingPlan() {
  const [stream, setStream] = useState("");
  const q = useRegister<Block[]>(`/plan${stream ? `?stream=${stream}` : ""}`);
  const all = useRegister<Block[]>("/plan");
  const me = useMe();
  const confirm = useAction<{ ref: string }>("POST", (v) => `/plan/${v.ref}/confirm`);
  const [open, setOpen] = useState<string | null>(null);

  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="training plan" />;
  const blocks = q.data.data;
  const streams = Array.from(new Map((all.data?.data ?? []).map((b) => [b.streamCode, { name: b.stream, colour: b.streamColour }])).entries());
  const canConfirm = me.data?.data.role === "TrainingManager";
  const selected = blocks.find((b) => b.ref === open);

  return (
    <>
      <Hero
        title="Plan delivery and see the clashes before a booking is confirmed."
        statement="Warnings are derived on every read: fill below half is an observation; a facilitator registration that has lapsed is a hard block; expiry inside a block is an observation. The three calendar horizons and the block editor follow in phase 3."
        stats={[
          { v: String(blocks.length), l: "Blocks", c: stream ? "In the selected stream" : "In the plan" },
          { v: String(blocks.filter((b) => b.state === "Confirmed").length), l: "Confirmed", c: "Booked and communicated" },
          { v: String(blocks.filter((b) => b.warnings.some((w) => w.tone === "bad")).length), l: "Hard blocks", c: "Cannot be confirmed" },
          { v: String(blocks.filter((b) => b.fill < 50).length), l: "Below half full", c: "Follow up the quotations" },
        ]}
      />
      <div className="row">
        <span className="eyebrow">Stream</span>
        <button className={`btn btn-sm${stream === "" ? " on" : ""}`} onClick={() => setStream("")}>All streams</button>
        {streams.map(([code, st]) => (
          <button key={code} className={`btn btn-sm${stream === code ? " on" : ""}`} onClick={() => setStream(code)}>
            <i style={{ width: 10, height: 10, background: st.colour, display: "inline-block", borderRadius: 1 }} /> {st.name}
          </button>
        ))}
      </div>
      <Blocked refusal={confirm.refusal} />
      <Register rows={blocks} rowKey={(b) => b.ref} onRow={(b) => { setOpen(b.ref === open ? null : b.ref); confirm.clear(); }} source={q.data.meta.source as string}
        columns={[
          { key: "ref", label: "Block", render: (b) => <><span className="mono">{b.ref}</span><div className="small muted mono">{b.session}</div></> },
          { key: "course", label: "Course", render: (b) => <><span style={{ display: "inline-block", width: 10, height: 10, background: b.streamColour, marginRight: 6, borderRadius: 1 }} /><b>{b.course}</b><div className="small muted">{b.venue} · {b.cadence === "AdHoc" ? "ad hoc" : `${b.cadence.toLowerCase()} intake`}</div></> },
          { key: "fac", label: "Facilitator", render: (b) => b.facilitator },
          { key: "dates", label: "Dates", render: (b) => `${b.start} → ${b.end}`, mono: true },
          { key: "fill", label: "Fill", render: (b) => `${b.seats}/${b.capacity} · ${b.fill}%`, mono: true },
          { key: "state", label: "State", render: (b) => {
            const worst = b.warnings.find((w) => w.tone === "bad") ?? b.warnings.find((w) => w.tone === "warn");
            return <div className="row" style={{ gap: 6 }}><span>{b.state}</span>{worst ? <Status tone={worst.tone} /> : <Status tone="ok" />}</div>;
          } },
        ]} />
      {selected ? (
        <section className="card" style={{ padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="row"><span className="mono">{selected.ref}</span><b>{selected.course}</b><span className="spacer" />
            <button className="btn btn-sm" onClick={() => setOpen(null)}>Close</button></div>
          <div className="small muted">{selected.facilitator} · {selected.venue} · {selected.mode} · {selected.hours} supervised practical hours</div>
          {selected.notes ? <p style={{ margin: 0 }}>{selected.notes}</p> : null}
          {selected.warnings.length === 0 ? <div className="callout ok"><p>No warnings on this block.</p></div> : selected.warnings.map((w) => (
            <div key={w.message} className={`callout ${w.tone}`}><h4>{w.tone === "bad" ? "Finding" : "Observation"} · {w.kind}</h4><p>{w.message}</p></div>
          ))}
          {selected.state === "Draft" && canConfirm ? (
            <div className="row">
              <button className="btn btn-primary" disabled={confirm.isPending} onClick={() => confirm.mutate({ ref: selected.ref })}>Confirm block</button>
              <span className="small muted">Confirming issues the booking. A lapsed registration refuses it.</span>
            </div>
          ) : null}
        </section>
      ) : null}
      <AuditTrail />
    </>
  );
}
