"use client";

import { useEffect, useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, SectionHead, Stat, Status } from "@/components/ui";
import type { Tone } from "@/lib/api";
import { useAction, useFocusRef, useMe, useRegister } from "@/lib/hooks";
import { DelegatesForm, Modal, RegisterLearnerForm } from "@/components/registration";
import { EnquiryEditor } from "@/components/EnquiryEditor";
import { PhoneInput } from "@/components/PhoneInput";
import { TopicPicker } from "@/components/TopicPicker";
import { NewQuotationForm } from "@/components/QuoteForm";
import { courseOptions, SearchSelect } from "@/components/SearchSelect";

type Enquiry = {
  ref: string; name: string; org: string; course: string; kind: string; channel: string; workingDaysOpen: number;
  stageIndex: number; stage: string; owner: string | null; tone: Tone; stale: boolean;
  courseCode: string; email: string; phone: string; enrolment: string | null;
  topicLabels: string[]; clockText: string; carriedOver: boolean; receivedOn: string; orgRef: string; contactRef: string; enquiringFor: string;
  quotations: { ref: string; value: string; learners: number; registered: number; state: string; course: string; courseCode: string;
    client: string; needsApproval: boolean; canAddDelegates: boolean }[];
};

type Period = { kind: Kind; start: string; end: string; current: boolean; previous: string; next: string; carriedOver: number };
type Kind = "week" | "month" | "year";
const KINDS: [Kind, string][] = [["week", "Week"], ["month", "Month"], ["year", "Year"]];
const THIS: Record<Kind, string> = { week: "This week", month: "This month", year: "This year" };

function periodTitle(p: Period) {
  const d = new Date(p.start + "T00:00:00");
  if (p.kind === "year") return String(d.getFullYear());
  if (p.kind === "month") return d.toLocaleDateString("en-ZA", { month: "long", year: "numeric" });
  return `Week of ${dayMonth(p.start)} – ${dayMonth(p.end, true)}`;
}

function dayMonth(iso: string, year = false) {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { day: "numeric", month: "short", ...(year ? { year: "numeric" } : {}) });
}

const QUOTED = 2;
const REGISTERED = 3;

const CHANNELS = [["Phone", "Phone"], ["Email", "Email"], ["WhatsApp", "WhatsApp"]];

