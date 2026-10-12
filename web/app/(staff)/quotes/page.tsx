"use client";

import { AuditTrail, Hero, LoadError, Loading, Register, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useState } from "react";
import { useMe, useRegister } from "@/lib/hooks";
import { DelegatesForm, Modal } from "@/components/registration";

type Quote = { ref: string; client: string; course: string; basis: string; value: string; issued: string | null; followUpDue: string | null; owner: string | null; status: string; tone: Tone;
  courseCode: string; learners: number; registered: number; canAddDelegates: boolean };

export default function Quotes() {
  const q = useRegister<Quote[]>("/quotations");
  const me = useMe();
  const [adding, setAdding] = useState<Quote | null>(null);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const rows = q.data.data;
  return (
    <>
      <Hero
        title="Quotations per learner or per group, with follow-up discipline."
        statement="No follow-up within fourteen days flags the quotation as an observation and puts it on the head of department's desk. A quotation over R 50 000 needs her approval."
        stats={[
          { v: String(rows.length), l: "Quotations", c: "Open on the register" },
          { v: String(rows.filter((r) => r.status === "Follow-up overdue").length), l: "Follow-up overdue", c: "Past fourteen days" },
          { v: String(rows.filter((r) => r.status === "Approval needed").length), l: "Approval needed", c: "Over R 50 000" },
          { v: String(rows.filter((r) => r.basis === "Per group").length), l: "Group quotes", c: "Corporate accounts" },
        ]}
      />
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string}
        columns={[
          { key: "ref", label: "Reference", render: (r) => r.ref, mono: true },
          { key: "client", label: "Client", render: (r) => <b>{r.client}</b> },
          { key: "course", label: "Course", render: (r) => r.course },
          { key: "basis", label: "Basis", render: (r) => r.basis },
          { key: "value", label: "Value", render: (r) => r.value, mono: true },
          { key: "issued", label: "Issued", render: (r) => r.issued ?? "—", mono: true },
          { key: "due", label: "Follow-up due", render: (r) => r.followUpDue ?? "—", mono: true },
          { key: "owner", label: "Owner", render: (r) => r.owner ?? "Unassigned" },
          { key: "status", label: "Status", render: (r) => <Status tone={r.tone}>{r.status}</Status> },
          { key: "reg", label: "Registered", render: (r) => `${r.registered} / ${r.learners}`, mono: true },
          { key: "act", label: "", render: (r) => (r.canAddDelegates && me.data?.data.writes.includes("learners") ? (
            <button className="btn btn-sm" onClick={() => setAdding(r)}>Add delegates</button>
          ) : null) },
        ]} />
      {adding ? (
        <Modal title={`Delegates for ${adding.ref}`} onClose={() => setAdding(null)}>
          <DelegatesForm quote={adding} onDone={() => setAdding(null)} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
