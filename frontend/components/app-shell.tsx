"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Archive, BookMarked, BookOpenText, Calculator, ChevronLeft, ChevronRight, FolderInput, History, Landmark, Inbox, LogOut, Menu, Moon, PackageSearch, ReceiptIndianRupee, Sun, UserCog, Users, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { authApi, boardApi, BoardRow, Me } from "@/lib/api";

type Item = { href: string; label: string; icon: React.ComponentType; exact?: boolean; section?: string };

// Title and subtitle shown in the top bar, by route.
const TITLES: [RegExp, string, string][] = [
  [/^\/$/, "The Board", "Every client, every return — from recorded workflow state"],
  [/^\/clients$/, "Clients", "Client folders, registrations and periods"],
  [/^\/clients\//, "Client folder", "Demo registrations and filing periods"],
  [/\/workspace$/, "Imports", "Purchase and statement files, validation and reconciliation runs"],
  [/\/review$/, "Reconciliation", "Trace every finding to its source"],
  [/\/ims$/, "IMS inbox", "Accept, reject or keep pending each supplier invoice"],
  [/\/categories$/, "Categories", "Confirm suggestions and maintain mappings"],
  [/\/sales$/, "Sales", "Review the period's sales register"],
  [/\/worksheet$/, "Tax Worksheet", "Build, review and explicitly approve"],
  [/^\/history/, "History & Audit", "Every action, figure and approval"],
  [/^\/knowledge/, "Knowledge & rules", "Client quirks, captured once and applied with approval"],
  [/^\/firm/, "Firm & team", "People, roles and the approval policy"],
];
const SECTIONS = ["worksheet", "review", "ims", "sales", "categories", "workspace"];
const PERIOD_KEY = "gsth_period";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const periodLabel = (code: string) => { const [y, m] = code.split("-"); return `${MONTHS[Number(m) - 1]} ${y}`.toUpperCase(); };

export function DemoPill() { return <span className="demo-pill">Synthetic demo — not for filing</span>; }

function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => { const t = setTimeout(() => setDark(document.documentElement.classList.contains("dark")), 0); return () => clearTimeout(t); }, []);
  function toggle() {
    const next = !dark; setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try { localStorage.setItem("theme", next ? "dark" : "light"); } catch { /* storage unavailable: theme applies for this visit only */ }
  }
  const label = dark ? "Use Day Ledger" : "Use Night Ledger";
  return <button type="button" onClick={toggle} aria-label={label} title={label} className="grid h-9 w-9 place-items-center rounded-md border bg-card hover:bg-muted">
    {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
  </button>;
}

function Account() {
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => { let active = true; authApi.me().then(m => { if (active) setMe(m); }).catch(() => {}); return () => { active = false; }; }, []);
  // A full page load (not client routing) so nothing from the signed-out session stays in memory.
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  async function signOut() { try { await authApi.logout(); } finally { window.location.assign("/login"); } }
  if (!me) return null;
  return <div className="flex items-center gap-2">
    <span className="hidden text-right leading-tight xl:block"><span className="block text-xs font-semibold" data-testid="firm-name">{me.firm}</span><span className="block text-[11px] text-muted-foreground">{me.email} · <span data-testid="my-role">{me.role}</span></span></span>
    <button type="button" onClick={signOut} aria-label="Sign out" title="Sign out" className="grid h-9 w-9 place-items-center rounded-md border bg-card hover:bg-muted"><LogOut className="h-4 w-4" /></button>
  </div>;
}

/** Which client-period the period screens (worksheet, reconciliation, sales, categories, imports) show. */
function usePeriod(path: string) {
  const [rows, setRows] = useState<BoardRow[]>([]);
  const [remembered, setRemembered] = useState<string | null>(null);
  const fromPath = path.match(/^\/periods\/([^/]+)/)?.[1] ?? null;
  useEffect(() => {
    let active = true;
    boardApi.get().then(r => { if (active) setRows(r); }).catch(() => {});
    const t = setTimeout(() => { try { setRemembered(localStorage.getItem(PERIOD_KEY)); } catch { /* no storage: fall back to the first period */ } }, 0);
    return () => { active = false; clearTimeout(t); };
  }, []);
  useEffect(() => { if (fromPath) { try { localStorage.setItem(PERIOD_KEY, fromPath); } catch { /* ignore */ } } }, [fromPath]);
  const valid = (id: string | null) => !!id && rows.some(r => r.period_id === id);
  const current = fromPath ?? (valid(remembered) ? remembered : rows[0]?.period_id ?? null);
  return { rows, current, row: rows.find(r => r.period_id === current) };
}

