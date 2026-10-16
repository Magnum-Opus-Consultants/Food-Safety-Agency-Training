"use client";

// The training depository: what an external verifier is shown. Click a library to see what it holds, each item
// with its file (view or download) and a link to the record it belongs to. Click an outstanding item to go
// straight to where it is resolved.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useRegister } from "@/lib/hooks";

type Library = { code: string; name: string; holds: string; count: number; outstanding: number; retention: string; owner: string | null; position: string; tone: Tone };
type Source = { href: string; label: string } | null;
type Doc = { ref: string; title: string; state: string; added: string; by: string; entityRef: string; file: string | null; source: Source };
type Outstanding = { ref: string; title: string; library: string; source: Source };

function LibraryDocs({ code }: { code: string }) {
  const q = useRegister<Doc[]>(`/depository/libraries/${code}`);
  if (q.error) return <Blocked refusal={q.error} />;
  if (!q.data) return <p className="muted">Opening the library…</p>;
  const docs = q.data.data;
  if (!docs.length) return <p className="small muted" style={{ margin: 0 }}>Nothing filed in this library yet.</p>;
  return (
    <table className="plain-table">
      <thead><tr><th>Item</th><th>Filed</th><th>State</th><th style={{ textAlign: "right" }}>Open</th></tr></thead>
      <tbody>
        {docs.map((d) => (
          <tr key={d.ref}>
            <td><b>{d.title}</b><div className="small muted mono">{d.ref}</div></td>
            <td className="small">{d.added}<div className="muted">{d.by}</div></td>
            <td><Status tone={d.state === "Held" ? "ok" : d.state === "Outstanding" ? "bad" : "na"}>{d.state}</Status></td>
            <td style={{ textAlign: "right" }}>
              <div className="row" style={{ justifyContent: "flex-end" }}>
                {d.file ? <>
                  <a className="btn btn-sm" href={d.file} target="_blank" rel="noopener"><i className="fas fa-file-lines" aria-hidden /> View</a>
                  <a className="btn btn-sm" href={`${d.file}?download=true`}><i className="fas fa-download" aria-hidden /> Download</a>
                </> : <span className="small muted">Recorded, no file held</span>}
                {d.source ? <Link className="btn btn-sm" href={d.source.href}>{d.source.label} →</Link> : null}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Depository() {
  const q = useRegister<{ libraries: Library[]; outstanding: Outstanding[] }>("/depository");
  const router = useRouter();
  const [open, setOpen] = useState<string | null>(null);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="depository" />;
  const { libraries, outstanding } = q.data.data;
  return (
    <>
      <Hero stats={[
        { v: String(libraries.reduce((n, l) => n + l.count, 0)), l: "Items held", c: `Across ${libraries.length} libraries` },
        { v: String(outstanding.length), l: "Outstanding", c: "Recorded, not yet filed" },
        { v: "24", l: "Months live", c: "Then NAS archive" },
        { v: String(libraries.length), l: "Libraries", c: "With a named owner" },
      ]} />
      <Register rows={libraries} rowKey={(l) => l.code} source={q.data.meta.source as string}
        onRow={(l) => setOpen(l.code === open ? null : l.code)}
        expanded={(l) => (l.code === open ? <LibraryDocs code={l.code} /> : null)}
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
            onRow={(d) => { if (d.source) router.push(d.source.href); }}
            columns={[
              { key: "ref", label: "Reference", render: (d) => d.ref, mono: true },
              { key: "title", label: "Item", render: (d) => <b>{d.title}</b> },
              { key: "lib", label: "Library", render: (d) => d.library },
              { key: "pos", label: "Position", render: () => <Status tone="bad">Outstanding</Status> },
              { key: "go", label: "", render: (d) => (d.source ? <span className="btn btn-sm">{d.source.label} →</span> : null) },
            ]} />
        </>
      ) : null}
      <AuditTrail />
    </>
  );
}
