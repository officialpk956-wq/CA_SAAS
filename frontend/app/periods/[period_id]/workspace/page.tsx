"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useParams, useRouter } from "next/navigation";

import Link from "next/link";

import { api, errorMessage, Gstr2bConversion, ImportBatch, Period, ReconciliationRun, SourceRecord } from "@/lib/api";

import { Button } from "@/components/ui/button";

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { ColumnMapper } from "@/components/assist";
import { ClientRequests } from "@/components/client-requests";



export default function Workspace() {

  const periodId = useParams().period_id as string;

  const router = useRouter();

  const [period, setPeriod] = useState<Period | null>(null);

  const [imports, setImports] = useState<ImportBatch[]>([]);

  const [runs, setRuns] = useState<ReconciliationRun[]>([]);

  const [purchase, setPurchase] = useState("");

  const [statement, setStatement] = useState("");

  const [error, setError] = useState("");

  const [busy, setBusy] = useState(false);

  const generation = useRef<object>({});

  const load = useCallback(async () => {

    const ticket = {}; generation.current = ticket;

    try {

      const [p, i, r] = await Promise.all([api.getPeriod(periodId), api.getImports(periodId), api.getRuns(periodId)]);

      if (ticket !== generation.current) return;

      setPeriod(p); setImports(i); setRuns(r); setError("");

    } catch(e) { if(ticket === generation.current) setError(errorMessage(e)); }

  }, [periodId]);

  useEffect(() => { const timer=setTimeout(()=>void load(),0); return () => { clearTimeout(timer); generation.current={}; }; }, [load]);

  async function reconcile() {

    setBusy(true); setError("");

    try {

      const run = await api.runReconciliation(periodId, purchase, statement);

      if(run.status !== "succeeded") throw new Error("Run failed");

      router.push(`/periods/${periodId}/review?run_id=${run.id}`);

    } catch { setError("Reconciliation did not complete. Inspect run history and retry."); await load(); }

    finally { setBusy(false); }

  }

  return <div className="console-content w-full min-w-0 space-y-6">

    <Link href="/clients" className="underline">Clients</Link>
    <Link className="block underline" href={`/periods/${periodId}/sales`}>Sales preparation</Link>
    <Link className="block underline" href={`/periods/${periodId}/worksheet`}>Tax worksheet and approval</Link>
    <Link className="block underline" href={`/history?period_id=${periodId}`}>Period history</Link>

    <h2 className="font-display text-4xl">Period {period?.period_code || "workspace"}</h2>

    <ClientRequests periodId={periodId} />

    {error && <p role="alert" className="red-ink">{error} <button onClick={load}>Retry</button></p>}

    {!period && !error && <p>Loading period...</p>}

    <div className="grid md:grid-cols-2 gap-6">{(["purchase", "statement"] as const).map(type => <ImportCard key={type} periodId={periodId} type={type} batches={imports.filter(i => i.source_type === type)} reload={load} />)}</div>

    <Card><CardHeader><CardTitle>Choose committed import versions</CardTitle></CardHeader><CardContent className="space-y-4">

      <p>New uploads do not replace prior runs. Choose both versions explicitly.</p>
      {purchase && <Link className="block underline" href={`/periods/${periodId}/categories?batch_id=${purchase}`}>Review purchase categories</Link>}

      {(["purchase", "statement"] as const).map(type => <label key={type} className="block">{type === "purchase" ? "Purchase version" : "Statement version"}

        <select className="border rounded p-2 block w-full" aria-label={`${type} version`} value={type === "purchase" ? purchase : statement} onChange={e => type === "purchase" ? setPurchase(e.target.value) : setStatement(e.target.value)}>

          <option value="">Select committed import</option>{imports.filter(i => i.source_type === type && i.status === "committed").map(i => <option key={i.id} value={i.id}>{i.id} — {i.record_count} rows</option>)}

        </select></label>)}

      <Button disabled={!purchase || !statement || busy} onClick={reconcile}>{busy ? "Reconciling..." : "Run Reconciliation"}</Button>

      {(!purchase || !statement) && <p className="text-sm text-muted-foreground">Commit and select both imports to continue.</p>}

    </CardContent></Card>

    <Card><CardHeader><CardTitle>Run history</CardTitle></CardHeader><CardContent className="space-y-3">{runs.length ? runs.map(r => <div key={r.id} className="border-b pb-2 break-all"><Link className="underline" href={`/periods/${periodId}/review?run_id=${r.id}`}>{r.id}</Link> — {r.status}<p className="text-sm">{new Date(r.created_at).toLocaleString()}</p></div>) : <p>No runs yet.</p>}</CardContent></Card>

  </div>;

}

