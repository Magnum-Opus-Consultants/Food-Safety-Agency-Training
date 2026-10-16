"use client";

// The management dashboard: throughput, which courses succeed, the seasons of demand, where interest comes
// from (marketing), and how well the department keeps up. Every figure is read from the registers.

import { useState } from "react";
import { AuditTrail, Hero, LoadError, Loading, SectionHead, Stat, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useRegister } from "@/lib/hooks";

type Series = { key: string; label: string; values: number[] };
type Funnel = { enquiries: number; responded: number; quoted: number; registered: number; lost: number };
type Group = Funnel & { name: string; conversion: number | null };
type CourseRow = { course: string; enquiries: number; registered: number; assessed: number; competent: number; nyc: number; certified: number; passRate: number | null };
type CampaignRow = { ref: string; name: string; channel: string; starts: string; ends: string; cost: string; enquiries: number; registered: number;
  learners: number; accepted: string; conversion: number | null; costPerLearner: string | null; returnOnCost: number | null; tone: Tone; position: string };
type Fac = { name: string; position: string; tone: Tone; items: { label: string; tone: Tone; note: string }[] };
type Board = {
  period: { from: string; to: string; months: number }; course: string; courses_list: { code: string; title: string }[];
  totals: Stat[];
  throughput: { months: string[]; series: Series[]; funnel: { label: string; v: number }[] };
  courses: CourseRow[];
  seasons: { months: string[]; enquiries: number[]; registered: number[]; peaks: string[]; years: number[] };
  marketing: { funnel: Funnel; byCourse: Group[]; byChannel: Group[]; byTopic: Group[]; byWho: Group[]; bySource: Group[];
    unmet: { course: string; enquiries: number }[]; campaigns: CampaignRow[] };
  effectiveness: {
    enquiries: { answered: number; onTime: number | null; median: number | null; waitingLate: number; standard: number;
      byHandler: { name: string; answered: number; onTime: number | null; median: number }[] };
    moderation: { moderated: number; median: number | null; awaiting: number };
    certificates: { issued: number; onTime: number | null; median: number | null; standard: number };
    facilitators: Fac[];
    feedback: { asked: number; answered: number; responseRate: number | null; overall: number | null; recommend: number | null;
      scores: Record<string, number | null>; dimensions: { key: string; label: string }[];
      byFacilitator: { name: string; answered: number; scores: Record<string, number | null>; recommend: number | null }[] };
  };
};

const PERIODS = [3, 6, 12, 24];
const COLORS: Record<string, string> = { enquiries: "var(--aps-teal)", registered: "#0F5E6E", assessed: "#C58A1B", certified: "var(--ok)" };
const pct = (v: number | null) => (v === null ? "—" : `${v}%`);
const toneOf = (v: number | null, good = 80, fair = 60): Tone => (v === null ? "na" : v >= good ? "ok" : v >= fair ? "warn" : "bad");

