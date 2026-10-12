"use client";

import { AuditTrail, Hero, LoadError, Loading, Register } from "@/components/ui";
import { useRegister } from "@/lib/hooks";

type Course = { code: string; title: string; service: string; stream: string; streamColour: string; days: number; mode: string; entryRequirement: string; gated: boolean; accredited: boolean; body: string | null };

export default function Catalogue() {
  const q = useRegister<Course[]>("/courses");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="catalogue" />;
  const rows = q.data.data;
  return (
    <>
      <Hero
        title={`${rows.length} courses. The entry requirement drives the enrolment gate.`}
        statement="Meat examiner streams carry the entry gate: a prerequisite test of 50% or better and Grade 10 evidence. Short courses carry none."
        stats={[
          { v: String(rows.length), l: "Courses", c: "In the catalogue" },
          { v: String(rows.filter((c) => c.gated).length), l: "Gated", c: "Prerequisite and Grade 10" },
          { v: String(rows.filter((c) => c.accredited).length), l: "Accredited", c: "AgriSETA or SAATCA" },
          { v: String(new Set(rows.map((c) => c.service)).size), l: "Services", c: "FSA services supported" },
        ]}
      />
      <Register rows={rows} rowKey={(c) => c.code} source={q.data.meta.source as string}
        columns={[
          { key: "code", label: "Code", render: (c) => c.code, mono: true },
          { key: "title", label: "Course", render: (c) => <><span style={{ display: "inline-block", width: 10, height: 10, background: c.streamColour, marginRight: 6, borderRadius: 1 }} /><b>{c.title}</b></> },
          { key: "svc", label: "Service supported", render: (c) => c.service },
          { key: "days", label: "Duration", render: (c) => `${c.days} ${c.days === 1 ? "day" : "days"}`, mono: true },
          { key: "mode", label: "Delivery", render: (c) => c.mode },
          { key: "req", label: "Entry requirement", render: (c) => c.entryRequirement },
        ]} />
      <AuditTrail />
    </>
  );
}
