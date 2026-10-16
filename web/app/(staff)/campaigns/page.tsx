"use client";

// Marketing campaigns and the feedback loop to FSA: each campaign's channel, dates, courses and cost; what it
// brought (read from the enquiries that name it); and marketing's evaluation and recommendations.

import { useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useAction, useRegister } from "@/lib/hooks";

type Results = { enquiries: number; responded: number; quoted: number; registered: number; lost: number; learners: number;
  accepted: string; conversion: number | null; costPerEnquiry: string | null; costPerLearner: string | null; returnOnCost: number | null;
  byCourse: { course: string; enquiries: number }[]; state: string; tone: Tone; position: string };
type Campaign = { ref: string; name: string; channel: string; starts: string; ends: string; courses: { code: string; title: string }[];
  cost: string; costRand: number; objective: string; recommendations: string; results: Results };
type Data = { items: Campaign[]; channels: string[]; canEdit: boolean; courses: { code: string; title: string }[] };

function CampaignForm({ data, onDone, onCancel }: { data: Data; onDone: (m: string) => void; onCancel: () => void }) {
  const add = useAction<Record<string, unknown>>("POST", "/campaigns");
  const [f, setF] = useState({ name: "", channel: "", starts: "", ends: "", cost: "", objective: "", courses: [] as string[] });
  const [tried, setTried] = useState(false);
  const p: Record<string, string> = {};
  if (!f.name.trim()) p.name = "Name the campaign.";
  if (!f.channel) p.channel = "Choose the channel.";
  if (!f.starts || !f.ends) p.dates = "Give the dates it runs.";
  else if (f.ends < f.starts) p.dates = "The end is before the start.";
  if (f.cost && Number.isNaN(Number(f.cost.replace(/[\s,]/g, "")))) p.cost = "Give the cost in rand, e.g. 5000.";
  const e = tried ? p : {};
  const toggle = (code: string) => setF({ ...f, courses: f.courses.includes(code) ? f.courses.filter((c) => c !== code) : [...f.courses, code] });
  return (
    <div className="stack-12">
      <Blocked refusal={add.refusal} />
      <div className="form-grid">
        <div className="field" style={{ gridColumn: "span 2" }}><label htmlFor="cp-name">Campaign</label>
          <input id="cp-name" value={f.name} className={e.name ? "invalid" : undefined} placeholder="e.g. February meat examiner intake drive"
                 onChange={(x) => setF({ ...f, name: x.target.value })} />{e.name ? <span className="field-error">{e.name}</span> : null}</div>
        <div className="field"><label htmlFor="cp-ch">Channel</label>
          <select id="cp-ch" value={f.channel} className={e.channel ? "invalid" : undefined} onChange={(x) => setF({ ...f, channel: x.target.value })}>
            <option value="">Choose…</option>{data.channels.map((c) => <option key={c}>{c}</option>)}
          </select>{e.channel ? <span className="field-error">{e.channel}</span> : null}</div>
        <div className="field"><label htmlFor="cp-s">Starts</label>
          <input id="cp-s" type="date" value={f.starts} className={e.dates ? "invalid" : undefined} onChange={(x) => setF({ ...f, starts: x.target.value })} /></div>
        <div className="field"><label htmlFor="cp-e">Ends</label>
          <input id="cp-e" type="date" value={f.ends} min={f.starts || undefined} className={e.dates ? "invalid" : undefined} onChange={(x) => setF({ ...f, ends: x.target.value })} />
          {e.dates ? <span className="field-error">{e.dates}</span> : null}</div>
        <div className="field"><label htmlFor="cp-c">Cost (R)</label>
          <input id="cp-c" inputMode="decimal" value={f.cost} placeholder="0" className={e.cost ? "invalid" : undefined} onChange={(x) => setF({ ...f, cost: x.target.value })} />
          {e.cost ? <span className="field-error">{e.cost}</span> : null}</div>
      </div>
      <div className="field"><label>Courses it promotes <span className="optional">(optional)</span></label>
        <div className="topic-chips">{data.courses.map((c) => (
          <button key={c.code} type="button" className={`topic-chip${f.courses.includes(c.code) ? " on" : ""}`} aria-pressed={f.courses.includes(c.code)}
                  onClick={() => toggle(c.code)}>{c.title}</button>
        ))}</div></div>
      <div className="field"><label htmlFor="cp-o">Objective <span className="optional">(optional)</span></label>
        <textarea id="cp-o" rows={2} value={f.objective} placeholder="e.g. Fill the February PME 1 intake; reach abattoirs in KZN"
                  onChange={(x) => setF({ ...f, objective: x.target.value })} /></div>
      <div className="row">
        <button className="btn btn-primary" disabled={add.isPending} onClick={() => {
          setTried(true);
          if (!Object.keys(p).length) add.mutate({ ...f, cost: f.cost || "0" }, { onSuccess: (r) => onDone(r.meta.audit?.what ?? "") });
        }}>{add.isPending ? "Saving…" : "Record campaign"}</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
        <span className="small muted">Enquiries then name it under &ldquo;How did they hear about us?&rdquo;.</span>
      </div>
    </div>
  );
}

