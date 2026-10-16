"use client";

// The learner's course evaluation, opened from the private link they were sent. No sign-in; answered once.

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";

type View = { learner: string; course: string; dates: string; venue: string; facilitator: string; submitted: boolean;
  dimensions: { key: string; label: string }[] };

export default function Feedback() {
  const { token } = useParams<{ token: string }>();
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState("");
  const [scores, setScores] = useState<Record<string, number>>({});
  const [recommend, setRecommend] = useState<boolean | null>(null);
  const [comments, setComments] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);

  useEffect(() => {
    api<View>(`/public/feedback/${token}`).then((r) => setView(r.data)).catch((e: ApiError) => setError(e.blockedBy?.[0] ?? e.message));
  }, [token]);

  async function send() {
    setBusy(true);
    setProblems([]);
    try {
      await api(`/public/feedback/${token}`, { method: "POST", body: { ...scores, recommend, comments } });
      setSent(true);
    } catch (e) {
      if (e instanceof ApiError) setProblems(e.blockedBy?.length ? e.blockedBy : [e.message]);
    } finally {
      setBusy(false);
    }
  }

  const complete = view ? view.dimensions.every((d) => scores[d.key]) && recommend !== null : false;
  return (
    <div className="fb-page">
      <div className="fb-card">
        <img src="/brand/fsa-logo.png" alt="Food Safety Agency" className="fb-logo" />
        {error ? <p className="fb-msg">{error}</p>
          : !view ? <p className="fb-msg">Opening your feedback form…</p>
          : sent || view.submitted ? (
            <div className="fb-done"><i className="fas fa-circle-check" aria-hidden />
              <h1>Thank you{sent ? `, ${view.learner}` : ""}.</h1>
              <p>{sent ? "Your feedback has been received. It helps the FSA Academy improve its courses." : "Your feedback was already received."}</p></div>
          ) : (
            <>
              <h1>How was your course, {view.learner}?</h1>
              <p className="fb-sub"><b>{view.course}</b><br />{view.dates}{view.venue ? ` · ${view.venue}` : ""}{view.facilitator ? ` · facilitated by ${view.facilitator}` : ""}</p>
              <p className="fb-note">Rate each from 1 (poor) to 5 (excellent). Your answers are read together with your classmates&apos;; your facilitator does not see who said what.</p>
              {view.dimensions.map((d) => (
                <div key={d.key} className="fb-q">
                  <div className="fb-label">{d.label}</div>
                  <div className="fb-scale" role="radiogroup" aria-label={d.label}>
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button key={n} type="button" role="radio" aria-checked={scores[d.key] === n} className={scores[d.key] === n ? "on" : undefined}
                              onClick={() => setScores({ ...scores, [d.key]: n })}>{n}</button>
                    ))}
                  </div>
                </div>
              ))}
              <div className="fb-q">
                <div className="fb-label">Would you recommend this course to someone else?</div>
                <div className="fb-scale" role="radiogroup" aria-label="Recommend">
                  <button type="button" role="radio" aria-checked={recommend === true} className={recommend === true ? "on" : undefined} onClick={() => setRecommend(true)}>Yes</button>
                  <button type="button" role="radio" aria-checked={recommend === false} className={recommend === false ? "on" : undefined} onClick={() => setRecommend(false)}>No</button>
                </div>
              </div>
              <div className="fb-q">
                <label className="fb-label" htmlFor="fb-c">Anything else you would like to tell us? <span className="fb-opt">(optional)</span></label>
                <textarea id="fb-c" rows={4} value={comments} maxLength={2000} onChange={(e) => setComments(e.target.value)}
                          placeholder="What worked well, and what should we improve?" />
              </div>
              {problems.length ? <ul className="fb-problems">{problems.map((p) => <li key={p}>{p}</li>)}</ul> : null}
              <button className="fb-send" disabled={busy || !complete} onClick={send}>{busy ? "Sending…" : "Send my feedback"}</button>
              {!complete ? <p className="fb-hint">Answer each rating and the recommendation to send.</p> : null}
            </>
          )}
      </div>
    </div>
  );
}
