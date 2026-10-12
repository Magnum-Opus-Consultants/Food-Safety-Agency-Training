"use client";

// Stand-ins for the FSA Design System components (Badge, StatBlock, DataTable, Callout…),
// built to its tokens. Swap each for the design system's own component when the bundle arrives.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { findNav } from "@/lib/nav";
import type { ApiError, Tone } from "@/lib/api";
import { useRegister, useScreen } from "@/lib/hooks";
import type { AuditEntry } from "@/lib/api";

// Rule 12: the status vocabulary is fixed. ok|warn|bad|na|info (the HR Hub's kinds) map to
// Compliant / Observation / Finding / Pending / Info. Never pass, fail, problem or issue.
const TONE_LABEL: Record<Tone, string> = { ok: "Compliant", warn: "Observation", bad: "Finding", na: "Pending", info: "Info" };

export function Status({ tone, children }: { tone: Tone; children?: ReactNode }) {
  return <span className={`badge tone-${tone}`}>{children ?? TONE_LABEL[tone]}</span>;
}

export type Stat = { v: string; l: string; c?: string };

/** The page heading, white on the photo as on every APS page: the screen's name, then the
 *  derived headline and its explanation. */
export function PageHeader({ lead, statement }: { lead?: ReactNode; statement?: ReactNode }) {
  const where = findNav(usePathname());
  return (
    <header className="page-head">
      {where ? <div className="page-group">{where.group}</div> : null}
      <h1>{where?.item.label ?? "Training Hub"}</h1>
      {lead ? <p className="lead">{lead}</p> : null}
      {statement ? <p>{statement}</p> : null}
    </header>
  );
}

export function Hero({ title, statement, stats }: { title: string; statement?: ReactNode; stats?: Stat[] }) {
  return (
    <section className="hero">
      <PageHeader lead={title} statement={statement} />
      {stats?.length ? (
        <div className="stats">
          {stats.map((s) => (
            <div key={s.l} className="stat">
              <div className="stat-l">{s.l}</div>
              <div className="stat-v">{s.v}</div>
              {s.c ? <div className="stat-c">{s.c}</div> : null}
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export type Column<T> = { key: string; label: string; render: (row: T) => ReactNode; mono?: boolean; width?: string };

export function Register<T>({ rows, columns, source, rowKey, onRow, empty }: {
  rows: T[]; columns: Column<T>[]; source?: string; rowKey: (r: T) => string; onRow?: (r: T) => void; empty?: string;
}) {
  return (
    <div>
      <div className="table-wrap">
        <table className="register">
          <thead>
            <tr>{columns.map((c) => <th key={c.key} style={c.width ? { width: c.width } : undefined}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={columns.length} className="muted">{empty ?? "Nothing on this register."}</td></tr>
            ) : rows.map((r) => (
              <tr key={rowKey(r)} className={onRow ? "clickable" : undefined} onClick={onRow ? () => onRow(r) : undefined}>
                {columns.map((c) => <td key={c.key} className={c.mono ? "mono" : undefined}>{c.render(r)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {source ? <div className="source">Source: {source}.</div> : null}
    </div>
  );
}

/** Rule 2: a blocked transition names what is outstanding. Rendered verbatim from the API. */
export function Blocked({ refusal, reasons, title }: { refusal?: ApiError | null; reasons?: string[]; title?: string }) {
  const list = refusal?.blockedBy?.length ? refusal.blockedBy : reasons ?? [];
  if (!refusal && !list.length) return null;
  return (
    <div className="callout bad" role="alert">
      <h4>{title ?? refusal?.message ?? "This cannot go ahead yet"}</h4>
      {list.length ? <ul>{list.map((r) => <li key={r}>{r}</li>)}</ul> : null}
    </div>
  );
}

export function SectionHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="section-head">
      <h3>{title}</h3>
      {children ? <div className="row">{children}</div> : null}
    </div>
  );
}

/** Rule 11: every state change writes an audit entry, visible on the screen that caused it. */
export function AuditTrail({ screen }: { screen?: string }) {
  const current = useScreen();
  const key = screen ?? current;
  const q = useRegister<AuditEntry[]>(`/audit?screen=${encodeURIComponent(key)}&take=12`);
  const rows = q.data?.data ?? [];
  return (
    <section className="no-print">
      <SectionHead title="Audit trail" />
      <div className="card" style={{ padding: "6px 20px" }}>
        {rows.length === 0 ? (
          <div className="audit-empty">No changes recorded from this screen yet.</div>
        ) : (
          <div className="audit">
            {rows.map((a, i) => (
              <div className="audit-row" key={`${a.at}-${i}`}>
                <span className="when">{a.at}</span>
                <span>{a.what}</span>
                <span className="who">{a.who}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="source">Source: audit trail, last 12 entries from this screen.</div>
    </section>
  );
}

export function Loading({ what = "register" }: { what?: string }) {
  return (
    <>
      <PageHeader />
      <div className="card" style={{ padding: 20, display: "flex", alignItems: "center", gap: 10, color: "var(--aps-muted)" }}>
        <i className="fas fa-spinner fa-spin" style={{ color: "var(--aps-teal)" }} aria-hidden /> Reading the {what}…
      </div>
    </>
  );
}

export function LoadError({ error }: { error: ApiError | null }) {
  if (!error) return null;
  if (error.status === 403) return <Blocked refusal={error} title="Your role does not have access to this register" />;
  return <div className="callout bad"><h4>The register could not be read</h4><p>{error.message}</p></div>;
}

export function Stub({ title, phase, children }: { title: string; phase: string; children: ReactNode }) {
  return (
    <>
      <PageHeader lead={title} />
      <section className="card" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 8 }}>
        <span className="eyebrow">{phase}</span>
        <div style={{ fontSize: ".9rem", color: "var(--aps-text)" }}>{children}</div>
        <p className="muted small" style={{ margin: 0 }}>This screen is a stub in the demo, so the department can react to
          the idea. Its badges and figures, where shown in the sidebar, are already derived from the live registers.</p>
      </section>
    </>
  );
}

export function RefLink({ href, children }: { href: string; children: ReactNode }) {
  return <Link href={href} className="mono">{children}</Link>;
}
