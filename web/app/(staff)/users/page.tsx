"use client";

// Managing staff accounts: add a user, change role, position and access, reset a password, suspend
// or reinstate. Open to the head of department and the system administrator; the API enforces it.

import { useState } from "react";
import { AuditTrail, Blocked, Hero, LoadError, Loading, Register, SectionHead, Status } from "@/components/ui";
import { Modal } from "@/components/registration";
import { SearchSelect } from "@/components/SearchSelect";
import type { Tone } from "@/lib/api";
import { useAction, useMe, useRegister } from "@/lib/hooks";

type Grants = Record<string, [string, string] | string[]>;
type User = { ref: string; name: string; position: string; reportsTo: string; reportsToRef: string; role: string; roleLabel: string;
  segments: string; state: string; tone: Tone; serviceAccount: boolean; username: string; email: string; isMe: boolean;
  suspendedReason: string; grants: Grants };
type Options = { roles: { code: string; label: string; defaults: Grants }[]; segments: { code: string; name: string }[];
  people: { ref: string; name: string }[] };

function Credentials({ who, username, password, onClose }: { who: string; username: string; password: string; onClose: () => void }) {
  return (
    <div className="callout ok" role="status">
      <h4>Sign-in details for {who}</h4>
      <p>Username <b className="mono">{username}</b> · Password <b className="mono">{password}</b></p>
      <p className="small">Give these to {who} now: the password is shown only this once. They can sign in at the Training Hub straight away.</p>
      <button className="btn btn-sm" onClick={onClose}>Done</button>
    </div>
  );
}

function AddUser({ onDone }: { onDone: (r: { ref: string; username: string; password: string }, name: string) => void }) {
  const opts = useRegister<Options>("/users/options");
  const save = useAction<Record<string, string>, { ref: string; username: string; password: string }>("POST", "/users");
  const [f, setF] = useState({ name: "", email: "", position: "", role: "", reportsTo: "" });
  const [tried, setTried] = useState(false);
  if (!opts.data) return <p className="muted">Loading…</p>;
  const p: Record<string, string> = {};
  if (!f.name.trim()) p.name = "Give the person's full name.";
  if (!f.role) p.role = "Choose the role.";
  if (!f.position.trim()) p.position = "Give the position.";
  if (f.email.trim() && !f.email.includes("@")) p.email = "Enter a valid email address, or leave it blank.";
  const e = tried ? p : {};
  const role = opts.data.data.roles.find((r) => r.code === f.role);
  const segName = (c: string) => opts.data?.data.segments.find((s) => s.code === c)?.name ?? c;
  return (
    <div className="stack-12">
      <Blocked refusal={save.refusal} />
      <div className="form-grid">
        <div className="field"><label htmlFor="nu-name">Full name</label>
          <input id="nu-name" value={f.name} className={e.name ? "invalid" : undefined} onChange={(x) => setF({ ...f, name: x.target.value })} />
          {e.name ? <span className="field-error">{e.name}</span> : null}</div>
        <div className="field"><label htmlFor="nu-role">Role</label>
          <select id="nu-role" value={f.role} className={e.role ? "invalid" : undefined} onChange={(x) => setF({ ...f, role: x.target.value })}>
            <option value="">Choose…</option>{opts.data.data.roles.map((r) => <option key={r.code} value={r.code}>{r.label}</option>)}
          </select>{e.role ? <span className="field-error">{e.role}</span> : null}</div>
        <div className="field"><label htmlFor="nu-pos">Position</label>
          <input id="nu-pos" value={f.position} placeholder="e.g. Facilitator — IMI and Classification" className={e.position ? "invalid" : undefined}
                 onChange={(x) => setF({ ...f, position: x.target.value })} />{e.position ? <span className="field-error">{e.position}</span> : null}</div>
        <div className="field"><label htmlFor="nu-email">Email <span className="optional">(optional)</span></label>
          <input id="nu-email" type="email" value={f.email} className={e.email ? "invalid" : undefined} onChange={(x) => setF({ ...f, email: x.target.value })} />
          {e.email ? <span className="field-error">{e.email}</span> : null}</div>
        <div className="field"><label htmlFor="nu-rep">Reports to <span className="optional">(optional)</span></label>
          <SearchSelect id="nu-rep" value={f.reportsTo} onChange={(v) => setF({ ...f, reportsTo: v })} placeholder="Type to search people…"
                        options={opts.data.data.people.map((x) => ({ value: x.ref, label: x.name }))} /></div>
      </div>
      {role ? (
        <p className="small" style={{ margin: 0 }}><b>{role.label}</b> starts with access to: {Object.keys(role.defaults).length
          ? Object.entries(role.defaults).map(([k, v]) => `${segName(k)} (${v[0]}${v[1] === "own" ? ", own only" : ""})`).join(", ")
          : "everything, read-only, by role"}. You can adjust it after adding.</p>
      ) : null}
      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending} onClick={() => {
          setTried(true);
          if (Object.keys(p).length) return;
          save.mutate(f, { onSuccess: (r) => onDone(r.data, f.name.trim()) });
        }}>Add user</button>
        <span className="small muted">A username and password are made for them and shown once.</span>
      </div>
    </div>
  );
}

