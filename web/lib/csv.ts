// Minimal CSV / pasted-list reader: commas, tabs (pasted from Excel) or semicolons, quoted fields,
// and a header row if the first line names its columns.

export type Row = Record<string, string>;

function splitLine(line: string, sep: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (quoted && line[i + 1] === '"') { cur += '"'; i++; } else quoted = !quoted;
    } else if (ch === sep && !quoted) {
      out.push(cur.trim());
      cur = "";
    } else cur += ch;
  }
  out.push(cur.trim());
  return out;
}

/** Parse text into rows keyed by `columns`. A header row is recognised by any known alias. */
export function parseList(text: string, columns: string[], aliases: Record<string, string[]>): Row[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return [];
  const sep = lines[0].includes("\t") ? "\t" : lines[0].includes(";") && !lines[0].includes(",") ? ";" : ",";
  let order = columns;
  const first = splitLine(lines[0], sep).map((c) => c.toLowerCase());
  const isHeader = first.some((c) => Object.values(aliases).some((names) => names.includes(c)));
  if (isHeader) {
    order = first.map((c) => Object.keys(aliases).find((k) => aliases[k].includes(c)) ?? "");
    lines.shift();
  }
  return lines.map((line) => {
    const cells = splitLine(line, sep);
    const row: Row = {};
    order.forEach((key, i) => { if (key) row[key] = cells[i] ?? ""; });
    return row;
  });
}
