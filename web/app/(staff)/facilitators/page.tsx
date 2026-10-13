"use client";

import Link from "next/link";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { Modal } from "@/components/registration";
import { SearchSelect } from "@/components/SearchSelect";
import { ACCEPT } from "@/components/Prerequisites";
import { api, ApiError, upload } from "@/lib/api";
import type { Tone } from "@/lib/api";
import { useRegister, useScreen, useUpload } from "@/lib/hooks";

type Row = { ref: string; name: string; registration: string; body: string; expires: string; blocks: string[]; position: string; tone: Tone };
type Options = { bodies: { code: string; name: string }[]; people: { ref: string; name: string; role: string; registered: boolean }[]; canRecord: boolean };
type Reg = { id: number; registration: string; body: string; bodyCode: string; number: string; issued: string | null; expires: string;
  standing: string; recorded: string; recordedBy: string; certificate: { name: string; url: string } | null };
type Detail = { ref: string; name: string; role: string; state: string; suspendedReason: string; registrations: Reg[];
  intakes: { ref: string; course: string; start: string; end: string; state: string }[] };

const STANDING_TONE: Record<string, Tone> = { Current: "ok", Expiring: "warn", Lapsed: "bad" };

/** Record a registration (a renewal is a new one) and, optionally, its certificate, in one step. */
function RegistrationForm({ personRef, current, onDone, onCancel }: {
  personRef?: string; current?: Reg; onDone: (what: string) => void; onCancel: () => void;
}) {
  const opts = useRegister<Options>("/facilitators/options");
  const qc = useQueryClient();
  const screen = useScreen();
  const [who, setWho] = useState(personRef ?? "");
  const [f, setF] = useState({ registrationType: current?.registration ?? "", body: current?.bodyCode ?? "", number: "", issued: "", expires: "" });
  const [file, setFile] = useState<File | null>(null);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<ApiError | null>(null);
  if (!opts.data) return <p className="muted">Loading…</p>;
  const today = new Date().toISOString().slice(0, 10);
  const p: Record<string, string> = {};
  if (!who) p.who = "Choose the facilitator.";
  if (!f.registrationType.trim()) p.type = "Name the registration.";
  if (!f.body) p.body = "Choose the registering body.";
  if (!f.expires) p.expires = "Give the expiry date.";
  else if (f.expires < today) p.expires = "That date has passed; record the current registration.";
  else if (f.issued && f.expires <= f.issued) p.expires = "The expiry must be after the issue date.";
  if (file && file.size > 5 * 1024 * 1024) p.file = "The file is larger than 5 MB.";
  const e = tried ? p : {};
  const cls = (k: string) => (e[k] ? "invalid" : undefined);
  const Err = ({ k }: { k: string }) => (e[k] ? <span className="field-error">{e[k]}</span> : null);

  async function save() {
    setTried(true);
    if (Object.keys(p).length) return;
    setBusy(true);
    setRefusal(null);
    try {
      const r = await api<{ id: number }>(`/facilitators/${who}/registrations`, { method: "POST", screen,
        body: { ...f, issued: f.issued || null, expires: f.expires } });
      if (file) await upload(`/facilitators/registrations/${r.data.id}/certificate`, file, screen);
      await qc.invalidateQueries();
      onDone(r.meta.audit?.what ?? "");
    } catch (err) {
      if (err instanceof ApiError) setRefusal(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack-12">
      <Blocked refusal={refusal} />
      <div className="form-grid cols-4">
        {!personRef ? (
          <div className="field"><label htmlFor="rg-who">Facilitator</label>
            <SearchSelect id="rg-who" value={who} onChange={setWho} invalid={!!e.who} placeholder="Type to search people…" emptyText="Nobody matches"
                          options={opts.data.data.people.map((x) => ({ value: x.ref, label: x.name, hint: x.registered ? `${x.role} · registered` : x.role }))} />
            <Err k="who" /></div>
        ) : null}
        <div className="field"><label htmlFor="rg-type">Registration</label>
          <input id="rg-type" value={f.registrationType} className={cls("type")} placeholder="e.g. Assessor — meat examination"
                 onChange={(x) => setF({ ...f, registrationType: x.target.value })} /><Err k="type" /></div>
        <div className="field"><label htmlFor="rg-body">Registering body</label>
          <select id="rg-body" value={f.body} className={cls("body")} onChange={(x) => setF({ ...f, body: x.target.value })}>
            <option value="">Choose…</option>{opts.data.data.bodies.map((b) => <option key={b.code} value={b.code}>{b.name}</option>)}
          </select><Err k="body" /></div>
        <div className="field"><label htmlFor="rg-no">Registration number <span className="optional">(optional)</span></label>
          <input id="rg-no" value={f.number} onChange={(x) => setF({ ...f, number: x.target.value })} /></div>
        <div className="field"><label htmlFor="rg-issued">Issued <span className="optional">(optional)</span></label>
          <input id="rg-issued" type="date" value={f.issued} onChange={(x) => setF({ ...f, issued: x.target.value })} /></div>
        <div className="field"><label htmlFor="rg-exp">Expires</label>
          <input id="rg-exp" type="date" value={f.expires} min={today} className={cls("expires")} onChange={(x) => setF({ ...f, expires: x.target.value })} /><Err k="expires" /></div>
        <div className="field"><label htmlFor="rg-file">Certificate <span className="optional">(PDF, JPG or PNG)</span></label>
          <input id="rg-file" type="file" accept={ACCEPT} className={cls("file")} onChange={(x) => setFile(x.target.files?.[0] ?? null)} /><Err k="file" /></div>
      </div>
      <div className="row">
        <button className="btn btn-primary" disabled={busy} onClick={save}>{busy ? "Saving…" : current ? "Record renewal" : "Record registration"}</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
        <span className="small muted">The previous registration stays in the history; nothing is overwritten.</span>
      </div>
    </div>
  );
}

function longDate(iso: string | null) {
  return iso ? new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { day: "numeric", month: "long", year: "numeric" }) : "";
}

function daysFrom(iso: string) {
  const today = new Date(new Date().toISOString().slice(0, 10) + "T00:00:00");
  return Math.round((new Date(iso + "T00:00:00").getTime() - today.getTime()) / 86400000);
}

/** Add the certificate to a registration already recorded. */
function CertificateUpload({ regId, onDone }: { regId: number; onDone: (what: string) => void }) {
  const send = useUpload((id) => `/facilitators/registrations/${id}/certificate`);
  return (
    <label className="btn btn-sm" style={{ cursor: "pointer" }}>
      <i className="fas fa-upload" aria-hidden /> {send.isPending ? "Uploading…" : "Upload certificate"}
      <input type="file" accept={ACCEPT} hidden onChange={(e) => {
        const f = e.target.files?.[0];
        if (f) send.mutate({ ref: String(regId), file: f }, { onSuccess: (r) => onDone(r.meta.audit?.what ?? "") });
        e.target.value = "";
      }} />
      {send.refusal ? <span className="field-error"> {send.refusal.blockedBy[0] ?? send.refusal.message}</span> : null}
    </label>
  );
}

function FacilitatorPanel({ code, canRecord, onSaved }: { code: string; canRecord: boolean; onSaved: (what: string) => void }) {
  const q = useRegister<Detail>(`/facilitators/${code}`);
  const [renewing, setRenewing] = useState(false);
  if (q.error) return <Blocked refusal={q.error} />;
  if (!q.data) return <p className="muted">Loading…</p>;
  const d = q.data.data;
  const current = d.registrations[0];
  const left = current ? daysFrom(current.expires) : null;
  const earlier = d.registrations.slice(1);
  return (
    <div className="stack-12">
      {/* At a glance: who, the registration that counts now, how long it has left, and the evidence. */}
      <div className="fac-summary">
        <div><span className="qd-label">Role</span><b>{d.role}</b>
          {d.state === "Suspended" ? <Status tone="bad">Account suspended</Status> : <span className="small muted">Account active</span>}</div>
        {current ? (
          <>
            <div><span className="qd-label">Current registration</span><b>{current.registration}</b>
              <span className="small muted">{current.body}{current.number ? ` · No. ${current.number}` : ""}</span></div>
            <div><span className="qd-label">Valid until</span><b>{longDate(current.expires)}</b>
              <Status tone={STANDING_TONE[current.standing] ?? "na"}>
                {left !== null && left < 0 ? `Lapsed ${-left} days ago` : left !== null ? `${left} days left` : current.standing}
              </Status></div>
            <div><span className="qd-label">Certificate</span>
              {current.certificate ? <a href={current.certificate.url} target="_blank" rel="noopener"><i className="fas fa-file-pdf" aria-hidden /> {current.certificate.name}</a>
                : <span className="small tone-warn">None on file</span>}
              {canRecord && !current.certificate ? <CertificateUpload regId={current.id} onDone={onSaved} /> : null}</div>
          </>
        ) : <div><span className="qd-label">Current registration</span><span className="tone-bad">None recorded</span></div>}
        {canRecord && !renewing ? (
          <div className="fac-act"><button className="btn btn-sm btn-primary" onClick={() => setRenewing(true)}>
            <i className="fas fa-rotate" aria-hidden /> Record renewal</button></div>
        ) : null}
      </div>
      {renewing ? (
        <div className="card inset-form">
          <RegistrationForm personRef={d.ref} current={current} onCancel={() => setRenewing(false)} onDone={(w) => { setRenewing(false); onSaved(w); }} />
        </div>
      ) : null}

      <div className="fac-cols">
        <section>
          <div className="eyebrow">Scheduled to deliver · {d.intakes.length}</div>
          {d.intakes.length ? (
            <table className="plain-table">
              <thead><tr><th>Intake</th><th>Course</th><th>Dates</th><th>State</th></tr></thead>
              <tbody>
                {d.intakes.map((b) => {
                  const covered = !current || current.expires >= b.end;
                  return (
                    <tr key={b.ref}>
                      <td><Link href={`/plan?focus=${b.ref}`}>{b.ref}</Link></td>
                      <td>{b.course}</td>
                      <td>{b.start} to {b.end}</td>
                      <td>{b.state}{!covered ? <> <Status tone="bad">Not covered</Status></> : null}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : <p className="small muted" style={{ margin: 0 }}>Nothing scheduled.</p>}
        </section>
        <section>
          <div className="eyebrow">Registration history</div>
          <ul className="fac-history">
            {d.registrations.map((r, i) => (
              <li key={r.id} className={i === 0 ? "now" : ""}>
                <b>{r.registration}</b> <span className="small muted">· {r.body}</span>
                <div className="small">{r.issued ? `${longDate(r.issued)} to ` : "Valid to "}{longDate(r.expires)}
                  {r.certificate ? <> · <a href={r.certificate.url} target="_blank" rel="noopener">certificate</a></> : null}</div>
                <div className="small muted">Recorded by {r.recordedBy}, {r.recorded}</div>
              </li>
            ))}
          </ul>
          {!earlier.length ? <p className="small muted" style={{ margin: 0 }}>No earlier registrations recorded.</p> : null}
        </section>
      </div>
    </div>
  );
}

export default function Facilitators() {
  const q = useRegister<Row[]>("/facilitators");
  const opts = useRegister<Options>("/facilitators/options");
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState("");
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const rows = q.data.data;
  const canRecord = opts.data?.data.canRecord ?? false;
  const say = (w: string) => { setNotice(w); window.setTimeout(() => setNotice(""), 10000); };
  return (
    <>
      <Hero
        stats={[
          { v: String(rows.length), l: "Registrations", c: "Held by facilitators" },
          { v: String(rows.filter((r) => r.tone === "bad").length), l: "Action required", c: "Registration lapsed" },
          { v: String(rows.filter((r) => r.tone === "warn").length), l: "Needs attention", c: "Expiring within ninety days" },
          { v: String(rows.filter((r) => r.tone === "ok").length), l: "In order", c: "Current registrations" },
        ]}
      />
      {notice ? <div className="callout ok" role="status"><p><b>Saved.</b> {notice}</p></div> : null}
      <SectionHead title="Facilitator registrations">
        {canRecord ? <button className="btn btn-teal" onClick={() => setAdding(true)}>Add registration</button> : null}
      </SectionHead>
      <Register rows={rows} rowKey={(r) => r.ref}
        onRow={(r) => setOpen(r.ref === open ? null : r.ref)}
        expanded={(r) => (r.ref === open ? <FacilitatorPanel code={r.ref} canRecord={canRecord} onSaved={say} /> : null)}
        columns={[
          { key: "name", label: "Facilitator", render: (r) => <b>{r.name}</b> },
          { key: "reg", label: "Registration", render: (r) => r.registration },
          { key: "body", label: "Body", render: (r) => r.body },
          { key: "exp", label: "Expires", render: (r) => r.expires, mono: true },
          { key: "blocks", label: "Scheduled intakes", render: (r) => r.blocks.join(", ") || "—", mono: true },
          { key: "pos", label: "Position", render: (r) => <Status tone={r.tone}>{r.position}</Status> },
        ]} />
      {adding ? (
        <Modal title="Add a facilitator registration" onClose={() => setAdding(false)} wide>
          <RegistrationForm onCancel={() => setAdding(false)} onDone={(w) => { setAdding(false); say(w); }} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