function Report({ c, canEdit, onDone }: { c: Campaign; canEdit: boolean; onDone: (m: string) => void }) {
  const save = useAction<{ recommendations: string }>("PATCH", `/campaigns/${c.ref}`);
  const [rec, setRec] = useState(c.recommendations);
  const r = c.results;
  return (
    <div className="stack-12">
      <dl className="facts">
        <div><dt>Ran</dt><dd>{c.starts} to {c.ends} · {c.channel} · cost {c.cost}</dd></div>
        <div><dt>Courses</dt><dd>{c.courses.map((x) => x.title).join(", ") || "Not tied to a course"}</dd></div>
        {c.objective ? <div><dt>Objective</dt><dd>{c.objective}</dd></div> : null}
      </dl>
      <div className="dash-kpis">
        <div><span className="qd-label">Enquiries it brought</span><b>{r.enquiries}</b>
          <span className="small muted">{r.responded} answered · {r.quoted} quoted · {r.lost} closed without take-up</span></div>
        <div><span className="qd-label">Registered</span><b>{r.registered} enquiries · {r.learners} learners</b>
          <span className="small muted">{r.conversion === null ? "—" : `${r.conversion}%`} of enquiries registered</span></div>
        <div><span className="qd-label">Value accepted</span><b>{r.accepted}</b>
          <span className="small muted">{r.returnOnCost === null ? "No cost recorded" : `${r.returnOnCost}× the cost`}</span></div>
        <div><span className="qd-label">Cost per result</span><b>{r.costPerLearner ?? "—"} per learner</b>
          <span className="small muted">{r.costPerEnquiry ?? "—"} per enquiry</span></div>
      </div>
      {r.byCourse.length ? <p className="small muted" style={{ margin: 0 }}>Enquiries by course: {r.byCourse.map((x) => `${x.course} (${x.enquiries})`).join(", ")}</p> : null}
      <div className="field"><label htmlFor={`rec-${c.ref}`}>Evaluation and recommendations for FSA</label>
        <textarea id={`rec-${c.ref}`} rows={4} value={rec} readOnly={!canEdit} onChange={(x) => setRec(x.target.value)}
                  placeholder="How the campaign did against its objective, what worked, and what to do next (run again, change channel, timing, budget)." /></div>
      <Blocked refusal={save.refusal} />
      {canEdit ? (
        <div className="row">
          <button className="btn btn-primary" disabled={save.isPending || rec === c.recommendations}
                  onClick={() => save.mutate({ recommendations: rec }, { onSuccess: (x) => onDone(x.meta.audit?.what ?? "") })}>Save evaluation</button>
          <button className="btn" onClick={() => window.print()}><i className="fas fa-print" aria-hidden /> Print for FSA</button>
        </div>
      ) : null}
    </div>
  );
}

export default function Campaigns() {
  const q = useRegister<Data>("/campaigns");
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [done, setDone] = useState("");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="campaigns" />;
  const d = q.data.data;
  const ended = d.items.filter((c) => c.results.state === "Ended");
  return (
    <>
      <Hero stats={[
        { v: String(d.items.filter((c) => c.results.state === "Running").length), l: "Running", c: "Campaigns live now" },
        { v: String(d.items.reduce((n, c) => n + c.results.enquiries, 0)), l: "Enquiries brought", c: "Across all campaigns" },
        { v: String(d.items.reduce((n, c) => n + c.results.learners, 0)), l: "Learners registered", c: "From campaign enquiries" },
        { v: String(ended.filter((c) => !c.recommendations).length), l: "Evaluation needed", c: "Ended, no recommendations for FSA yet" },
      ]} />
      {done ? <div className="callout ok" role="status"><p><b>Saved.</b> {done}</p></div> : null}
      <SectionHead title="Campaigns">
        {d.canEdit && !adding ? <button className="btn btn-teal" onClick={() => { setAdding(true); setDone(""); }}>Record a campaign</button> : null}
      </SectionHead>
      {adding ? <div className="card inset-form"><CampaignForm data={d} onCancel={() => setAdding(false)} onDone={(m) => { setAdding(false); setDone(m); }} /></div> : null}
      <Register rows={d.items} rowKey={(c) => c.ref} source={q.data.meta.source as string} empty="No campaigns recorded yet."
        onRow={(c) => setOpen(c.ref === open ? null : c.ref)}
        expanded={(c) => (c.ref === open ? <Report key={c.recommendations} c={c} canEdit={d.canEdit} onDone={setDone} /> : null)}
        columns={[
          { key: "ref", label: "Campaign", render: (c) => <><b>{c.name}</b><div className="small muted mono">{c.ref}</div></> },
          { key: "ch", label: "Channel", render: (c) => c.channel },
          { key: "dates", label: "Ran", render: (c) => <>{c.starts}<div className="small muted">to {c.ends}</div></>, mono: true },
          { key: "cost", label: "Cost", render: (c) => c.cost, mono: true },
          { key: "enq", label: "Enquiries", render: (c) => String(c.results.enquiries), mono: true },
          { key: "lrn", label: "Learners", render: (c) => String(c.results.learners), mono: true },
          { key: "cpl", label: "Per learner", render: (c) => c.results.costPerLearner ?? "—", mono: true },
          { key: "pos", label: "Position", render: (c) => <Status tone={c.results.tone}>{c.results.position}</Status> },
        ]} />
      <AuditTrail />
    </>
  );
}
