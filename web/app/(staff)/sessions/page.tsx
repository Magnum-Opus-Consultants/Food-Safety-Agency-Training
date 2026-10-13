"use client";

import { useState } from "react";
import { SessionPanel } from "@/components/SessionPanel";
import { AuditTrail, Hero, LoadError, Loading, Register, Stat, Status } from "@/components/ui";
import type { SessionRow } from "@/lib/types";
import { useRegister } from "@/lib/hooks";


export default function Sessions() {
  const [open, setOpen] = useState<string | null>(null);
  const [filter, setFilter] = useState({ q: "", register: "", facilitator: "", course: "", from: "", to: "" });
  const setF = (k: keyof typeof filter, v: string) => setFilter((x) => ({ ...x, [k]: v }));
  const q = useRegister<{ items: SessionRow[]; stats: Stat[]; scope: string }>("/sessions");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { items: all, stats, scope } = q.data.data;
  const words = filter.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const items = all
    .filter((x) => !filter.register || x.registerState === filter.register)
    .filter((x) => !filter.facilitator || x.facilitator === filter.facilitator)
    .filter((x) => !filter.course || x.course === filter.course)
    .filter((x) => !filter.from || x.end >= filter.from)
    .filter((x) => !filter.to || x.start <= filter.to)
    .filter((x) => words.every((w) => `${x.ref} ${x.block} ${x.course} ${x.venue} ${x.facilitator}`.toLowerCase().includes(w)));
  const filtered = Object.values(filter).some(Boolean);
  const facilitators = Array.from(new Set(all.map((x) => x.facilitator))).sort();
  const courses = Array.from(new Set(all.map((x) => x.course))).sort();
  const count = (st: string) => all.filter((x) => x.registerState === st).length;
  const outstanding = all.filter((s) => s.registerState === "Outstanding");
  return (
    <>
      <Hero
        title={outstanding.length
          ? `${outstanding.length} delivered ${outstanding.length === 1 ? "session has" : "sessions have"} no captured register.`
          : "Every delivered session has a locked register."}
        statement={`Capture the register against the scheduled session. It locks on save; a correction after capture is a new audited entry, never an edit.${scope === "own" ? " You are seeing your own sessions." : ""}`}
        stats={stats}
      />
      <div className="card filter-bar">
        <div className="field filter-search"><label htmlFor="sf-q">Search</label>
          <input id="sf-q" type="search" value={filter.q} onChange={(e) => setF("q", e.target.value)}
                 placeholder="Session, intake, course, venue or facilitator" /></div>
        <div className="field"><label htmlFor="sf-reg">Register</label>
          <select id="sf-reg" value={filter.register} onChange={(e) => setF("register", e.target.value)}>
            <option value="">Any</option>
            {["Outstanding", "Today", "In progress", "Not yet delivered", "Locked"].map((st) => <option key={st} value={st}>{st} ({count(st)})</option>)}
          </select></div>
        <div className="field"><label htmlFor="sf-course">Course</label>
          <select id="sf-course" value={filter.course} onChange={(e) => setF("course", e.target.value)}>
            <option value="">Any course</option>{courses.map((c) => <option key={c}>{c}</option>)}
          </select></div>
        <div className="field"><label htmlFor="sf-fac">Facilitator</label>
          <select id="sf-fac" value={filter.facilitator} onChange={(e) => setF("facilitator", e.target.value)}>
            <option value="">Anyone</option>{facilitators.map((f) => <option key={f}>{f}</option>)}
          </select></div>
        <div className="field"><label htmlFor="sf-from">Between</label>
          <input id="sf-from" type="date" value={filter.from} onChange={(e) => setF("from", e.target.value)} /></div>
        <div className="field"><label htmlFor="sf-to">and</label>
          <input id="sf-to" type="date" value={filter.to} min={filter.from || undefined} onChange={(e) => setF("to", e.target.value)} /></div>
        <div className="filter-foot">
          <span className="small muted">Showing {items.length} of {all.length} sessions</span>
          {filtered ? <button className="btn btn-sm" onClick={() => setFilter({ q: "", register: "", facilitator: "", course: "", from: "", to: "" })}>Clear filters</button> : null}
        </div>
      </div>
      <Register rows={items} rowKey={(s) => s.ref} empty={filtered ? "No session matches these filters." : undefined} onRow={(s) => setOpen(s.ref === open ? null : s.ref)}
        expanded={(s) => (s.ref === open ? <SessionPanel code={s.ref} /> : null)} source={q.data.meta.source as string}
        columns={[
          { key: "ref", label: "Session", render: (s) => s.ref, mono: true },
          { key: "course", label: "Course", render: (s) => <><b>{s.course}</b><div className="small muted">{s.venue}</div></> },
          { key: "fac", label: "Facilitator", render: (s) => s.facilitator },
          { key: "dates", label: "Date", render: (s) => s.day ? (
            <>{new Date(s.day + "T00:00:00").toLocaleDateString("en-ZA", { weekday: "short", day: "numeric", month: "short", year: "numeric" })}
              <div className="small muted">Session {s.sequence} of {s.of} · {s.block}{s.times ? ` · ${s.times}` : ""}</div></>
          ) : <>{s.start} to {s.end}<div className="small muted">Whole intake · {s.block}</div></>, mono: true },
          { key: "seats", label: "Learners", render: (s) => `${s.seats} / ${s.capacity}`, mono: true },
          { key: "state", label: "Register", render: (s) => <Status tone={s.tone}>{s.registerState}</Status> },
          // The action each register needs, so it is clear the row opens to do it.
          { key: "act", label: "", render: (s) => (
            <button className={`btn btn-sm${s.registerState === "Locked" || s.registerState === "Not yet delivered" ? "" : " btn-primary"}`}
                    onClick={(e) => { e.stopPropagation(); setOpen(s.ref === open ? null : s.ref); }}>
              {s.registerState === "Locked" ? "View register" : s.registerState === "Not yet delivered" ? "View learners" : "Capture register"}
            </button>
          ) },
        ]} />
      <AuditTrail />
    </>
  );
}
