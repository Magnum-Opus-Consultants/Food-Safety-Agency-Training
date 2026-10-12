"use client";

import { AuditTrail, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useRegister } from "@/lib/hooks";

type Library = { code: string; name: string; holds: string; count: number; outstanding: number; retention: string; owner: string | null; position: string; tone: Tone };

export default function Depository() {
  const q = useRegister<{ libraries: Library[]; outstanding: { ref: string; title: string; library: string }[] }>("/depository");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="depository" />;
  const { libraries, outstanding } = q.data.data;
  return (
    <>
      <Hero
        title="This is what an external verifier is shown."
        statement="Six libraries, each with its holdings, retention rule and owner. Records are retained two years live, then archived to the NAS. Exclusions are recorded with a reason, never deleted."
        stats={[
          { v: String(libraries.reduce((n, l) => n + l.count, 0)), l: "Items held", c: "Across six libraries" },
          { v: String(outstanding.length), l: "Outstanding", c: "Recorded, not yet filed" },
          { v: "24", l: "Months live", c: "Then NAS archive" },
          { v: String(libraries.length), l: "Libraries", c: "With a named owner" },
        ]}
      />
      <Register rows={libraries} rowKey={(l) => l.code} source={q.data.meta.source as string}
        columns={[
          { key: "name", label: "Library", render: (l) => <b>{l.name}</b> },
          { key: "holds", label: "Holds", render: (l) => l.holds },
          { key: "n", label: "Items", render: (l) => l.count, mono: true },
          { key: "ret", label: "Retention", render: (l) => l.retention },
          { key: "owner", label: "Owner", render: (l) => l.owner ?? "—" },
          { key: "pos", label: "Position", render: (l) => <Status tone={l.tone}>{l.position}</Status> },
        ]} />
      {outstanding.length ? (
        <>
          <SectionHead title="Outstanding items" />
          <Register rows={outstanding} rowKey={(d) => d.ref}
            columns={[
              { key: "ref", label: "Reference", render: (d) => d.ref, mono: true },
              { key: "title", label: "Item", render: (d) => d.title },
              { key: "lib", label: "Library", render: (d) => d.library },
              { key: "pos", label: "Position", render: () => <Status tone="bad">Outstanding</Status> },
            ]} />
        </>
      ) : null}
      <AuditTrail />
    </>
  );
}
