"use client";

// The risk and escalation register. Click a risk to open it: update its rating, trigger, owner and position,
// record a review, link the complaints that show it happening, or close it with a reason. A link from the desk
// (?focus=TRK-02) opens that risk straight away.

import { useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useAction, useFocusRef, useRegister } from "@/lib/hooks";

type Risk = { ref: string; risk: string; cause: string; rating: string; trigger: string; breached: boolean; breachedAt: string | null;
  owner: string; ownerRef: string; position: string; tone: Tone; open: boolean; closedReason: string; reviewedAt: string | null; reviewNote: string;
  enquiries: { ref: string; kind: string; name: string; details: string; received: string; stage: string }[];
  history: { at: string; who: string; what: string }[] };
type Data = { items: Risk[]; canEdit: boolean; owners: { ref: string; name: string }[]; linkable: { ref: string; label: string }[] };

const RATINGS = ["Low", "Medium", "High"];

function RiskForm({ d, onDone, onCancel }: { d: Data; onDone: (m: string) => void; onCancel: () => void }) {
  const add = useAction<Record<string, string>>("POST", "/risks");
  const [f, setF] = useState({ risk: "", cause: "", rating: "", trigger: "", ownerRef: "", position: "" });
  const [tried, setTried] = useState(false);
  const p: Record<string, string> = {};
  if (!f.risk.trim()) p.risk = "Describe what could happen.";
  if (!f.cause.trim()) p.cause = "Give its cause.";
  if (!f.rating) p.rating = "Rate it.";
  if (!f.trigger.trim()) p.trigger = "Name the trigger: an event or a number.";
  if (!f.ownerRef) p.ownerRef = "Choose the owner.";
  const e = tried ? p : {};
  const err = (k: string) => (e[k] ? <span className="field-error">{e[k]}</span> : null);
  return (
    <div className="stack-12">
      <Blocked refusal={add.refusal} />
      <div className="form-grid">
        <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor="rk-risk">Risk</label>
          <input id="rk-risk" value={f.risk} className={e.risk ? "invalid" : undefined} placeholder="e.g. Placement report late to the university"
                 onChange={(x) => setF({ ...f, risk: x.target.value })} />{err("risk")}</div>
        <div className="field"><label htmlFor="rk-rating">Rating</label>
          <select id="rk-rating" value={f.rating} className={e.rating ? "invalid" : undefined} onChange={(x) => setF({ ...f, rating: x.target.value })}>
            <option value="">Choose…</option>{RATINGS.map((r) => <option key={r}>{r}</option>)}
          </select>{err("rating")}</div>
        <div className="field"><label htmlFor="rk-owner">Owner</label>
          <select id="rk-owner" value={f.ownerRef} className={e.ownerRef ? "invalid" : undefined} onChange={(x) => setF({ ...f, ownerRef: x.target.value })}>
            <option value="">Choose…</option>{d.owners.map((o) => <option key={o.ref} value={o.ref}>{o.name}</option>)}
          </select>{err("ownerRef")}</div>
        <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor="rk-cause">Cause</label>
          <input id="rk-cause" value={f.cause} className={e.cause ? "invalid" : undefined} onChange={(x) => setF({ ...f, cause: x.target.value })} />{err("cause")}</div>
        <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor="rk-trig">Escalation trigger</label>
          <input id="rk-trig" value={f.trigger} className={e.trigger ? "invalid" : undefined} placeholder="e.g. Any report unsubmitted at day 15"
                 onChange={(x) => setF({ ...f, trigger: x.target.value })} />{err("trigger")}</div>
      </div>
      <div className="row">
        <button className="btn btn-primary" disabled={add.isPending} onClick={() => {
          setTried(true);
          if (!Object.keys(p).length) add.mutate(f, { onSuccess: (r) => onDone(r.meta.audit?.what ?? "") });
        }}>{add.isPending ? "Saving…" : "Add risk"}</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

function RiskPanel({ r, d, onDone }: { r: Risk; d: Data; onDone: (m: string) => void }) {
  const save = useAction<Record<string, unknown>>("PATCH", `/risks/${r.ref}`);
  const review = useAction<{ note: string }>("POST", `/risks/${r.ref}/review`);
  const close = useAction<{ note: string }>("POST", `/risks/${r.ref}/close`);
  const link = useAction<{ enquiryRef: string }>("POST", `/risks/${r.ref}/enquiries`);
  const unlink = useAction<{ e: string }>("DELETE", (v) => `/risks/${r.ref}/enquiries/${v.e}`);
  const original = { rating: r.rating, trigger: r.trigger, ownerRef: r.ownerRef, position: r.position === "—" ? "" : r.position, breached: r.breached };
  const [f, setF] = useState(original);
  const [note, setNote] = useState("");
  const [closing, setClosing] = useState(false);
  const [reason, setReason] = useState("");
  const [pick, setPick] = useState("");
  const changed = Object.fromEntries(Object.entries(f).filter(([k, v]) => v !== original[k as keyof typeof original]));
  const can = d.canEdit && r.open;
  const say = (x: { meta: { audit?: { what?: string } } }) => onDone(x.meta.audit?.what ?? "");
  return (
    <div className="stack-20">
      <Blocked refusal={save.refusal ?? review.refusal ?? close.refusal ?? link.refusal ?? unlink.refusal} />
      {!r.open ? <div className="callout"><p><b>Closed.</b> {r.closedReason}</p></div> : null}
      <dl className="facts">
        <div><dt>Risk</dt><dd>{r.risk}</dd></div>
        <div><dt>Cause</dt><dd>{r.cause}</dd></div>
        <div><dt>Last review</dt><dd>{r.reviewedAt ? <>{r.reviewedAt} — {r.reviewNote}</> : <span className="muted">Not reviewed yet</span>}</dd></div>
      </dl>
      {can ? (
        <section className="stack-12">
          <div className="eyebrow">Update</div>
          <div className="form-grid">
            <div className="field"><label htmlFor={`rr-${r.ref}`}>Rating</label>
              <select id={`rr-${r.ref}`} value={f.rating} onChange={(x) => setF({ ...f, rating: x.target.value })}>{RATINGS.map((x) => <option key={x}>{x}</option>)}</select></div>
            <div className="field"><label htmlFor={`ro-${r.ref}`}>Owner</label>
              <select id={`ro-${r.ref}`} value={f.ownerRef} onChange={(x) => setF({ ...f, ownerRef: x.target.value })}>
                {d.owners.map((o) => <option key={o.ref} value={o.ref}>{o.name}</option>)}</select></div>
            <div className="field"><label>Trigger</label>
              <div className="seg" role="group" aria-label="Trigger">
                <button type="button" className={!f.breached ? "on" : undefined} aria-pressed={!f.breached} onClick={() => setF({ ...f, breached: false })}>Not breached</button>
                <button type="button" className={f.breached ? "on" : undefined} aria-pressed={f.breached} onClick={() => setF({ ...f, breached: true })}>Breached</button>
              </div>{r.breachedAt ? <span className="small muted">Breached since {r.breachedAt}</span> : null}</div>
            <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor={`rt-${r.ref}`}>Escalation trigger</label>
              <input id={`rt-${r.ref}`} value={f.trigger} onChange={(x) => setF({ ...f, trigger: x.target.value })} /></div>
            <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor={`rp-${r.ref}`}>Position — what is being done</label>
              <input id={`rp-${r.ref}`} value={f.position} onChange={(x) => setF({ ...f, position: x.target.value })} /></div>
          </div>
          <div className="row">
            <button className="btn btn-primary" disabled={!Object.keys(changed).length || save.isPending} onClick={() => save.mutate(changed, { onSuccess: say })}>Save changes</button>
            <button className="btn" disabled={!Object.keys(changed).length} onClick={() => setF(original)}>Undo</button>
          </div>
        </section>
      ) : null}

      <section className="stack-12">
        <div className="eyebrow">Complaints and enquiries that show it happening</div>
        {r.enquiries.length ? (
          <table className="plain-table"><tbody>{r.enquiries.map((e) => (
            <tr key={e.ref}><td style={{ width: 110 }}><a href={`/enquiries?focus=${e.ref}`} className="mono">{e.ref}</a></td>
              <td><b>{e.kind}</b> · {e.name}{e.details ? <div className="small muted">{e.details}</div> : null}</td>
              <td className="small muted">{e.received} · {e.stage}</td>
              <td style={{ textAlign: "right" }}>{can ? <button className="btn btn-sm btn-ghost-danger" onClick={() => unlink.mutate({ e: e.ref }, { onSuccess: say })}>Unlink</button> : null}</td></tr>
          ))}</tbody></table>
        ) : <p className="small muted" style={{ margin: 0 }}>None linked.</p>}
        {can && d.linkable.length ? (
          <div className="row">
            <select aria-label="Link a complaint" className="bar-select" value={pick} onChange={(x) => setPick(x.target.value)}>
              <option value="">Link a complaint or opportunity…</option>
              {d.linkable.filter((l) => !r.enquiries.some((e) => e.ref === l.ref)).map((l) => <option key={l.ref} value={l.ref}>{l.label}</option>)}
            </select>
            <button className="btn btn-sm" disabled={!pick || link.isPending} onClick={() => link.mutate({ enquiryRef: pick }, { onSuccess: (x) => { setPick(""); say(x); } })}>Link</button>
          </div>
        ) : null}
      </section>

      {can ? (
        <section className="stack-12">
          <div className="eyebrow">Review</div>
          <div className="field"><label htmlFor={`rv-${r.ref}`}>Review note</label>
            <textarea id={`rv-${r.ref}`} rows={2} value={note} placeholder="Is the risk still live? What changed, and what is being done?"
                      onChange={(x) => setNote(x.target.value)} /></div>
          <div className="row">
            <button className="btn btn-primary" disabled={!note.trim() || review.isPending} onClick={() => review.mutate({ note }, { onSuccess: (x) => { setNote(""); say(x); } })}>Record review</button>
            <span className="spacer" />
            {!closing ? <button className="btn btn-ghost-danger" onClick={() => setClosing(true)}>Close risk</button> : null}
          </div>
          {closing ? (
            <div className="card inset-form stack-12">
              <div className="field"><label htmlFor={`rc-${r.ref}`}>Why is {r.ref} being closed?</label>
                <input id={`rc-${r.ref}`} value={reason} placeholder="e.g. Second facilitator appointed in KZN" onChange={(x) => setReason(x.target.value)} /></div>
              <div className="row">
                <button className="btn btn-danger" disabled={!reason.trim() || close.isPending} onClick={() => close.mutate({ note: reason }, { onSuccess: say })}>Close risk</button>
                <button className="btn" onClick={() => setClosing(false)}>Keep it open</button>
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {r.history.length ? (
        <section className="stack-12">
          <div className="eyebrow">History</div>
          <ul className="fac-history">{r.history.map((h, i) => (
            <li key={i} className={i === 0 ? "now" : ""}><div className="small">{h.what}</div><div className="small muted">{h.who}, {h.at}</div></li>
          ))}</ul>
        </section>
      ) : null}
    </div>
  );
}

export default function RiskRegister() {
  const q = useRegister<Data>("/risks");
  const focus = useFocusRef();
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [done, setDone] = useState("");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="risk register" />;
  const d = q.data.data;
  const live = d.items.filter((r) => r.open);
  const shown = open ?? focus;
  return (
    <>
      <Hero stats={[
        { v: String(live.length), l: "Risks", c: "Open on the register" },
        { v: String(live.filter((r) => r.rating === "High").length), l: "High", c: "Escalated by rating" },
        { v: String(live.filter((r) => r.breached).length), l: "Triggers breached", c: "Escalated by trigger" },
        { v: String(live.filter((r) => r.tone === "ok").length), l: "Within appetite", c: "No escalation" },
      ]} />
      {done ? <div className="callout ok" role="status"><p><b>Saved.</b> {done}</p></div> : null}
      <SectionHead title="Risks">
        {d.canEdit && !adding ? <button className="btn btn-teal" onClick={() => { setAdding(true); setDone(""); }}>Add risk</button> : null}
      </SectionHead>
      {adding ? <div className="card inset-form"><RiskForm d={d} onCancel={() => setAdding(false)} onDone={(m) => { setAdding(false); setDone(m); }} /></div> : null}
      <Register rows={d.items} rowKey={(r) => r.ref} source={q.data.meta.source as string} empty="No risks recorded."
        onRow={(r) => setOpen(r.ref === shown ? "" : r.ref)}
        expanded={(r) => (r.ref === shown ? <RiskPanel key={JSON.stringify(r)} r={r} d={d} onDone={setDone} /> : null)}
        columns={[
          { key: "ref", label: "Reference", render: (r) => r.ref, mono: true },
          { key: "risk", label: "Risk", render: (r) => <><b>{r.risk}</b>{r.enquiries.length ? <div className="small muted">{r.enquiries.length} linked {r.enquiries.length === 1 ? "complaint" : "complaints"}</div> : null}</> },
          { key: "rating", label: "Rating", render: (r) => r.rating },
          { key: "trigger", label: "Escalation trigger", render: (r) => <>{r.trigger}{r.breached ? <div><Status tone="bad">Breached</Status></div> : null}</> },
          { key: "owner", label: "Owner", render: (r) => r.owner },
          { key: "pos", label: "Position", render: (r) => r.open ? <Status tone={r.tone}>{r.position}</Status> : <Status tone="na">Closed</Status> },
        ]} />
      <AuditTrail />
    </>
  );
}
