"use client";

// Open and correct an enquiry. Only the fields that changed are sent; the API validates, refuses
// with named reasons, and writes one audit entry with each field's previous and new value.
// The received time and the stage are shown but not edited here: the time drives the
// two-working-day clock, and the stage moves on the board where its rules apply.

import { useState } from "react";
import { Blocked, Status } from "@/components/ui";
import { PhoneInput } from "@/components/PhoneInput";
import { TopicPicker } from "@/components/TopicPicker";
import type { AuditEntry, Tone } from "@/lib/api";
import { useAction, useRegister } from "@/lib/hooks";
import { courseOptions, SearchSelect } from "@/components/SearchSelect";

type Detail = {
  ref: string; name: string; org: string; email: string; phone: string; channel: string; kind: string;
  courseCode: string; interest: string; ownerRef: string; owner: string | null; notes: string;
  topics: string[]; topicOther: string; clockText: string; updatedAt: string | null; updatedBy: string | null;
  receivedAt: string; workingDaysOpen: number; stage: string; stale: boolean; tone: Tone; enrolment: string | null;
  canEdit: boolean; courseLocked: boolean; kindLocked: boolean; enquiringFor: string; forLocked: boolean;
  owners: { ref: string; name: string }[]; history: AuditEntry[]; historyVisible: boolean;
};

const CHANNELS: [string, string][] = [["Phone", "Phone"], ["Email", "Email"], ["WhatsApp", "WhatsApp"]];

type Fields = { names: string; organisation: string; email: string; phone: string; channel: string; kind: string; enquiringFor: string;
  courseCode: string; interest: string; ownerRef: string; notes: string; topics: string[]; topicOther: string };

function fieldsOf(d: Detail): Fields {
  return { names: d.name, organisation: d.org, email: d.email, phone: d.phone, channel: d.channel, kind: d.kind, enquiringFor: d.enquiringFor,
    courseCode: d.courseCode, interest: d.interest, ownerRef: d.ownerRef, notes: d.notes,
    topics: d.topics, topicOther: d.topicOther };
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? "") === JSON.stringify(b ?? "");

/** Saving closes the window and hands the audit sentence to `onSaved`, for the page to confirm.
 *  A refused save keeps the window open with the reasons. */
export function EnquiryEditor({ enquiryRef, onClose, onSaved }: {
  enquiryRef: string; onClose: () => void; onSaved?: (what: string) => void;
}) {
  const q = useRegister<Detail>(`/enquiries/${enquiryRef}`);
  const courses = useRegister<{ code: string; title: string }[]>("/courses");
  // Owned here, not by the form: the form is rebuilt when the saved values reload, and a save
  // whose owner has gone would lose its confirmation.
  const save = useAction<Partial<Fields>, Detail>("PATCH", `/enquiries/${enquiryRef}`);
  if (q.error) return <Blocked refusal={q.error} title="This enquiry could not be opened" />;
  if (!q.data) return <p className="muted">Opening {enquiryRef}…</p>;
  return (
    <Form key={JSON.stringify(fieldsOf(q.data.data))} d={q.data.data} courses={courses.data?.data ?? []} save={save}
          onClose={onClose} onSaved={(what) => { onSaved?.(what); onClose(); }} />
  );
}

