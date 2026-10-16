"use client";

// Course feedback: when an intake ends, each learner gets a private link to evaluate the course. This page
// shows who still has to answer (to remind them) and the scores per intake and per facilitator. Who said
// what is never shown.

import { useState } from "react";
import { AuditTrail, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useRegister } from "@/lib/hooks";

type Scores = Record<string, number | null>;
type Summary = { asked: number; answered: number; responseRate: number | null; scores: Scores; overall: number | null; recommend: number | null };
type Intake = Summary & { intake: string; course: string; facilitator: string; venue: string; ended: string; comments: string[];
  learners: { name: string; email: string; phone: string; answered: boolean; link: string }[] };
type Data = { items: Intake[]; dimensions: { key: string; label: string }[]; byFacilitator: (Summary & { name: string })[] };

const scoreTone = (v: number | null): Tone => (v === null ? "na" : v >= 4 ? "ok" : v >= 3 ? "warn" : "bad");
const score = (v: number | null) => (v === null ? "—" : `${v.toFixed(1)} / 5`);
/** A score as a coloured badge, or a plain dash when there is nothing to score yet. */
const Score = ({ v }: { v: number | null }) => (v === null ? <span className="muted">—</span> : <Status tone={scoreTone(v)}>{score(v)}</Status>);

function message(course: string, link: string) {
  return `Thank you for attending ${course} with the FSA Academy. Please tell us how it went (2 minutes): ${link}`;
}

function Learners({ i }: { i: Intake }) {
  const [copied, setCopied] = useState("");
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  const copy = (text: string, key: string) => {
    navigator.clipboard?.writeText(text).then(() => { setCopied(key); window.setTimeout(() => setCopied(""), 2500); }).catch(() => undefined);
  };
  return (
    <table className="plain-table fb-table">
      <colgroup><col /><col style={{ width: 130 }} /><col style={{ width: 330 }} /></colgroup>
      <thead><tr><th>Learner</th><th>Answered</th><th style={{ textAlign: "right" }}>Send or remind</th></tr></thead>
      <tbody>
        {i.learners.map((l) => {
          const link = `${origin}${l.link}`;
          const text = message(i.course, link);
          const wa = l.phone ? `https://wa.me/${l.phone.replace(/[^\d]/g, "")}?text=${encodeURIComponent(text)}` : "";
          const mail = l.email ? `mailto:${l.email}?subject=${encodeURIComponent(`Your feedback on ${i.course}`)}&body=${encodeURIComponent(text)}` : "";
          return (
            <tr key={l.link}>
              <td><b>{l.name}</b><div className="small muted">{[l.email, l.phone].filter(Boolean).join(" · ") || "No email or phone on record"}</div></td>
              <td>{l.answered ? <Status tone="ok">Answered</Status> : <Status tone="warn">Not yet</Status>}</td>
              <td style={{ textAlign: "right" }}>{l.answered ? <span className="small muted">—</span> : (
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  {wa ? <a className="btn btn-sm" href={wa} target="_blank" rel="noopener"><i className="fab fa-whatsapp" aria-hidden /> WhatsApp</a> : null}
                  {mail ? <a className="btn btn-sm" href={mail}><i className="fas fa-envelope" aria-hidden /> Email</a> : null}
                  <button className="btn btn-sm" onClick={() => copy(link, l.link)}><i className="fas fa-link" aria-hidden /> {copied === l.link ? "Copied" : "Copy link"}</button>
                </div>
              )}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function Feedback() {
  const q = useRegister<Data>("/feedback");
  const [open, setOpen] = useState<string | null>(null);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="course feedback" />;
  const d = q.data.data;
  const asked = d.items.reduce((n, i) => n + i.asked, 0);
  const answered = d.items.reduce((n, i) => n + i.answered, 0);
  const all = d.items.filter((i) => i.overall !== null);
  const overall = all.length ? Math.round((10 * all.reduce((n, i) => n + (i.overall ?? 0) * i.answered, 0)) / Math.max(1, answered)) / 10 : null;
  return (
    <>
      <Hero stats={[
        { v: String(asked), l: "Asked", c: "Learners on intakes that ended in the last six months" },
        { v: String(answered), l: "Answered", c: asked ? `${Math.round((100 * answered) / asked)}% response rate` : "No one asked yet" },
        { v: overall === null ? "—" : `${overall}`, l: "Average score", c: "Out of 5, across every question" },
        { v: String(d.items.reduce((n, i) => n + i.learners.filter((l) => !l.answered).length, 0)), l: "Still to answer", c: "Send or remind from the intake" },
      ]} />
      <SectionHead title="By intake" />
      <Register rows={d.items} rowKey={(i) => i.intake} source={q.data.meta.source as string} empty="No intake has ended in the last six months."
        onRow={(i) => setOpen(i.intake === open ? null : i.intake)}
        expanded={(i) => (i.intake === open ? (
          <div className="stack-12">
            {i.answered ? (
              <div className="fb-tiles">
                {d.dimensions.map((x) => (
                  <div key={x.key} className={`fb-tile tone-${scoreTone(i.scores[x.key])}`}><span>{x.label}</span><b>{i.scores[x.key]?.toFixed(1) ?? "—"}</b><small>out of 5</small></div>
                ))}
                <div className="fb-tile"><span>Would recommend</span><b>{i.recommend === null ? "—" : `${i.recommend}%`}</b><small>of {i.answered} who answered</small></div>
              </div>
            ) : (
              <p className="small muted" style={{ margin: 0 }}><i className="fas fa-hourglass-half" aria-hidden /> No answers yet — send the links below. The scores appear here as learners answer.</p>
            )}
            {i.comments.length ? (
              <section><div className="eyebrow">What learners wrote</div>
                <ul className="dash-list">{i.comments.map((c, n) => <li key={n}>&ldquo;{c}&rdquo;</li>)}</ul></section>
            ) : null}
            <Learners i={i} />
          </div>
        ) : null)}
        columns={[
          { key: "intake", label: "Intake", render: (i) => <>{i.intake}<div className="small muted">ended {i.ended}</div></>, mono: true },
          { key: "course", label: "Course", render: (i) => <><b>{i.course}</b><div className="small muted">{i.venue}</div></> },
          { key: "fac", label: "Facilitator", render: (i) => i.facilitator },
          { key: "resp", label: "Answered", render: (i) => `${i.answered} of ${i.asked}`, mono: true },
          { key: "fscore", label: "Facilitator score", render: (i) => <Score v={i.scores.facilitation} /> },
          { key: "overall", label: "Overall", render: (i) => <Score v={i.overall} /> },
        ]} />
      <SectionHead title="By facilitator" />
      <Register rows={d.byFacilitator} rowKey={(f) => f.name} empty="No feedback yet."
        columns={[
          { key: "name", label: "Facilitator", render: (f) => <b>{f.name}</b> },
          { key: "resp", label: "Answered", render: (f) => `${f.answered} of ${f.asked}`, mono: true },
          ...d.dimensions.map((x) => ({ key: x.key, label: x.label, render: (f: Summary & { name: string }) => <Score v={f.scores[x.key]} /> })),
          { key: "rec", label: "Would recommend", render: (f) => (f.recommend === null ? "—" : `${f.recommend}%`), mono: true },
        ]} />
      <AuditTrail />
    </>
  );
}
