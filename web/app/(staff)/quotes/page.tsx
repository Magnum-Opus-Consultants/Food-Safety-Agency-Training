"use client";

import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useEffect, useState } from "react";
import { useAction, useFocusRef, useMe, useRegister } from "@/lib/hooks";
import { DelegatesForm, Modal } from "@/components/registration";
import { NewQuotationForm } from "@/components/QuoteForm";
import { QuoteDetail } from "@/components/QuoteDetail";

type Quote = { ref: string; client: string; course: string; basis: string; value: string; issued: string | null; followUpDue: string | null; owner: string | null; status: string; tone: Tone;
  courseCode: string; learners: number; registered: number; canAddDelegates: boolean; state: string; needsApproval: boolean; individual: boolean;
  contact: string; contactEmail: string; enquiry: string | null };

type View = "" | "corporate" | "individual";
const VIEWS: [View, string][] = [["", "All"], ["corporate", "Corporate"], ["individual", "Individuals"]];
const STATUSES = ["Approval needed", "Follow-up overdue", "Draft", "Issued", "Accepted", "Declined", "Lapsed"];

function initialView(): View {
  if (typeof window === "undefined") return "";
  const v = new URLSearchParams(window.location.search).get("view");
  return v === "corporate" || v === "individual" ? v : "";
}