function Form({ d, courses, save, onClose, onSaved }: {
  d: Detail; courses: { code: string; title: string }[]; save: ReturnType<typeof useAction<Partial<Fields>, Detail>>;
  onClose: () => void; onSaved: (what: string) => void;
}) {
  const original = fieldsOf(d);
  const [f, setF] = useState<Fields>(original);
  const set = (k: keyof Fields, v: string) => setF((x) => ({ ...x, [k]: v }));
  const changed = (Object.keys(f) as (keyof Fields)[]).filter((k) => !same(f[k], original[k]));
  const ro = !d.canEdit;
  // Required fields, checked as you type so Save is only offered when the enquiry can be saved.
  // The API checks the same rules again.
  const errors: Partial<Record<"names" | "email" | "topics" | "topicOther" | "interest" | "organisation", string>> = {};
  if (f.kind === "Enquiry" && f.enquiringFor === "Company" && !f.organisation.trim()) errors.organisation = "Give the company's name.";
  if (!f.names.trim()) errors.names = "Enter the enquirer's name.";
  if (f.email.trim() && !f.email.includes("@")) errors.email = "Enter a valid email address, or leave it blank.";
  if (f.kind === "Enquiry") {
    if (!same(f.topics, original.topics) && !f.topics.length) errors.topics = "Tick at least one thing they asked about.";
    if (f.topics.includes("Other") && !f.topicOther.trim()) errors.topicOther = "Describe the other question they asked.";
  } else if (!f.interest.trim()) errors.interest = `Describe the ${f.kind.toLowerCase()}.`;
  const blocked = Object.keys(errors).length > 0;

  function submit() {
    const body: Record<string, unknown> = {};
    changed.forEach((k) => { body[k] = f[k]; });
    // topics and their "Other" text travel together, so the API can check them as a pair
    if (changed.includes("topics") || changed.includes("topicOther")) { body.topics = f.topics; body.topicOther = f.topicOther; }
    save.mutate(body as Partial<Fields>, { onSuccess: (r) => onSaved(r.meta.audit?.what ?? "") });
  }

  return (
    <div className="stack-12">
      <div className="row" style={{ gap: 14 }}>
        <span className="mono">{d.ref}</span>
        <Status tone={d.stale ? "bad" : "info"}>{d.stage}</Status>
        <span className="small muted">
          Received {d.receivedAt}
          {d.updatedAt && d.updatedAt !== d.receivedAt ? <> · Last updated {d.updatedAt}{d.updatedBy ? ` by ${d.updatedBy}` : ""}</> : null}
          {" · "}{d.clockText}
        </span>
        {d.enrolment ? <span className="small muted">Registered as <span className="mono">{d.enrolment}</span></span> : null}
      </div>
      <Blocked refusal={save.refusal} />

      <div className="eyebrow">Enquirer</div>
      <div className="form-grid">
        <div className="field"><label htmlFor="ee-name">Name</label>
          <input id="ee-name" value={f.names} readOnly={ro} onChange={(e) => set("names", e.target.value)}
                 className={errors.names ? "invalid" : undefined} aria-invalid={!!errors.names} />
          {errors.names ? <span className="field-error">{errors.names}</span> : null}</div>
        {f.kind === "Enquiry" ? (
          <div className="field"><label htmlFor="ee-for">Enquiring for</label>
            <select id="ee-for" value={f.enquiringFor} disabled={ro || d.forLocked} onChange={(e) => set("enquiringFor", e.target.value)}>
              <option value="Company">A company: its staff or a group</option>
              <option value="Individual">Themselves, as an individual</option>
            </select>
            {d.forLocked ? <span className="small muted">A quotation exists, so this stays a company enquiry.</span> : null}</div>
        ) : null}
        <div className="field"><label htmlFor="ee-org">{f.kind === "Enquiry" && f.enquiringFor === "Company" ? "Company"
            : f.kind === "Enquiry" ? <>Employer <span className="optional">(optional)</span></> : <>Organisation <span className="optional">(optional)</span></>}</label>
          <input id="ee-org" value={f.organisation} readOnly={ro} onChange={(e) => set("organisation", e.target.value)}
                 className={errors.organisation ? "invalid" : undefined} />
          {errors.organisation ? <span className="field-error">{errors.organisation}</span> : null}</div>
        <div className="field"><label htmlFor="ee-email">Email <span className="optional">(optional)</span></label>
          <input id="ee-email" type="email" value={f.email} readOnly={ro} onChange={(e) => set("email", e.target.value)}
                 className={errors.email ? "invalid" : undefined} aria-invalid={!!errors.email} />
          {errors.email ? <span className="field-error">{errors.email}</span> : null}</div>
        <div className="field"><label htmlFor="ee-phone">Phone <span className="optional">(optional)</span></label>
          <PhoneInput id="ee-phone" value={f.phone} readOnly={ro} onChange={(v) => set("phone", v)} /></div>
      </div>

      <div className="eyebrow">Enquiry</div>
      <div className="form-grid">
        <div className="field"><label htmlFor="ee-channel">Channel</label>
          <select id="ee-channel" value={f.channel} disabled={ro} onChange={(e) => set("channel", e.target.value)}>
            {CHANNELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select></div>
        <div className="field"><label htmlFor="ee-kind">Kind</label>
          <select id="ee-kind" value={f.kind} disabled={ro || d.kindLocked} onChange={(e) => set("kind", e.target.value)}>
            <option>Enquiry</option><option>Complaint</option><option>Opportunity</option>
          </select>
          {d.kindLocked ? <span className="small muted">A learner is registered, so this stays a course enquiry.</span> : null}</div>
        <div className="field"><label htmlFor="ee-course">Course</label>
          <SearchSelect id="ee-course" options={courseOptions(courses, "Not a catalogue course")} value={f.courseCode}
                        disabled={ro || d.courseLocked} placeholder="Type to search courses…" emptyText="No course matches"
                        onChange={(v) => set("courseCode", v)} />
          {d.courseLocked ? <span className="small muted">Locked: change the course on the enrolment.</span> : null}</div>
        {f.kind === "Enquiry" && !f.courseCode ? (
          <div className="field"><label htmlFor="ee-interest">Course not in the catalogue (optional)</label>
            <input id="ee-interest" value={f.interest} readOnly={ro} placeholder="Which training they meant"
                   onChange={(e) => set("interest", e.target.value)} /></div>
        ) : null}
        <div className="field"><label htmlFor="ee-owner">Owner</label>
          <select id="ee-owner" value={f.ownerRef} disabled={ro} onChange={(e) => set("ownerRef", e.target.value)}>
            <option value="">Unassigned</option>
            {d.owners.map((o) => <option key={o.ref} value={o.ref}>{o.name}</option>)}
          </select></div>
      </div>
      {f.kind === "Enquiry" ? (
        <div className="field"><label>What they asked about</label>
          <TopicPicker idPrefix="ee-topic" topics={f.topics} other={f.topicOther} readOnly={ro}
                       otherError={errors.topicOther}
                       onChange={(topics, other) => setF((x) => ({ ...x, topics, topicOther: other }))} />
          {errors.topics ? <span className="field-error">{errors.topics}</span> : null}</div>
      ) : (
        <div className="field"><label htmlFor="ee-details">Details of the {f.kind.toLowerCase()}</label>
          <textarea id="ee-details" rows={2} value={f.interest} readOnly={ro} onChange={(e) => set("interest", e.target.value)}
                    style={{ fontFamily: "var(--font-sans)" }} className={errors.interest ? "invalid" : undefined} />
          {errors.interest ? <span className="field-error">{errors.interest}</span> : null}</div>
      )}
      <div className="field"><label htmlFor="ee-notes">Additional remarks</label>
        <textarea id="ee-notes" rows={4} value={f.notes} readOnly={ro} onChange={(e) => set("notes", e.target.value)}
                  placeholder="What was discussed, what was promised, when to call back." style={{ fontFamily: "var(--font-sans)" }} /></div>

      {!ro ? (
        <div className="row">
          <button className="btn btn-primary" disabled={!changed.length || blocked || save.isPending} onClick={submit}>
            <i className="fas fa-save" aria-hidden /> {save.isPending ? "Saving…" : "Save changes"}
          </button>
          <button className="btn btn-light" disabled={!changed.length} onClick={() => { setF(original); save.clear(); }}>Undo edits</button>
          <span className="small muted">
            {blocked ? <span className="tone-bad">Fill in the highlighted {Object.keys(errors).length === 1 ? "field" : "fields"} to save.</span>
              : changed.length ? `${changed.length} ${changed.length === 1 ? "field" : "fields"} changed. Each change is audited with its previous value.`
              : "The received time and stage are not edited here: the time drives the response clock, and the stage moves on the board."}
          </span>
          <span className="spacer" />
          <button className="btn btn-light" onClick={onClose}>Close</button>
        </div>
      ) : <p className="small muted" style={{ margin: 0 }}>Your role can view enquiries but not change them.</p>}

      {d.historyVisible ? (
        <>
          <div className="eyebrow">History</div>
          <div className="audit">
            {d.history.length ? d.history.map((a, i) => (
              <div className="audit-row" key={`${a.at}-${i}`}>
                <span className="when">{a.at}</span><span>{a.what}</span><span className="who">{a.who}</span>
              </div>
            )) : <div className="audit-empty">No changes recorded for this enquiry yet.</div>}
          </div>
        </>
      ) : null}
    </div>
  );
}