function UserPanel({ u, onDone }: { u: User; onDone: (what: string, creds?: { username: string; password: string }) => void }) {
  const opts = useRegister<Options>("/users/options");
  const save = useAction<Record<string, unknown>>("PATCH", `/users/${u.ref}`);
  const suspend = useAction<{ reason: string }>("POST", `/users/${u.ref}/suspend`);
  const reinstate = useAction<Record<string, never>>("POST", `/users/${u.ref}/reinstate`);
  const reset = useAction<Record<string, never>, { password: string }>("POST", `/users/${u.ref}/password`);
  const [f, setF] = useState({ position: u.position, email: u.email, role: u.role, reportsTo: u.reportsToRef });
  const [grants, setGrants] = useState<Grants>(u.grants);
  const [reason, setReason] = useState("");
  const [suspending, setSuspending] = useState(false);
  if (u.serviceAccount) return <p className="small muted" style={{ margin: 0 }}>A service account for the HR Hub link. It has no sign-in and is not managed here.</p>;
  if (!opts.data) return <p className="muted">Loading…</p>;
  const o = opts.data.data;
  const roleAllowed = o.roles.some((r) => r.code === u.role);
  const refusal = save.refusal ?? suspend.refusal ?? reinstate.refusal ?? reset.refusal;
  const setGrant = (code: string, access: string, scope?: string) =>
    setGrants((g) => { const n = { ...g }; if (!access) delete n[code]; else n[code] = [access, scope ?? (g[code]?.[1] || "all")]; return n; });
  const grantsChanged = JSON.stringify(grants) !== JSON.stringify(u.grants);
  const roleChanged = f.role !== u.role;
  const detailsChanged = f.position !== u.position || f.email !== u.email || f.reportsTo !== u.reportsToRef || roleChanged;
  const suspended = u.state === "Suspended";

  return (
    <div className="stack-12">
      <Blocked refusal={refusal} />
      <div className="form-grid cols-4">
        <div className="field"><label>Username</label><div className="readonly-value mono">{u.username}</div></div>
        <div className="field"><label htmlFor={`ur-${u.ref}`}>Role</label>
          <select id={`ur-${u.ref}`} value={f.role} disabled={u.isMe || !roleAllowed} onChange={(x) => setF({ ...f, role: x.target.value })}>
            {roleAllowed ? o.roles.map((r) => <option key={r.code} value={r.code}>{r.label}</option>) : <option value={u.role}>{u.roleLabel}</option>}
          </select>
          {u.isMe ? <span className="small muted">You cannot change your own role.</span>
            : roleChanged ? <span className="small tone-warn">Access resets to the new role&rsquo;s default unless you adjust it below.</span> : null}</div>
        <div className="field"><label htmlFor={`up-${u.ref}`}>Position</label>
          <input id={`up-${u.ref}`} value={f.position} onChange={(x) => setF({ ...f, position: x.target.value })} /></div>
        <div className="field"><label htmlFor={`ue-${u.ref}`}>Email</label>
          <input id={`ue-${u.ref}`} type="email" value={f.email} onChange={(x) => setF({ ...f, email: x.target.value })} /></div>
        <div className="field"><label htmlFor={`ut-${u.ref}`}>Reports to</label>
          <SearchSelect id={`ut-${u.ref}`} value={f.reportsTo} onChange={(v) => setF({ ...f, reportsTo: v })} placeholder="Type to search people…"
                        options={o.people.filter((x) => x.ref !== u.ref).map((x) => ({ value: x.ref, label: x.name }))} /></div>
      </div>

      <div>
        <div className="eyebrow">Access</div>
        {u.role === "Director" && !Object.keys(grants).length ? <p className="small muted" style={{ margin: 0 }}>Directors read everything by their role.</p> : null}
        <table className="plain-table">
          <thead><tr><th>Area of the hub</th><th>Access</th><th>Which records</th></tr></thead>
          <tbody>
            {o.segments.map((s) => {
              const g = grants[s.code];
              // Training home is everyone's start page: it is always viewable, so there is nothing to grant.
              if (s.code === "overview") return (
                <tr key={s.code}><td>{s.name}</td><td colSpan={2} className="small muted">Everyone who can sign in can view it.</td></tr>
              );
              return (
                <tr key={s.code}>
                  <td>{s.name}</td>
                  <td>
                    <select aria-label={`${s.name} access`} value={g?.[0] ?? ""} disabled={u.isMe} onChange={(x) => setGrant(s.code, x.target.value)}>
                      <option value="">{READS_ALL.includes(u.role) ? "View only (by role)" : "No access"}</option>
                      <option value="read">View only</option><option value="write">View and change</option>
                    </select>
                  </td>
                  <td>
                    {g ? (
                      <select aria-label={`${s.name} records`} value={g[1] ?? "all"} disabled={u.isMe} onChange={(x) => setGrant(s.code, g[0], x.target.value)}>
                        <option value="all">All records</option><option value="own">Their own only</option>
                      </select>
                    ) : <span className="muted">—</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="row">
        <button className="btn btn-primary" disabled={save.isPending || (!detailsChanged && !grantsChanged)}
                onClick={() => save.mutate({ position: f.position, email: f.email, reportsTo: f.reportsTo || "",
                  ...(roleChanged ? { role: f.role } : {}), ...(grantsChanged && !u.isMe ? { grants } : {}) },
                  { onSuccess: (r) => onDone(r.meta.audit?.what ?? "") })}>Save changes</button>
        <button className="btn" disabled={reset.isPending}
                onClick={() => reset.mutate({}, { onSuccess: (r) => onDone(r.meta.audit?.what ?? "", { username: u.username, password: r.data.password }) })}>
          <i className="fas fa-key" aria-hidden /> Reset password</button>
        <span className="spacer" />
        {u.isMe ? null : suspended ? (
          <button className="btn" disabled={reinstate.isPending} onClick={() => reinstate.mutate({}, { onSuccess: (r) => onDone(r.meta.audit?.what ?? "") })}>
            <i className="fas fa-user-check" aria-hidden /> Reinstate</button>
        ) : !suspending ? (
          <button className="btn btn-ghost-danger" onClick={() => setSuspending(true)}><i className="fas fa-user-slash" aria-hidden /> Suspend</button>
        ) : null}
      </div>
      {suspending ? (
        <div className="card inset-form">
          <div className="field"><label htmlFor={`us-${u.ref}`}>Why is {u.name} being suspended?</label>
            <input id={`us-${u.ref}`} value={reason} placeholder="e.g. Left FSA; on extended leave" onChange={(x) => setReason(x.target.value)} /></div>
          <div className="row">
            <button className="btn btn-danger" disabled={suspend.isPending || !reason.trim()}
                    onClick={() => suspend.mutate({ reason }, { onSuccess: (r) => { setSuspending(false); onDone(r.meta.audit?.what ?? ""); } })}>Suspend account</button>
            <button className="btn" onClick={() => setSuspending(false)}>Keep active</button>
            <span className="small muted">They can no longer sign in. Their records and history stay.</span>
          </div>
        </div>
      ) : null}
      {suspended && u.suspendedReason ? <p className="small tone-bad" style={{ margin: 0 }}>Suspended: {u.suspendedReason}</p> : null}
    </div>
  );
}

// These roles can view every area by their role, whatever is granted here (identity.models.READ_ALL_ROLES).
const READS_ALL = ["TrainingManager", "Director", "SystemAdministrator"];

export default function UserManagement() {
  const q = useRegister<User[]>("/users");
  const me = useMe();
  const [open, setOpen] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState("");
  const [creds, setCreds] = useState<{ who: string; username: string; password: string } | null>(null);
  const [filter, setFilter] = useState({ q: "", role: "", state: "" });
  if (q.error) return <LoadError error={q.error} />;
  if (!q.data) return <Loading what="accounts" />;
  const all = q.data.data.filter((u) => !u.serviceAccount);
  const canManage = me.data?.data.canManageUsers ?? false;
  const words = filter.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const rows = all.filter((u) => (!filter.role || u.role === filter.role) && (!filter.state || u.state.startsWith(filter.state))
    && words.every((w) => `${u.name} ${u.username} ${u.position} ${u.email} ${u.ref}`.toLowerCase().includes(w)));
  const roles = Array.from(new Map(all.map((u) => [u.role, u.roleLabel])).entries()).sort((a, b) => a[1].localeCompare(b[1]));
  const done = (what: string, c?: { username: string; password: string }, who?: string) => {
    setNotice(what);
    if (c) setCreds({ who: who ?? "", ...c });
  };
  return (
    <>
      <Hero
        stats={[
          { v: String(all.length), l: "Users", c: "Staff accounts" },
          { v: String(all.filter((u) => u.tone === "ok").length), l: "Active", c: "Can sign in" },
          { v: String(all.filter((u) => u.tone === "bad").length), l: "Suspended", c: "Cannot sign in" },
        ]}
      />
      {creds ? <Credentials who={creds.who} username={creds.username} password={creds.password} onClose={() => setCreds(null)} /> : null}
      {notice && !creds ? <div className="callout ok" role="status"><p><b>Saved.</b> {notice}</p></div> : null}
      <SectionHead title="Users">
        {canManage ? <button className="btn btn-teal" onClick={() => setAdding(true)}>Add user</button> : null}
      </SectionHead>
      <div className="card filter-bar">
        <div className="field filter-search"><label htmlFor="uf-q">Search</label>
          <input id="uf-q" type="search" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })}
                 placeholder="Name, username, position or email" /></div>
        <div className="field"><label htmlFor="uf-role">Role</label>
          <select id="uf-role" value={filter.role} onChange={(e) => setFilter({ ...filter, role: e.target.value })}>
            <option value="">Any role</option>{roles.map(([c, l]) => <option key={c} value={c}>{l}</option>)}
          </select></div>
        <div className="field"><label htmlFor="uf-state">Status</label>
          <select id="uf-state" value={filter.state} onChange={(e) => setFilter({ ...filter, state: e.target.value })}>
            <option value="">Any</option><option value="Active">Active</option><option value="Suspended">Suspended</option>
          </select></div>
        <div className="filter-foot"><span className="small muted">Showing {rows.length} of {all.length} users</span></div>
      </div>
      <Register rows={rows} rowKey={(r) => r.ref}
        onRow={(r) => setOpen(r.ref === open ? null : r.ref)}
        expanded={(r) => (r.ref === open && canManage ? (
          <UserPanel key={JSON.stringify(r)} u={r} onDone={(w, c) => done(w, c, r.name)} />
        ) : null)}
        columns={[
          { key: "name", label: "Person", render: (r) => <><b>{r.name}</b>{r.isMe ? <span className="for-tag co">You</span> : null}<div className="small muted">{r.username}</div></> },
          { key: "pos", label: "Position", render: (r) => r.position },
          { key: "role", label: "Role", render: (r) => r.roleLabel },
          { key: "rep", label: "Reports to", render: (r) => r.reportsTo || "—" },
          { key: "seg", label: "Access", render: (r) => <span className="small">{r.segments}</span> },
          { key: "state", label: "Status", render: (r) => <><Status tone={r.tone}>{r.state}</Status>
            {r.state === "Suspended" && r.suspendedReason ? <div className="small muted">{r.suspendedReason}</div> : null}</> },
        ]} />
      {adding ? (
        <Modal title="Add a user" onClose={() => setAdding(false)} wide>
          <AddUser onDone={(r, name) => { setAdding(false); setNotice(""); setCreds({ who: name, username: r.username, password: r.password }); setOpen(r.ref); }} />
        </Modal>
      ) : null}
      <AuditTrail />
    </>
  );
}
