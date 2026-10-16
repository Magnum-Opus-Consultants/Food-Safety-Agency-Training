"use client";

// The minimum prerequisites of a gated course: a test result at the pass mark or more AND Grade 10 evidence,
// both, not either. The result is typed in; the Grade 10 evidence is an uploaded document (PDF, JPG
// or PNG) that can be opened, replaced or deleted while the enrolment is at its first stage, Registered.

import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Blocked, Status } from "@/components/ui";
import { ApiError, upload } from "@/lib/api";
import { useAction, useScreen, useUpload } from "@/lib/hooks";

export type EvidenceFile = { ref: string; name: string; type: string; uploadedAt: string; uploadedBy: string | null; url: string };
export type TestAttempt = { n: number; result: number; capturedAt: string | null; capturedBy: string | null; file: { name: string; url: string } | null };
export type GatedEnrolment = {
  ref: string; stageIndex: number; prerequisiteResult: number | null; grade10: boolean; grade10File: EvidenceFile | null; testFile?: EvidenceFile | null;
  testAttempts?: TestAttempt[];
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

const ordinal = (n: number) => `${n}${n % 10 === 1 && n % 100 !== 11 ? "st" : n % 10 === 2 && n % 100 !== 12 ? "nd" : n % 10 === 3 && n % 100 !== 13 ? "rd" : "th"} attempt`;

export function Prerequisites({ e, canWrite }: { e: GatedEnrolment; canWrite: boolean }) {
  const open = e.stageIndex === 0;
  const editable = canWrite && open;
  const [score, setScore] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const screen = useScreen();
  const [testFile, setTestFile] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [testRefusal, setTestRefusal] = useState<ApiError | null>(null);
  const testPicker = useRef<HTMLInputElement>(null);
  const remove = useAction<{ ref: string }>("DELETE", (v) => `/enrolments/${v.ref}/grade10`);
  const send = useUpload((ref) => `/enrolments/${ref}/grade10`);
  const refusal = testRefusal ?? remove.refusal ?? send.refusal;

  const result = e.prerequisiteResult;
  const mark = e.passMark ?? 50;
  const n = Number(score);
  const scoreProblem = score.trim() === "" ? null : Number.isNaN(n) || n < 0 || n > 100 ? "Enter a percentage from 0 to 100." : null;
  const file = e.grade10File;
  const attempts = e.testAttempts ?? [];

  // The result and the marked test it comes from are saved together.
  async function saveTest() {
    if (scoreProblem || !score.trim() || !testFile) return;
    setSaving(true);
    setTestRefusal(null);
    try {
      await upload(`/enrolments/${e.ref}/test`, testFile, screen, { result: score });
      setScore("");
      setTestFile(null);
      if (testPicker.current) testPicker.current.value = "";
      await qc.invalidateQueries();
    } catch (err) {
      if (err instanceof ApiError) setTestRefusal(err);
    } finally {
      setSaving(false);
    }
  }

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
          <div className="small muted">{mark}% or more · with the marked test</div>
        </div>
        <div className="prereq-state">
          {result === null ? <Status tone="bad">Not captured</Status>
            : result < mark ? <Status tone="bad">{result}% · below {mark}%</Status>
            : <Status tone="ok">{result}% · met</Status>}
          {attempts.length ? (
            <ol className="attempts">
              {attempts.map((a) => (
                <li key={a.n} className={a.n === attempts.length ? "latest" : undefined}>
                  <b>{ordinal(a.n)}</b> · {a.result}% <span className={a.result >= mark ? "tone-ok" : "tone-bad"}>{a.result >= mark ? "met" : "below"}</span>
                  {a.file ? <> · <a href={a.file.url} target="_blank" rel="noopener"><i className="fas fa-paperclip" aria-hidden /> {a.file.name}</a></>
                    : <span className="small muted"> · no marked test on file</span>}
                  <div className="small muted">{a.capturedAt ? `${a.capturedAt}${a.capturedBy ? ` by ${a.capturedBy}` : ""}` : "Captured before attempts were kept"}
                    {a.n === attempts.length && attempts.length > 1 ? " · counts" : ""}</div>
                </li>
              ))}
            </ol>
          ) : null}
        </div>
        {editable ? (
          <form className="prereq-act" onSubmit={(ev) => {
            ev.preventDefault();
            saveTest();
          }}>
            <input aria-label="Test result (%)" inputMode="decimal" value={score} onChange={(ev) => setScore(ev.target.value)}
                   className={scoreProblem ? "invalid" : undefined} placeholder={result === null ? "Result %" : "New result %"} />
            <input ref={testPicker} type="file" accept={ACCEPT} hidden onChange={(ev) => setTestFile(ev.target.files?.[0] ?? null)} />
            {score.trim() ? (
              <button type="button" className="btn btn-sm" onClick={() => testPicker.current?.click()}>
                <i className="fas fa-paperclip" aria-hidden /> {testFile ? testFile.name : "Attach the marked test"}</button>
            ) : null}
            {score.trim() ? <button className="btn btn-sm btn-primary" type="submit" disabled={!!scoreProblem || !testFile || saving}>
              {saving ? "Saving…" : "Save"}</button> : null}
            {scoreProblem ? <span className="field-error">{scoreProblem}</span>
              : score.trim() && !testFile ? <span className="small muted">Attach the test to save the result.</span> : null}
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
