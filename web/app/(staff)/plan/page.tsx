"use client";

import { useState } from "react";
import { SearchSelect } from "@/components/SearchSelect";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { Modal } from "@/components/registration";
import { Affected, CancelIntake, IntakeForm, LearnerContacts } from "@/components/IntakeForm";
import { useAction, useMe, useRegister } from "@/lib/hooks";
import type { Block } from "@/lib/types";

// The plan as a register: intakes are added, changed and cancelled here by the head of department,
// with derived warnings and the confirm hard block. Calendar views are not built yet.
const intakes = (n: number) => `${n} ${n === 1 ? "intake" : "intakes"}`;

/** A heading that says what the warning is about, in plain words. */
function warningTitle(w: { kind: string; tone: string }, state: string) {
  if (w.kind === "fill") return "Less than half the seats are booked";
  if (w.kind === "clash") return "The facilitator is booked twice";
  if (w.kind === "accreditation" && w.tone === "bad" && state === "Confirmed") return "The facilitator's registration will not cover this intake";
  if (w.kind === "accreditation") return w.tone === "bad" ? "Cannot be confirmed: the facilitator's registration has lapsed"
    : "The facilitator's registration expires during this intake";
  return w.tone === "bad" ? "Action required" : "Needs attention";
}

export default function TrainingPlan() {
  const [stream, setStream] = useState("");
  const q = useRegister<Block[]>(`/plan${stream ? `?stream=${stream}` : ""}`);
  const all = useRegister<Block[]>("/plan");
  const me = useMe();
  const confirm = useAction<{ ref: string }>("POST", (v) => `/plan/${v.ref}/confirm`);
  const [open, setOpen] = useState<string | null>(null);
  const [mode, setMode] = useState<"" | "edit" | "cancel">("");
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState<{ what: string; affected: Affected[] } | null>(null);
  const done = (what: string, affected: Affected[]) => { setMode(""); setAdding(false); setNotice({ what, affected }); };
  const [scope, setScope] = useState<"" | "mine" | "all">("");
  const [filter, setFilter] = useState({ q: "", state: "", attention: "", facilitator: "", when: "", from: "", to: "" });
  const setF = (k: keyof typeof filter, v: string) => setFilter((x) => ({ ...x, [k]: v }));

  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="training plan" />;
  const canConfirm = me.data?.data.role === "TrainingManager";
  const myName = me.data?.data.name ?? "";
  const delivers = ["Facilitator", "Assessor", "Moderator"].includes(me.data?.data.role ?? "");
  const view = scope || (delivers ? "mine" : "all");
  const today = new Date().toISOString().slice(0, 10);
  const words = filter.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const attentionOf = (b: Block) => (b.warnings.some((w) => w.tone === "bad") ? "bad" : b.warnings.some((w) => w.tone === "warn") ? "warn" : "ok");
  // Soonest first, so the next intakes to deliver are at the top.
  const blocks = q.data.data
    .filter((b) => words.every((w) => `${b.ref} ${b.session ?? ""} ${b.course} ${b.facilitator} ${b.venue} ${b.notes}`.toLowerCase().includes(w)))
    .filter((b) => !filter.state || b.state === filter.state)
    .filter((b) => !filter.attention || attentionOf(b) === filter.attention)
    .filter((b) => !filter.facilitator || b.facilitator === filter.facilitator)
    .filter((b) => view === "all" || b.facilitator === myName)
    .filter((b) => filter.when !== "upcoming" || b.start > today)
    .filter((b) => filter.when !== "running" || (b.start <= today && b.end >= today))
    .filter((b) => filter.when !== "past" || b.end < today)
    .filter((b) => !filter.from || b.end >= filter.from)
    .filter((b) => !filter.to || b.start <= filter.to)
    .sort((a, b) => a.start.localeCompare(b.start));
  const filtered = Boolean(stream || Object.values(filter).some(Boolean));
  const facilitators = Array.from(new Set((all.data?.data ?? []).map((b) => b.facilitator))).sort();
  const streams = Array.from(new Map((all.data?.data ?? []).map((b) => [b.streamCode, { name: b.stream, colour: b.streamColour }])).entries());

  return (
    <>
      <Hero
        title="Plan delivery and see the clashes before a booking is confirmed."
        statement="Warnings are derived on every read: fill below half is an observation; a facilitator registration that has lapsed is a hard block; expiry inside a block is an observation. The three calendar horizons and the block editor follow in phase 3."
        stats={[
          { v: String(blocks.length), l: "Intakes", c: filtered ? "Matching the filters" : "On the plan" },
          { v: String(blocks.filter((b) => b.state === "Confirmed").length), l: "Confirmed", c: "Booked and communicated" },
          { v: String(blocks.filter((b) => b.warnings.some((w) => w.tone === "bad")).length), l: "Blocked", c: "Cannot be confirmed" },
          { v: String(blocks.filter((b) => b.fill < 50).length), l: "Below half full", c: "Follow up the quotations" },
        ]}
      />
      {/* A searchable drop-down rather than a row of buttons, so the bar stays tidy however many streams there are. */}
      {delivers ? (
        <div className="seg" role="group" aria-label="Show" style={{ alignSelf: "flex-start" }}>
          <button className={view === "mine" ? "on" : undefined} aria-pressed={view === "mine"} onClick={() => setScope("mine")}>
            My intakes <span className="seg-n">{(all.data?.data ?? []).filter((b) => b.facilitator === myName).length}</span></button>
          <button className={view === "all" ? "on" : undefined} aria-pressed={view === "all"} onClick={() => setScope("all")}>
            All intakes <span className="seg-n">{(all.data?.data ?? []).length}</span></button>
        </div>
      ) : null}
      <div className="card filter-bar">
        <div className="field">
          <label htmlFor="plan-stream">Stream</label>
          <SearchSelect id="plan-stream" value={stream} onChange={setStream} placeholder="Type to search streams…" emptyText="No stream matches"
            options={[{ value: "", label: "All streams", hint: intakes((all.data?.data ?? []).length) },
              ...streams.map(([code, st]) => ({ value: code, label: st.name,
                hint: intakes((all.data?.data ?? []).filter((b) => b.streamCode === code).length) }))
                .sort((a, b) => a.label.localeCompare(b.label))]} />
        </div>
        <div className="field"><label htmlFor="pf-when">When</label>
          <select id="pf-when" value={filter.when} onChange={(e) => setF("when", e.target.value)}>
            <option value="">Any time</option><option value="upcoming">Not started yet</option>
            <option value="running">Running now</option><option value="past">Finished</option>
          </select></div>
        <div className="field"><label htmlFor="pf-state">State</label>
          <select id="pf-state" value={filter.state} onChange={(e) => setF("state", e.target.value)}>
            <option value="">Any state</option><option>Draft</option><option>Confirmed</option><option>Cancelled</option>
          </select></div>
        <div className="field"><label htmlFor="pf-att">Status</label>
          <select id="pf-att" value={filter.attention} onChange={(e) => setF("attention", e.target.value)}>
            <option value="">Any status</option><option value="bad">Action required</option>
            <option value="warn">Needs attention</option><option value="ok">In order</option>
          </select></div>
        <div className="field"><label htmlFor="pf-fac">Facilitator</label>
          <select id="pf-fac" value={filter.facilitator} onChange={(e) => setF("facilitator", e.target.value)}>
            <option value="">Anyone</option>{facilitators.map((f) => <option key={f}>{f}</option>)}
          </select></div>
        <div className="field"><label htmlFor="pf-from">Between</label>
          <input id="pf-from" type="date" value={filter.from} onChange={(e) => setF("from", e.target.value)} /></div>
        <div className="field"><label htmlFor="pf-to">and</label>
          <input id="pf-to" type="date" value={filter.to} min={filter.from || undefined} onChange={(e) => setF("to", e.target.value)} /></div>
        <div className="field filter-search"><label htmlFor="pf-q">Search</label>
          <input id="pf-q" type="search" value={filter.q} onChange={(e) => setF("q", e.target.value)}
                 placeholder="Intake, session, course, facilitator, venue or note" /></div>
        <div className="filter-foot">
          <span className="small muted">Showing {blocks.length} of {(all.data?.data ?? []).length} intakes, soonest first</span>
          {filtered ? <button className="btn btn-sm" onClick={() => { setStream(""); setFilter({ q: "", state: "", attention: "", facilitator: "", when: "", from: "", to: "" }); }}>Clear filters</button> : null}
        </div>
      </div>
      {notice ? (
        <div className="callout ok" role="status">
          <div className="row" style={{ alignItems: "flex-start" }}>
            <p style={{ flex: 1 }}><b>Saved.</b> {notice.what}</p>
            <button className="btn btn-ghost btn-sm" onClick={() => setNotice(null)} aria-label="Dismiss"><i className="fas fa-times" aria-hidden /></button>
          </div>
          <LearnerContacts list={notice.affected} title="Tell these learners" />
        </div>
      ) : null}
      <SectionHead title="Intakes">
        {canConfirm ? <button className="btn btn-teal" onClick={() => setAdding(true)}>New intake</button> : null}
      </SectionHead>
      <Blocked refusal={confirm.refusal} />
      <Register rows={blocks} rowKey={(b) => b.ref} onRow={(b) => { setOpen(b.ref === open ? null : b.ref); setMode(""); confirm.clear(); }}
        expanded={(b) => (b.ref === open ? (
          <div className="stack-12">
            <div className="small muted">{b.facilitator} · {b.venue} · {b.mode} · {b.hours} supervised practical hours</div>
            {b.notes ? <p style={{ margin: 0 }}>{b.notes}</p> : null}
            {b.warnings.length === 0 ? <div className="callout ok"><p>No warnings on this intake.</p></div> : b.warnings.map((w) => (
              <div key={w.message} className={`callout ${w.tone}`}><h4>{warningTitle(w, b.state)}</h4><p>{w.message}</p></div>
            ))}
            {canConfirm && b.state !== "Cancelled" && !b.started && !mode ? (
              <div className="row">
                <button className="btn btn-sm" onClick={() => setMode("edit")}><i className="fas fa-pen" aria-hidden /> Edit intake</button>
                <button className="btn btn-sm btn-ghost-danger" onClick={() => setMode("cancel")}><i className="fas fa-ban" aria-hidden /> Cancel intake</button>
              </div>
            ) : null}
            {mode === "edit" ? (
              <div className="card inset-form">
                <IntakeForm refCode={b.ref} learners={b.seats} onDone={done} onCancel={() => setMode("")}
                  initial={{ courseCode: b.courseCode, facilitatorRef: b.facilitatorRef, venueId: b.venueId, newVenue: "", mode: b.mode,
                             cadence: b.cadence, start: b.start, end: b.end, capacity: String(b.capacity), hours: String(b.hours), notes: b.notes,
                             schedule: b.schedule, weekdays: b.weekdays, startsAt: b.startsAt, endsAt: b.endsAt }} />
              </div>
            ) : null}
            {mode === "cancel" ? <CancelIntake refCode={b.ref} onDone={done} onClose={() => setMode("")} /> : null}
            {b.seats ? <IntakeLearners code={b.ref} /> : null}
            {b.state === "Draft" && canConfirm ? (
              <div className="row">
                <button className="btn btn-primary" disabled={confirm.isPending} onClick={() => confirm.mutate({ ref: b.ref })}>Confirm intake</button>
                <span className="small muted">Confirming issues the booking. A lapsed registration refuses it.</span>
              </div>
            ) : null}
          </div>
        ) : null)}
        columns={[
          { key: "ref", label: "Intake", render: (b) => <><span className="mono">{b.ref}</span><div className="small muted">{b.sessionCount > 1 ? `${b.sessionCount} sessions` : b.session}</div></> },
          { key: "course", label: "Course", render: (b) => <><span style={{ display: "inline-block", width: 10, height: 10, background: b.streamColour, marginRight: 6, borderRadius: 1 }} /><b>{b.course}</b><div className="small muted">{b.venue} · {b.cadence === "AdHoc" ? "ad hoc" : `${b.cadence.toLowerCase()} intake`}</div></> },
          { key: "fac", label: "Facilitator", render: (b) => b.facilitator },
          { key: "dates", label: "Dates", render: (b) => `${b.start} to ${b.end}`, mono: true },
          { key: "fill", label: "Fill", render: (b) => `${b.seats}/${b.capacity} · ${b.fill}%`, mono: true },
          { key: "state", label: "State", render: (b) => {
            const worst = b.warnings.find((w) => w.tone === "bad") ?? b.warnings.find((w) => w.tone === "warn");
            return <div className="row" style={{ gap: 6 }}><span>{b.state}</span>{worst ? <Status tone={worst.tone} /> : <Status tone="ok" />}</div>;
          } },
        ]} />
      {adding ? (
        <Modal title="New intake" onClose={() => setAdding(false)} wide>
          <IntakeForm onDone={done} onCancel={() => setAdding(false)} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}

function IntakeLearners({ code }: { code: string }) {
  const q = useRegister<Affected[]>(`/plan/${code}/learners`);
  return <LearnerContacts list={q.data?.data ?? []} title="Registered learners" />;
}
