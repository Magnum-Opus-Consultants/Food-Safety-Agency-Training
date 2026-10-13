"use client";

import { useState } from "react";
import { AuditTrail, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { CohortImportForm, Modal } from "@/components/registration";
import type { Tone } from "@/lib/api";
import { useMe, useRegister } from "@/lib/hooks";

type Row = { ref: string; university: string; cohort: string; size: number; periodEnd: string; reportDue: string; position: string; tone: Tone };

export default function Partnerships() {
  const q = useRegister<Row[]>("/partnerships");
  const me = useMe();
  const [importing, setImporting] = useState(false);
  const [done, setDone] = useState("");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const rows = q.data.data;
  return (
    <>
      <Hero
        title="Each placement period is reported to the university within twenty days of period end."
        statement="Students are marked at the abattoir in cohorts of five. A report unsubmitted at fifteen days is an observation; past twenty days it is a finding."
        stats={[
          { v: String(rows.length), l: "Placements", c: "On the register" },
          { v: String(rows.filter((r) => r.tone === "bad").length), l: "Action required", c: "Report past twenty days" },
          { v: String(rows.filter((r) => r.tone === "warn").length), l: "Needs attention", c: "Report due within five days" },
          { v: "7", l: "University partners", c: "MUT, DUT, CUT, CPUT, UP, UJ, TUT" },
        ]}
      />
      <SectionHead title="Placements">
        {me.data?.data.writes.includes("learners") ? (
          <button className="btn btn-teal" onClick={() => { setDone(""); setImporting(true); }}>Import cohort list</button>
        ) : null}
      </SectionHead>
      {done ? <div className="callout ok"><p>{done}</p></div> : null}
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string}
        columns={[
          { key: "ref", label: "Placement", render: (r) => r.ref, mono: true },
          { key: "uni", label: "University", render: (r) => <b>{r.university}</b> },
          { key: "cohort", label: "Cohort", render: (r) => `${r.cohort} · ${r.size}` },
          { key: "end", label: "Period end", render: (r) => r.periodEnd, mono: true },
          { key: "due", label: "Report due", render: (r) => r.reportDue, mono: true },
          { key: "pos", label: "Position", render: (r) => <Status tone={r.tone}>{r.position}</Status> },
        ]} />
      {importing ? (
        <Modal title="Import a university cohort list" onClose={() => setImporting(false)}>
          <CohortImportForm onDone={(msg) => { setImporting(false); setDone(msg); }} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
