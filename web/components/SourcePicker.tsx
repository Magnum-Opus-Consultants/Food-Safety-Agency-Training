"use client";

// "How did they hear about us?": asked on every enquiry. When a campaign brought them, the campaign is named,
// so its results can be reported back to FSA.

import { useRegister } from "@/lib/hooks";

type Options = { sources: { value: string; label: string }[]; campaigns: { ref: string; name: string; channel: string; running: boolean }[] };

export function SourcePicker({ idPrefix, source, campaignRef, onChange, readOnly, errors = {} }: {
  idPrefix: string; source: string; campaignRef: string; onChange: (source: string, campaignRef: string) => void;
  readOnly?: boolean; errors?: { source?: string; campaign?: string };
}) {
  const q = useRegister<Options>("/campaigns/options");
  const o = q.data?.data;
  return (
    <>
      <div className="field"><label htmlFor={`${idPrefix}-src`}>How did they hear about us?</label>
        <select id={`${idPrefix}-src`} value={source} disabled={readOnly} className={errors.source ? "invalid" : undefined}
                onChange={(e) => onChange(e.target.value, e.target.value === "Campaign" ? campaignRef : "")}>
          <option value="">Choose…</option>
          {(o?.sources ?? []).map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        {errors.source ? <span className="field-error">{errors.source}</span> : null}</div>
      {source === "Campaign" ? (
        <div className="field"><label htmlFor={`${idPrefix}-cmp`}>Which campaign</label>
          <select id={`${idPrefix}-cmp`} value={campaignRef} disabled={readOnly} className={errors.campaign ? "invalid" : undefined}
                  onChange={(e) => onChange(source, e.target.value)}>
            <option value="">Choose…</option>
            {(o?.campaigns ?? []).map((c) => <option key={c.ref} value={c.ref}>{c.name} · {c.channel}{c.running ? "" : " (ended)"}</option>)}
          </select>
          {errors.campaign ? <span className="field-error">{errors.campaign}</span>
            : o && !o.campaigns.length ? <span className="small muted">No campaign is recorded. Add it on the Campaigns page.</span> : null}</div>
      ) : null}
    </>
  );
}