/** Bars side by side per month, one colour per series. */
function MonthBars({ months, series }: { months: string[]; series: Series[] }) {
  const max = Math.max(1, ...series.flatMap((s) => s.values));
  return (
    <div className="dash-chart">
      <div className="dash-legend">{series.map((s) => <span key={s.key}><i style={{ background: COLORS[s.key] }} /> {s.label}</span>)}</div>
      <div className="dash-bars" style={{ gridTemplateColumns: `repeat(${months.length}, 1fr)` }}>
        {months.map((m, i) => (
          <div key={m} className="dash-col">
            <div className="dash-stack">
              {series.map((s) => (
                <div key={s.key} className="dash-bar" title={`${s.label}, ${m}: ${s.values[i]}`}
                     style={{ height: `${(100 * s.values[i]) / max}%`, background: COLORS[s.key] }}>
                  {s.values[i] ? <span>{s.values[i]}</span> : null}
                </div>
              ))}
            </div>
            <div className="dash-x">{m}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

/** A horizontal funnel: each step as a share of the first. */
function FunnelBars({ steps }: { steps: { label: string; v: number }[] }) {
  const top = Math.max(1, steps[0]?.v ?? 1);
  return (
    <div className="dash-funnel">
      {steps.map((s) => (
        <div key={s.label} className="dash-frow">
          <span className="dash-flabel">{s.label}</span>
          <div className="dash-ftrack"><div className="dash-fbar" style={{ width: `${(100 * s.v) / top}%` }} /></div>
          <b className="mono">{s.v}</b>
        </div>
      ))}
    </div>
  );
}

/** One breakdown at a time: each row a bar of enquiries, the registered share darker, and the conversion. */
const BREAKDOWNS: [keyof Board["marketing"], string][] = [
  ["bySource", "How they heard about us"], ["byCourse", "Course"], ["byChannel", "Channel"], ["byTopic", "Topic asked about"], ["byWho", "Who it is for"],
];

function Breakdown({ m }: { m: Board["marketing"] }) {
  const [by, setBy] = useState<keyof Board["marketing"]>("bySource");
  const rows = m[by] as Group[];
  const max = Math.max(1, ...rows.map((r) => r.enquiries));
  return (
    <section className="stack-12">
      <div className="dash-head">
        <div className="eyebrow">Enquiries broken down by</div>
        <div className="seg" role="group" aria-label="Break down by">
          {BREAKDOWNS.map(([k, l]) => <button key={k} className={by === k ? "on" : undefined} aria-pressed={by === k} onClick={() => setBy(k)}>{l}</button>)}
        </div>
      </div>
      {rows.length ? (
        <div className="dash-rows">
          {rows.map((r) => (
            <div key={r.name} className="dash-row">
              <span className="dash-name" title={r.name}>{r.name}</span>
              <div className="dash-track" title={`${r.enquiries} enquiries, ${r.registered} registered`}>
                <div className="dash-fill" style={{ width: `${(100 * r.enquiries) / max}%` }}>
                  <div className="dash-fill-in" style={{ width: r.enquiries ? `${(100 * r.registered) / r.enquiries}%` : 0 }} />
                </div>
              </div>
              <span className="dash-num"><b>{r.enquiries}</b> {r.enquiries === 1 ? "enquiry" : "enquiries"} · {r.registered} registered</span>
              <Status tone={toneOf(r.conversion, 50, 25)}>{pct(r.conversion)}</Status>
            </div>
          ))}
        </div>
      ) : <p className="small muted" style={{ margin: 0 }}>No enquiries in this period.</p>}
      <div className="dash-legend"><span><i style={{ background: "var(--aps-teal-50)", border: "1px solid var(--aps-teal)" }} /> Enquiries</span>
        <span><i style={{ background: "var(--aps-teal)" }} /> Of which registered</span><span>% = enquiries that became a registration</span></div>
    </section>
  );
}

export default function ManagementDashboard() {
  const [months, setMonths] = useState(12);
  const [course, setCourse] = useState("");
  const q = useRegister<Board>(`/dashboard?months=${months}${course ? `&course=${course}` : ""}`);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="dashboard" />;
  const d = q.data.data;
  const s = d.seasons;
  const seasonMax = Math.max(1, ...s.enquiries.map((v, i) => Math.max(v, s.registered[i])));
  const e = d.effectiveness;
  const m = d.marketing;
  return (
    <>
      <Hero stats={d.totals} />
      <div className="card week-bar">
        <div className="seg" role="group" aria-label="Period">
          {PERIODS.map((p) => <button key={p} className={months === p ? "on" : undefined} aria-pressed={months === p} onClick={() => setMonths(p)}>{p} months</button>)}
        </div>
        <select aria-label="Course" className="bar-select" value={course} onChange={(x) => setCourse(x.target.value)}>
          <option value="">All courses</option>{d.courses_list.map((c) => <option key={c.code} value={c.code}>{c.title}</option>)}
        </select>
        <span className="small muted">{d.period.from} to {d.period.to}</span>
      </div>

      <SectionHead title="Throughput" />
      <div className="card dash-card dash-two">
        <section className="stack-12"><div className="eyebrow">Month by month</div>
          <MonthBars months={d.throughput.months} series={d.throughput.series} /></section>
        <section className="stack-12"><div className="eyebrow">From registration to certificate</div>
          <FunnelBars steps={d.throughput.funnel} /></section>
      </div>

      <SectionHead title="Courses — what is taken and what succeeds" />
      <div className="card dash-card">
        <div className="dash-scroll">
          <table className="plain-table">
            <thead><tr><th>Course</th><th className="num">Enquiries</th><th className="num">Registered</th><th className="num">Assessed</th>
              <th className="num">Competent</th><th className="num">Not yet</th><th>Pass rate</th><th className="num">Certified</th></tr></thead>
            <tbody>
              {d.courses.map((c) => (
                <tr key={c.course}><td><b>{c.course}</b></td><td className="num">{c.enquiries}</td><td className="num">{c.registered}</td>
                  <td className="num">{c.assessed}</td><td className="num">{c.competent}</td><td className="num">{c.nyc}</td>
                  <td><Status tone={toneOf(c.passRate)}>{pct(c.passRate)}</Status></td><td className="num">{c.certified}</td></tr>
              ))}
              {!d.courses.length ? <tr><td colSpan={8} className="muted">Nothing delivered in this period.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </div>

      <SectionHead title="Seasons — when demand comes" />
      <div className="card dash-card stack-12">
        <p className="small" style={{ margin: 0 }}>
          {s.peaks.length ? <>Busiest months: <b>{s.peaks.join(", ")}</b>. Plan intakes and campaigns ahead of them. </> : null}
          <span className="muted">All enquiries and registrations on record{s.years.length ? ` (${s.years.join(", ")})` : ""}, by calendar month.</span>
        </p>
        <div className="dash-bars" style={{ gridTemplateColumns: "repeat(12, 1fr)" }}>
          {s.months.map((mo, i) => (
            <div key={mo} className={`dash-col${s.peaks.includes(mo) ? " peak" : ""}`}>
              <div className="dash-stack">
                <div className="dash-bar" style={{ height: `${(100 * s.enquiries[i]) / seasonMax}%`, background: COLORS.enquiries }} title={`Enquiries in ${mo}: ${s.enquiries[i]}`}>
                  {s.enquiries[i] ? <span>{s.enquiries[i]}</span> : null}</div>
                <div className="dash-bar" style={{ height: `${(100 * s.registered[i]) / seasonMax}%`, background: COLORS.registered }} title={`Registered in ${mo}: ${s.registered[i]}`}>
                  {s.registered[i] ? <span>{s.registered[i]}</span> : null}</div>
              </div>
              <div className="dash-x">{mo}</div>
            </div>
          ))}
        </div>
        <div className="dash-legend"><span><i style={{ background: COLORS.enquiries }} /> Enquiries</span><span><i style={{ background: COLORS.registered }} /> Learners registered</span></div>
      </div>

      <SectionHead title="Marketing — where interest comes from" />
      <div className="card dash-card stack-20">
        <div className="dash-two">
          <section className="stack-12"><div className="eyebrow">Enquiries this period</div>
            <FunnelBars steps={[{ label: "Enquiries", v: m.funnel.enquiries }, { label: "Responded", v: m.funnel.responded },
              { label: "Quoted", v: m.funnel.quoted }, { label: "Registered", v: m.funnel.registered }, { label: "No take-up", v: m.funnel.lost }]} /></section>
          <section className="stack-12"><div className="eyebrow">Asked for, but no intake planned · last 90 days</div>
            {m.unmet.length ? (
              <div className="dash-rows">{m.unmet.map((u) => (
                <div key={u.course} className="dash-row dash-row-2"><span className="dash-name">{u.course}</span>
                  <span className="dash-num"><b>{u.enquiries}</b> {u.enquiries === 1 ? "enquiry" : "enquiries"}</span></div>
              ))}</div>
            ) : <p className="small muted" style={{ margin: 0 }}>Every course asked about has an intake coming up.</p>}</section>
        </div>
        <hr className="dash-rule" />
        <Breakdown m={m} />
        <hr className="dash-rule" />
        <section className="stack-12">
          <div className="dash-head"><div className="eyebrow">Campaigns in this period</div><a className="small" href="/campaigns">Campaigns page →</a></div>
          {m.campaigns.length ? (
            <div className="dash-scroll">
              <table className="plain-table">
                <thead><tr><th>Campaign</th><th className="num">Enquiries</th><th className="num">Learners</th><th className="num">Cost per learner</th><th>Position</th></tr></thead>
                <tbody>{m.campaigns.map((c) => (
                  <tr key={c.ref}><td><b>{c.name}</b><div className="small muted">{c.channel} · {c.starts} to {c.ends} · {c.cost}</div></td>
                    <td className="num">{c.enquiries}</td><td className="num">{c.learners}</td><td className="num">{c.costPerLearner ?? "—"}</td>
                    <td><Status tone={c.tone}>{c.position}</Status></td></tr>
                ))}</tbody>
              </table>
            </div>
          ) : <p className="small muted" style={{ margin: 0 }}>No campaigns ran in this period.</p>}
        </section>
      </div>

      <SectionHead title="Internal effectiveness — how well we keep up" />
      <div className="card dash-card stack-20">
        <div className="dash-kpis">
          <div className="dash-kpi"><span className="qd-label">Enquiries answered within {e.enquiries.standard} working days</span>
            <span className="dash-big">{pct(e.enquiries.onTime)}</span>
            <span className="small muted">{e.enquiries.answered} answered · {e.enquiries.waitingLate} waiting past the standard</span></div>
          <div className="dash-kpi"><span className="qd-label">Results moderated</span>
            <span className="dash-big">{e.moderation.moderated}</span>
            <span className="small muted">median {e.moderation.median ?? "—"} working days · {e.moderation.awaiting} awaiting</span></div>
          <div className="dash-kpi"><span className="qd-label">Certificates within {e.certificates.standard} working days</span>
            <span className="dash-big">{pct(e.certificates.onTime)}</span>
            <span className="small muted">{e.certificates.issued} issued · median {e.certificates.median ?? "—"} days</span></div>
          <div className="dash-kpi"><span className="qd-label">Learner feedback</span>
            <span className="dash-big">{e.feedback.overall === null ? "—" : `${e.feedback.overall}/5`}</span>
            <span className="small muted">{e.feedback.answered} of {e.feedback.asked} answered{e.feedback.recommend !== null ? ` · ${e.feedback.recommend}% recommend` : ""}</span></div>
        </div>
        <div className="dash-two">
          <section className="stack-12"><div className="eyebrow">Enquiry response by handler</div>
            <div className="dash-scroll"><table className="plain-table">
              <thead><tr><th>Handler</th><th className="num">Answered</th><th>On time</th><th className="num">Median days</th></tr></thead>
              <tbody>{e.enquiries.byHandler.map((h) => (
                <tr key={h.name}><td>{h.name}</td><td className="num">{h.answered}</td><td><Status tone={toneOf(h.onTime)}>{pct(h.onTime)}</Status></td><td className="num">{h.median}</td></tr>
              ))}</tbody>
            </table></div></section>
          <section className="stack-12"><div className="eyebrow">Learners&apos; rating of each facilitator (out of 5)</div>
            <div className="dash-scroll"><table className="plain-table">
              <thead><tr><th>Facilitator</th><th className="num">Answered</th><th className="num">Facilitator</th><th className="num">Content</th><th className="num">Recommend</th></tr></thead>
              <tbody>
                {e.feedback.byFacilitator.map((f) => (
                  <tr key={f.name}><td>{f.name}</td><td className="num">{f.answered}</td>
                    <td className="num"><Status tone={f.scores.facilitation === null ? "na" : f.scores.facilitation >= 4 ? "ok" : f.scores.facilitation >= 3 ? "warn" : "bad"}>
                      {f.scores.facilitation ?? "—"}</Status></td>
                    <td className="num">{f.scores.content ?? "—"}</td><td className="num">{f.recommend === null ? "—" : `${f.recommend}%`}</td></tr>
                ))}
                {!e.feedback.byFacilitator.length ? <tr><td colSpan={5} className="muted">No feedback for intakes in this period.</td></tr> : null}
              </tbody>
            </table></div></section>
        </div>
        <section className="stack-12"><div className="eyebrow">Facilitators keeping up · registers, results, moderation and feedback</div>
          <div className="dash-scroll"><table className="plain-table">
            <tbody>{e.facilitators.map((f) => (
              <tr key={f.name}><td style={{ width: 200 }}><b>{f.name}</b></td>
                <td className="small">{f.items.filter((i) => i.tone !== "ok").map((i) => <div key={i.label}><b>{i.label}:</b> {i.note}</div>)}
                  {!f.items.some((i) => i.tone !== "ok") ? <span className="muted">Everything on time.</span> : null}</td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}><Status tone={f.tone}>{f.position}</Status></td></tr>
            ))}</tbody>
          </table></div></section>
      </div>
      <AuditTrail />
    </>
  );
}
