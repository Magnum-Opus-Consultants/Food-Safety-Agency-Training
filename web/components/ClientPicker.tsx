"use client";

// Type to search the companies on record, grouped into clients (they have registered learners) and
// prospects (enquired only). The typed name can also be added as a new client.

import { useEffect, useMemo, useRef, useState } from "react";

export type PickerClient = { ref: string; name: string; sector: string; relationship: string };
export const NEW_CLIENT = "__new__";

export function ClientPicker({ id, clients, value, onChange, invalid }: {
  id: string; clients: PickerClient[]; value: string; invalid?: boolean;
  onChange: (ref: string, typedName?: string) => void;
}) {
  const chosen = clients.find((c) => c.ref === value);
  const [text, setText] = useState(chosen?.name ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => { if (chosen) setText(chosen.name); }, [chosen]);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const q = text.trim().toLowerCase();
  const matches = useMemo(() => {
    const hit = (c: PickerClient) => !q || chosen?.name.toLowerCase() === q || c.name.toLowerCase().includes(q) || c.sector.toLowerCase().includes(q);
    const list = clients.filter(hit);
    return [...list.filter((c) => c.relationship === "Client"), ...list.filter((c) => c.relationship !== "Client")];
  }, [clients, q, chosen]);
  const exact = clients.some((c) => c.name.toLowerCase() === q);
  // "Add a new client" comes first so it is always in view, however long the list grows.
  const options: { ref: string; label: string; group?: string }[] = [
    { ref: NEW_CLIENT, label: q && !exact ? `+ Add "${text.trim()}" as a new client` : "+ Add a new client" },
    ...matches.map((c) => ({ ref: c.ref, label: c.name, group: c.relationship === "Client" ? "Clients" : "Prospects (enquired, not yet trained)" })),
  ];

  function pick(i: number) {
    const o = options[i];
    if (!o) return;
    if (o.ref === NEW_CLIENT) { onChange(NEW_CLIENT, exact ? "" : text.trim()); setText(""); }
    else { onChange(o.ref); setText(o.label); }
    setOpen(false);
  }

  return (
    <div className="picker" ref={box}>
      <input id={id} role="combobox" aria-expanded={open} aria-autocomplete="list" autoComplete="off"
             className={invalid ? "invalid" : undefined} value={value === NEW_CLIENT ? "" : text}
             placeholder={value === NEW_CLIENT ? "New client: fill in the details below" : "Type to search clients and prospects…"}
             onFocus={() => setOpen(true)}
             onChange={(e) => { setText(e.target.value); setOpen(true); setActive(e.target.value.trim() ? 1 : 0); if (value) onChange(""); }}
             onKeyDown={(e) => {
               if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, options.length - 1)); }
               else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
               else if (e.key === "Enter" && open) { e.preventDefault(); pick(active); }
               else if (e.key === "Escape") setOpen(false);
             }} />
      {open ? (
        <ul className="picker-list" role="listbox">
          {options.map((o, i) => (
            <li key={o.ref} role="option" aria-selected={i === active}
                className={`${i === active ? "active" : ""}${o.ref === NEW_CLIENT ? " add" : ""}`}
                onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(i); }}>
              {o.group && options[i - 1]?.group !== o.group ? <div className="picker-group">{o.group}</div> : null}
              {o.label}
            </li>
          ))}
          {!matches.length && q ? <li className="picker-none">No company matches &ldquo;{text.trim()}&rdquo;.</li> : null}
        </ul>
      ) : null}
    </div>
  );
}
