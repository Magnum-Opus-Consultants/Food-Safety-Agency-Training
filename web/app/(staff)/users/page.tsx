"use client";

import { AuditTrail, Hero, LoadError, Loading, Register, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useRegister } from "@/lib/hooks";

type User = { ref: string; name: string; position: string; reportsTo: string; roleLabel: string; segments: string; state: string; tone: Tone };

export default function UserManagement() {
  const q = useRegister<User[]>("/users");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="accounts" />;
  const rows = q.data.data;
  return (
    <>
      <Hero
        title="Access is granted by segment, not by screen."
        statement="Accounts are provisioned by HR and Administration. An account is suspended the day the accreditation behind its role lapses; accounts expiring within ninety days show an observation. Every role or segment change is audited."
        stats={[
          { v: String(rows.length), l: "Accounts", c: "Including the HR Hub service account" },
          { v: String(rows.filter((r) => r.tone === "ok").length), l: "Active", c: "Current" },
          { v: String(rows.filter((r) => r.tone === "warn").length), l: "Expiring", c: "Within ninety days" },
          { v: String(rows.filter((r) => r.tone === "bad").length), l: "Suspended", c: "Registration lapsed" },
        ]}
      />
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string}
        columns={[
          { key: "name", label: "Person", render: (r) => <><b>{r.name}</b><div className="small muted mono">{r.ref}</div></> },
          { key: "pos", label: "Position", render: (r) => r.position },
          { key: "rep", label: "Reports to", render: (r) => r.reportsTo || "—" },
          { key: "role", label: "Hub role", render: (r) => r.roleLabel },
          { key: "seg", label: "Segments", render: (r) => <span className="small">{r.segments}</span> },
          { key: "state", label: "Status", render: (r) => <Status tone={r.tone}>{r.state}</Status> },
        ]} />
      <AuditTrail />
    </>
  );
}