export default function Quotes() {
  const q = useRegister<Quote[]>("/quotations");
  const me = useMe();
  const [adding, setAdding] = useState<Quote | null>(null);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");
  const [view, setView] = useState<View>(initialView);
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [editRef, setEditRef] = useState<string | null>(null);
  const focus = useFocusRef();
  useEffect(() => { if (focus) setOpen(focus); }, [focus]);
  useEffect(() => {
    try { const st = new URLSearchParams(window.location.search).get("status"); if (st && STATUSES.includes(st)) setStatus(st); } catch { /* no window */ }
  }, []);
  const approve = useAction<{ ref: string }>("POST", (v) => `/quotations/${v.ref}/approve`);
  const issue = useAction<{ ref: string }>("POST", (v) => `/quotations/${v.ref}/issue`);
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const all = q.data.data;
  const words = search.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const rows = all.filter((r) => (!view || (view === "individual") === r.individual)
    && (!status || r.status === status)
    && words.every((w) => `${r.ref} ${r.client} ${r.contact} ${r.contactEmail} ${r.course} ${r.enquiry ?? ""} ${r.owner ?? ""} ${r.status}`
      .toLowerCase().includes(w)));
  const filtered = Boolean(view || status || words.length);
  const canApprove = Boolean(q.data.meta.canApprove);
  const canWrite = me.data?.data.writes.includes("demand") ?? false;
  const say = (what?: string) => { setNotice(what ?? ""); window.setTimeout(() => setNotice(""), 10000); };
  return (
    <>
      <Hero
        title="Quotations per learner or per group, with follow-up discipline."
        statement="No follow-up within fourteen days flags the quotation as an observation and puts it on the head of department's desk. A quotation over R 50 000 needs the head of department's approval."
        stats={[
          { v: String(all.length), l: "Quotations", c: "On the register" },
          { v: String(all.filter((r) => r.status === "Follow-up overdue").length), l: "Follow-up overdue", c: "Past fourteen days" },
          { v: String(all.filter((r) => r.status === "Approval needed").length), l: "Approval needed", c: "Over R 50 000" },
          { v: `${all.filter((r) => !r.individual).length} / ${all.filter((r) => r.individual).length}`, l: "Corporate / individual", c: "Companies and people quoted" },
        ]}
      />
      {notice ? <div className="callout ok" role="status"><p><b>Saved.</b> {notice}</p></div> : null}
      <Blocked refusal={approve.refusal ?? issue.refusal} />
      <SectionHead title="Quotation register">
        {canWrite ? <button className="btn btn-teal" onClick={() => setCreating(true)}>New quotation</button> : null}
      </SectionHead>
      <div className="card week-bar">
        <div className="seg" role="group" aria-label="Show">
          {VIEWS.map(([v, l]) => (
            <button key={l} className={view === v ? "on" : undefined} aria-pressed={view === v} onClick={() => setView(v)}>
              {l} <span className="seg-n">{v ? all.filter((r) => (v === "individual") === r.individual).length : all.length}</span>
            </button>
          ))}
        </div>
        <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="bar-select">
          <option value="">Any status</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <div className="week-search">
          <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search quotations"
                 placeholder="Search: client, company, contact, course, QTE or ENQ number" />
        </div>
        <span className="small muted">{rows.length} of {all.length}</span>
        {filtered ? <button className="btn btn-sm" onClick={() => { setView(""); setStatus(""); setSearch(""); }}>Clear</button> : null}
      </div>
      <Register rows={rows} rowKey={(r) => r.ref} source={q.data.meta.source as string}
        empty={filtered ? "No quotation matches these filters." : "No quotations yet."}
        onRow={(r) => { setEditRef(null); setOpen(r.ref === open ? null : r.ref); }}
        expanded={(r) => (r.ref === open ? <QuoteDetail code={r.ref} edit={editRef === r.ref} /> : null)}
        columns={[
          { key: "ref", label: "Reference", render: (r) => r.ref, mono: true },
          { key: "client", label: "Client", render: (r) => (
            <><b>{r.client}</b><span className={`for-tag ${r.individual ? "ind" : "co"}`}>{r.individual ? "Individual" : "Corporate"}</span>
              {!r.individual && r.contact ? <div className="small muted">{r.contact}</div> : null}</>
          ) },
          { key: "course", label: "Course", render: (r) => r.course },
          { key: "basis", label: "Basis", render: (r) => r.basis },
          { key: "value", label: "Value", render: (r) => r.value, mono: true },
          { key: "issued", label: "Issued", render: (r) => r.issued ?? "—", mono: true },
          { key: "due", label: "Follow-up due", render: (r) => r.followUpDue ?? "—", mono: true },
          { key: "owner", label: "Owner", render: (r) => r.owner ?? "Unassigned" },
          { key: "status", label: "Status", render: (r) => <Status tone={r.tone}>{r.status}</Status> },
          { key: "reg", label: "Registered", render: (r) => `${r.registered} / ${r.learners}`, mono: true },
          { key: "act", label: "", render: (r) => (
            <div className="row" style={{ flexWrap: "nowrap", justifyContent: "flex-end" }} onClick={(e) => e.stopPropagation()}>
              {r.state === "Draft" && canApprove ? (
                <button className="btn btn-sm" onClick={() => { setOpen(r.ref); setEditRef(r.ref); }}>
                  <i className="fas fa-pen" aria-hidden /> Edit</button>
              ) : null}
              {r.needsApproval && canApprove ? (
                <button className="btn btn-sm btn-primary" disabled={approve.isPending}
                        onClick={() => approve.mutate({ ref: r.ref }, { onSuccess: (x) => say(x.meta.audit?.what) })}>Approve</button>
              ) : null}
              {r.state === "Draft" && canWrite && !r.needsApproval ? (
                <button className="btn btn-sm" disabled={issue.isPending}
                        onClick={() => issue.mutate({ ref: r.ref }, { onSuccess: (x) => say(x.meta.audit?.what) })}>Issue</button>
              ) : null}
              {r.canAddDelegates && me.data?.data.writes.includes("learners") ? (
                <button className="btn btn-sm" onClick={() => setAdding(r)}>Add delegates</button>
              ) : null}
            </div>
          ) },
        ]} />
      {creating ? (
        <Modal title="New quotation" onClose={() => setCreating(false)}>
          <NewQuotationForm onDone={(_, what) => { setCreating(false); say(what); }} />
        </Modal>
      ) : null}
      {adding ? (
        <Modal title={`Delegates for ${adding.ref}`} onClose={() => setAdding(null)} wide>
          <DelegatesForm quote={adding} onDone={() => setAdding(null)} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
