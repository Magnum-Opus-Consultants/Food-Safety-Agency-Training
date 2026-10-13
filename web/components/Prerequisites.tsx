"use client";

// The minimum prerequisites of a gated course: a test result at the pass mark or more AND Grade 10 evidence,
// both, not either. The result is typed in; the Grade 10 evidence is an uploaded document (PDF, JPG
// or PNG) that can be opened, replaced or deleted while the enrolment is at its first stage, Registered.

import { useRef, useState } from "react";
import { Blocked, Status } from "@/components/ui";
import { useAction, useUpload } from "@/lib/hooks";

export type EvidenceFile = { ref: string; name: string; type: string; uploadedAt: string; uploadedBy: string | null; url: string };
export type GatedEnrolment = {
  ref: string; stageIndex: number; prerequisiteResult: number | null; grade10: boolean; grade10File: EvidenceFile | null;
  gateBlockedBy: string[]; passMark: number | null;
};

export const ACCEPT = ".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png";

/** One short label for the register's Stage column. */
export function prerequisiteLabel(reasons: string[]) {
  if (reasons.length !== 1) return "Minimum prerequisites not met";
  const r = reasons[0];
  if (r.startsWith("Prerequisite test result not captured")) return "Test result not captured";
  if (r.startsWith("Prerequisite test result is")) return "Test result below the pass mark";
  if (r.startsWith("Grade 10")) return "Grade 10 evidence outstanding";
  return "Minimum prerequisites not met";
}

export function Prerequisites({ e, canWrite }: { e: GatedEnrolment; canWrite: boolean }) {
  const open = e.stageIndex === 0;
  const editable = canWrite && open;
  const [score, setScore] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const saveScore = useAction<{ ref: string; prerequisiteResult: number }>("PATCH", (v) => `/enrolments/${v.ref}/gate`);
  const remove = useAction<{ ref: string }>("DELETE", (v) => `/enrolments/${v.ref}/grade10`);
  const send = useUpload((ref) => `/enrolments/${ref}/grade10`);
  const refusal = saveScore.refusal ?? remove.refusal ?? send.refusal;

  const result = e.prerequisiteResult;
  const mark = e.passMark ?? 50;
  const n = Number(score);
  const scoreProblem = score.trim() === "" ? null : Number.isNaN(n) || n < 0 || n > 100 ? "Enter a percentage from 0 to 100." : null;
  const file = e.grade10File;

  function choose(f?: File | null) {
    if (f) send.mutate({ ref: e.ref, file: f }, { onSettled: () => { if (picker.current) picker.current.value = ""; } });
  }

  return (
    <div className="prereq">
      <div className="prereq-head">
        <b>Minimum prerequisites</b>
        <span className="small muted">{open ? "Both are required before the learner can be confirmed." : "Met and confirmed, so they can no longer change."}</span>
      </div>
      <Blocked refusal={refusal} />

      <div className="prereq-row">
        <div className="prereq-what">
          <div className="prereq-name">Prerequisite test result</div>
          <div className="small muted">{mark}% or more</div>
        </div>
        <div className="prereq-state">
          {result === null ? <Status tone="bad">Not captured</Status>
            : result < mark ? <Status tone="bad">{result}% · below {mark}%</Status>
            : <Status tone="ok">{result}% · met</Status>}
        </div>
        {editable ? (
          <form className="prereq-act" onSubmit={(ev) => {
            ev.preventDefault();
            if (!scoreProblem && score.trim()) saveScore.mutate({ ref: e.ref, prerequisiteResult: n }, { onSuccess: () => setScore("") });
          }}>
            <input aria-label="Test result (%)" inputMode="decimal" value={score} onChange={(ev) => setScore(ev.target.value)}
                   className={scoreProblem ? "invalid" : undefined} placeholder={result === null ? "Result %" : "New result %"} />
            {score.trim() ? <button className="btn btn-sm btn-primary" type="submit" disabled={!!scoreProblem || saveScore.isPending}>Save</button> : null}
            {scoreProblem ? <span className="field-error">{scoreProblem}</span> : null}
          </form>
        ) : <div />}
      </div>

      <div className="prereq-row">
        <div className="prereq-what">
          <div className="prereq-name">Grade 10 evidence</div>
          <div className="small muted">Report or certificate · PDF, JPG or PNG, up to 5 MB</div>
        </div>
        <div className="prereq-state">
          {file ? (
            <div>
              <a href={file.url} target="_blank" rel="noopener" className="prereq-file">
                <i className={`fas ${file.type === "PDF" ? "fa-file-pdf" : "fa-file-image"}`} aria-hidden /> {file.name}
              </a>
              <div className="small muted">Uploaded {file.uploadedAt}{file.uploadedBy ? ` by ${file.uploadedBy}` : ""}</div>
            </div>
          ) : e.grade10 ? (
            <div><Status tone="warn">Recorded, no file</Status>
              <div className="small muted">Marked as received before uploads existed. Upload the document to keep it on file.</div></div>
          ) : <Status tone="bad">Not uploaded</Status>}
        </div>
        {editable ? (
          <div className="prereq-act">
            <input ref={picker} type="file" accept={ACCEPT} hidden onChange={(ev) => choose(ev.target.files?.[0])} />
            {confirmDelete ? (
              <>
                <span className="small">Delete this file?</span>
                <button className="btn btn-sm btn-danger" disabled={remove.isPending}
                        onClick={() => remove.mutate({ ref: e.ref }, { onSettled: () => setConfirmDelete(false) })}>Delete</button>
                <button className="btn btn-sm" onClick={() => setConfirmDelete(false)}>Keep</button>
              </>
            ) : (
              <>
                <button className="btn btn-sm" disabled={send.isPending} onClick={() => picker.current?.click()}>
                  <i className="fas fa-upload" aria-hidden /> {send.isPending ? "Uploading…" : file || e.grade10 ? "Replace" : "Upload"}
                </button>
                {file || e.grade10 ? (
                  <button className="btn btn-sm btn-ghost-danger" onClick={() => setConfirmDelete(true)} title="Delete the file">
                    <i className="fas fa-trash" aria-hidden /> Delete
                  </button>
                ) : null}
              </>
            )}
          </div>
        ) : <div />}
      </div>
    </div>
  );
}