function PeriodPicker({ rows, current, path }: { rows: BoardRow[]; current: string | null; path: string }) {
  const router = useRouter();
  if (!rows.length) return null;
  const section = path.match(/^\/periods\/[^/]+\/([^/?]+)/)?.[1];
  const go = (id: string) => router.push(`/periods/${id}/${section && SECTIONS.includes(section) ? section : "worksheet"}`);
  return <label className="period-picker"><span className="font-label text-[0.68rem] font-bold uppercase tracking-[0.16em]">Period</span>
    <select aria-label="Period" value={current ?? ""} onChange={e => go(e.target.value)} className="max-w-[240px] truncate">
      {rows.map(r => <option key={r.period_id} value={r.period_id}>{r.client_name.replace(" (synthetic)", "")} · {periodLabel(r.period_code)}</option>)}
    </select></label>;
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  if (path === "/login" || path.startsWith("/u/")) return <div className="gst-app block">{children}</div>;
  return <SignedInShell path={path}>{children}</SignedInShell>;
}

function SignedInShell({ path, children }: { path: string; children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const { rows, current, row } = usePeriod(path);
  const [, title, subtitle] = TITLES.find(([re]) => re.test(path)) ?? [null, "GST Helper", ""];
  const periodHref = (section: string) => current ? `/periods/${current}/${section}` : "/clients";
  const items: Item[] = [
    { href: "/", label: "The Board", icon: Landmark, exact: true },
    { href: "/clients", label: "Clients", icon: Users },
    { href: periodHref("worksheet"), label: "Tax Worksheet", icon: Calculator, section: "worksheet" },
    { href: periodHref("review"), label: "Reconciliation", icon: PackageSearch, section: "review" },
    { href: periodHref("ims"), label: "IMS inbox", icon: Inbox, section: "ims" },
    { href: periodHref("sales"), label: "Sales", icon: ReceiptIndianRupee, section: "sales" },
    { href: periodHref("categories"), label: "Categories", icon: Archive, section: "categories" },
    { href: periodHref("workspace"), label: "Imports", icon: FolderInput, section: "workspace" },
    { href: "/knowledge", label: "Knowledge", icon: BookMarked },
    { href: "/history", label: "History & Audit", icon: History, exact: true },
    { href: "/firm", label: "Firm & team", icon: UserCog, exact: true },
  ];
  const active = (i: Item) => i.section ? path.startsWith("/periods/") && path.endsWith(`/${i.section}`) : i.exact ? path === i.href : path.startsWith(i.href);
  const ledger = row ? `${MONTH_NAMES[Number(row.period_code.split("-")[1]) - 1]} ledger` : "Ledger";

  return <div className="gst-app">
    <button className={cn("mobile-scrim", mobileOpen && "open")} aria-label="Close navigation" tabIndex={mobileOpen ? 0 : -1} onClick={() => setMobileOpen(false)} />
    <aside className={cn("ledger-spine", collapsed && "collapsed", mobileOpen && "mobile-open")}>
      <div className="seal-row">
        <Link href="/" className="brand-seal" title="GST Helper home" aria-label="GST Helper home"><BookOpenText /><span>GH</span></Link>
        {!collapsed && <div><b>GST Helper</b><small>Monthly work console</small></div>}
        <button className="mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X className="h-5 w-5" /></button>
      </div>
      <p className={cn("nav-label font-label text-[0.68rem] font-bold uppercase tracking-[0.16em]", collapsed && "sr-only")}>{ledger}</p>
      <nav aria-label="Main">{items.map(i => <Link key={i.label} href={i.href} onClick={() => setMobileOpen(false)} aria-current={active(i) ? "page" : undefined} title={collapsed ? i.label : undefined} className={cn(active(i) && "active")}><i.icon /><span>{i.label}</span></Link>)}</nav>
      <button className="collapse-control" onClick={() => setCollapsed(v => !v)}>{collapsed ? <ChevronRight /> : <ChevronLeft />}<span>{collapsed ? "Expand" : "Collapse spine"}</span></button>
    </aside>
    <div className="console-main">
      <header className="topbar">
        <button aria-label="Open navigation" className="menu-trigger h-9 w-9 place-items-center rounded-md border bg-card" onClick={() => setMobileOpen(true)}><Menu className="h-4 w-4" /></button>
        <div className="title-block"><h1>{title}</h1>{subtitle && <p>{subtitle}</p>}</div>
        <div className="top-actions"><PeriodPicker rows={rows} current={current} path={path} /><Account /><ThemeToggle /><DemoPill /></div>
      </header>
      <div className="mobile-demo"><DemoPill /></div>
      <main className="flex flex-col">{children}</main>
    </div>
  </div>;
}
