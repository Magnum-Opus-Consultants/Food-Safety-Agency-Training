"use client";

// Planning an intake: add one, change it, cancel it, and see who to tell when it moves. Only the head
// of department (training manager) plans; the API refuses anyone else.

import { useState } from "react";
import { Blocked } from "@/components/ui";
import { courseOptions, SearchSelect } from "@/components/SearchSelect";
import { ApiError } from "@/lib/api";
import { useAction, useRegister } from "@/lib/hooks";

type Options = {
  courses: { code: string; title: string; days: number; mode: string }[];
  facilitators: { ref: string; name: string; role: string }[];
  venues: { id: number; name: string }[];
  modes: string[]; cadences: string[]; canPlan: boolean;
};
export type Affected = { enrolment: string; learner: string; learnerRef: string; email: string; phone: string; company: string; companyContact: string };
export type IntakeValues = {
  courseCode: string; facilitatorRef: string; venueId: number | null; newVenue: string; mode: string; cadence: string;
  start: string; end: string; capacity: string; hours: string; notes: string;
  schedule: string; weekdays: number[]; startsAt: string; endsAt: string;
};

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** The meetings the schedule makes (public holidays are skipped when it is saved). */
function meetings(schedule: string, weekdays: number[], start: string, end: string) {
  if (!start) return 0;
  if (schedule === "Single") return 1;
  if (!end || end < start) return 0;
  const days = schedule === "Weekly" ? weekdays : [0, 1, 2, 3, 4];
  let n = 0;
  for (let d = new Date(start + "T00:00:00"); d <= new Date(end + "T00:00:00"); d.setDate(d.getDate() + 1)) {
    if (days.includes((d.getDay() + 6) % 7)) n++;
  }
  return n;
}

const CADENCE_LABEL: Record<string, string> = { AdHoc: "Ad hoc", Monthly: "Monthly", Quarterly: "Quarterly" };
const NEW_VENUE = -1;

export function usePlanOptions() {
  return useRegister<Options>("/plan/options");
}

