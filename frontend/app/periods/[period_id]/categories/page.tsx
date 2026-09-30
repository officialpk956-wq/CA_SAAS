"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Wand2 } from "lucide-react";
import { api, CategoryPage, CategoryRow, errorMessage, ImportBatch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Drawer } from "@/components/drawer";
import { Eyebrow, StatusChip } from "@/components/status-chip";

const SOURCE: Record<string, string> = { mock: "mock model", approved_rule: "approved mapping", rule_conflict: "conflicting mappings" };

function Suggestion({ row }: { row: CategoryRow }) {
  if (!row.proposal) return <span className="text-xs text-muted-foreground">not requested</span>;
  return row.proposal.category ? <span className="category-chip">{row.proposal.category}</span> : <span className="category-chip opacity-70">abstained</span>;
}

function Categories() {
  const periodId = useParams().period_id as string;
  const batchParam = useSearchParams().get("batch_id") || "";
  const [batchId, setBatchId] = useState(batchParam);
  const [noBatch, setNoBatch] = useState(false);
  const [data, setData] = useState<CategoryPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [category, setCategory] = useState("");
  const [note, setNote] = useState("");
  const [saveRule, setSaveRule] = useState(false);
  const [effective, setEffective] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Without an explicit import, use the period's latest committed purchase register.
  useEffect(() => {
    let active = true;
    if (batchParam) { const t = setTimeout(() => setBatchId(batchParam), 0); return () => clearTimeout(t); }
    api.getImports(periodId).then((items: ImportBatch[]) => {
      if (!active) return;
      const latest = items.find(b => b.source_type === "purchase" && b.status === "committed");
      if (latest) setBatchId(latest.id); else setNoBatch(true);
    }).catch(e => { if (active) setError(errorMessage(e)); });
    return () => { active = false; };
  }, [periodId, batchParam]);
  const load = useCallback(async () => { if (batchId) setData(await api.getCategories(periodId, batchId, offset)); }, [periodId, batchId, offset]);
  useEffect(() => {
    let active = true;
    if (batchId) api.getCategories(periodId, batchId, offset).then(value => { if (active) setData(value); }).catch(e => { if (active) setError(errorMessage(e)); });
    return () => { active = false; };
  }, [periodId, batchId, offset]);

  const row = data?.items.find(r => r.id === selected);
  const close = useCallback(() => setSelected(""), []);
  function inspect(r: CategoryRow) { setSelected(r.id); setCategory(r.category || ""); setNote(""); setSaveRule(false); setEffective(r.invoice_date); }
  async function perform(action: () => Promise<unknown>) { setBusy(true); setError(""); try { await action(); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  async function decide(action: "accept" | "reject" | "manual") {
    if (!row) return;
    await perform(async () => {
      await api.decideCategory(row.id, { action, category: category || undefined, proposal_id: action === "manual" ? undefined : row.proposal?.id, previous_decision_id: row.last_decision_id, note, save_rule: action !== "reject" && saveRule, effective_from: saveRule && action !== "reject" ? effective : undefined });
      setNote(""); setSaveRule(false);
    });
  }
  const pending = row?.proposal && ["proposed", "needs_review"].includes(row.proposal.status);
  const unrequested = (data?.items || []).filter(r => !r.proposal);
  const open = (data?.items || []).filter(r => !r.category).length;

  return <div className="console-content w-full min-w-0 space-y-6 break-words">
    <Link className="text-sm underline underline-offset-4" href={`/periods/${periodId}/workspace`}>Back to period</Link>
    {error && <p role="alert" className="red-ink">{error} Reload the page if a newer decision exists.</p>}
    {noBatch && <div className="paper-card py-12 text-center"><h3 className="font-display text-2xl">No committed purchase register</h3><p className="mt-1 text-sm text-muted-foreground">Commit a purchase import for this period first.</p><Link href={`/periods/${periodId}/workspace`} className="mt-3 inline-block font-semibold text-primary">Go to imports →</Link></div>}
    {batchId && !data && !error && <p className="text-sm text-muted-foreground">Loading purchases…</p>}

    {data && <section className="paper-card">
      <div className="section-heading flex-wrap"><div><Eyebrow>Purchase classification</Eyebrow><h2 className="font-display text-2xl">Suggested categories</h2></div>
        <div className="flex flex-wrap items-center gap-2">
          {open > 0 ? <StatusChip tone="action">{open} decision(s) open on this page</StatusChip> : <StatusChip tone="done">All categorised on this page</StatusChip>}
          <Button size="sm" variant="outline" disabled={busy || !unrequested.length} onClick={() => perform(async () => { for (const r of unrequested) await api.suggestCategory(r.id); })}><Wand2 className="mr-2 h-4 w-4" />Suggest for {unrequested.length} row(s)</Button>
        </div></div>
      <p className="mb-3 text-xs text-muted-foreground">Mock suggestions only — the teammate&apos;s SLM is not connected. Categories do not determine GST rate, ITC eligibility or reconciliation results. Every decision needs a note.</p>
      <div className="table-wrap"><table className="min-w-[760px]"><thead><tr><th>Record</th><th>Supplier &amp; narration</th><th>Suggestion</th><th>Source</th><th>Decision</th><th><span className="sr-only">Review</span></th></tr></thead>
        <tbody>{data.items.map(r => <tr key={r.id} className="clickable-row" onClick={() => inspect(r)}>
          <td className="id-cell">{r.record_id}</td>
          <td><b>{r.supplier_ref}</b><small className="block text-muted-foreground">{r.description || "No description"}</small></td>
          <td><Suggestion row={r} /></td>
          <td className="text-sm">{r.proposal ? SOURCE[r.proposal.source] || r.proposal.source : "—"}</td>
          <td>{r.category ? <StatusChip tone="done">{r.category}</StatusChip> : <StatusChip tone="waiting">uncategorised</StatusChip>}</td>
          <td><Button size="sm" variant="outline" disabled={busy} onClick={e => { e.stopPropagation(); inspect(r); }}>Review category</Button></td>
        </tr>)}</tbody></table></div>
      <div className="mt-3 flex items-center gap-2"><Button size="sm" variant="outline" disabled={busy || offset === 0} onClick={() => { setSelected(""); setOffset(offset - 25); }}>Previous</Button><Button size="sm" variant="outline" disabled={busy || offset + 25 >= data.total} onClick={() => { setSelected(""); setOffset(offset + 25); }}>Next</Button><span className="text-xs text-muted-foreground">{data.total} valid purchase row(s)</span></div>
    </section>}

    {data && <section className="paper-card">
      <div className="section-heading"><div><Eyebrow>Client rules</Eyebrow><h2 className="font-display text-2xl">Approved mappings</h2></div></div>
      {data.rules.length === 0 ? <p className="margin-note">No approved mappings yet. Tick “approve a reusable mapping” when you decide a row.</p> :
        <div className="ledger-list">{data.rules.map(r => <div className="ledger-entry" key={r.id} data-testid="mapping">
          <span><b>{r.supplier_ref}</b><small className="block text-muted-foreground">{r.description} · From {r.effective_from}</small></span>
          <span className="category-chip">{r.category}</span>
          <StatusChip tone={r.active ? "done" : "waiting"}>{r.active ? "Active" : "Inactive"}</StatusChip>
          {r.active ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => perform(() => api.deactivateCategoryRule(r.id))}>Deactivate mapping</Button> : <span />}
        </div>)}</div>}
    </section>}

    <Drawer open={!!row} onClose={close} testId="category-detail" eyebrow={row ? `${row.record_id} · ${row.supplier_ref}` : undefined} title="Review category" description={row ? `${row.description || "No description"} · Approved category: ${row.category || "Uncategorized"}` : undefined}>
      {row && <>
        <div className="space-y-2">
          <Button variant="outline" disabled={busy} onClick={() => perform(() => api.suggestCategory(row.id))}><Wand2 className="mr-2 h-4 w-4" />Get suggestion</Button>
          {row.proposal && <div className="rounded-lg border border-dashed border-primary/60 bg-accent/30 p-3 text-sm">
            <p data-testid="category-suggestion" className="font-semibold">{row.proposal.category || "Needs manual review (abstained)"}</p>
            <p className="text-muted-foreground">Source: {row.proposal.source} · {row.proposal.model_version} · {row.proposal.status}</p>
            {row.proposal.evidence && <p className="margin-note !m-0 text-lg">“{row.proposal.evidence}”</p>}
          </div>}
        </div>
        <label className="block space-y-1 text-sm"><Eyebrow>Manual category</Eyebrow><select aria-label="Manual category" className="native-field" value={category} onChange={e => setCategory(e.target.value)}><option value="">Choose category</option>{data?.categories.map(c => <option key={c}>{c}</option>)}</select></label>
        <label className="block space-y-1 text-sm"><Eyebrow>Review note (required)</Eyebrow><Textarea aria-label="Category review note" maxLength={2000} value={note} onChange={e => setNote(e.target.value)} /></label>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={saveRule} onChange={e => setSaveRule(e.target.checked)} />Approve a reusable mapping for this exact supplier and description</label>
        {saveRule && <label className="block space-y-1 text-sm"><Eyebrow>Mapping effective from</Eyebrow><Input aria-label="Mapping effective from" type="date" value={effective} onChange={e => setEffective(e.target.value)} /><span className="text-xs text-muted-foreground">Applies to this client only. Future suggestions still require review.</span></label>}
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy || !category || !note.trim() || (saveRule && !effective)} onClick={() => decide("manual")}>Save manual category</Button>
          <Button disabled={busy || !pending || !row.proposal?.category || !note.trim() || (saveRule && !effective)} onClick={() => decide("accept")}>Accept suggestion</Button>
          <Button variant="outline" disabled={busy || !pending || !note.trim()} onClick={() => decide("reject")}>Reject suggestion</Button>
        </div>
        <div><Eyebrow>Decision history</Eyebrow>{row.history.length === 0 ? <p className="text-sm text-muted-foreground">No decisions yet.</p> : row.history.map(h => <blockquote key={h.id} className="margin-note">{h.action}: {h.category || "Uncategorized"} — {h.note}<cite>{new Date(h.created_at).toLocaleString("en-IN")} · actor {h.actor_id.slice(0, 8)}</cite></blockquote>)}</div>
      </>}
    </Drawer>
  </div>;
}
export default function Page() { return <Suspense fallback={<p className="console-content">Loading categories…</p>}><Categories /></Suspense>; }
