"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Download, FileDown, Filter, Upload } from "lucide-react";
import { api, errorMessage, SalesBatch, SalesDetail, SalesRow } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ColumnMapper } from "@/components/assist";
import { Drawer } from "@/components/drawer";
import { Eyebrow, StatusChip, Tone } from "@/components/status-chip";

const TAX = ["cgst", "sgst", "igst", "cess"];
const TOTAL_LABEL: Record<string, string> = { taxable_value: "Taxable", cgst: "CGST", sgst: "SGST", igst: "IGST", cess: "Cess", invoice_total: "Total" };
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob); const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
// Sum of supplied tax amounts in paise (integers), so no floating-point rounding.
const paise = (v: string) => { const m = /^(\d+)\.(\d{2})$/.exec(v || ""); return m ? Number(m[1]) * 100 + Number(m[2]) : 0; };
const rupees = (p: number) => `${Math.floor(p / 100)}.${String(p % 100).padStart(2, "0")}`;
function rowTax(r: SalesRow) { return TAX.every(h => /^\d+\.\d{2}$/.test(r.raw_data[h] || "")) ? rupees(TAX.reduce((s, h) => s + paise(r.raw_data[h]), 0)) : "—"; }
function statusOf(r: SalesRow): [string, Tone] {
  if (r.decision === "reviewed") return ["reviewed", "done"];
  if (r.decision === "excluded") return ["excluded", "waiting"];
  if (r.validation_status === "ready") return ["to review", "action"];
  return [r.validation_status, r.validation_status === "invalid" ? "blocked" : "action"];
}