function addDays(iso: string, days: number) {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/** The intake form. `refCode` set means editing that intake; `learners` is how many are registered on it. */
export function IntakeForm({ initial, refCode, learners = 0, onDone, onCancel }: {
  initial?: IntakeValues; refCode?: string; learners?: number;
  onDone: (what: string, affected: Affected[]) => void; onCancel: () => void;
}) {
  const opts = usePlanOptions();
  const save = useAction<Record<string, unknown>>(refCode ? "PATCH" : "POST", refCode ? `/plan/${refCode}` : "/plan");
  const [f, setF] = useState<IntakeValues>(initial ?? { courseCode: "", facilitatorRef: "", venueId: null, newVenue: "", mode: "", cadence: "AdHoc",
    start: "", end: "", capacity: "", hours: "0", notes: "", schedule: "Block", weekdays: [], startsAt: "", endsAt: "" });
  const [reason, setReason] = useState("");
  const [tried, setTried] = useState(false);
  if (!opts.data) return <p className="muted">Loading…</p>;
  const o = opts.data.data;
  const set = (k: keyof IntakeValues, v: string | number | null) => setF((x) => ({ ...x, [k]: v }));
  const today = new Date().toISOString().slice(0, 10);

  const moving = refCode && initial && learners > 0 &&
    (f.start !== initial.start || f.end !== initial.end || f.facilitatorRef !== initial.facilitatorRef
      || f.venueId !== initial.venueId || f.newVenue.trim() !== "");
  const p: Record<string, string> = {};
  if (!f.courseCode) p.course = "Choose the course.";
  if (!f.facilitatorRef) p.facilitator = "Choose the facilitator.";
  if (f.venueId === null && !f.newVenue.trim()) p.venue = "Choose the venue.";
  if (f.venueId === NEW_VENUE && !f.newVenue.trim()) p.venue = "Type the new venue's name.";
  if (!f.mode) p.mode = "Choose how it is delivered.";
  if (!f.start) p.start = "Give the start date.";
  else if (f.start < today && (!initial || f.start !== initial.start)) p.start = "It cannot start in the past.";
  if (f.schedule !== "Single") {
    if (!f.end) p.end = "Give the end date.";
    else if (f.start && f.end < f.start) p.end = "The end is before the start.";
  }
  if (f.schedule === "Weekly" && !f.weekdays.length) p.weekdays = "Choose the days the class meets.";
  if (f.startsAt && f.endsAt && f.endsAt <= f.startsAt) p.endsAt = "The class ends before it starts.";
  const count = meetings(f.schedule, f.weekdays, f.start, f.schedule === "Single" ? f.start : f.end);
  if (!p.start && !p.end && !p.weekdays && count === 0) p.weekdays = "No meeting falls between those dates on the days chosen.";
  const cap = Number(f.capacity);
  if (!Number.isInteger(cap) || cap < 1) p.capacity = "Give the number of seats.";
  else if (cap < learners) p.capacity = `${learners} learners are registered, so at least ${learners} seats.`;
  if (moving && !reason.trim()) p.reason = "Give the reason; the registered learners will need to be told.";
  const e = tried ? p : {};
  const cls = (k: string) => (e[k] ? "invalid" : undefined);
  const Err = ({ k }: { k: string }) => (e[k] ? <span className="field-error">{e[k]}</span> : null);

  function pickCourse(code: string) {
    const c = o.courses.find((x) => x.code === code);
    setF((x) => ({ ...x, courseCode: code, mode: x.mode || (c && o.modes.includes(c.mode) ? c.mode : x.mode),
      end: x.start && c && !x.end ? addDays(x.start, Math.max(c.days - 1, 0)) : x.end }));
  }

  return (
    <div className="stack-12">
      <Blocked refusal={save.refusal as ApiError | null} />
      <div className="form-grid cols-4">
        <div className="field"><label htmlFor="in-course">Course</label>
          <SearchSelect id="in-course" options={courseOptions(o.courses)} value={f.courseCode} invalid={!!e.course}
                        placeholder="Type to search courses…" emptyText="No course matches" onChange={pickCourse} /><Err k="course" /></div>
        <div className="field"><label htmlFor="in-fac">Facilitator</label>
          <SearchSelect id="in-fac" value={f.facilitatorRef} invalid={!!e.facilitator} placeholder="Type to search facilitators…"
                        emptyText="No facilitator matches" onChange={(v) => set("facilitatorRef", v)}
                        options={o.facilitators.map((a) => ({ value: a.ref, label: a.name, hint: a.role }))} /><Err k="facilitator" /></div>
        <div className="field"><label htmlFor="in-venue">Venue</label>
          <SearchSelect id="in-venue" value={f.venueId === null ? "" : String(f.venueId)} invalid={!!e.venue} placeholder="Type to search venues…"
                        emptyText="No venue matches" onChange={(v) => setF((x) => ({ ...x, venueId: v ? Number(v) : null, newVenue: "" }))}
                        options={[...o.venues.map((v) => ({ value: String(v.id), label: v.name })), { value: String(NEW_VENUE), label: "+ A new venue" }]} />
          {f.venueId === NEW_VENUE ? <input aria-label="New venue" placeholder="Name of the new venue" value={f.newVenue}
                                            className={cls("venue")} onChange={(x) => set("newVenue", x.target.value)} style={{ marginTop: 6 }} /> : null}
          <Err k="venue" /></div>
        <div className="field"><label htmlFor="in-mode">Delivery</label>
          <select id="in-mode" value={f.mode} className={cls("mode")} onChange={(x) => set("mode", x.target.value)}>
            <option value="">Choose…</option>{o.modes.map((m) => <option key={m}>{m}</option>)}
          </select><Err k="mode" /></div>
        <div className="field"><label htmlFor="in-sched">How the class meets</label>
          <select id="in-sched" value={f.schedule} onChange={(x) => setF((y) => ({ ...y, schedule: x.target.value, end: x.target.value === "Single" ? y.start : y.end }))}>
            <option value="Block">Every weekday, start to end</option>
            <option value="Weekly">Set days each week</option>
            <option value="Single">One day</option>
          </select></div>
        <div className="field"><label htmlFor="in-start">{f.schedule === "Single" ? "Date" : "Starts"}</label>
          <input id="in-start" type="date" value={f.start} className={cls("start")} onChange={(x) => {
            const v = x.target.value;
            const c = o.courses.find((cc) => cc.code === f.courseCode);
            setF((y) => ({ ...y, start: v, end: !y.end && c && v ? addDays(v, Math.max(c.days - 1, 0)) : y.end }));
          }} /><Err k="start" /></div>
        {f.schedule !== "Single" ? (
          <div className="field"><label htmlFor="in-end">Ends</label>
            <input id="in-end" type="date" value={f.end} min={f.start || undefined} className={cls("end")} onChange={(x) => set("end", x.target.value)} /><Err k="end" /></div>
        ) : null}
        <div className="field"><label htmlFor="in-from">Class from <span className="optional">(optional)</span></label>
          <input id="in-from" type="time" value={f.startsAt} onChange={(x) => set("startsAt", x.target.value)} /></div>
        <div className="field"><label htmlFor="in-to">to <span className="optional">(optional)</span></label>
          <input id="in-to" type="time" value={f.endsAt} className={cls("endsAt")} onChange={(x) => set("endsAt", x.target.value)} /><Err k="endsAt" /></div>
        <div className="field"><label htmlFor="in-cap">Seats</label>
          <input id="in-cap" inputMode="numeric" value={f.capacity} className={cls("capacity")} onChange={(x) => set("capacity", x.target.value)} /><Err k="capacity" /></div>
        <div className="field"><label htmlFor="in-cad">How often it runs</label>
          <select id="in-cad" value={f.cadence} onChange={(x) => set("cadence", x.target.value)}>
            {o.cadences.map((c) => <option key={c} value={c}>{CADENCE_LABEL[c] ?? c}</option>)}
          </select></div>
        <div className="field"><label htmlFor="in-hours" title="Supervised practical hours">Practical hours <span className="optional">(optional)</span></label>
          <input id="in-hours" inputMode="numeric" value={f.hours} onChange={(x) => set("hours", x.target.value)} /></div>
      </div>
      {f.schedule === "Weekly" ? (
        <div className="field"><label>Days of the week</label>
          <div className="day-picks" role="group" aria-label="Days of the week">
            {DAYS.map((d, i) => (
              <button key={d} type="button" className={f.weekdays.includes(i) ? "on" : undefined} aria-pressed={f.weekdays.includes(i)}
                      onClick={() => setF((y) => ({ ...y, weekdays: y.weekdays.includes(i) ? y.weekdays.filter((w) => w !== i) : [...y.weekdays, i].sort() }))}>{d}</button>
            ))}
          </div><Err k="weekdays" /></div>
      ) : e.weekdays ? <Err k="weekdays" /> : null}
      {count > 0 ? (
        <p className="small" style={{ margin: 0 }}><i className="fas fa-calendar-check" aria-hidden /> This makes <b>{count} {count === 1 ? "session" : "sessions"}</b>
          {f.schedule === "Weekly" ? ` (${f.weekdays.map((i) => DAYS[i]).join(" and ")})` : f.schedule === "Block" ? " (every weekday)" : ""}, each with its own register.
          {f.schedule !== "Single" ? " Public holidays are left out." : ""}</p>
      ) : null}
      <div className="field"><label htmlFor="in-notes">Notes <span className="optional">(optional)</span></label>
        <input id="in-notes" value={f.notes} placeholder="e.g. Group intake for QTE-0224; student list awaited" onChange={(x) => set("notes", x.target.value)} /></div>
      {moving ? (
        <div className="field"><label htmlFor="in-reason">Reason for the change ({learners} {learners === 1 ? "learner is" : "learners are"} registered)</label>
          <input id="in-reason" value={reason} className={cls("reason")} placeholder="e.g. Facilitator on leave; venue unavailable"
                 onChange={(x) => setReason(x.target.value)} /><Err k="reason" /></div>
      ) : null}
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending} onClick={() => {
          setTried(true);
          if (Object.keys(p).length) return;
          save.mutate({ ...f, end: f.schedule === "Single" ? f.start : f.end, startsAt: f.startsAt || null, endsAt: f.endsAt || null,
            venueId: f.venueId === NEW_VENUE ? null : f.venueId, newVenue: f.venueId === NEW_VENUE ? f.newVenue : "",
            capacity: cap, hours: Number(f.hours) || 0, reason },
          { onSuccess: (r) => onDone(r.meta.audit?.what ?? "", (r.meta.affected as Affected[] | undefined) ?? []) });
        }}>{refCode ? "Save changes" : "Add intake as a draft"}</button>
        <button className="btn" onClick={onCancel}>Cancel</button>
        {!refCode ? <span className="small muted">It is added as a draft; confirm it once the facilitator and venue are settled.</span> : null}
      </div>
    </div>
  );
}

