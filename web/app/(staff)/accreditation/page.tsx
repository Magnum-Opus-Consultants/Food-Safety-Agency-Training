"use client";

import { AuditTrail, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useRegister } from "@/lib/hooks";

type Held = { ref: string; body: string; scope: string; expires: string; tone: Tone; position: string };
type Project = { ref: string; body: string; scope: string; owner: string; target: string; step: number; steps: string[] };

export default function Accreditation() {
  const q = useRegister<{ held: Held[]; projects: Project[] }>("/accreditations");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { held, projects } = q.data.data;
  return (
    <>
      <Hero
        title="Bodies held, and new scope run as project plans."
        statement="Accreditation held with AgriSETA and SAATCA, plus each new scope run through six steps with a due date per step."
        stats={[
          { v: String(held.length), l: "Held", c: "Accreditations in force" },
          { v: String(held.filter((h) => h.tone === "bad").length), l: "Renewals due", c: "Inside ninety days" },
          { v: String(projects.length), l: "Projects", c: "New scope in progress" },
          { v: String(projects.filter((p) => p.step >= 3).length), l: "Submitted", c: "With the body" },
        ]}
      />
      <Register rows={held} rowKey={(h) => h.ref}
        columns={[
          { key: "ref", label: "Reference", render: (h) => h.ref, mono: true },
          { key: "body", label: "Body", render: (h) => <b>{h.body}</b> },
          { key: "scope", label: "Scope", render: (h) => h.scope },
          { key: "exp", label: "Expires", render: (h) => h.expires, mono: true },
          { key: "pos", label: "Position", render: (h) => <Status tone={h.tone}>{h.position}</Status> },
        ]} />
      <SectionHead title="New scope — project plans" />
      <div className="list">
        {projects.map((p) => (
          <div key={p.ref} className="item info">
            <span className="item-title">{p.body} · {p.scope}</span>
            <span className="mono small">{p.ref}</span>
            <div className="item-detail" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="rail-steps" aria-hidden>{p.steps.map((s, i) => <i key={s} className={i < p.step ? "done" : i === p.step ? "now" : ""} />)}</div>
              <span className="small muted">Current step: {p.steps[p.step]} · owner {p.owner} · target <span className="mono">{p.target}</span></span>
            </div>
          </div>
        ))}
      </div>
      <div className="source">Source: {q.data.meta.source as string}.</div>
      <AuditTrail />
    </>
  );
}
