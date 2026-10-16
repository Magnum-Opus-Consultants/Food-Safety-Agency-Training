"use client";

import Link from "next/link";
import { AuditTrail, Hero, LoadError, Loading, SectionHead, Stat } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useRegister } from "@/lib/hooks";

type Home = {
  hero: { statement: string; stats: Stat[] };
  attention: { title: string; n: number; tone: Tone; route: string; detail: string }[];
  week: { date: string; course: string; detail: string }[];
};

export default function TrainingHome() {
  const q = useRegister<Home>("/training/home");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="training home" />;
  const { hero, week } = q.data.data;
  // Only what needs doing: a row with nothing outstanding is not shown.
  const attention = q.data.data.attention.filter((a) => a.n > 0);
  return (
    <>
      <Hero title="" stats={hero.stats} />
      <div className="two-col">
        <section className="list">
          <SectionHead title="Needs attention" />
          {attention.length === 0 ? <p className="muted">Nothing needs your attention right now.</p> : attention.map((a) => (
            <Link key={a.title} href={a.route} className={`item ${a.n ? a.tone : "ok"}`}>
              <span className="item-title">{a.title}</span>
              <span className="item-n">{a.n}</span>
              <span className="item-detail">{a.detail}</span>
            </Link>
          ))}
        </section>
        <section className="list">
          <SectionHead title="This week"><Link href="/plan" className="small">Open training plan &amp; schedule</Link></SectionHead>
          {week.length === 0 ? <p className="muted">Nothing is scheduled this week.</p> : week.map((w) => (
            <div key={w.date + w.course} className="item info">
              <span className="item-title">{w.course}</span>
              <span className="mono small muted">{w.date}</span>
              <span className="item-detail muted">{w.detail}</span>
            </div>
          ))}
        </section>
      </div>
      <AuditTrail />
    </>
  );
}
