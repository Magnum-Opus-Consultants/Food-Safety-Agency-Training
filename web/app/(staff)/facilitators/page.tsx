"use client";

import { AuditTrail, Hero, LoadError, Loading, Register, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useRegister } from "@/lib/hooks";

type Row = { ref: string; name: string; registration: string; body: string; expires: string; blocks: string[]; position: string; tone: Tone };

export default function Facilitators() {
  const q = useRegister<Row[]>("/facilitators");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const rows = q.data.data;
  return (
    <>
      <Hero
        title="Registrations checked against the courses each facilitator is scheduled to deliver."
        statement="A lapsed registration against a scheduled session is a finding; within ninety days it is an observation. An account is suspended the day the registration behind it lapses."
        stats={[
          { v: String(rows.length), l: "Registrations", c: "Held by facilitators" },
          { v: String(rows.filter((r) => r.tone === "bad").length), l: "Findings", c: "Lapsed" },
          { v: String(rows.filter((r) => r.tone === "warn").length), l: "Observations", c: "Expiring within ninety days" },
          { v: String(rows.filter((r) => r.tone === "ok").length), l: "Compliant", c: "Current registrations" },
        ]}
      />
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string}
        columns={[
          { key: "name", label: "Facilitator", render: (r) => <b>{r.name}</b> },
          { key: "reg", label: "Registration", render: (r) => r.registration },
          { key: "body", label: "Body", render: (r) => r.body },
          { key: "exp", label: "Expires", render: (r) => r.expires, mono: true },
          { key: "blocks", label: "Scheduled blocks", render: (r) => r.blocks.join(", ") || "—", mono: true },
          { key: "pos", label: "Position", render: (r) => <Status tone={r.tone}>{r.position}</Status> },
        ]} />
      <AuditTrail />
    </>
  );
}
