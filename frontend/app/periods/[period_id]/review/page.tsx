"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Download, Filter } from "lucide-react";
import { api, errorMessage, ReconciliationResult, ReconciliationRun, SourceRecord } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Eyebrow, StatusChip, Tone } from "@/components/status-chip";
import { Drawer } from "@/components/drawer";
import { Investigator, SupplierFollowups } from "@/components/assist";

const FINDING_TONE = (s: string): Tone => s === "matched" ? "done" : s === "validation_error" ? "blocked" : "action";
const FIELDS = ["supplier_ref", "invoice_number", "invoice_date", "taxable_value", "cgst", "sgst", "igst", "cess", "invoice_total"];

function taxable(r: ReconciliationResult) {
  return r.purchase_records[0]?.raw_data.taxable_value || r.statement_records[0]?.raw_data.taxable_value || "—";
}
function difference(r: ReconciliationResult) {
  const d = r.differences.taxable_value ?? r.differences.invoice_total ?? Object.values(r.differences)[0];
  return d ?? null;
}

function Review() {
  const periodId = useParams().period_id as string;
  const router = useRouter();
  const runParam = useSearchParams().get("run_id");
  const [runs, setRuns] = useState<ReconciliationRun[] | null>(null);
  const [run, setRun] = useState<ReconciliationRun | null>(null);
  const [results, setResults] = useState<ReconciliationResult[]>([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [reviewFilter, setReviewFilter] = useState("");
  const [selected, setSelected] = useState("");
  const [decision, setDecision] = useState("investigating");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const succeeded = (runs || []).filter(r => r.status === "succeeded");
  const runId = runParam || succeeded[0]?.id || null;

  const load = useCallback(async () => {
    const all: ReconciliationRun[] = await api.getRuns(periodId); setRuns(all);
    const id = runParam || all.find(r => r.status === "succeeded")?.id;
    if (!id) return;
    const [r, items] = await Promise.all([api.getReconciliationRun(periodId, id), api.getReconciliationResults(periodId, id)]);
    setRun(r); setResults(items); setError("");
  }, [periodId, runParam]);
  useEffect(() => { let active = true; const t = setTimeout(() => load().catch(e => { if (active) setError(errorMessage(e)); }), 0); return () => { active = false; clearTimeout(t); }; }, [load]);

  async function save(e: React.FormEvent) { e.preventDefault(); if (!runId || !selected) return; setBusy(true); try { await api.resolveException(runId, selected, { decision, notes: note }); setNote(""); await load(); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); } }
  async function download() { if (!runId) return; setBusy(true); try { const blob = await api.exportReconciliation(periodId, runId); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = `reconciliation_${runId}.xlsx`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); } }

  const active = results.find(r => r.result_id === selected);
  const filtered = results.filter(r => (!filter || r.status === filter) && (!reviewFilter || r.review_status === reviewFilter));
  const counts = run?.summary_data?.distinct_results_by_status || {};
  const groups = Object.values(counts).reduce((a, b) => a + b, 0);
  const close = useCallback(() => setSelected(""), []);

  return <div className="console-content w-full min-w-0 space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Link className="text-sm underline underline-offset-4" href={`/periods/${periodId}/workspace`}>Back to period</Link>
      <div className="flex flex-wrap items-center gap-2">
        {succeeded.length > 1 && <select aria-label="Reconciliation run" className="native-field w-auto" value={runId ?? ""} onChange={e => router.push(`/periods/${periodId}/review?run_id=${e.target.value}`)}>{succeeded.map(r => <option key={r.id} value={r.id}>{new Date(r.created_at).toLocaleString("en-IN")} · {r.id.slice(0, 8)}</option>)}</select>}
        <Button disabled={busy || run?.status !== "succeeded"} onClick={download}><Download className="mr-2 h-4 w-4" />Export Working Paper</Button>
      </div>
    </div>
    {error && <p role="alert" className="red-ink">{error} <button className="underline" onClick={() => void load()}>Retry</button></p>}
    {runs && !runId && <div className="paper-card py-12 text-center"><h3 className="font-display text-2xl">No reconciliation yet</h3><p className="mt-1 text-sm text-muted-foreground">Commit a purchase register and a statement, then run reconciliation.</p><Link href={`/periods/${periodId}/workspace`} className="mt-3 inline-block font-semibold text-primary">Go to imports →</Link></div>}
    {run?.status === "failed" && <p role="alert" className="red-ink">This run failed. Return to imports and inspect its inputs.</p>}

    {run && <>
      <div className="grid gap-3 sm:grid-cols-3">
        <section className="paper-card big-number"><strong data-testid="matched-count">{run.summary_data?.matched_pair_count ?? 0}</strong><Eyebrow>Exact matches</Eyebrow></section>
        <section className="paper-card big-number"><strong>{groups}</strong><Eyebrow>Result groups</Eyebrow></section>
        <section className="paper-card big-number"><strong>{(run.summary_data?.purchase_rows_total || 0) + (run.summary_data?.statement_rows_total || 0)}</strong><Eyebrow>Source rows</Eyebrow></section>
      </div>

      <section className="paper-card">
        <div className="section-heading flex-wrap"><div><Eyebrow>Result ledger</Eyebrow><h2 className="font-display text-2xl">Reconciliation findings</h2></div>
          <div className="flex flex-wrap gap-2">
            <label className="filter-select"><Filter /><span className="sr-only">Finding</span><select aria-label="Finding" value={filter} onChange={e => setFilter(e.target.value)}><option value="">All findings</option>{Object.keys(counts).sort().map(s => <option key={s} value={s}>{s}</option>)}</select></label>
            <label className="filter-select"><Filter /><span className="sr-only">Review state</span><select aria-label="Review state" value={reviewFilter} onChange={e => setReviewFilter(e.target.value)}><option value="">All review states</option>{["unresolved", "investigating", "explained", "correction_required"].map(s => <option key={s}>{s}</option>)}</select></label>
          </div></div>
        <div className="table-wrap"><table className="min-w-[860px]"><thead><tr><th>Result</th><th>Purchase</th><th>Statement</th><th>Finding</th><th>Review state</th><th className="!text-right">Taxable</th><th className="!text-right">Difference</th><th><span className="sr-only">Evidence</span></th></tr></thead>
          <tbody>{filtered.map(r => { const d = difference(r); return <tr key={r.id} className="clickable-row" onClick={() => { setSelected(r.result_id); setNote(""); }}>
            <td className="id-cell">{r.result_id.slice(0, 12)}</td><td className="id-cell">{r.purchase_record_ids.join(", ") || "—"}</td><td className="id-cell">{r.statement_record_ids.join(", ") || "—"}</td>
            <td><StatusChip tone={FINDING_TONE(r.status)}>{r.status.replaceAll("_", " ")}</StatusChip></td>
            <td>{r.status === "matched" ? "not required" : r.review_status.replaceAll("_", " ")}</td>
            <td className="font-figures text-right">{taxable(r)}</td>
            <td className={`font-figures text-right ${d && d !== "0.00" ? "text-destructive" : ""}`}>{d ?? "—"}</td>
            <td><Button size="sm" variant="outline" onClick={e => { e.stopPropagation(); setSelected(r.result_id); setNote(""); }}>Inspect</Button></td>
          </tr>; })}</tbody></table></div>
        {!filtered.length && <p className="py-6 text-center text-sm text-muted-foreground">No findings match these filters.</p>}
        <p className="mt-3 text-xs text-muted-foreground">Purchase version {run.purchase_batch_id.slice(0, 8)} · statement version {run.statement_batch_id.slice(0, 8)} · run {run.id.slice(0, 8)}</p>
      </section>
      {run.status === "succeeded" && runId && <SupplierFollowups runId={runId} />}
    </>}

    <Drawer open={!!active} onClose={close} testId="result-detail" eyebrow={active ? `Evidence folio · ${active.result_id.slice(0, 12)}` : undefined} title="Facing source pages" description={active ? `${active.status} — ${active.reason}` : undefined}>
      {active && <>
        <div className="grid gap-3 sm:grid-cols-2"><EvidencePage title="Purchase register" records={active.purchase_records} /><EvidencePage title="Statement" records={active.statement_records} /></div>
        {Object.keys(active.differences).length > 0 ? <div className="space-y-1">{Object.entries(active.differences).map(([k, v]) => <p key={k} className="red-ink font-figures">{k} {v} · purchase minus statement</p>)}</div> : <p className="text-sm text-muted-foreground">No numerical differences recorded.</p>}
        <div><Eyebrow>Review margin</Eyebrow>{active.history.length ? active.history.map(h => <blockquote key={h.id} className="margin-note">{h.decision}: {h.note}<cite>{new Date(h.created_at).toLocaleString("en-IN")} · actor {h.actor_id.slice(0, 8)}</cite></blockquote>) : <p className="text-sm text-muted-foreground">No review decisions yet.</p>}</div>
        {active.status !== "matched" && runId && <Investigator key={active.result_id} runId={runId} resultId={active.result_id} onUseNote={setNote} />}
        {active.status !== "matched" && <form onSubmit={save} className="resolution-form">
          <p className="text-sm text-muted-foreground">Review does not change the finding or establish tax eligibility. Correct source data through a new import and run.</p>
          <label className="space-y-1 text-sm"><Eyebrow>Decision</Eyebrow><select aria-label="Decision" className="native-field" value={decision} onChange={e => setDecision(e.target.value)}><option value="investigating">Investigating</option><option value="explained">Explained</option><option value="correction_required">Correction required</option><option value="unresolved">Reopen</option></select></label>
          <label className="space-y-1 text-sm"><Eyebrow>Resolution note (required)</Eyebrow><Textarea aria-label="Resolution note" required maxLength={4000} value={note} onChange={e => setNote(e.target.value)} /></label>
          <Button disabled={busy || !note.trim()} type="submit">Save Resolution</Button>
        </form>}
      </>}
    </Drawer>
  </div>;
}

function EvidencePage({ title, records }: { title: string; records: SourceRecord[] }) {
  return <div className="ledger-page"><Eyebrow>{title}</Eyebrow>
    {!records.length && <p className="mt-6 text-sm text-muted-foreground">No source record.</p>}
    {records.map(r => <div key={r.row_number} className="mt-4 text-sm">
      <p className="id-cell">{r.record_id || "(blank id)"} · source row {r.row_number}</p>
      <dl className="mt-2 space-y-0.5">{FIELDS.map(f => <div key={f} className="flex justify-between gap-3"><dt className="text-muted-foreground">{f.replaceAll("_", " ")}</dt><dd className="font-figures">{r.raw_data[f] || "(blank)"}</dd></div>)}</dl>
      {r.issues.map((issue, i) => <p className="red-ink mt-1" key={i}>{issue}</p>)}
    </div>)}
  </div>;
}

export default function ReviewPage() { return <Suspense fallback={<p className="console-content">Loading…</p>}><Review /></Suspense>; }
