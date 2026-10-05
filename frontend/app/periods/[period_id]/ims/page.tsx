"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, errorMessage, imsApi, ImportBatch, ImsInbox, ImsItem } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Eyebrow, StatusChip, Tone } from "@/components/status-chip";

const ACTION_TONE: Record<string, Tone> = { accept: "done", reject: "blocked", pending: "action" };
const FINDING_TONE = (f: string | null): Tone => f === "matched" ? "done" : f === "validation_error" ? "blocked" : f ? "action" : "waiting";

export default function ImsPage() {
  const periodId = useParams().period_id as string;
  const [batch, setBatch] = useState<ImportBatch | null | undefined>(undefined);
  const [inbox, setInbox] = useState<ImsInbox | null>(null);
  const [note, setNote] = useState("");
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const imports: ImportBatch[] = await api.getImports(periodId);
    const statement = imports.filter(i => i.source_type === "statement" && i.status === "committed").sort((a, b) => b.created_at.localeCompare(a.created_at))[0] ?? null;
    setBatch(statement);
    if (statement) setInbox(await imsApi.get(statement.id));
  }, [periodId]);
  useEffect(() => { let active = true; const t = setTimeout(() => load().catch(e => { if (active) setError(errorMessage(e)); }), 0); return () => { active = false; clearTimeout(t); }; }, [load]);

  async function act(items: ImsItem[], action: string) {
    if (!batch) return;
    setBusy(true); setError("");
    try { await imsApi.act(batch.id, items.map(i => ({ record_id: i.id, action, previous_action_id: i.previous_action_id })), note); setNote(""); await load(); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  if (batch === undefined) return <div className="console-content">{error ? <p role="alert" className="red-ink">{error}</p> : <p className="text-sm text-muted-foreground">Opening the IMS inbox…</p>}</div>;
  if (!batch) return <div className="console-content"><p className="paper-card text-sm">No committed supplier statement for this period yet. <Link className="underline" href={`/periods/${periodId}/workspace`}>Upload and commit it under Imports</Link>.</p></div>;
  if (!inbox) return <div className="console-content"><p className="text-sm text-muted-foreground">Loading invoices…</p></div>;

  const untouchedMatches = inbox.items.filter(i => !i.action && i.finding === "matched");
  const shown = inbox.items.filter(i => filter === "all" || (filter === "no_action" ? !i.action : i.action === filter));
  return <div className="console-content w-full space-y-5">
    <p className="max-w-3xl text-sm text-muted-foreground">{inbox.notice}</p>
    {error && <p role="alert" className="red-ink">{error}</p>}
    <div className="summary-strip" data-testid="ims-counts">{(["accept", "reject", "pending", "no_action"] as const).map(k => <div key={k}><strong>{inbox.counts[k]}</strong><Eyebrow>{k.replace("_", " ")}</Eyebrow></div>)}<div><strong>{inbox.items.length}</strong><Eyebrow>invoices</Eyebrow></div></div>

    <section className="paper-card space-y-3">
      <label className="block space-y-1 text-sm"><Eyebrow>Note for the next action (required)</Eyebrow><Textarea aria-label="IMS note" value={note} onChange={e => setNote(e.target.value)} placeholder="e.g. Matched against books; supplier confirmed by email" /></label>
      <div className="flex flex-wrap items-center gap-3">
        <Button disabled={busy || !note.trim() || !untouchedMatches.length} onClick={() => act(untouchedMatches, "accept")}>Accept exact matches with no action ({untouchedMatches.length})</Button>
        <label className="ml-auto flex items-center gap-2 text-sm"><Eyebrow>Show</Eyebrow><select aria-label="IMS filter" className="native-field w-auto py-1" value={filter} onChange={e => setFilter(e.target.value)}>{["all", "no_action", "accept", "reject", "pending"].map(f => <option key={f} value={f}>{f.replace("_", " ")}</option>)}</select></label>
      </div>
      <div className="table-wrap"><table className="min-w-[860px]"><thead><tr><th>Record</th><th>Supplier</th><th>Invoice</th><th>Date</th><th className="!text-right">Taxable</th><th className="!text-right">Tax</th><th>Finding</th><th>IMS</th><th>Change</th></tr></thead>
        <tbody>{shown.map(i => <tr key={i.id} data-testid="ims-row">
          <td className="id-cell">{i.record_id}</td><td className="id-cell">{i.supplier_ref}</td><td className="id-cell">{i.invoice_number}</td><td className="id-cell">{i.invoice_date}</td>
          <td className="font-figures text-right">{i.taxable_value}</td><td className="font-figures text-right">{i.tax}</td>
          <td><StatusChip tone={FINDING_TONE(i.finding)}>{i.finding?.replaceAll("_", " ") ?? "not reconciled"}</StatusChip></td>
          <td data-testid={`ims-${i.record_id}`}>{i.action ? <StatusChip tone={ACTION_TONE[i.action]}>{i.action}</StatusChip> : <span className="text-xs text-muted-foreground">no action (deemed accepted)</span>}
            {i.history.length > 0 && <span className="margin-note !m-0 !ml-1 block text-base" title={i.history.map(h => `${h.action}: ${h.note}`).join("\n")}>{i.history[i.history.length - 1].note}</span>}</td>
          <td><select aria-label={`IMS action for ${i.record_id}`} className="native-field py-1" disabled={busy || !note.trim()} value="" onChange={e => { if (e.target.value) void act([i], e.target.value); }}><option value="">Set…</option><option value="accept">Accept</option><option value="reject">Reject</option><option value="pending">Keep pending</option></select></td>
        </tr>)}</tbody></table></div>
      {!shown.length && <p className="text-sm text-muted-foreground">No invoices match this filter.</p>}
    </section>
  </div>;
}
