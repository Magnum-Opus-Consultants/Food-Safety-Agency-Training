"use client";

import { useRouter } from "next/navigation";
import { AuditTrail, Hero, LoadError, Loading, Register, Stat, Status } from "@/components/ui";
import type { SessionRow } from "@/lib/types";
import { useRegister } from "@/lib/hooks";


export default function Sessions() {
  const router = useRouter();
  const q = useRegister<{ items: SessionRow[]; stats: Stat[]; scope: string }>("/sessions");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { items, stats, scope } = q.data.data;
  const outstanding = items.filter((s) => s.registerState === "Outstanding");
  return (
    <>
      <Hero
        title={outstanding.length
          ? `${outstanding.length} delivered ${outstanding.length === 1 ? "session has" : "sessions have"} no captured register.`
          : "Every delivered session has a locked register."}
        statement={`Capture the register against the scheduled session. It locks on save; a correction after capture is a new audited entry, never an edit.${scope === "own" ? " You are seeing your own sessions." : ""}`}
        stats={stats}
      />
      <Register rows={items} rowKey={(s) => s.ref} onRow={(s) => router.push(`/sessions/${s.ref}`)} source={q.data.meta.source as string}
        columns={[
          { key: "ref", label: "Session", render: (s) => s.ref, mono: true },
          { key: "course", label: "Course", render: (s) => <><b>{s.course}</b><div className="small muted">{s.venue}</div></> },
          { key: "fac", label: "Facilitator", render: (s) => s.facilitator },
          { key: "dates", label: "Dates", render: (s) => `${s.start} → ${s.end}`, mono: true },
          { key: "seats", label: "Learners", render: (s) => `${s.seats} / ${s.capacity}`, mono: true },
          { key: "state", label: "Register", render: (s) => <Status tone={s.tone}>{s.registerState}</Status> },
        ]} />
      <AuditTrail />
    </>
  );
}