export default function EnquiryQueue() {
  // The board shows one period at a time, a week by default ("" is the current one); a search looks
  // across every period.
  const [kind, setKind] = useState<Kind>("week");
  const [week, setWeek] = useState("");
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const t = window.setTimeout(() => setSearch(searchText.trim()), 300);
    return () => window.clearTimeout(t);
  }, [searchText]);
  const params = new URLSearchParams();
  if (kind !== "week") params.set("period", kind);
  if (week) params.set("date", week);
  if (search) params.set("q", search);
  const query = params.toString();
  const q = useRegister<{ stages: string[]; items: Enquiry[]; stats: Stat[]; askedThisMonth: { label: string; n: number }[] }>(
    `/enquiries${query ? `?${query}` : ""}`);
  // Keep showing the last board while the next week loads, rather than flashing a loading screen.
  const [last, setLast] = useState(q.data);
  useEffect(() => { if (q.data) setLast(q.data); }, [q.data]);
  const data = q.data ?? last;
  const courses = useRegister<{ code: string; title: string }[]>("/courses");
  const me = useMe();
  const move = useAction<{ ref: string; stageIndex: number }>("PATCH", (v) => `/enquiries/${v.ref}/stage`);
  const log = useAction<Record<string, string | string[]>>("POST", "/enquiries");
  const [drag, setDrag] = useState<string | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const [form, setForm] = useState<Record<string, string> | null>(null);
  const [formTopics, setFormTopics] = useState<{ topics: string[]; other: string }>({ topics: [], other: "" });
  const [registering, setRegistering] = useState<Enquiry | null>(null);
  const [quoting, setQuoting] = useState<Enquiry | null>(null);
  const [delegatesFor, setDelegatesFor] = useState<Enquiry["quotations"][number] | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const focus = useFocusRef();
  // Arriving from the desk (?focus=ENQ-0423): the card is highlighted on the board, not opened. An
  // enquiry outside the week on screen is found by searching for it.
  const [scrolled, setScrolled] = useState(false);
  const [looked, setLooked] = useState(false);
  useEffect(() => {
    if (!focus || looked || !q.data) return;
    setLooked(true);
    if (!q.data.data.items.some((e) => e.ref === focus)) setSearchText(focus);
  }, [focus, looked, q.data]);
  useEffect(() => {
    if (!focus || scrolled) return;
    const el = document.getElementById(`card-${focus}`);
    if (el) { el.scrollIntoView({ behavior: "smooth", block: "center" }); setScrolled(true); }
  });
  const [notice, setNotice] = useState("");

  if (q.error) return <LoadError error={q.error} />;
  if (!data) return <Loading what="enquiry queue" />;
  const { stages, items, stats, askedThisMonth } = data.data;
  const wk = data.meta.period as Period;
  const unit = wk.kind;
  const logErrors: Record<string, string> = {};
  if (form) {
    if (!(form.names ?? "").trim()) logErrors.names = "Enter the enquirer's name.";
    if (form.kind === "Enquiry" && !form.enquiringFor) logErrors.enquiringFor = "Say whether they are enquiring for a company or for themselves.";
    if (form.kind === "Enquiry" && form.enquiringFor === "Company" && !(form.organisation ?? "").trim()) logErrors.organisation = "Give the company's name.";
    if ((form.email ?? "").trim() && !(form.email ?? "").includes("@")) logErrors.email = "Enter a valid email address, or leave it blank.";
    if (form.kind === "Enquiry") {
      if (!formTopics.topics.length) logErrors.topics = "Tick at least one thing they asked about.";
      if (formTopics.topics.includes("Other") && !formTopics.other.trim()) logErrors.topicOther = "Describe the other question they asked.";
    } else if (!(form.interest ?? "").trim()) logErrors.interest = `Describe the ${(form.kind ?? "").toLowerCase()}.`;
  }
  const logBlocked = Object.keys(logErrors).length > 0;
  const canWrite = me.data?.data.writes.includes("demand") ?? false;
  // The board carries course enquiries. A complaint or opportunity appears only when a link points at it.
  const enquiries = items.filter((e) => e.kind === "Enquiry" || e.ref === focus);

  function drop(stageIndex: number) {
    const ref = drag;
    setDrag(null);
    setOver(null);
    const card = enquiries.find((e) => e.ref === ref);
    if (card && card.stageIndex !== stageIndex) toStage(card, stageIndex);
  }

  // Quoted means a quotation exists, and Registered that a learner exists: moving there opens the
  // quotation or the registration instead of moving the card.
  function toStage(card: Enquiry, stageIndex: number) {
    const open = card.quotations.find((qt) => qt.canAddDelegates);
    if (stageIndex === QUOTED && !card.quotations.length) {
      move.clear();
      setQuoting(card);
    } else if (stageIndex === REGISTERED && card.enquiringFor === "Company" && open) {
      move.clear();
      setDelegatesFor(open);
    } else if (stageIndex === REGISTERED && card.enquiringFor === "Individual" && !card.enrolment) {
      move.clear();
      setRegistering(card);
    } else move.mutate({ ref: card.ref, stageIndex });
  }

  return (
    <>
      <Hero
        title="A shared queue, not an individual's inbox."
        statement="Enquiries arrive by phone, email and WhatsApp and route to the admin rotation; open a card to change its owner. Drag a card to change its stage. The two-working-day response clock stops on first response."
        stats={stats}
      />
      <Blocked refusal={move.refusal ?? log.refusal} />
      {notice ? (
        <div className="callout ok" role="status">
          <div className="row" style={{ alignItems: "flex-start" }}>
            <p style={{ flex: 1 }}><b>Saved.</b> {notice}</p>
            <button className="btn btn-ghost btn-sm" onClick={() => setNotice("")} aria-label="Dismiss">
              <i className="fas fa-times" aria-hidden />
            </button>
          </div>
        </div>
      ) : null}
      <SectionHead title="Enquiry board">
        {canWrite ? <button className="btn btn-teal" onClick={() => { setFormTopics({ topics: [], other: "" }); setForm(form ? null : { channel: "Phone", kind: "Enquiry" }); }}>Log enquiry</button> : null}
      </SectionHead>
      {form ? (
        <div className="card" style={{ padding: 16, display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="form-grid">
            <div className="field"><label htmlFor="n">Enquirer</label><input id="n" value={form.names ?? ""} onChange={(e) => setForm({ ...form, names: e.target.value })} className={logErrors.names ? "invalid" : undefined} />
              {logErrors.names ? <span className="field-error">{logErrors.names}</span> : null}</div>
            {form.kind === "Enquiry" ? (
              <div className="field"><label htmlFor="ef">Enquiring for</label>
                <select id="ef" value={form.enquiringFor ?? ""} className={logErrors.enquiringFor ? "invalid" : undefined}
                        onChange={(e) => setForm({ ...form, enquiringFor: e.target.value })}>
                  <option value="">Choose…</option>
                  <option value="Company">A company: its staff or a group</option>
                  <option value="Individual">Themselves, as an individual</option>
                </select>
                {logErrors.enquiringFor ? <span className="field-error">{logErrors.enquiringFor}</span>
                  : <span className="small muted">{form.enquiringFor === "Company" ? "Quoted, and kept on the company's account."
                    : form.enquiringFor === "Individual" ? "Registered directly; never quoted." : ""}</span>}</div>
            ) : null}
            <div className="field"><label htmlFor="o">{form.kind === "Enquiry" && form.enquiringFor === "Company" ? "Company"
                : form.kind === "Enquiry" && form.enquiringFor === "Individual" ? <>Employer <span className="optional">(optional)</span></>
                : <>Organisation <span className="optional">(optional)</span></>}</label>
              <input id="o" value={form.organisation ?? ""} className={logErrors.organisation ? "invalid" : undefined}
                     placeholder={form.enquiringFor === "Individual" ? "Where they work, if they say" : undefined}
                     onChange={(e) => setForm({ ...form, organisation: e.target.value })} />
              {logErrors.organisation ? <span className="field-error">{logErrors.organisation}</span> : null}</div>
            <div className="field"><label htmlFor="ph">Phone <span className="optional">(optional)</span></label><PhoneInput id="ph" value={form.phone ?? ""} onChange={(v) => setForm({ ...form, phone: v })} /></div>
            <div className="field"><label htmlFor="em">Email <span className="optional">(optional)</span></label><input id="em" type="email" value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} className={logErrors.email ? "invalid" : undefined} />
              {logErrors.email ? <span className="field-error">{logErrors.email}</span> : null}</div>
            <div className="field"><label htmlFor="c">Channel</label>
              <select id="c" value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
                {CHANNELS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></div>
            <div className="field"><label htmlFor="k">Kind</label>
              <select id="k" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                <option>Enquiry</option><option>Complaint</option><option>Opportunity</option>
              </select></div>
            <div className="field"><label htmlFor="cc">Course</label>
              <SearchSelect id="cc" options={courseOptions(courses.data?.data ?? [], "Not a catalogue course")} value={form.courseCode ?? ""}
                            placeholder="Type to search courses…" emptyText="No course matches"
                            onChange={(v) => setForm({ ...form, courseCode: v })} /></div>
            {form.kind === "Enquiry" && !form.courseCode ? (
              <div className="field"><label htmlFor="i">Course not in the catalogue (optional)</label><input id="i" value={form.interest ?? ""} placeholder="Which training they meant" onChange={(e) => setForm({ ...form, interest: e.target.value })} /></div>
            ) : null}
          </div>
          {form.kind === "Enquiry" ? (
            <div className="field"><label>What they asked about</label>
              <TopicPicker idPrefix="log-topic" topics={formTopics.topics} other={formTopics.other} otherError={logErrors.topicOther}
                           onChange={(topics, other) => setFormTopics({ topics, other })} />
              {logErrors.topics ? <span className="field-error">{logErrors.topics}</span> : null}</div>
          ) : (
            <div className="field"><label htmlFor="i">Details of the {(form.kind ?? "").toLowerCase()}</label>
              <textarea id="i" rows={2} value={form.interest ?? ""} onChange={(e) => setForm({ ...form, interest: e.target.value })}
                        style={{ fontFamily: "var(--font-sans)" }} className={logErrors.interest ? "invalid" : undefined} />
              {logErrors.interest ? <span className="field-error">{logErrors.interest}</span> : null}</div>
          )}
          <div className="row">
            <button className="btn btn-primary" disabled={log.isPending || logBlocked} onClick={() => log.mutate({ ...form, topics: formTopics.topics, topicOther: formTopics.other }, { onSuccess: () => { setForm(null); setWeek(""); setSearchText(""); } })}>Log and route</button>
            <button className="btn" onClick={() => setForm(null)}>Cancel</button>
            <span className="small muted">{logBlocked ? <span className="tone-bad">Fill in the highlighted fields to log this.</span>
              : "Complaints and opportunities go straight to the head of department\u2019s desk."}</span>
          </div>
        </div>
      ) : null}
      {askedThisMonth.some((a) => a.n) ? (
        <div className="asked-row">
          <span className="asked-label">Asked about this month</span>
          {askedThisMonth.filter((a) => a.n).sort((a, b) => b.n - a.n).map((a) => (
            <span key={a.label} className="asked-chip">{a.label} <b>{a.n}</b></span>
          ))}
        </div>
      ) : null}
      <div className="card week-bar" aria-label="Choose the week">
        {search ? (
          <div className="week-title"><b>Search results for &ldquo;{search}&rdquo;</b>
            <span className="small muted">{enquiries.length} {enquiries.length === 1 ? "enquiry" : "enquiries"} across all dates</span></div>
        ) : (
          <>
            <div className="seg" role="group" aria-label="Show by">
              {KINDS.map(([k, label]) => (
                <button key={k} className={k === kind ? "on" : undefined} aria-pressed={k === kind}
                        onClick={() => { setKind(k); setWeek(wk.current ? "" : wk.start); }}>{label}</button>
              ))}
            </div>
            <div className="week-nav">
              <button className="btn btn-sm btn-light" onClick={() => setWeek(wk.previous)} aria-label={`Previous ${unit}`}><i className="fas fa-chevron-left" aria-hidden /></button>
              <div className="week-title">
                <b>{periodTitle(wk)}</b>
                <span className="small muted">{enquiries.filter((e) => !e.carriedOver).length} received this {unit}
                  {wk.carriedOver ? ` · ${wk.carriedOver} still open from earlier` : ""}</span>
              </div>
              <button className="btn btn-sm btn-light" onClick={() => setWeek(wk.next)} aria-label={`Next ${unit}`}><i className="fas fa-chevron-right" aria-hidden /></button>
              {!wk.current ? <button className="btn btn-sm" onClick={() => setWeek("")}>{THIS[unit]}</button> : null}
            </div>
            <label className="week-jump small muted">Go to
              <input type="date" value="" onChange={(e) => e.target.value && setWeek(e.target.value)} aria-label={`Go to the ${unit} of a date`} />
            </label>
          </>
        )}
        <div className="week-search">
          <input type="search" value={searchText} onChange={(e) => setSearchText(e.target.value)}
                 placeholder="Search all dates: name, organisation, course or ENQ number" aria-label="Search enquiries" />
        </div>
      </div>
      {!search && !wk.current ? (
        <p className="small muted week-note">Showing enquiries received in this {unit} only. Open enquiries from earlier are carried onto the current {unit}.</p>
      ) : null}
      <div className="board">
        {stages.map((stage, i) => {
          const cards = enquiries.filter((e) => e.stageIndex === i);
          return (
            <div key={stage} className={`col${over === i && drag ? " over" : ""}`}
                 onDragOver={(e) => { if (canWrite) { e.preventDefault(); setOver(i); } }}
                 onDragLeave={() => setOver(null)} onDrop={(e) => { e.preventDefault(); drop(i); }}>
              <div className="col-head"><span>{stage}</span><span className="mono">{cards.length}</span></div>
              {!cards.length ? <div className="col-empty small muted">None</div> : null}
              {cards.map((e) => (
                <div key={e.ref} id={`card-${e.ref}`} className={`kcard${drag === e.ref ? " dragging" : ""}${focus === e.ref ? " focused" : ""}`} draggable={canWrite}
                     onClick={(ev) => { if (!(ev.target as HTMLElement).closest("button, select")) setEditing(e.ref); }}
                     title="Open to view or edit"
                     onDragStart={(ev) => { setDrag(e.ref); ev.dataTransfer.setData("text/plain", e.ref); ev.dataTransfer.effectAllowed = "move"; }}
                     onDragEnd={() => { setDrag(null); setOver(null); }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span className="mono small">{e.ref}</span>
                    {e.carriedOver ? <span className="carried" title="Received in an earlier week and still open">From {dayMonth(e.receivedOn)}</span>
                      : search ? <span className="carried">{dayMonth(e.receivedOn, true)}</span> : null}
                    {e.stale ? <Status tone="bad">Over two days</Status> : !e.owner ? <Status tone="bad">Unassigned</Status> : null}
                  </div>
                  <b>{e.name}</b>
                  <span>{e.org ? (e.enquiringFor === "Individual" ? `Works at ${e.org}` : e.org) : null}
                    {e.kind === "Enquiry" ? <span className={`for-tag ${e.enquiringFor === "Company" ? "co" : "ind"}`}>
                      {e.enquiringFor === "Company" ? "Company" : "Individual"}</span> : null}</span>
                  <span>{e.course}</span>
                  {e.topicLabels.length ? (
                    <div className="kcard-topics">{e.topicLabels.map((t) => <span key={t} className="kcard-topic">{t}</span>)}</div>
                  ) : null}
                  <span>{e.clockText} · {e.channel}</span>
                  <span>Owner: {e.owner ?? "unassigned"}</span>
                  {e.quotations.map((qt) => (
                    <span key={qt.ref} className="kcard-quote">
                      <i className="fas fa-file-invoice-dollar" aria-hidden /> <span className="mono">{qt.ref}</span> · {qt.value} · {qt.learners} {qt.learners === 1 ? "learner" : "learners"} · {qt.state}
                    </span>
                  ))}
                  {e.stageIndex === QUOTED && !e.quotations.length ? <span className="tone-warn small">Marked Quoted, but no quotation is on record.</span> : null}
                  {e.quotations.filter((qt) => qt.state === "Draft").map((qt) => (
                    <span key={qt.ref} className="tone-warn small">{qt.ref} is a draft{qt.needsApproval ? ", awaiting the head of department’s approval" : ": issue it on Quotations"}.</span>
                  ))}
                  {e.enrolment ? <span>Registered as <span className="mono">{e.enrolment}</span></span> : null}
                  <div className="kcard-actions">
                    <button className="btn btn-sm btn-light" onClick={() => setEditing(e.ref)}>
                      <i className={`fas ${canWrite ? "fa-pen" : "fa-eye"}`} aria-hidden /> {canWrite ? "Edit" : "View"}
                    </button>
                    {canWrite && e.kind === "Enquiry" && !e.enrolment && e.stageIndex < REGISTERED && !e.quotations.length ? (
                      <button className="btn btn-sm" onClick={() => { move.clear(); setQuoting(e); }}>Create quotation</button>
                    ) : null}
                    {/* A company sends a list of people on its quotation; an individual registers themselves. */}
                    {canWrite && e.enquiringFor === "Company" ? e.quotations.filter((qt) => qt.canAddDelegates).map((qt) => (
                      <button key={qt.ref} className="btn btn-sm" onClick={() => { move.clear(); setDelegatesFor(qt); }}>
                        Add delegates ({qt.registered}/{qt.learners})</button>
                    )) : null}
                    {canWrite && e.kind === "Enquiry" && e.enquiringFor === "Individual" && !e.enrolment && e.stageIndex < REGISTERED ? (
                      <button className="btn btn-sm" onClick={() => { move.clear(); setRegistering(e); }}>Register learner</button>
                    ) : null}
                  </div>
                  {canWrite ? (
                    <select aria-label={`Move ${e.ref}`} value={e.stageIndex} className="small"
                            onChange={(ev) => toStage(e, Number(ev.target.value))}>
                      {stages.map((s, si) => <option key={s} value={si}>{si === e.stageIndex ? `Stage: ${s}` : `Move to ${s}`}</option>)}
                    </select>
                  ) : null}
                </div>
              ))}
            </div>
          );
        })}
      </div>
      {registering ? (
        <Modal title={`Register a learner from ${registering.ref}`} onClose={() => setRegistering(null)}>
          <RegisterLearnerForm
            prefill={{ enquiryRef: registering.ref, names: registering.name === "Training desk" ? "" : registering.name,
                       email: registering.email, phone: registering.phone, organisation: registering.org,
                       courseCode: registering.courseCode, learnerType: registering.enquiringFor === "Company" ? "Corporate" : "Public" }}
            onDone={() => setRegistering(null)} />
        </Modal>
      ) : null}
      {quoting ? (
        <Modal title={`Quotation for ${quoting.ref} · ${quoting.org || quoting.name}`} onClose={() => setQuoting(null)}>
          <NewQuotationForm
            prefill={{ enquiryRef: quoting.ref, orgRef: quoting.enquiringFor === "Individual" ? "" : quoting.orgRef, contactRef: quoting.contactRef,
                       contactName: quoting.name, courseCode: quoting.courseCode, individual: quoting.enquiringFor === "Individual", employer: quoting.org }}
            onDone={(_, what) => { setQuoting(null); setNotice(what); window.setTimeout(() => setNotice(""), 10000); }} />
        </Modal>
      ) : null}
      {delegatesFor ? (
        <Modal title={`Delegates for ${delegatesFor.ref}`} onClose={() => setDelegatesFor(null)} wide>
          <DelegatesForm quote={{ ref: delegatesFor.ref, client: delegatesFor.client, course: delegatesFor.course, courseCode: delegatesFor.courseCode,
                                  learners: delegatesFor.learners, registered: delegatesFor.registered }}
                         onDone={() => setDelegatesFor(null)} />
        </Modal>
      ) : null}
      {editing ? (
        <Modal title={`Enquiry ${editing}`} onClose={() => setEditing(null)}>
          <EnquiryEditor enquiryRef={editing} onClose={() => setEditing(null)}
                         onSaved={(what) => { setNotice(what); window.setTimeout(() => setNotice(""), 10000); }} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