export default function Sales() {
  const periodId = useParams().period_id as string;
  const [batches, setBatches] = useState<SalesBatch[]>([]);
  const [periodCode, setPeriodCode] = useState("");
  const [selected, setSelected] = useState("");
  const [data, setData] = useState<SalesDetail | null>(null);
  const [offset, setOffset] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [filter, setFilter] = useState("all");
  const [rowId, setRowId] = useState("");
  const [decision, setDecision] = useState("reviewed");
  const [note, setNote] = useState("");
  const [ack, setAck] = useState(false);
  const [commitNote, setCommitNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [gstr1Warnings, setGstr1Warnings] = useState<string[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [mapperFile, setMapperFile] = useState<File | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([api.getSalesImports(periodId), api.getPeriod(periodId)]).then(([value, period]) => {
      if (!active) return; setBatches(value); setPeriodCode(period.period_code); setLoading(false);
      const committed = value.find(b => b.status === "committed") || value[0];
      if (committed) setSelected(s => s || committed.id);
    }).catch(e => { if (active) { setError(errorMessage(e)); setLoading(false); } });
    return () => { active = false; };
  }, [periodId]);
  useEffect(() => {
    let active = true;
    if (selected) api.getSales(selected, offset, filter).then(value => { if (active) setData(value); }).catch(e => { if (active) setError(errorMessage(e)); });
    return () => { active = false; };
  }, [selected, offset, filter, reloadKey]);
  const row = data?.items.find(r => r.id === rowId);
  const blocked = data ? data.summary.source_rows - data.summary.ready : 0;
  const version = batches.length - batches.findIndex(b => b.id === selected);
  const month = periodCode ? MONTHS[Number(periodCode.split("-")[1]) - 1] : "";
  const close = useCallback(() => setRowId(""), []);
  function choose(id: string) { setReloadKey(k => k + 1); setSelected(id); setData(null); setRowId(""); setOffset(0); setFilter("all"); setAck(false); setCommitNote(""); setError(""); }
  function inspect(r: SalesRow) { setRowId(r.id); setDecision(r.validation_status === "ready" ? "reviewed" : "excluded"); setNote(""); }
  async function perform(action: () => Promise<void>) { setBusy(true); setError(""); try { await action(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  function uploadFile(file: File) {
    return perform(async () => {
      try { const result = await api.uploadSales(periodId, file); setMapperFile(null); setBatches(await api.getSalesImports(periodId)); choose(result.id); }
      catch (e) { if (/headers/i.test(errorMessage(e))) setMapperFile(file); throw e; }
    });
  }
  async function refresh() { if (selected) setData(await api.getSales(selected, offset, filter)); setBatches(await api.getSalesImports(periodId)); }

  return <div className="console-content w-full min-w-0 space-y-6 break-words">
    <Link className="text-sm underline underline-offset-4" href={`/periods/${periodId}/workspace`}>Back to period</Link>
    {error && <p role="alert" data-testid="sales-error" className="red-ink">{error} <Button variant="outline" size="sm" disabled={busy} onClick={() => perform(refresh)}>Reload sales import</Button></p>}

    <section className="paper-card sales-upload flex-wrap gap-4">
      <div className="min-w-0">
        <Eyebrow>Sales source{data ? ` · V${version}` : ""}</Eyebrow>
        <h2 className="font-display text-2xl">{month ? `${month} sales register` : "Sales register"}</h2>
        <p className="text-sm text-muted-foreground">{data ? <>{data.summary.source_rows} rows parsed from {data.batch.filename} · <span>Selected import: {data.batch.status}</span></> : loading ? "Loading sales imports…" : "No sales imports yet. Upload the synthetic sales sample to begin."}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" disabled={busy} onClick={() => perform(async () => download(new Blob([await api.salesTemplate()], { type: "text/csv" }), "synthetic_sales_template.csv"))}><FileDown className="mr-2 h-4 w-4" />Download sales template</Button>
        <Button variant="outline" disabled={busy} title="Adds customer GSTIN, state code, rate, HSN, unit and quantity — needed for a GSTR-1 draft" onClick={() => perform(async () => download(new Blob([await api.salesTemplate("2")], { type: "text/csv" }), "synthetic_sales_template_v2.csv"))}><FileDown className="mr-2 h-4 w-4" />Template v2 (for GSTR-1)</Button>
        <label className={`inline-flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-1.5 text-sm font-medium hover:bg-muted ${busy ? "pointer-events-none opacity-50" : ""}`}>
          <Upload className="h-4 w-4" />{data ? "Replace file" : "Upload file"}
          <input aria-label="Sales CSV" type="file" accept=".csv" disabled={busy} className="sr-only" onChange={e => { const file = e.target.files?.[0]; e.target.value = ""; if (file) void uploadFile(file); }} />
        </label>
      </div>
      {mapperFile && <div className="w-full"><ColumnMapper template="sales" file={mapperFile} onCancel={() => setMapperFile(null)} onReady={async f => { setMapperFile(null); await uploadFile(f); }} /></div>}
      <p className="w-full text-xs text-muted-foreground">Synthetic draft — not for filing. UTF-8 CSV, up to 5 MiB and 10,000 rows. Corrections create a new version; identical uploads reopen the existing one. Customer registration, place of supply and GST treatment are not verified.</p>
    </section>

    {batches.length > 0 && <label className="block max-w-xl space-y-1 text-sm"><Eyebrow>Sales version</Eyebrow><select aria-label="Sales version" className="native-field" disabled={busy} value={selected} onChange={e => choose(e.target.value)}><option value="">Select a sales import</option>{batches.map((b, i) => <option key={b.id} value={b.id}>V{batches.length - i} · {b.filename} · {b.status} · {new Date(b.created_at).toLocaleString("en-IN")}</option>)}</select></label>}
    {selected && !data && !error && <p className="text-sm text-muted-foreground">Loading selected import…</p>}

    {data && <>
      <div className="summary-strip" data-testid="sales-summary">
        {([["rows", data.summary.source_rows], ["ready", data.summary.ready], ["invalid", data.summary.invalid], ["duplicate", data.summary.duplicate], ["unsupported", data.summary.unsupported]] as const).map(([label, value]) => <div key={label} data-testid={`sales-count-${label}`}><strong>{value}</strong><Eyebrow>{label}</Eyebrow></div>)}
      </div>

      {data.batch.status === "preview" && <section className="paper-card space-y-3 border-status-needs">
        <Eyebrow className="text-primary">Commit before reviewing</Eyebrow>
        <p className="text-sm">Check the rows below first. Acknowledging blocked rows does not make them valid or include them in totals.</p>
        {blocked > 0 && <><label className="flex items-start gap-2 text-sm"><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />I acknowledge the blocked sales rows</label>
          <label className="block space-y-1 text-sm"><Eyebrow>Acknowledgement note</Eyebrow><Textarea aria-label="Sales acknowledgement note" maxLength={2000} value={commitNote} onChange={e => setCommitNote(e.target.value)} /></label></>}
        <Button disabled={busy || (blocked > 0 && (!ack || !commitNote.trim()))} onClick={() => perform(async () => { await api.commitSales(selected, ack, commitNote); await refresh(); })}>Commit sales import</Button>
      </section>}
      {data.batch.commit_note && <p className="margin-note">Commit note: {data.batch.commit_note}</p>}

      <div className="grid gap-5 xl:grid-cols-[1fr_280px]">
        <section className="paper-card min-w-0">
          <div className="section-heading"><h2 className="font-display text-2xl">Source rows</h2>
            <label className="filter-select"><Filter /><span className="sr-only">Sales validation filter</span><select aria-label="Sales validation filter" disabled={busy} value={filter} onChange={e => { setFilter(e.target.value); setOffset(0); setRowId(""); setData(null); }}>{["all", "ready", "invalid", "duplicate", "unsupported"].map(s => <option key={s}>{s}</option>)}</select></label></div>
          <div className="table-wrap"><table className="min-w-[760px]"><thead><tr><th>Record</th><th>Date</th><th>Customer</th><th>Type</th><th className="!text-right">Taxable</th><th className="!text-right">Tax</th><th>Status</th><th><span className="sr-only">Review</span></th></tr></thead>
            <tbody>{data.items.map(r => { const [label, tone] = statusOf(r); return <tr key={r.id} className="clickable-row" onClick={() => inspect(r)}>
              <td className="id-cell">{r.raw_data.record_id || `row ${r.row_number}`}</td><td className="id-cell">{r.raw_data.invoice_date || "—"}</td><td>{r.raw_data.customer_ref || "Missing"}</td>
              <td>{r.raw_data.customer_type === "registered" ? "B2B" : r.raw_data.customer_type === "unregistered" ? "B2C" : "—"}</td>
              <td className="font-figures text-right">{r.raw_data.taxable_value || "—"}</td><td className="font-figures text-right">{rowTax(r)}</td>
              <td><StatusChip tone={tone}>{label}</StatusChip></td>
              <td><Button size="sm" variant="outline" disabled={busy} onClick={e => { e.stopPropagation(); inspect(r); }}>Inspect sale</Button></td></tr>; })}</tbody></table></div>
          {data.items.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No rows match this filter.</p>}
          <div className="mt-3 flex gap-2"><Button variant="outline" size="sm" disabled={busy || offset === 0} onClick={() => { setData(null); setRowId(""); setOffset(offset - 25); }}>Previous sales rows</Button><Button variant="outline" size="sm" disabled={busy || offset + 25 >= data.total} onClick={() => { setData(null); setRowId(""); setOffset(offset + 25); }}>Next sales rows</Button></div>
        </section>

        <aside className="receipt" aria-label="Included totals">
          <div className="receipt-mark">GSTH</div>
          <Eyebrow>Included totals</Eyebrow>
          <p className="id-cell">{periodCode} · reviewed ready rows only</p>
          <div className="receipt-lines">{Object.entries(data.summary.included_totals).map(([k, v]) => <div key={k} className={k === "invoice_total" ? "receipt-total" : ""}><span>{TOTAL_LABEL[k] || k}</span><span data-testid={`sales-total-${k}`} className="font-figures text-right">{v}</span></div>)}</div>
          <p className="mt-4 text-xs">Included <b data-testid="sales-included">{data.summary.included}</b> · excluded {data.summary.excluded} · pending <b data-testid="sales-pending">{data.summary.pending}</b></p>
          <Button className="mt-4 w-full" size="sm" disabled={busy || data.batch.status !== "committed"} onClick={() => perform(async () => download(await api.exportSales(selected), `Synthetic_Sales_${selected}.xlsx`))}><Download className="mr-2 h-4 w-4" />Export sales working paper</Button>
          {data.batch.contract_version === "sales-v2" && <Button className="mt-2 w-full" size="sm" variant="outline" disabled={busy || data.batch.status !== "committed"} onClick={() => perform(async () => { const r = await api.gstr1Draft(selected); setGstr1Warnings(r.warnings); download(new Blob([JSON.stringify(r.document, null, 2)], { type: "application/json" }), `GSTR1_draft_${r.document.fp}.json`); })}><Download className="mr-2 h-4 w-4" />Export GSTR-1 draft (JSON)</Button>}
          {gstr1Warnings && <ul data-testid="gstr1-warnings" className="mt-2 list-disc pl-4 text-left text-[11px] text-muted-foreground">{gstr1Warnings.map(w => <li key={w}>{w}</li>)}<li>Draft from GSTN&apos;s published field names; not validated. Open it in the GSTN offline tool and have a CA review it.</li></ul>}
          <p className="mt-4 text-center font-note text-lg">Reviewed totals only</p>
        </aside>
      </div>

      <Drawer open={!!row} onClose={close} testId="sales-detail" eyebrow={row ? `Source row ${row.row_number}` : undefined} title={row ? `Sale ${row.raw_data.record_id || row.row_number}` : ""} description="Set a human review state and leave a traceable note.">
        {row && <>
          <p className="text-sm">{row.validation_status}: {row.issues.join(", ") || "Source checks passed"} · current review: <b>{row.decision}</b></p>
          <div className="ledger-page"><dl className="space-y-0.5 text-sm">{Object.entries(row.raw_data).map(([key, value]) => <div key={key} className="flex justify-between gap-3"><dt className="text-muted-foreground">{key.replaceAll("_", " ")}</dt><dd className="font-figures text-right">{value || "Blank"}</dd></div>)}</dl></div>
          <label className="block space-y-1 text-sm"><Eyebrow>Decision</Eyebrow><select aria-label="Sales decision" value={decision} className="native-field" onChange={e => setDecision(e.target.value)}><option value="reviewed" disabled={row.validation_status !== "ready"}>Reviewed — include supplied amounts</option><option value="excluded">Excluded — retain with reason</option><option value="unresolved">Unresolved — reopen review</option></select></label>
          <label className="block space-y-1 text-sm"><Eyebrow>Review note (required)</Eyebrow><Textarea aria-label="Sales review note" value={note} maxLength={2000} onChange={e => setNote(e.target.value)} /></label>
          <Button className="w-full" disabled={busy || data.batch.status !== "committed" || !note.trim()} onClick={() => perform(async () => { await api.reviewSales(selected, row.id, { decision, note, previous_review_id: row.previous_review_id }); setNote(""); await refresh(); })}>Save sales review</Button>
          {data.batch.status !== "committed" && <p className="text-sm text-muted-foreground">Commit this import before saving reviews.</p>}
          <div><Eyebrow>Review history</Eyebrow>{row.history.length === 0 ? <p className="text-sm text-muted-foreground">No reviews yet.</p> : row.history.map(h => <blockquote key={h.id} className="margin-note">{h.decision}: {h.note}<cite>{new Date(h.created_at).toLocaleString("en-IN")} · actor {h.actor_id.slice(0, 8)}</cite></blockquote>)}</div>
        </>}
      </Drawer>
    </>}
  </div>;
}
