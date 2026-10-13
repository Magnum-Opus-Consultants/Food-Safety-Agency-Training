"use client";

// A new quotation. The client is chosen from the list or added on the spot (company plus contact
// person); the contact can be added the same way. Saving can issue it straight away, unless it is
// over R 50 000, which waits as a draft for the head of department's approval.

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Blocked } from "@/components/ui";
import { PhoneInput } from "@/components/PhoneInput";
import { api, ApiError } from "@/lib/api";
import { useRegister, useScreen } from "@/lib/hooks";
import { ClientPicker } from "@/components/ClientPicker";
import { courseOptions, SearchSelect } from "@/components/SearchSelect";

type Contact = { ref: string; names: string; email: string; phone: string };
type Client = { ref: string; name: string; sector: string; relationship: string; contacts: Contact[] };

const NEW = "__new__";
const LIMIT = 50000;

/** Filled from an enquiry card: the quotation is linked to it and moves it to Quoted when issued. */
export type QuotePrefill = { enquiryRef: string; orgRef: string; contactRef: string; contactName: string; courseCode: string;
  individual: boolean; employer?: string };

export function NewQuotationForm({ onDone, prefill }: { onDone: (ref: string, what: string) => void; prefill?: QuotePrefill }) {
  const clients = useRegister<Client[]>("/clients");
  const courses = useRegister<{ code: string; title: string }[]>("/courses");
  const qc = useQueryClient();
  const screen = useScreen();
  const [clientRef, setClientRef] = useState(prefill?.orgRef ?? "");
  const [contactRef, setContactRef] = useState(prefill?.contactRef ?? "");
  // An enquiry from a private individual (no company) is quoted per learner, to that person.
  const individual = Boolean(prefill?.individual);
  const [nc, setNc] = useState({ name: "", sector: "" });
  const [person, setPerson] = useState({ names: "", email: "", phone: "" });
  const [q, setQ] = useState({ courseCode: prefill?.courseCode ?? "", basis: individual ? "PerLearner" : "PerGroup", learners: individual ? "1" : "", value: "" });
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<ApiError | null>(null);

  const list = clients.data?.data ?? [];
  const client = list.find((c) => c.ref === clientRef);
  const newClient = clientRef === NEW;
  const newContact = newClient || contactRef === NEW;
  const amount = Number(q.value.replace(/[R\s]/g, "").replace(",", "."));
  const over = amount > LIMIT;

  const p: Record<string, string> = {};
  if (!clientRef && !individual) p.client = "Choose the client, or add a new one.";
  if (newClient && !nc.name.trim()) p.name = "Give the company's name.";
  if (newClient && list.some((c) => c.name.toLowerCase() === nc.name.trim().toLowerCase())) p.name = "This company is already a client: choose it from the list.";
  if (client && !contactRef) p.contact = "Choose who the quotation is addressed to, or add a contact.";
  if (newContact && clientRef && !person.names.trim()) p.names = "Name the contact person.";
  if (newContact && person.email.trim() && !person.email.includes("@")) p.email = "Enter a valid email address, or leave it blank.";
  if (!q.courseCode) p.course = "Choose the course.";
  const n = Number(q.learners);
  if (!q.learners.trim() || !Number.isInteger(n) || n < 1) p.learners = "Give the number of learners.";
  if (!q.value.trim() || Number.isNaN(amount) || amount <= 0) p.value = "Give the quoted value in rand.";
  const errors = tried ? p : {};
  const cls = (k: string) => (errors[k] ? "invalid" : undefined);
  const Err = ({ k }: { k: string }) => (errors[k] ? <span className="field-error">{errors[k]}</span> : null);

  async function save(issue: boolean) {
    setTried(true);
    if (Object.keys(p).length) return;
    setBusy(true);
    setRefusal(null);
    try {
      let orgRef = clientRef, personRef = contactRef;
      if (newClient) {
        const r = await api<{ ref: string; contactRef: string }>("/clients", { method: "POST", screen,
          body: { name: nc.name, sector: nc.sector, contactNames: person.names, email: person.email, phone: person.phone } });
        orgRef = r.data.ref; personRef = r.data.contactRef;
        setClientRef(orgRef); setContactRef(personRef);
      } else if (newContact) {
        const r = await api<{ contactRef: string }>(`/clients/${orgRef}/contacts`, { method: "POST", screen, body: person });
        personRef = r.data.contactRef;
        setContactRef(personRef);
      }
      const r = await api<{ ref: string; state: string }>("/quotations", { method: "POST", screen,
        body: { organisationRef: individual ? "" : orgRef, contactRef: personRef, courseCode: q.courseCode, basis: q.basis, learners: n,
                value: q.value, issue, enquiryRef: prefill?.enquiryRef ?? "" } });
      await qc.invalidateQueries();
      onDone(r.data.ref, r.meta.audit?.what ?? "");
    } catch (e) {
      if (e instanceof ApiError) setRefusal(e);
      await qc.invalidateQueries();
    } finally {
      setBusy(false);
    }
  }

  if (!clients.data || !courses.data) return <p className="muted">Loading…</p>;
  return (
    <div className="stack-12">
      <Blocked refusal={refusal} />
      <div className="eyebrow">Client</div>
      <div className="form-grid">
        {individual ? (
          <div className="field"><label>Quoted to</label>
            <div className="readonly-value">{prefill?.contactName} <span className="muted small">· for themselves, from {prefill?.enquiryRef}
              {prefill?.employer ? ` · works at ${prefill.employer} (not billed)` : ""}</span></div></div>
        ) : (
          <div className="field"><label htmlFor="nq-client">Company</label>
            <ClientPicker id="nq-client" clients={list} value={clientRef} invalid={!!errors.client}
                          onChange={(ref, typed) => { setClientRef(ref); setContactRef(""); if (typed) setNc({ ...nc, name: typed }); }} />
            <Err k="client" /></div>
        )}
        {newClient ? (
          <>
            <div className="field"><label htmlFor="nq-name">Company name</label>
              <input id="nq-name" value={nc.name} className={cls("name")} onChange={(e) => setNc({ ...nc, name: e.target.value })} /><Err k="name" /></div>
            <div className="field"><label htmlFor="nq-sector">Sector <span className="optional">(optional)</span></label>
              <input id="nq-sector" value={nc.sector} placeholder="e.g. Poultry abattoir" onChange={(e) => setNc({ ...nc, sector: e.target.value })} /></div>
          </>
        ) : client && !individual ? (
          <div className="field"><label htmlFor="nq-contact">Addressed to</label>
            <select id="nq-contact" value={contactRef} className={cls("contact")} onChange={(e) => setContactRef(e.target.value)}>
              <option value="">Choose a contact…</option>
              <option value={NEW}>+ Add a new contact</option>
              {client.contacts.map((c) => <option key={c.ref} value={c.ref}>{c.names}{c.email ? ` · ${c.email}` : ""}</option>)}
            </select><Err k="contact" /></div>
        ) : null}
      </div>
      {newContact && clientRef && !individual ? (
        <div className="form-grid">
          <div className="field"><label htmlFor="nq-person">Contact person</label>
            <input id="nq-person" value={person.names} className={cls("names")} onChange={(e) => setPerson({ ...person, names: e.target.value })} /><Err k="names" /></div>
          <div className="field"><label htmlFor="nq-email">Email <span className="optional">(optional)</span></label>
            <input id="nq-email" type="email" value={person.email} className={cls("email")} onChange={(e) => setPerson({ ...person, email: e.target.value })} /><Err k="email" /></div>
          <div className="field"><label htmlFor="nq-phone">Phone <span className="optional">(optional)</span></label>
            <PhoneInput id="nq-phone" value={person.phone} onChange={(v) => setPerson({ ...person, phone: v })} /></div>
        </div>
      ) : null}
      <div className="eyebrow">Quotation</div>
      <div className="form-grid">
        <div className="field"><label htmlFor="nq-course">Course</label>
          <SearchSelect id="nq-course" options={courseOptions(courses.data.data)} value={q.courseCode} invalid={!!errors.course}
                        placeholder="Type to search courses…" emptyText="No course matches" onChange={(v) => setQ({ ...q, courseCode: v })} />
          <Err k="course" /></div>
        <div className="field"><label htmlFor="nq-basis">Basis</label>
          <select id="nq-basis" value={q.basis} disabled={individual} onChange={(e) => setQ({ ...q, basis: e.target.value })}>
            <option value="PerGroup">Per group: the company sends its delegates</option>
            <option value="PerLearner">Per learner</option>
          </select></div>
        <div className="field"><label htmlFor="nq-learners">Number of learners</label>
          <input id="nq-learners" inputMode="numeric" value={q.learners} className={cls("learners")} onChange={(e) => setQ({ ...q, learners: e.target.value })} /><Err k="learners" /></div>
        <div className="field"><label htmlFor="nq-value">Quoted value (R)</label>
          <input id="nq-value" inputMode="decimal" value={q.value} placeholder="e.g. 68 400" className={cls("value")} onChange={(e) => setQ({ ...q, value: e.target.value })} />
          {errors.value ? <Err k="value" /> : over ? <span className="small tone-warn">Over R 50 000: saved as a draft until the head of department approves it.</span> : null}</div>
      </div>
      <div className="row">
        <button className="btn btn-primary" disabled={busy} onClick={() => save(!over)}>{over ? "Save for approval" : "Save and issue"}</button>
        {!over ? <button className="btn" disabled={busy} onClick={() => save(false)}>Save as draft</button> : null}
        <span className="small muted">Issuing starts the fourteen-day follow-up clock.</span>
      </div>
    </div>
  );
}
