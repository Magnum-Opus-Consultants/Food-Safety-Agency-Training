// Client-side check of an SA ID number, for immediate feedback only. The API validates again and
// is the authority; this mirrors backend/core/pii.py.

export function saIdProblem(raw: string): string | null {
  const n = raw.replace(/[\s-]/g, "");
  if (!/^\d{13}$/.test(n)) return "An SA ID number has 13 digits.";
  const yy = Number(n.slice(0, 2)), mm = Number(n.slice(2, 4)), dd = Number(n.slice(4, 6));
  const year = (2000 + yy <= new Date().getFullYear() ? 2000 : 1900) + yy;
  const d = new Date(year, mm - 1, dd);
  if (d.getFullYear() !== year || d.getMonth() !== mm - 1 || d.getDate() !== dd) return `The date of birth ${n.slice(0, 6)} is not a real date.`;
  if (!"012".includes(n[10])) return "The citizenship digit (11th) must be 0, 1 or 2.";
  let total = 0;
  [...n].reverse().forEach((ch, i) => {
    let v = Number(ch);
    if (i % 2 === 1) { v *= 2; if (v > 9) v -= 9; }
    total += v;
  });
  return total % 10 === 0 ? null : "The check digit does not match; check for a mistyped digit.";
}

/** 13 digits reads as an SA ID; anything else as a passport number. */
export function idTypeOf(raw: string): "SAID" | "Passport" {
  return /^\d{13}$/.test(raw.replace(/[\s-]/g, "")) ? "SAID" : "Passport";
}
