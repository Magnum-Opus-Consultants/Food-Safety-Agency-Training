"use client";

// What an enquirer asked about: any of the topics from the meeting review, plus "Other", which
// opens a box to describe it. Codes match backend/demand/models.py ENQ_TOPICS.

export const TOPICS: { code: string; label: string }[] = [
  { code: "Accreditation", label: "Accreditation" },
  { code: "Costs", label: "Costs" },
  { code: "Delivery", label: "Online or in person" },
  { code: "Duration", label: "Duration" },
  { code: "Quote", label: "Quote" },
  { code: "Other", label: "Other" },
];

export function TopicPicker({ idPrefix, topics, other, onChange, readOnly = false, otherError }: {
  idPrefix: string; topics: string[]; other: string; readOnly?: boolean; otherError?: string;
  onChange: (topics: string[], other: string) => void;
}) {
  function toggle(code: string) {
    const next = topics.includes(code) ? topics.filter((t) => t !== code) : [...topics, code];
    const ordered = TOPICS.map((t) => t.code).filter((c) => next.includes(c));
    onChange(ordered, ordered.includes("Other") ? other : "");
  }
  return (
    <div className="topic-picker">
      <div className="topic-chips" role="group" aria-label="What they asked about">
        {TOPICS.map((t) => {
          const on = topics.includes(t.code);
          return (
            <label key={t.code} className={`topic-chip${on ? " on" : ""}${readOnly ? " ro" : ""}`}>
              <input type="checkbox" checked={on} disabled={readOnly} onChange={() => toggle(t.code)} />
              <i className={`fas ${on ? "fa-check" : "fa-plus"}`} aria-hidden /> {t.label}
            </label>
          );
        })}
      </div>
      {topics.includes("Other") ? (
        <>
          <input id={`${idPrefix}-other`} className={`topic-other${otherError ? " invalid" : ""}`} value={other} readOnly={readOnly}
                 autoFocus={!readOnly && !other} aria-invalid={!!otherError}
                 placeholder="Describe the other question they asked (required)" aria-label="Other question"
                 onChange={(e) => onChange(topics, e.target.value)} />
          {otherError ? <span className="field-error">{otherError}</span> : null}
        </>
      ) : null}
    </div>
  );
}