function ImportCard({periodId, type, batches, reload}: {periodId:string;type:"purchase"|"statement";batches:ImportBatch[];reload:()=>Promise<void>}) {

  const [selected, setSelected] = useState("");

  const batch = batches.find(b=>b.id===selected) || batches[0];

  const [rows, setRows] = useState<SourceRecord[]>([]);

  const [offset, setOffset] = useState(0);

  const [ack, setAck] = useState(false);

  const [note, setNote] = useState("");

  const [busy, setBusy] = useState(false);

  const [error, setError] = useState("");

  const [mapperFile, setMapperFile] = useState<File | null>(null);

  const [conversion, setConversion] = useState<Gstr2bConversion | null>(null);

  useEffect(()=>{

    let active=true;

    if(batch) api.getImportRows(batch.id, offset).then(r=>{if(active)setRows(r.items);}).catch(e=>{if(active)setError(errorMessage(e));});

    return ()=>{active=false;};

  },[batch, offset]);

  async function upload(file: File) {

    setBusy(true); setError("");

    try { const b=await api.uploadImport(periodId,type==="purchase"?"purchase_register":"statement_2b",file);setSelected(b.id);setOffset(0);setAck(false);setNote("");setMapperFile(null);await reload(); }

    catch(e){const message=errorMessage(e);setError(message);if(/headers/i.test(message)&&!/\.xlsx$/i.test(file.name))setMapperFile(file);}finally{setBusy(false);}

  }

  async function commit(){

    if(!batch)return;setBusy(true);setError("");

    try{await api.commitImport(batch.id,ack,note);await reload();}catch(e){setError(errorMessage(e));}finally{setBusy(false);}

  }

  async function import2b(file: File) {
    setBusy(true); setError(""); setConversion(null);
    try { const r = await api.importGstr2b(periodId, file); setConversion(r.conversion); setSelected(r.batch.id); setOffset(0); setAck(false); setNote(""); await reload(); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }

  return <Card data-testid={`batch-${type}`} className="min-w-0"><CardHeader><CardTitle>{type==="purchase"?"Purchase Register":"GSTR-2B demo statement"}</CardTitle></CardHeader><CardContent className="space-y-4">

    <label className="block">Upload CSV or Excel .xlsx (first sheet, 5 MiB maximum)<input aria-label={`${type} CSV`} className="block w-full border rounded p-2 mt-2" type="file" accept=".csv,.xlsx" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f);e.target.value="";}}/></label>

    {type==="statement" && <label className="block text-sm">…or import a GSTR-2B JSON download (B2B invoices, credit and debit notes)<input aria-label="GSTR-2B JSON" className="block w-full border rounded p-2 mt-2" type="file" accept=".json,application/json" disabled={busy} onChange={e=>{const f=e.target.files?.[0];if(f)void import2b(f);e.target.value="";}}/></label>}

    {conversion && <div data-testid="gstr2b-conversion" className="rounded-lg border border-dashed p-3 text-sm space-y-1"><p><b>{conversion.converted}</b> document(s) converted. {conversion.notice}</p>{conversion.skipped.length>0 && <ul className="list-disc pl-5">{conversion.skipped.map(s=><li key={s.invoice}>Not imported: {s.invoice} — {s.reason}</li>)}</ul>}{conversion.itc_unavailable.length>0 && <p>ITC not available per the statement: {conversion.itc_unavailable.map(i=>`${i.record_id} (${i.reason})`).join(", ")} — decide these in the worksheet.</p>}</div>}

    {error && <p role="alert" className="red-ink">{error}</p>}

    {mapperFile && <ColumnMapper template={type} file={mapperFile} onCancel={()=>setMapperFile(null)} onReady={async f=>{setMapperFile(null);await upload(f);}}/>}

    {batch && <>

      <label className="block">Import version<select aria-label={`${type} preview version`} className="block border p-2 w-full" value={batch.id} onChange={e=>{setSelected(e.target.value);setOffset(0);setAck(false);setNote("");}}>{batches.map(b=><option key={b.id} value={b.id}>{b.id}</option>)}</select></label>

      <p><strong>{batch.status==="committed"?"Committed":"Preview"}</strong> · Total rows: {batch.record_count} · Invalid rows: {batch.invalid_count}</p>

      <details><summary className="cursor-pointer underline">Preview source rows and validation</summary><div className="overflow-auto max-h-72 mt-2"><table className="text-sm w-full"><thead><tr><th>Row</th><th>Record</th><th>Invoice</th><th>Validation</th></tr></thead><tbody>{rows.map(r=><tr key={r.row_number} className="border-b"><td>{r.row_number}</td><td>{r.record_id}</td><td>{r.raw_data.invoice_number}</td><td>{r.is_valid?"Valid":r.issues.join("; ")}</td></tr>)}</tbody></table></div><div className="flex gap-2 mt-2"><Button variant="outline" disabled={offset===0} onClick={()=>setOffset(o=>o-25)}>Previous rows</Button><Button variant="outline" disabled={offset+25>=batch.record_count} onClick={()=>setOffset(o=>o+25)}>Next rows</Button></div></details>

      {batch.status!=="committed" && <>

        {batch.invalid_count>0 && <div className="space-y-2 border rounded p-3"><p>Invalid rows remain visible but are excluded from matching.</p><label className="flex gap-2"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>I acknowledge the invalid rows</label><label className="block">Acknowledgement note<textarea aria-label={`${type} acknowledgement note`} className="border rounded w-full p-2" value={note} onChange={e=>setNote(e.target.value)}/></label></div>}

        <Button disabled={busy || (batch.invalid_count>0 && (!ack || !note.trim()))} onClick={commit}>{busy?"Saving...":"Commit Import"}</Button>

      </>}

      {batch.commit_note && <p className="text-sm">Acknowledgement: {batch.commit_note}</p>}

    </>}

  </CardContent></Card>;

}

