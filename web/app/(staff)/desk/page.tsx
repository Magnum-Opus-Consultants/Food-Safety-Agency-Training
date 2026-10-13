"use client";

import { useRouter } from "next/navigation";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useAction, useMe, useRegister } from "@/lib/hooks";

type Item = { ref: string; route: string; title: string; detail: string; trigger: string; triggerKind: string; age: string; state: string; tone: Tone };
type Stream = { title: string; owner: string; escalates: string; n: number; state: string; tone: Tone; route: string };
type Desk = {
  escalated: Item[]; running: Stream[]; runningTotal: number;
  triggers: { rule: string; kind: string }[]; channelRule: string; rotation: { area: string; member: string | null }[];
};

export default function HeadOfDepartmentDesk() {
  const router = useRouter();
  const q = useRegister<Desk>("/desk");
  const me = useMe();
  const resolve = useAction<{ ref: string }>("POST", (v) => `/enquiries/${v.ref}/resolve`);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="desk" />;
  const d = q.data.data;
  const canResolve = me.data?.data.writes.includes("demand");
  const triage = d.rotation.find((r) => r.area === "Enquiry triage")?.member;

  return (
    <>
      <Hero
        title={`${d.escalated.length} ${d.escalated.length === 1 ? "item needs" : "items need"} the head of department; ${d.runningTotal} are handled by the team.`}
        statement="An item reaches this desk only when one of the six triggers fires. It arrives by itself and leaves when the condition clears. Everything else carries a named owner and the condition under which it would escalate."
        stats={[
          { v: String(d.escalated.length), l: "Escalated by rule", c: "Each names its trigger" },
          { v: String(d.runningTotal), l: "Handled by the team", c: "Across six streams of work" },
          { v: String(d.escalated.filter((i) => i.tone === "bad").length), l: "Action required", c: "Serious enough to act on now" },
          { v: triage ?? "Unassigned", l: "On rotation", c: "Enquiry triage this week" },
        ]}
      />
      <Blocked refusal={resolve.refusal} />
      <div className="two-col">
        <section className="list">
          <SectionHead title="Needs the head of department" />
          {d.escalated.length === 0 ? <p className="muted">No trigger has fired. Nothing needs the head of department today.</p> : d.escalated.map((i) => (
            <div key={i.ref + i.trigger} className={`item ${i.tone} item-link`} role="link" tabIndex={0} title={`Open ${i.ref}`}
                 onClick={() => router.push(`${i.route}?focus=${encodeURIComponent(i.ref)}`)}
                 onKeyDown={(e) => { if (e.key === "Enter") router.push(`${i.route}?focus=${encodeURIComponent(i.ref)}`); }}>
              <span className="item-title">{i.title}</span>
              <Status tone={i.tone}>{i.state}</Status>
              <span className="item-detail">{i.detail}</span>
              <span className="item-meta">
                <span>Trigger: <b>{i.trigger}</b> ({i.triggerKind})</span>
                <span className="mono">{i.ref}</span>
                <span>{i.age}</span>
                {canResolve && (i.state === "Complaint" || i.state === "Opportunity") ? (
                  <button className="btn btn-sm" disabled={resolve.isPending} onClick={(e) => { e.stopPropagation(); resolve.mutate({ ref: i.ref }); }}>
                    Mark resolved
                  </button>
                ) : null}
              </span>
            </div>
          ))}
        </section>
        <section className="list">
          <SectionHead title="Handled by the team" />
          {d.running.map((r) => (
            <div key={r.title} className={`item ${r.tone}${r.route ? " item-link" : ""}`} role={r.route ? "link" : undefined}
                 tabIndex={r.route ? 0 : undefined} title={r.route ? `Open ${r.title.toLowerCase()}` : undefined}
                 onClick={() => r.route && router.push(r.route)}
                 onKeyDown={(e) => { if (e.key === "Enter" && r.route) router.push(r.route); }}>
              <span className="item-title">{r.title}</span>
              <span className="item-n">{r.n}</span>
              <span className="item-meta"><span>{r.owner}</span><Status tone={r.tone}>{r.state}</Status></span>
              <span className="item-detail muted">Escalates when {r.escalates}.</span>
            </div>
          ))}
        </section>
      </div>
      <AuditTrail />
    </>
  );
}
