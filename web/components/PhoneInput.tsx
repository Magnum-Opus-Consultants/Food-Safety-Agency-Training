"use client";

// A phone number with its country code. Emits "+264 812345678"-style values (the API checks and
// stores them in that form). Mirrors backend/core/phone.py.

import { useState } from "react";

export const COUNTRIES: { code: string; iso: string; name: string }[] = [
  { code: "27", iso: "ZA", name: "South Africa" },
  { code: "264", iso: "NA", name: "Namibia" },
  { code: "267", iso: "BW", name: "Botswana" },
  { code: "266", iso: "LS", name: "Lesotho" },
  { code: "268", iso: "SZ", name: "Eswatini" },
  { code: "263", iso: "ZW", name: "Zimbabwe" },
  { code: "258", iso: "MZ", name: "Mozambique" },
  { code: "260", iso: "ZM", name: "Zambia" },
  { code: "265", iso: "MW", name: "Malawi" },
  { code: "244", iso: "AO", name: "Angola" },
  { code: "44", iso: "GB", name: "United Kingdom" },
];
const BY_LENGTH = [...COUNTRIES].sort((a, b) => b.code.length - a.code.length);

/** Split a stored or typed number into country code and national number. */
export function splitPhone(value: string): { code: string; national: string } {
  const v = (value ?? "").trim();
  if (!v) return { code: "27", national: "" };
  const compact = v.replace(/[\s\-().]/g, "").replace(/^00/, "+");
  if (compact.startsWith("+")) {
    const digits = compact.slice(1);
    const known = BY_LENGTH.find((c) => digits.startsWith(c.code));
    if (known) return { code: known.code, national: digits.slice(known.code.length) };
  }
  if (compact.startsWith("0")) return { code: "27", national: compact.slice(1) };
  return { code: "27", national: v };
}

export function PhoneInput({ id, value, onChange, readOnly = false }: {
  id: string; value: string; onChange: (v: string) => void; readOnly?: boolean;
}) {
  const initial = splitPhone(value);
  const [code, setCode] = useState(initial.code);
  const [national, setNational] = useState(initial.national);

  function emit(c: string, n: string) {
    const digits = n.trim();
    onChange(digits ? `+${c} ${digits.replace(/^0+/, "")}` : "");
  }

  const current = COUNTRIES.find((c) => c.code === code) ?? COUNTRIES[0];
  return (
    <div className="phone-input">
      {/* Compact when closed ("NA +264"); the native list still shows full country names. */}
      <label className={`phone-country${readOnly ? " is-readonly" : ""}`} title={`${current.name} +${current.code}`}>
        <span className="phone-iso">{current.iso}</span>
        <span className="phone-code">+{current.code}</span>
        {!readOnly ? <i className="fas fa-chevron-down" aria-hidden /> : null}
        <select aria-label={`Country code, ${current.name} +${current.code}`} value={code} disabled={readOnly}
                onChange={(e) => { setCode(e.target.value); emit(e.target.value, national); }}>
          {COUNTRIES.map((c) => <option key={c.code} value={c.code}>{c.name} +{c.code}</option>)}
        </select>
      </label>
      <input id={id} type="tel" inputMode="tel" autoComplete="tel-national" value={national} readOnly={readOnly}
             placeholder={code === "264" ? "81 234 5678" : "82 555 0101"}
             onChange={(e) => { setNational(e.target.value); emit(code, e.target.value); }} />
    </div>
  );
}
