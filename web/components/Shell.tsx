"use client";

// The shared shell, matched to the FSA APS portal (components/layout/Sidebar.tsx and
// app/(app)/layout.tsx on aps-demo): dark collapsible sidebar with the FSA logo, grouped
// icon navigation, the signed-in user and Sign Out at its foot; pages on the photo background.
// Badges are the Training Hub's own addition: counts read from /nav-counts on every navigation.

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { findNav, NAV, NavCounts } from "@/lib/nav";
import { useAction, useMe } from "@/lib/hooks";

function readCollapsed() {
  try {
    return typeof window !== "undefined" && window.localStorage.getItem("sidebarCollapsed") === "true";
  } catch {
    return false;
  }
}

export function longDate(iso?: string) {
  if (!iso) return "";
  return new Date(iso + "T00:00:00").toLocaleDateString("en-ZA", { weekday: "short", day: "numeric", month: "long", year: "numeric" });
}

export default function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  const [open, setOpen] = useState(false);
  // The sidebar renders only after /me resolves on the client, so reading storage here is safe.
  const [collapsed, setCollapsed] = useState(readCollapsed);

  // Rule 6: the rail reads one endpoint, computed from the registers on every navigation.
  const counts = useQuery({
    queryKey: ["/nav-counts", pathname],
    queryFn: () => api<NavCounts>("/nav-counts"),
    enabled: me.isSuccess,
  });
  const clock = useAction<{ days?: number; reset?: boolean }>("POST", "/clock");
  const logout = useAction("POST", "/auth/logout");

  useEffect(() => {
    if (me.error?.status === 401 || me.error?.status === 403) router.replace("/login");
  }, [me.error, router]);

  function toggle() {
    setCollapsed((c) => {
      try { window.localStorage.setItem("sidebarCollapsed", String(!c)); } catch { /* storage unavailable */ }
      return !c;
    });
  }

  if (!me.data) {
    return <div className="content"><p className="muted">{me.isError ? "Signing you out…" : "Opening the Training Hub…"}</p></div>;
  }
  const user = me.data.data;
  const today = (counts.data?.meta.today as string | undefined) ?? (me.data.meta.today as string | undefined);
  const moved = Boolean(counts.data?.meta.clockMoved ?? me.data.meta.clockMoved);
  const where = findNav(pathname);
  const badges = counts.data?.data ?? {};

  return (
    <div className="app">
      {open ? <div className="sidebar-scrim" onClick={() => setOpen(false)} /> : null}
      <div className={`sidebar-wrapper${open ? " open" : ""}`}>
        <aside className={`side${collapsed ? " collapsed" : ""}`} aria-label="Training Hub">
          {!collapsed ? (
            <div className="side-brand">
              <Image src="/brand/fsa-logo.png" alt="FSA Logo" width={110} height={57} priority />
              <div className="side-brand-title">Food Safety Agency</div>
              <div className="side-brand-sub">FSA Academy · Training Hub</div>
            </div>
          ) : null}
          <button className="side-toggle" onClick={toggle} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            <i className={`fas fa-chevron-${collapsed ? "right" : "left"}`} aria-hidden />
          </button>
          <nav className="sidebar-nav">
            {NAV.map((g) => {
              // Screens not built yet are left out of the rail rather than shown as placeholders.
              const items = g.items.filter((i) => i.built && user.segments.includes(i.segment) && (!i.needs || user[i.needs]));
              if (!items.length) return null;
              return (
                <div key={g.group}>
                  {!collapsed ? <div className="side-group-label">{g.group}</div> : null}
                  <ul>
                    {items.map((i) => {
                      const n = i.badge ? badges[i.badge] : 0;
                      const active = where?.item.href === i.href;
                      return (
                        <li key={i.href}>
                          <Link href={i.href} className={`side-item${active ? " active" : ""}${i.sub && !collapsed ? " sub" : ""}`} aria-current={active ? "page" : undefined}
                                title={collapsed ? i.label : undefined} onClick={() => setOpen(false)}>
                            <i className={i.icon} aria-hidden />
                            {!collapsed ? <span>{i.label}</span> : null}
                            {n ? <b className="side-badge" aria-label={`${n} outstanding`}>{n}</b> : null}
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </nav>
          <div className="side-foot">
            {!collapsed ? (
              <div className="side-user">
                <div className="side-avatar"><i className="fas fa-user" aria-hidden /></div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="side-user-name">{user.name}</div>
                  <div className="side-user-role">{user.roleLabel}</div>
                </div>
              </div>
            ) : null}
            <button className="side-signout" title={collapsed ? "Sign Out" : undefined}
                    onClick={() => logout.mutate(undefined, { onSettled: () => { qc.clear(); router.replace("/login"); } })}>
              <i className="fas fa-sign-out-alt" aria-hidden />{!collapsed ? " Sign Out" : null}
            </button>
          </div>
        </aside>
      </div>

      <div id="main-content">
        <div className="mobile-topbar">
          <button onClick={() => setOpen(true)} aria-label="Open menu"><i className="fas fa-bars" aria-hidden /></button>
        </div>
        <main className="content">
          <div className="clock-slot">
            <div className={`clock${moved ? " moved" : ""}`} title={moved ? "Demo date: moved away from today" : "Today"}>
              {user.canMoveClock ? (
                <button disabled={clock.isPending} onClick={() => clock.mutate({ days: -1 })} aria-label="Move the demo clock back a day">
                  <i className="fas fa-chevron-left" aria-hidden />
                </button>
              ) : null}
              <span>{moved ? <b className="clock-flag">Demo date</b> : null}<i className="far fa-calendar" aria-hidden /> {longDate(today)}</span>
              {user.canMoveClock ? (
                <button disabled={clock.isPending} onClick={() => clock.mutate({ days: 1 })} aria-label="Move the demo clock forward a day">
                  <i className="fas fa-chevron-right" aria-hidden />
                </button>
              ) : null}
              {user.canMoveClock && moved ? (
                <button className="clock-today" disabled={clock.isPending} onClick={() => clock.mutate({ reset: true })}>Back to today</button>
              ) : null}
            </div>
          </div>
          {children}
        </main>
      </div>
    </div>
  );
}
