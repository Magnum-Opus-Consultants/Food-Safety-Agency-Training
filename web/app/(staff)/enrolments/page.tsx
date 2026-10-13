"use client";

import { useMemo, useRef, useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { useAction, useMe, useRegister, useUpload } from "@/lib/hooks";
import { Modal, RegisterLearnerForm } from "@/components/registration";
import { ACCEPT, EvidenceFile, prerequisiteLabel, Prerequisites } from "@/components/Prerequisites";

type Enrolment = {
  ref: string; learner: string; course: string; gated: boolean; intake: string | null; intakeRef: string | null; passMark: number | null; requirement: string; stageIndex: number; stage: string;
  prerequisiteResult: number | null; grade10: boolean; basis: string; gateBlockedBy: string[]; advanceBlockedBy: string[];
  owner: string | null; grade10File: EvidenceFile | null;
};

export default function Enrolments() {
  const q = useRegister<{ stages: string[]; items: Enrolment[]; counts: number[] }>("/enrolments");
  const me = useMe();
  const advance = useAction<{ ref: string }>("PATCH", (v) => `/enrolments/${v.ref}/stage`);
  // Grade 10 evidence can be uploaded straight from a row: one hidden file picker, aimed at the row clicked.
  const evidence = useUpload((ref) => `/enrolments/${ref}/grade10`);
  const picker = useRef<HTMLInputElement>(null);
  const [uploadFor, setUploadFor] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);
  const [filter, setFilter] = useState(NO_FILTER);
  const setF = (k: keyof Filter, v: string) => setFilter((x) => ({ ...x, [k]: v }));
  const all = q.data?.data.items;
  const intakes = useMemo(() => [...new Map((all ?? []).filter((e) => e.intakeRef).map((e) => [e.intakeRef!, e])).values()]
    .sort((a, b) => (a.intake ?? "").localeCompare(b.intake ?? "")), [all]);

  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading />;
  const { stages, items: everything, counts } = q.data.data;
  const items = everything.filter((e) => matches(e, filter));
  const filtered = Object.values(filter).some(Boolean);
  const canWrite = me.data?.data.writes.includes("learners") ?? false;

  // The details open directly under the clicked row, as if coming out of it.
  const detail = (selected: Enrolment) => (
    <div className="stack-12">
      <div className="row small muted">Stage {selected.stageIndex + 1} of {stages.length} · {selected.stage} · {selected.basis} · owner {selected.owner ?? "unassigned"}</div>
      <div className="stage-rail">{stages.map((s, i) => (
        <div key={s} className={i < selected.stageIndex ? "done" : i === selected.stageIndex ? "now" : ""}><i aria-hidden /><span>{s}</span></div>
      ))}</div>
      {selected.gated ? <Prerequisites key={selected.ref} e={selected} canWrite={canWrite} />
        : selected.gateBlockedBy.length ? <Blocked reasons={selected.gateBlockedBy} title="Minimum prerequisites — outstanding" /> : null}
      {canWrite && selected.stageIndex < stages.length - 1 ? (
        <div className="row">
          <button className="btn btn-primary" disabled={advance.isPending || selected.gateBlockedBy.length > 0}
                  onClick={() => advance.mutate({ ref: selected.ref })}>
            {selected.stageIndex === 0 ? "Confirm — prerequisites met" : `Advance to ${stages[selected.stageIndex + 1].toLowerCase()}`}
          </button>
          {selected.gateBlockedBy.length ? <span className="small muted">Available once both minimum prerequisites are met.</span> : null}
        </div>
      ) : null}
      <Blocked refusal={advance.refusal} />
    </div>
  );

  return (
    <>
      <Hero
        title="The minimum prerequisites are a prerequisite test at the course's pass mark and Grade 10 evidence. Both, not either."
        statement="A learner cannot be confirmed while either part is outstanding, and the screen names which one. Click a row to open it."
        stats={stages.map((s, i) => ({ v: String(counts[i]), l: s, c: i === 0 ? "Checking minimum prerequisites" : undefined }))}
      />
      <SectionHead title="Enrolment register">
        {canWrite ? <button className="btn btn-teal" onClick={() => setRegistering(true)}>Register new learner</button> : null}
      </SectionHead>
      <section className="card filter-bar" aria-label="Search and filter enrolments">
        <div className="field filter-search"><label htmlFor="ef-q">Search</label>
          <input id="ef-q" type="search" value={filter.q} onChange={(e) => setF("q", e.target.value)}
                 placeholder="Learner name, enrolment (ENR-0012) or intake (PLN-14)" /></div>
        <div className="field"><label htmlFor="ef-intake">Intake</label>
          <select id="ef-intake" value={filter.intake} onChange={(e) => setF("intake", e.target.value)}>
            <option value="">All intakes</option>
            {intakes.map((e) => <option key={e.intakeRef} value={e.intakeRef!}>{e.intakeRef} · {e.intake} · {e.course}</option>)}
          </select></div>
        <div className="field"><label htmlFor="ef-stage">Stage</label>
          <select id="ef-stage" value={filter.stage} onChange={(e) => setF("stage", e.target.value)}>
            <option value="">All stages</option>
            <option value="gate">Minimum prerequisites not met</option>
            {stages.map((s, i) => <option key={s} value={String(i)}>{s}</option>)}
          </select></div>
        <div className="field"><label htmlFor="ef-g10">Grade 10</label>
          <select id="ef-g10" value={filter.grade10} onChange={(e) => setF("grade10", e.target.value)}>
            <option value="">Any</option><option value="held">Uploaded or recorded</option><option value="outstanding">Outstanding</option>
            <option value="na">Not required</option>
          </select></div>
        <div className="field"><label htmlFor="ef-from">Intake starts from</label>
          <input id="ef-from" type="date" value={filter.from} onChange={(e) => setF("from", e.target.value)} /></div>
        <div className="field"><label htmlFor="ef-to">to</label>
          <input id="ef-to" type="date" value={filter.to} min={filter.from || undefined} onChange={(e) => setF("to", e.target.value)} /></div>
        <div className="filter-foot">
          <span className="small muted">Showing {items.length} of {everything.length} {everything.length === 1 ? "enrolment" : "enrolments"}</span>
          {filtered ? <button className="btn btn-sm" onClick={() => setFilter(NO_FILTER)}>Clear filters</button> : null}
        </div>
      </section>
      <input ref={picker} type="file" accept={ACCEPT} hidden
             onChange={(ev) => {
               const f = ev.target.files?.[0];
               if (f && uploadFor) evidence.mutate({ ref: uploadFor, file: f }, { onSettled: () => { if (picker.current) picker.current.value = ""; } });
             }} />
      {evidence.refusal ? <Blocked refusal={evidence.refusal} /> : null}
      <Register rows={items} expanded={(e) => (e.ref === open ? detail(e) : null)} empty={filtered ? "No enrolment matches these filters." : undefined} rowKey={(e) => e.ref} source={q.data.meta.source as string}
        onRow={(e) => { setOpen(e.ref === open ? null : e.ref); advance.clear(); }}
        columns={[
          { key: "ref", label: "Enrolment", render: (e) => e.ref, mono: true },
          { key: "learner", label: "Learner", render: (e) => <b>{e.learner}</b> },
          { key: "course", label: "Course", render: (e) => e.course },
          { key: "intake", label: "Intake", render: (e) => (e.intakeRef ? <>{e.intakeRef}<div className="small muted">{e.intake}</div></> : "—"), mono: true },
          { key: "test", label: "Test", render: (e) => (e.gated ? (e.prerequisiteResult === null ? "—" : `${e.prerequisiteResult}%`) : "n/a"), mono: true },
          { key: "g10", label: "Grade 10", render: (e) => {
            if (!e.gated) return "n/a";
            if (e.grade10File) return (
              <a href={e.grade10File.url} target="_blank" rel="noopener" className="prereq-file" onClick={(ev) => ev.stopPropagation()}
                 title={`Open ${e.grade10File.name}`}><i className="fas fa-paperclip" aria-hidden /> View file</a>);
            const state = e.grade10 ? "Recorded, no file" : "Outstanding";
            if (!canWrite || e.stageIndex > 0) return state;
            const busy = evidence.isPending && uploadFor === e.ref;
            return (
              <div className="row-upload">
                <span className={e.grade10 ? undefined : "tone-bad"}>{state}</span>
                <button className="btn btn-sm" disabled={evidence.isPending}
                        onClick={(ev) => { ev.stopPropagation(); evidence.clear(); setUploadFor(e.ref); picker.current?.click(); }}>
                  <i className="fas fa-upload" aria-hidden /> {busy ? "Uploading…" : "Upload"}
                </button>
              </div>);
          } },
          { key: "stage", label: "Stage", render: (e) => (
            <Status tone={e.gateBlockedBy.length ? "bad" : e.stageIndex === stages.length - 1 ? "ok" : "info"}>{e.gateBlockedBy.length ? prerequisiteLabel(e.gateBlockedBy) : e.stage}</Status>
          ) },
        ]} />
      {registering ? (
        <Modal title="Register new learner" onClose={() => setRegistering(false)}>
          <RegisterLearnerForm onDone={(ref) => { setRegistering(false); setOpen(ref); }} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}

type Filter = { q: string; intake: string; stage: string; grade10: string; from: string; to: string };
const NO_FILTER: Filter = { q: "", intake: "", stage: "", grade10: "", from: "", to: "" };

function matches(e: Enrolment, f: Filter) {
  const q = f.q.trim().toLowerCase();
  if (q && ![e.learner, e.ref, e.intakeRef ?? "", e.course].some((v) => v.toLowerCase().includes(q))) return false;
  if (f.intake && e.intakeRef !== f.intake) return false;
  if (f.stage === "gate" ? !e.gateBlockedBy.length : f.stage && String(e.stageIndex) !== f.stage) return false;
  if (f.grade10 === "held" && !(e.gated && e.grade10)) return false;
  if (f.grade10 === "outstanding" && !(e.gated && !e.grade10)) return false;
  if (f.grade10 === "na" && e.gated) return false;
  if (f.from && (!e.intake || e.intake < f.from)) return false;
  if (f.to && (!e.intake || e.intake > f.to)) return false;
  return true;
}
