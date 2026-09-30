"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, CircleDot } from "lucide-react";
import { boardApi, errorMessage, BoardCell, BoardRow } from "@/lib/api";
import { Eyebrow } from "@/components/status-chip";
import { MorningBrief } from "@/components/assist";
import { cn } from "@/lib/utils";

const STREAMS = [["sales", "Sales"], ["purchases", "Purchases & ITC"], ["worksheet", "Tax worksheet"]] as const;
const FLIP: Record<BoardCell["tone"], string> = { done: "flip-done", action: "flip-needs", blocked: "flip-blocked", waiting: "" };
const href = (row: BoardRow, cell: BoardCell) => `/periods/${row.period_id}/${cell.target}`;

// Row remark: the most urgent state across the three streams.
function remark(row: BoardRow): { tone: BoardCell["tone"]; text: string } {
  const tones = STREAMS.map(([key]) => row[key].tone);
  if (tones.includes("blocked")) return { tone: "blocked", text: "Blocked" };
  if (tones.includes("action")) return { tone: "action", text: "Needs you" };
  if (tones.every(t => t === "done")) return { tone: "done", text: "Complete" };
  return { tone: "waiting", text: "Waiting" };
}

function FlipTile({ tone, delay, children }: { tone: BoardCell["tone"]; delay: number; children: React.ReactNode }) {
  return <span className={cn("flip-tile", FLIP[tone])} style={{ animationDelay: `${delay}ms` }}>{children}</span>;
}

export default function Board() {
  const [rows, setRows] = useState<BoardRow[] | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState("");
  useEffect(() => {
    let active = true;
    boardApi.get().then(r => { if (active) { setRows(r); setNow(new Date().toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }).toUpperCase()); } }).catch(e => { if (active) setError(errorMessage(e)); });
    return () => { active = false; };
  }, []);

  const needs = (rows || []).flatMap(row => STREAMS.map(([key, label]) => ({ row, label, cell: row[key] }))).filter(x => x.cell.tone === "action" || x.cell.tone === "blocked");
  const blocked = needs.filter(n => n.cell.tone === "blocked");

  return <div className="console-content w-full space-y-6">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div><Eyebrow className="text-primary">Departures</Eyebrow><h2 className="mt-1 font-display text-4xl font-semibold md:text-6xl">Everything due, at a glance.</h2></div>
      <Link href="/clients" className="font-label text-xs font-bold uppercase tracking-widest underline underline-offset-4">Manage clients</Link>
    </div>
    {error && <p role="alert" className="red-ink">{error}</p>}
    {!rows && !error && <p className="text-sm text-muted-foreground">Loading the board…</p>}
    {rows && rows.length > 0 && <MorningBrief />}

    {rows && rows.length === 0 && <div className="paper-card py-14 text-center">
      <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full border border-dashed border-primary/50 font-display text-xl">∅</div>
      <h3 className="font-display text-2xl">No departures scheduled</h3>
      <p className="mt-1 text-sm text-muted-foreground">Add a client, a demo registration and a period to see its work here.</p>
      <Link href="/clients" className="mt-4 inline-flex items-center gap-1 text-sm font-semibold text-primary">Go to clients <ArrowRight className="h-4 w-4" /></Link>
    </div>}

    {rows && rows.length > 0 && <>
      <section aria-labelledby="needs-heading">
        <div className="mb-3 flex items-center gap-2"><CircleDot className="size-4 text-status-needs" /><Eyebrow><span id="needs-heading">Boarding now — needs you</span></Eyebrow></div>
        {needs.length === 0 ? <p className="paper-card text-sm text-muted-foreground">Nothing is waiting on you. Everything else is done or waiting for files.</p>
          : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {needs.slice(0, 6).map(({ row, label, cell }) => <article className="ticket-card" data-testid="needs-card" key={row.period_id + label}>
              <div className="min-w-0"><Eyebrow className={cell.tone === "blocked" ? "text-destructive" : "text-primary"}>{label} · {row.period_code}</Eyebrow><h3 className="mt-1 truncate font-display text-2xl">{row.client_name}</h3><p className="mt-2 text-sm text-muted-foreground">{cell.label}</p></div>
              <Link href={href(row, cell)} className="inline-flex shrink-0 items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground">Open <ArrowRight className="h-4 w-4" /></Link>
            </article>)}
          </div>}
        {needs.length > 6 && <p className="mt-2 text-xs text-muted-foreground">+{needs.length - 6} more on the board below.</p>}
      </section>

      {blocked.length > 0 && <div className="delayed-strip" role="status"><AlertTriangle className="h-4 w-4 shrink-0" /><Eyebrow>Delayed</Eyebrow><span>{blocked.map(b => `${b.row.client_name}: ${b.cell.label}`).join(" · ")}</span></div>}

      <section className="departure-board" aria-labelledby="board-heading">
        <div className="flex items-center justify-between border-b border-board-line px-4 py-3">
          <div><Eyebrow className="text-board-muted">GST Helper desk</Eyebrow><h3 id="board-heading" className="font-display text-2xl text-board-ink">Departures</h3></div>
          <span className="font-figures text-xs text-board-muted">{now}</span>
        </div>
        <div className="board-scroll"><div className="min-w-[980px]">
          <div className="board-grid board-head"><span>Client</span><span>Period</span>{STREAMS.map(([, label]) => <span key={label}>{label}</span>)}<span>Remarks</span></div>
          {rows.map((row, index) => {
            const r = remark(row);
            return <div className="board-grid board-row" data-testid="board-row" key={row.period_id}>
              <Link href={`/clients/${row.client_id}`} className="board-client hover:underline"><b>{row.client_name}</b><small>{row.registration}</small></Link>
              <FlipTile tone="waiting" delay={index * 45}>{row.period_code}</FlipTile>
              {STREAMS.map(([key], i) => <Link key={key} href={href(row, row[key])} aria-label={`${row.client_name} ${key}: ${row[key].label}`}><FlipTile tone={row[key].tone} delay={index * 45 + (i + 1) * 25}>{row[key].label}</FlipTile></Link>)}
              <FlipTile tone={r.tone} delay={index * 45 + 100}>{r.text}</FlipTile>
            </div>;
          })}
        </div></div>
      </section>
    </>}
  </div>;
}
