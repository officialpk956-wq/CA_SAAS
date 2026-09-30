import { useEffect, useState } from "react";
import {
  Archive, BookOpenText, Calculator, ChevronLeft, ChevronRight, History,
  Landmark, Menu, Moon, PackageSearch, ReceiptIndianRupee, Sun, Users, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { DemoPill, Eyebrow } from "./primitives";
import { screenCopy } from "@/mock/data";
import {
  BoardScreen, CategoriesScreen, ClientsScreen, HistoryScreen, ReconciliationScreen,
  SalesScreen, WorksheetScreen, WorkspaceScreen,
} from "./screens";
import { cn } from "@/lib/utils";

const nav = [
  { id: "board", label: "The Board", icon: Landmark },
  { id: "clients", label: "Clients", icon: Users },
  { id: "worksheet", label: "Tax Worksheet", icon: Calculator },
  { id: "reconciliation", label: "Reconciliation", icon: PackageSearch },
  { id: "sales", label: "Sales", icon: ReceiptIndianRupee },
  { id: "categories", label: "Categories", icon: Archive },
  { id: "history", label: "History & Audit", icon: History },
];

export function GstHelperApp() {
  const [view, setView] = useState("board");
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [dark, setDark] = useState(false);
  const copy = screenCopy[view as keyof typeof screenCopy] ?? screenCopy.board;

  useEffect(() => { document.documentElement.classList.toggle("dark", dark); }, [dark]);
  const navigate = (next: string) => { setView(next); setMobileOpen(false); window.scrollTo({ top: 0, behavior: "smooth" }); };

  return <div className="gst-app">
    <button className={cn("mobile-scrim", mobileOpen && "open")} aria-label="Close navigation" onClick={() => setMobileOpen(false)}/>
    <aside className={cn("ledger-spine", collapsed && "collapsed", mobileOpen && "mobile-open")}>
      <div className="seal-row"><button className="brand-seal" title="GST Helper home" onClick={() => navigate("board")}><BookOpenText/><span>GH</span></button>{!collapsed && <div><b>GST Helper</b><small>Monthly work console</small></div>}<Button className="mobile-close" variant="ghost" size="icon" onClick={() => setMobileOpen(false)}><X/></Button></div>
      <Eyebrow className={cn("nav-label", collapsed && "sr-only")}>August ledger</Eyebrow>
      <nav>{nav.map((item) => <button className={cn(view === item.id && "active")} key={item.id} onClick={() => navigate(item.id)} title={collapsed ? item.label : undefined}><item.icon/><span>{item.label}</span></button>)}</nav>
      <button className="collapse-control" onClick={() => setCollapsed((value) => !value)}>{collapsed ? <ChevronRight/> : <ChevronLeft/>}<span>{collapsed ? "Expand" : "Collapse spine"}</span></button>
    </aside>
    <main className="console-main">
      <header className="topbar"><Button aria-label="Open navigation" className="menu-trigger" variant="outline" size="icon" onClick={() => setMobileOpen(true)}><Menu/></Button><div className="title-block"><h1>{copy[0]}</h1><p>{copy[1]}</p></div><div className="top-actions"><label className="period-picker"><Eyebrow>Period</Eyebrow><select aria-label="Tax period"><option>AUG 2026</option><option>JUL 2026</option><option>JUN 2026</option></select></label><Button aria-label={dark ? "Use Day Ledger" : "Use Night Ledger"} variant="outline" size="icon" onClick={() => setDark((value) => !value)} title={dark ? "Use Day Ledger" : "Use Night Ledger"}>{dark ? <Sun/> : <Moon/>}</Button><DemoPill/></div></header>
      <div className="mobile-demo"><DemoPill/></div>
      <div className="console-content">{view === "board" && <BoardScreen navigate={navigate}/>} {view === "clients" && <ClientsScreen navigate={navigate}/>} {view === "workspace" && <WorkspaceScreen navigate={navigate}/>} {view === "reconciliation" && <ReconciliationScreen/>} {view === "sales" && <SalesScreen/>} {view === "worksheet" && <WorksheetScreen/>} {view === "categories" && <CategoriesScreen/>} {view === "history" && <HistoryScreen/>}</div>
    </main>
  </div>;
}