/** Who is registered and how to reach them, with one click to email them all. */
export function LearnerContacts({ list, title }: { list: Affected[]; title: string }) {
  if (!list.length) return null;
  const emails = Array.from(new Set(list.flatMap((a) => [a.email, a.companyContact.split(" ").find((w) => w.includes("@")) ?? ""]).filter(Boolean)));
  return (
    <div className="stack-12">
      <div className="row"><div className="eyebrow">{title}</div><span className="spacer" />
        {emails.length ? <a className="btn btn-sm" href={`mailto:?bcc=${encodeURIComponent(emails.join(","))}`}><i className="fas fa-envelope" aria-hidden /> Email all ({emails.length})</a> : null}
      </div>
      <table className="plain-table">
        <thead><tr><th>Learner</th><th>Email</th><th>Phone</th><th>Company · contact</th></tr></thead>
        <tbody>
          {list.map((a) => (
            <tr key={a.enrolment}>
              <td>{a.learner} <span className="muted small">{a.enrolment}</span></td>
              <td>{a.email ? <a href={`mailto:${a.email}`}>{a.email}</a> : "—"}</td>
              <td>{a.phone || "—"}</td>
              <td>{a.company ? `${a.company}${a.companyContact ? ` · ${a.companyContact}` : ""}` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Cancelling asks for the reason; the learners on it are listed to be told and moved. */
export function CancelIntake({ refCode, onDone, onClose }: { refCode: string; onDone: (what: string, affected: Affected[]) => void; onClose: () => void }) {
  const cancel = useAction<{ reason: string }>("POST", `/plan/${refCode}/cancel`);
  const [reason, setReason] = useState("");
  const [tried, setTried] = useState(false);
  return (
    <div className="card inset-form">
      <Blocked refusal={cancel.refusal} />
      <div className="field"><label htmlFor={`cx-${refCode}`}>Why is {refCode} being cancelled?</label>
        <input id={`cx-${refCode}`} value={reason} className={tried && !reason.trim() ? "invalid" : undefined}
               placeholder="e.g. Too few learners; facilitator unavailable" onChange={(e) => setReason(e.target.value)} />
        {tried && !reason.trim() ? <span className="field-error">Give the reason.</span> : null}</div>
      <div className="row">
        <button className="btn btn-danger" disabled={cancel.isPending} onClick={() => {
          setTried(true);
          if (!reason.trim()) return;
          cancel.mutate({ reason }, { onSuccess: (r) => onDone(r.meta.audit?.what ?? "", (r.meta.affected as Affected[] | undefined) ?? []) });
        }}>Cancel the intake</button>
        <button className="btn" onClick={onClose}>Keep it</button>
        <span className="small muted">A cancelled intake stays on record and takes no new registrations.</span>
      </div>
    </div>
  );
}
