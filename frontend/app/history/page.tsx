"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Search } from "lucide-react";
import { errorMessage, worksheetApi, AuditEntry } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Eyebrow } from "@/components/status-chip";
import { cn } from "@/lib/utils";

const day = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase();
const time = (iso: string) => new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

function History() {
  const periodId = useSearchParams().get("period_id") || undefined;
  const [events, setEvents] = useState<AuditEntry[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { let active = true; worksheetApi.auditEvents(periodId).then(e => { if (active) setEvents(e); }).catch(e => { if (active) setError(errorMessage(e)); }); return () => { active = false; }; }, [periodId]);
  const q = query.toLowerCase();
  const shown = (events || []).filter(e => !q || [e.action, e.summary, e.client_name, e.period_code, e.actor].some(v => v?.toLowerCase().includes(q)));
  return <div className="console-content w-full space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted-foreground">Newest first{periodId ? " for this period" : " across your organization"} · latest 200 · summaries never contain full source rows.</p>
      <Link className="text-sm underline underline-offset-4" href={periodId ? `/periods/${periodId}/workspace` : "/"}>{periodId ? "Back to period" : "Board"}</Link>
    </div>
    <div className="relative"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input aria-label="Search history" className="pl-9" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search actions, clients, periods or actors…" /></div>
    {error && <p role="alert" className="red-ink">{error}</p>}
    {!events && !error && <p className="text-sm text-muted-foreground">Unrolling the receipt…</p>}
    {events && <div className="receipt-roll">
      {shown.map((e, i) => <article key={e.id} data-testid="audit-row" className={cn("audit-line", i > 0 && day(e.created_at) !== day(shown[i - 1].created_at) && "new-day")}>
        <div className="audit-time"><Eyebrow>{day(e.created_at)}</Eyebrow><span>{time(e.created_at)}</span></div>
        <div className="min-w-0"><Eyebrow className="text-primary">{e.action.replaceAll("_", " ")}</Eyebrow><h3>{e.client_name ? `${e.client_name} · ${e.period_code}` : "Organization"}</h3><p className="break-words">{e.summary || "—"}</p></div>
        <span className="audit-actor">{e.actor || "System"}</span>
      </article>)}
      {!shown.length && <div className="py-14 text-center"><h3 className="font-display text-xl">No receipt lines</h3><p className="mt-1 text-sm text-muted-foreground">Try a broader search.</p></div>}
    </div>}
  </div>;
}

export default function HistoryPage() { return <Suspense fallback={<p className="console-content">Loading…</p>}><History /></Suspense>; }
