"use client";

import { AuditTrail, Hero, LoadError, Loading, Register, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useRegister } from "@/lib/hooks";

type Risk = { ref: string; risk: string; cause: string; rating: string; trigger: string; breached: boolean; owner: string; position: string; tone: Tone };

export default function RiskRegister() {
  const q = useRegister<Risk[]>("/risks");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const rows = q.data.data;
  return (
    <>
      <Hero
        title="Each risk names a trigger, not a sentiment."
        statement="A high rating or a breached trigger escalates to GM Operations and GM Corporate Services in the monthly report, and to the board where material."
        stats={[
          { v: String(rows.length), l: "Risks", c: "On the register" },
          { v: String(rows.filter((r) => r.rating === "High").length), l: "High", c: "Escalated by rating" },
          { v: String(rows.filter((r) => r.breached).length), l: "Triggers breached", c: "Escalated by trigger" },
          { v: String(rows.filter((r) => r.tone === "ok").length), l: "Within appetite", c: "No escalation" },
        ]}
      />
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string}
        columns={[
          { key: "ref", label: "Reference", render: (r) => r.ref, mono: true },
          { key: "risk", label: "Risk", render: (r) => <b>{r.risk}</b> },
          { key: "cause", label: "Cause", render: (r) => r.cause },
          { key: "rating", label: "Rating", render: (r) => r.rating },
          { key: "trigger", label: "Escalation trigger", render: (r) => <>{r.trigger}{r.breached ? <div><Status tone="bad">Breached</Status></div> : null}</> },
          { key: "owner", label: "Owner", render: (r) => r.owner },
          { key: "pos", label: "Position", render: (r) => <Status tone={r.tone}>{r.position}</Status> },
        ]} />
      <AuditTrail />
    </>
  );
}
