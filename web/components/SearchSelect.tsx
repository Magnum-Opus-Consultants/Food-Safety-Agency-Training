"use client";

// A drop-down you can type into: the list narrows to what matches the typed words. Used where lists
// grow (courses), in place of a plain <select>. The list sits in the form's flow, so the edge of a
// window never cuts it off.

import { useEffect, useMemo, useRef, useState } from "react";

export type SearchOption = { value: string; label: string; hint?: string };

export function SearchSelect({ id, options, value, onChange, placeholder = "Type to search…", invalid, emptyText = "Nothing matches", disabled }: {
  id: string; options: SearchOption[]; value: string; onChange: (value: string) => void;
  placeholder?: string; invalid?: boolean; emptyText?: string; disabled?: boolean;
}) {
  const chosen = options.find((o) => o.value === value);
  const [text, setText] = useState(chosen?.label ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => { setText(chosen?.label ?? ""); }, [chosen?.label]);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) { setOpen(false); setText(chosen?.label ?? ""); }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [chosen?.label]);

  const words = text.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const showAll = !words.length || text === chosen?.label;
  const matches = useMemo(() => options.filter((o) => {
    if (showAll) return true;
    const hay = `${o.label} ${o.hint ?? ""} ${o.value}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  }), [options, words.join(" "), showAll]); // eslint-disable-line react-hooks/exhaustive-deps

  function pick(o?: SearchOption) {
    if (!o) return;
    onChange(o.value);
    setText(o.label);
    setOpen(false);
  }

  return (
    <div className="picker" ref={box}>
      <input id={id} role="combobox" aria-expanded={open} aria-autocomplete="list" autoComplete="off"
             className={invalid ? "invalid" : undefined} value={text} placeholder={placeholder} disabled={disabled}
             onFocus={(e) => { setOpen(true); e.target.select(); }}
             onChange={(e) => { setText(e.target.value); setOpen(true); setActive(0); }}
             onKeyDown={(e) => {
               if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, matches.length - 1)); }
               else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
               else if (e.key === "Enter" && open) { e.preventDefault(); pick(matches[active]); }
               else if (e.key === "Escape") { setOpen(false); setText(chosen?.label ?? ""); }
             }} />
      {open ? (
        <ul className="picker-list" role="listbox">
          {matches.map((o, i) => (
            <li key={o.value} role="option" aria-selected={o.value === value} className={i === active ? "active" : undefined}
                onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(o); }}>
              {o.label}{o.hint ? <span className="picker-hint">{o.hint}</span> : null}
            </li>
          ))}
          {!matches.length ? <li className="picker-none">{emptyText} &ldquo;{text.trim()}&rdquo;.</li> : null}
        </ul>
      ) : null}
    </div>
  );
}

/** Catalogue courses as search options: found by title, code (TRN-PME1) or a word in either. */
export function courseOptions(courses: { code: string; title: string }[], none?: string): SearchOption[] {
  return [...(none ? [{ value: "", label: none }] : []), ...courses.map((c) => ({ value: c.code, label: c.title, hint: c.code }))];
}
