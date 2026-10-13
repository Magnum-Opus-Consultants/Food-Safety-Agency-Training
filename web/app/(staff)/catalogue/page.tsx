"use client";

import { useState } from "react";
import { AuditTrail, Hero, LoadError, Loading, Register, SectionHead } from "@/components/ui";
import { useMe, useRegister } from "@/lib/hooks";
import { Modal } from "@/components/registration";
import { AddCourseForm, CourseDetailPanel } from "@/components/CourseEditor";

type Course = { code: string; title: string; service: string; stream: string; streamColour: string; days: number; mode: string;
  entryRequirement: string; gated: boolean; accredited: boolean; body: string | null; upcoming: { from: string; label: string }[] };

export default function Catalogue() {
  const q = useRegister<Course[]>("/courses");
  const me = useMe();
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState<"" | "mine" | "all">("");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="catalogue" />;
  const rows = q.data.data;
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const mine = (q.data.meta.mine as string[] | undefined) ?? [];
  // Facilitators open on the courses they deliver; the whole catalogue is one click away.
  const view = scope || (q.data.meta.focusMine ? "mine" : "all");
  const shown = rows.filter((c) => view === "all" || mine.includes(c.code)).filter((c) => {
    const hay = `${c.code} ${c.title} ${c.service} ${c.stream} ${c.mode} ${c.entryRequirement} ${c.body ?? ""}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
  const canWrite = me.data?.data.writes.includes("courses") ?? false;
  return (
    <>
      <Hero
        title={`${rows.length} courses. Each course's entry requirement drives its minimum prerequisites.`}
        statement="A requirement change applies from the next intake without learners; learners already registered keep the requirement they registered under. Every change is kept in the course's permanent trail. Click a course to open it."
        stats={[
          { v: String(rows.length), l: "Courses", c: "In the catalogue" },
          { v: String(rows.filter((c) => c.gated).length), l: "Test and Grade 10", c: "Prerequisite test required" },
          { v: String(rows.filter((c) => c.accredited).length), l: "Accredited", c: "AgriSETA or SAATCA" },
          { v: String(rows.filter((c) => c.upcoming.length).length), l: "Changes scheduled", c: "Requirement changes not yet in force" },
        ]}
      />
      {notice ? <div className="callout ok" role="status"><p><b>Saved.</b> {notice}</p></div> : null}
      <SectionHead title="Course catalogue">
        {canWrite ? <button className="btn btn-teal" onClick={() => setAdding(true)}>Add course</button> : null}
      </SectionHead>
      <div className="card week-bar">
        {q.data.meta.focusMine ? (
          <div className="seg" role="group" aria-label="Show">
            <button className={view === "mine" ? "on" : undefined} aria-pressed={view === "mine"} onClick={() => setScope("mine")}>
              Courses I deliver <span className="seg-n">{mine.length}</span></button>
            <button className={view === "all" ? "on" : undefined} aria-pressed={view === "all"} onClick={() => setScope("all")}>
              All courses <span className="seg-n">{rows.length}</span></button>
          </div>
        ) : null}
        <div className="week-search" style={{ justifyContent: "flex-start" }}>
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search courses"
                 placeholder="Search courses: title, code, service, delivery or entry requirement" />
        </div>
        <span className="small muted">{shown.length} of {rows.length} courses</span>
      </div>
      <Register rows={shown} empty={words.length ? "No course matches this search." : view === "mine" ? "You are not scheduled to deliver any course. Choose All courses to see the catalogue." : undefined} rowKey={(c) => c.code} source={q.data.meta.source as string}
        onRow={(c) => setOpen(c.code === open ? null : c.code)}
        expanded={(c) => (c.code === open ? <CourseDetailPanel code={c.code} /> : null)}
        columns={[
          { key: "code", label: "Code", render: (c) => c.code, mono: true },
          { key: "title", label: "Course", render: (c) => <><span style={{ display: "inline-block", width: 10, height: 10, background: c.streamColour, marginRight: 6, borderRadius: 1 }} /><b>{c.title}</b></> },
          { key: "svc", label: "Service supported", render: (c) => c.service },
          { key: "days", label: "Duration", render: (c) => `${c.days} ${c.days === 1 ? "day" : "days"}`, mono: true },
          { key: "mode", label: "Delivery", render: (c) => c.mode },
          { key: "req", label: "Entry requirement", render: (c) => (
            <>{c.entryRequirement}{c.upcoming.map((u) => <div key={u.from} className="small tone-warn">From {u.from}: {u.label}</div>)}</>
          ) },
        ]} />
      {adding ? (
        <Modal title="Add a course" onClose={() => setAdding(false)}>
          <AddCourseForm onDone={(code, what) => { setAdding(false); setOpen(code); setNotice(what); window.setTimeout(() => setNotice(""), 10000); }} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
