"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api, assistApi, authApi, boardApi, carryApi, CarryForward, errorMessage, firmApi, FirmUser, G3Row, Gstr3bView, Me, worksheetApi, ItcResult, ItcSuggestion, KnowledgeRule, ReconciliationRun, SalesBatch, SetoffResult, TaxAdjustment, TaxDraft, WorksheetPreview } from "@/lib/api";
import { AskLedger, AssistLabel, SavingsPanel } from "@/components/assist";
import { Button } from "@/components/ui/button";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3 } from "lucide-react";
import { Eyebrow, StatusChip, Tone } from "@/components/status-chip";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

const HEADS = ["igst", "cgst", "sgst", "cess"];
const COLUMNS: [string, string][] = [["output_tax", "Output tax"], ["liability_adjustments", "Liability adj."], ["liability", "Liability"], ["itc_claimed", "ITC claimed"], ["itc_reversal", "ITC reversal"], ["other_credit", "Other credit"], ["opening_credit", "Opening credit"], ["credit", "Credit"], ["net", "Net"]];
const ITC_TONE: Record<string, Tone> = { claim: "done", not_claimed: "waiting", deferred: "action", undecided: "blocked" };
const STATE_LABEL: Record<string, string> = { draft: "Draft", approved: "Approved", approved_stale: "Approved — out of date (inputs changed)", reopened: "Reopened" };

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob); const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function Worksheet() {
  const periodId = useParams().period_id as string;
  const [salesBatches, setSalesBatches] = useState<SalesBatch[]>([]);
  const [runs, setRuns] = useState<ReconciliationRun[]>([]);
  const [salesId, setSalesId] = useState("");
  const [runId, setRunId] = useState("");
  const [itc, setItc] = useState<ItcResult[]>([]);
  const [itcNote, setItcNote] = useState("");
  const [adjustments, setAdjustments] = useState<TaxAdjustment[]>([]);
  const [adj, setAdj] = useState({ adjustment_type: "rcm_liability", tax_head: "cgst", amount: "", note: "" });
  const [voidReason, setVoidReason] = useState("");
  const [preview, setPreview] = useState<WorksheetPreview | null>(null);
  const [drafts, setDrafts] = useState<TaxDraft[]>([]);
  const [approvalNote, setApprovalNote] = useState("");
  const [reopenReason, setReopenReason] = useState("");
  const [evidence, setEvidence] = useState({ arn: "", filed_on: "", note: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [suggestions, setSuggestions] = useState<ItcSuggestion[]>([]);
  const [rules, setRules] = useState<KnowledgeRule[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [step, setStep] = useState(1);
  const [ackNotes, setAckNotes] = useState<Record<string, string>>({});
  const [me, setMe] = useState<Me | null>(null);
  useEffect(() => { let active = true; authApi.me().then(m => { if (active) setMe(m); }).catch(() => {}); return () => { active = false; }; }, []);

  const load = useCallback(async () => {
    const [s, r, a, d, k] = await Promise.all([api.getSalesImports(periodId), api.getRuns(periodId), worksheetApi.adjustments(periodId), worksheetApi.drafts(periodId), assistApi.applicableRules(periodId)]);
    setSalesBatches(s.filter(b => b.status === "committed")); setRuns(r.filter(x => x.status === "succeeded")); setAdjustments(a); setDrafts(d); setRules(k); setRefreshKey(n => n + 1);
    if (runId) { const [items, sugg] = await Promise.all([worksheetApi.itcDecisions(runId), assistApi.itcSuggestions(runId)]); setItc(items); setSuggestions(sugg.suggestions); }
    if (salesId && runId) setPreview(await worksheetApi.preview(periodId, salesId, runId));
  }, [periodId, salesId, runId]);
  useEffect(() => { let active = true; const timer = setTimeout(() => load().catch(e => { if (active) setError(errorMessage(e)); }), 0); return () => { active = false; clearTimeout(timer); }; }, [load]);

  async function perform(action: () => Promise<void>) { setBusy(true); setError(""); try { await action(); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  function decide(rows: ItcResult[], decision: string) {
    return perform(async () => { await worksheetApi.decideItc(runId, rows.map(r => ({ result_id: r.result_id, decision, previous_decision_id: r.previous_decision_id })), itcNote); setItcNote(""); });
  }
  const undecidedMatched = itc.filter(r => r.status === "matched" && r.decision === "undecided");
  const undecided = itc.filter(r => r.decision === "undecided");
  const adjustmentRules = rules.filter(r => r.rule_kind === "adjustment");
  const reminders = rules.filter(r => r.rule_kind === "reminder");
  const suggestionFor = Object.fromEntries(suggestions.map(s => [s.result_id, s]));
  const suggestionCounts = suggestions.reduce<Record<string, number>>((acc, s) => ({ ...acc, [s.decision]: (acc[s.decision] || 0) + 1 }), {});
  function acceptSuggestions() {
    return perform(async () => { await worksheetApi.decideItc(runId, itc.filter(r => suggestionFor[r.result_id]).map(r => ({ result_id: r.result_id, decision: suggestionFor[r.result_id].decision, previous_decision_id: r.previous_decision_id })), itcNote); setItcNote(""); });
  }
  const latest = drafts[0];
  // Mirrors the API rules so the button explains itself instead of failing; the API still enforces them.
  const approveBlock = !me ? null : me.role === "preparer" ? "Your role (preparer) cannot approve. Ask an owner or reviewer." : me.require_separate_approver && latest?.actor_id === me.id ? "Firm policy: you saved this draft, so another owner or reviewer must approve it." : null;
  const activeApproval = drafts.find(d => d.approval && !d.approval.reopen)?.approval;
  // A saved draft is approvable only while the live inputs still match its fingerprint.
  const draftOutdated = !!(latest && preview && latest.state === "draft" && latest.sales_batch_id === salesId && latest.run_id === runId && preview.fingerprint !== latest.fingerprint);


  const steps: [string, boolean][] = [
    ["Choose inputs", !!(salesId && runId)],
    ["ITC decisions", itc.length > 0 && undecided.length === 0],
    ["Adjustments", adjustments.length > 0],
    ["Live worksheet", !!preview && preview.blockers.length === 0],
    ["Drafts & approval", !!activeApproval],
  ];
  const filed = !!activeApproval?.filing_evidence.length;
  const stamp = latest && (latest.state === "approved" ? (filed ? "Filed (user-reported)" : "Approved") : latest.state === "approved_stale" ? "Out of date" : latest.state === "reopened" ? "Reopened" : null);
  const field = "block space-y-1 text-sm";

  return <div className="console-content w-full space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="max-w-3xl text-sm text-muted-foreground">Synthetic draft — not for filing. Sums reviewed, supplied amounts per tax head. No set-off, rounding, rate or ITC-eligibility determination; a claim decision records your judgement only.</p>
      <div className="flex items-center gap-4"><AssignPicker periodId={periodId} /><Link className="text-sm underline underline-offset-4" href={`/periods/${periodId}/workspace`}>Back to period</Link></div>
    </div>
    {error && <p role="alert" data-testid="worksheet-error" className="red-ink text-sm">{error}</p>}

    <div className="open-ledger">
      <aside className="ledger-steps" aria-label="Worksheet steps">
        <Eyebrow className="mb-3 block text-muted-foreground">Ledger index</Eyebrow>
        {steps.map(([label, done], i) => <button type="button" key={label} onClick={() => setStep(i + 1)} aria-current={step === i + 1 ? "step" : undefined} className={cn("ledger-step-link", done && step !== i + 1 && "complete", step === i + 1 && "active")}><span>{done && step !== i + 1 ? <CheckCircle2 className="h-3.5 w-3.5" /> : i + 1}</span><b>{label}</b></button>)}
      </aside>
      <div className="ledger-content">

        {step === 1 && <LedgerStep n={1} title="Choose inputs" onNext={salesId && runId ? () => setStep(2) : undefined}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className={field}><Eyebrow>Sales version</Eyebrow><select aria-label="Worksheet sales version" className="native-field" value={salesId} onChange={e => { setSalesId(e.target.value); setPreview(null); }}><option value="">Select a committed sales import</option>{salesBatches.map(b => <option key={b.id} value={b.id}>{b.filename} · {b.id.slice(0, 8)}</option>)}</select></label>
            <label className={field}><Eyebrow>Reconciliation run</Eyebrow><select aria-label="Worksheet reconciliation run" className="native-field" value={runId} onChange={e => { setRunId(e.target.value); setPreview(null); setItc([]); }}><option value="">Select a succeeded run</option>{runs.map(r => <option key={r.id} value={r.id}>{new Date(r.created_at).toLocaleString("en-IN")} · {r.id.slice(0, 8)}</option>)}</select></label>
          </div>
          {(!salesBatches.length || !runs.length) && <p className="margin-note">Commit a sales import and run a reconciliation first.</p>}
        </LedgerStep>}

        {step === 2 && !runId && <LedgerStep n={2} title="ITC decisions"><p className="margin-note">Choose a reconciliation run in step one first.</p></LedgerStep>}
        {step === 2 && runId && <LedgerStep n={2} title="ITC decisions" onNext={() => setStep(3)}>
          <p className="text-sm text-muted-foreground">Only exactly matched results can be claimed. Every other result needs &quot;not claimed&quot; or &quot;deferred&quot; before approval. Decisions are appended; the latest applies.</p>
          <label className={cn(field, "mt-4")}><Eyebrow>Decision note (required)</Eyebrow><Textarea aria-label="ITC decision note" maxLength={2000} placeholder="Why these decisions…" value={itcNote} onChange={e => setItcNote(e.target.value)} /></label>
          {suggestions.length > 0 && <div className="mt-4 rounded-lg border border-dashed border-primary/60 bg-accent/30 p-4" data-testid="itc-suggestions">
            <AssistLabel>ITC pre-fill · rules, not a model</AssistLabel>
            <p className="mt-1 text-sm">Suggested for {suggestions.length} undecided result(s): {["claim", "deferred", "not_claimed"].filter(d => suggestionCounts[d]).map(d => `${suggestionCounts[d]} ${d.replace("_", " ")}`).join(" · ")}. Only exact matches are ever suggested for claiming. Nothing is recorded until you accept with a note.</p>
            <Button className="mt-2" disabled={busy || !itcNote.trim()} title={!itcNote.trim() ? "Add a decision note first" : undefined} onClick={acceptSuggestions}>Accept {suggestions.length} suggestion(s)</Button>
          </div>}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button disabled={busy || !itcNote.trim() || !undecidedMatched.length} onClick={() => decide(undecidedMatched, "claim")}>Claim undecided matched ({undecidedMatched.length})</Button>
            <Button variant="outline" disabled={busy || !itcNote.trim() || !undecided.length} onClick={() => decide(undecided, "not_claimed")}>Mark all undecided as not claimed ({undecided.length})</Button>
          </div>
          <div className="table-wrap mt-4"><table className="min-w-[640px]"><thead><tr><th>Finding</th><th>Purchase records</th><th className="!text-right">ITC at stake</th><th>ITC decision</th><th>Change</th><th>Suggestion</th></tr></thead>
            <tbody>{itc.map(r => <tr key={r.result_id}><td>{r.status}</td><td className="id-cell">{r.purchase_record_ids.join(", ") || "—"}</td><td className="font-figures text-right">{r.itc_at_stake ?? "—"}</td><td data-testid={`itc-${r.result_id}`}><StatusChip tone={ITC_TONE[r.decision] || "waiting"}>{r.decision}</StatusChip></td>
              <td><select aria-label={`ITC decision for ${r.result_id}`} className="native-field py-1" disabled={busy || !itcNote.trim()} value="" onChange={e => { if (e.target.value) void decide([r], e.target.value); }}><option value="">Set…</option>{r.status === "matched" && <option value="claim">Claim</option>}<option value="not_claimed">Not claimed</option><option value="deferred">Deferred</option></select>{r.status !== "matched" && <small className="ml-2 text-xs text-muted-foreground">Claim unavailable</small>}</td>
              <td className="max-w-[260px] text-xs text-muted-foreground">{suggestionFor[r.result_id] ? <><b className="font-label uppercase tracking-wider text-primary">{suggestionFor[r.result_id].decision.replace("_", " ")}</b> — {suggestionFor[r.result_id].reason}</> : "—"}</td></tr>)}</tbody></table></div>
        </LedgerStep>}

        {step === 3 && <LedgerStep n={3} title="Adjustments" onNext={() => setStep(4)}>
          <p className="text-sm text-muted-foreground">Supplied amounts with a note, applied to one tax head. Remove a mistake by voiding it; the entry stays visible.</p>
          <CarryPanel periodId={periodId} refreshKey={refreshKey} busy={busy} run={perform} />
          {adjustmentRules.length > 0 && <div className="mt-4 rounded-lg border border-dashed border-primary/60 bg-accent/30 p-4" data-testid="client-rules">
            <AssistLabel>Client rules from the knowledge base</AssistLabel>
            <ul className="mt-2 space-y-2">{adjustmentRules.map(r => <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
              <span><b>{r.adjustment_type?.replaceAll("_", " ")} · {r.tax_head?.toUpperCase()} · <span className="font-figures">{r.amount}</span></b> <span className="text-xs text-muted-foreground">({r.frequency.replace("_", "-")})</span> <span className="text-muted-foreground">— {r.note}</span></span>
              {r.applied ? <StatusChip tone="done">Applied this period</StatusChip> : <Button size="sm" variant="outline" disabled={busy} onClick={() => perform(async () => { await assistApi.applyRule(r.id, periodId); })}>Apply rule</Button>}
            </li>)}</ul>
          </div>}
          <div className="mt-4 grid gap-3 md:grid-cols-[1.2fr_.7fr_.7fr_1.6fr]">
            <label className={field}><Eyebrow>Type</Eyebrow><select aria-label="Adjustment type" className="native-field" value={adj.adjustment_type} onChange={e => setAdj({ ...adj, adjustment_type: e.target.value })}><option value="rcm_liability">Reverse-charge liability</option><option value="other_liability">Other liability</option><option value="itc_reversal">ITC reversal</option><option value="other_credit">Other credit</option><option value="opening_credit">Opening credit balance (user-reported)</option></select></label>
            <label className={field}><Eyebrow>Tax head</Eyebrow><select aria-label="Adjustment tax head" className="native-field" value={adj.tax_head} onChange={e => setAdj({ ...adj, tax_head: e.target.value })}>{HEADS.map(h => <option key={h} value={h}>{h.toUpperCase()}</option>)}</select></label>
            <label className={field}><Eyebrow>Amount</Eyebrow><Input aria-label="Adjustment amount" className="font-figures text-right" placeholder="0.00" value={adj.amount} onChange={e => setAdj({ ...adj, amount: e.target.value })} /></label>
            <label className={field}><Eyebrow>Note</Eyebrow><Input aria-label="Adjustment note" value={adj.note} onChange={e => setAdj({ ...adj, note: e.target.value })} /></label>
          </div>
          <Button className="mt-3" disabled={busy || !adj.amount || !adj.note.trim()} onClick={() => perform(async () => { await worksheetApi.addAdjustment(periodId, adj); setAdj({ ...adj, amount: "", note: "" }); })}>Add adjustment</Button>
          {adjustments.length > 0 && <>
            <label className={cn(field, "mt-5 max-w-md")}><Eyebrow>Void reason</Eyebrow><Input aria-label="Void reason" value={voidReason} onChange={e => setVoidReason(e.target.value)} /></label>
            <ul className="mt-3 border-t">{adjustments.map(a => <li key={a.id} data-testid="adjustment" className={cn("adjustment-line", a.void && "voided")}>
              <span className="font-label text-[0.68rem] font-bold uppercase tracking-wider">{a.adjustment_type.replaceAll("_", " ")}</span>
              <span className="id-cell">{a.tax_head.toUpperCase()}</span>
              <span className="font-figures text-right">{a.amount}</span>
              <span className="min-w-0">{a.note}{a.void ? <span className="margin-note !m-0 !ml-2 inline-block text-base">(void: {a.void.reason})</span> : null}</span>
              {a.void ? <span className="stamp px-1.5 text-xs" style={{ transform: "rotate(-5deg)" }}>Void</span> : <Button variant="outline" size="sm" disabled={busy || !voidReason.trim()} onClick={() => perform(async () => { await worksheetApi.voidAdjustment(a.id, voidReason); setVoidReason(""); })}>Void</Button>}
            </li>)}</ul>
          </>}
        </LedgerStep>}

        {step === 4 && !preview && <LedgerStep n={4} title="Live worksheet"><p className="margin-note">Choose the sales version and reconciliation run in step one first.</p></LedgerStep>}
        {step === 4 && preview && <LedgerStep n={4} title="Live worksheet" onNext={() => setStep(5)}>
          <p className="mb-4 text-sm text-muted-foreground">Sales rows included <b className="font-figures">{preview.payload.counts.sales_included}</b>, excluded <b className="font-figures">{preview.payload.counts.sales_excluded}</b>, pending <b className="font-figures">{preview.payload.counts.sales_pending}</b>. ITC: {Object.entries(preview.payload.counts.itc).map(([k, v]) => `${k.replaceAll("_", " ")} ${v}`).join(" · ")}.</p>
          {preview.blockers.length > 0
            ? <div data-testid="blockers" className="blocker-note has-blockers !w-auto !items-start"><AlertTriangle className="mt-0.5" /><ul className="space-y-1">{preview.blockers.map(b => <li key={b}>{b}</li>)}</ul></div>
            : <p data-testid="no-blockers" className="blocker-note clear"><CheckCircle2 />No blockers.</p>}
          {preview.payload.worksheet && <div className="mt-5"><HeadTable heads={preview.payload.worksheet.heads} prefix="live" /></div>}
          <SetoffPanel setoff={preview.payload.setoff} prefix="live" />
          <div className="mt-5 flex justify-end"><Button disabled={busy} onClick={() => perform(async () => { await worksheetApi.createDraft(periodId, salesId, runId); })}>Save draft snapshot</Button></div>
        </LedgerStep>}


        {step === 4 && <div className="mt-8"><SavingsPanel periodId={periodId} refreshKey={refreshKey} /></div>}

        {step === 5 && <LedgerStep n={5} title="Drafts & approval">
          {reminders.length > 0 && <div className="mb-6 rounded-lg border border-dashed border-primary/60 bg-accent/30 p-4" data-testid="reminders">
            <AssistLabel>Before approval · reminders from the knowledge base</AssistLabel>
            <ul className="mt-2 space-y-3">{reminders.map(r => <li key={r.id} className="space-y-2 text-sm" data-testid="reminder">
              <p className="flex flex-wrap items-center gap-2">{r.acknowledged ? <StatusChip tone="done">Checked</StatusChip> : <StatusChip tone="action">To check</StatusChip>}<b>{r.note}</b><span className="text-xs text-muted-foreground">{r.client_id ? "" : "firm-wide"}</span></p>
              {r.acknowledged ? <p className="margin-note !m-0 text-lg">{r.acknowledged.note}</p> :
                <div className="flex flex-wrap gap-2"><Input aria-label={`What was checked: ${r.note}`} className="max-w-md" placeholder="What did you check?" value={ackNotes[r.id] || ""} onChange={e => setAckNotes({ ...ackNotes, [r.id]: e.target.value })} />
                  <Button size="sm" disabled={busy || !(ackNotes[r.id] || "").trim()} onClick={() => perform(async () => { await assistApi.acknowledgeRule(r.id, periodId, ackNotes[r.id]); setAckNotes({ ...ackNotes, [r.id]: "" }); })}>Mark as checked</Button></div>}
            </li>)}</ul>
          </div>}
          {!drafts.length && <p className="margin-note">No drafts yet — save a snapshot from the live worksheet.</p>}
          {latest && <div data-testid="latest-draft" className="draft-sheet space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div><Eyebrow>Latest draft</Eyebrow><h3 className="font-display text-3xl">{latest.id.slice(0, 8).toUpperCase()}</h3><p className="id-cell mt-1">{new Date(latest.created_at).toLocaleString("en-IN")} · <strong data-testid="draft-state" className="font-label text-[0.7rem] uppercase tracking-wider">{STATE_LABEL[latest.state]}</strong></p></div>
              {stamp && <div aria-hidden className={cn("stamp stamp-large", (latest.state === "approved") && "stamp-green")}>{stamp}</div>}
            </div>
            {latest.blockers.length > 0 && <p className="blocker-note has-blockers !w-auto"><AlertTriangle />Blocked: {latest.blockers.join(" ")}</p>}
            {latest.payload.worksheet && <HeadTable heads={latest.payload.worksheet.heads} prefix="draft" />}
            <SetoffPanel setoff={latest.payload.setoff} prefix="draft" />
            <Gstr3bPanel view={latest.payload.gstr3b} />
            {latest.approval && <blockquote className="margin-note">{latest.approval.note}<cite>Approved · {new Date(latest.approval.created_at).toLocaleString("en-IN")}{latest.approval.reopen ? ` · reopened: ${latest.approval.reopen.reason}` : ""}</cite></blockquote>}
            <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={busy} onClick={() => perform(async () => download(await worksheetApi.exportDraft(latest.id), `Synthetic_Tax_Worksheet_${latest.id}.xlsx`))}>Export draft workbook</Button></div>
            {draftOutdated && <p data-testid="draft-outdated" className="blocker-note has-blockers !w-auto"><AlertTriangle />Inputs changed after this draft was saved. Save a new draft snapshot before approving.</p>}
            {latest.state === "draft" && !activeApproval && !draftOutdated && <div className="grid gap-3 border-t border-ledger-line pt-4 md:grid-cols-[1fr_auto] md:items-end">
              <label className={field}><Eyebrow>Approval note (required)</Eyebrow><Textarea aria-label="Approval note" value={approvalNote} onChange={e => setApprovalNote(e.target.value)} /></label>
              <Button disabled={busy || !approvalNote.trim() || latest.blockers.length > 0 || !!approveBlock} title={approveBlock ?? (latest.blockers.length ? "Resolve blockers first" : !approvalNote.trim() ? "Add an approval note first" : undefined)} onClick={() => perform(async () => { await worksheetApi.approve(latest.id, approvalNote); setApprovalNote(""); })}>Approve draft</Button></div>}
            {latest.state === "draft" && activeApproval && <p className="margin-note">An earlier approval is still active. Reopen it before approving a new draft.</p>}
          </div>}

          {activeApproval && <div className="paper-card mt-8 space-y-4">
            <div><Eyebrow className="text-primary">Active approval</Eyebrow><p className="mt-1 text-sm">{activeApproval.note} · <span className="id-cell">{new Date(activeApproval.created_at).toLocaleString("en-IN")}</span></p></div>
            {activeApproval.filing_evidence.map(e => <p key={e.id} data-testid="filing-evidence" className="text-sm">Filed: <span className="id-cell">{e.arn}</span> on <span className="id-cell">{e.filed_on}</span> — <i>{e.label}</i></p>)}
            <div className="grid gap-3 md:grid-cols-3">
              <label className={field}><Eyebrow>Acknowledgement reference</Eyebrow><Input aria-label="Filing reference" className="font-figures" value={evidence.arn} onChange={e => setEvidence({ ...evidence, arn: e.target.value })} /></label>
              <label className={field}><Eyebrow>Filed on</Eyebrow><Input aria-label="Filed on" type="date" value={evidence.filed_on} onChange={e => setEvidence({ ...evidence, filed_on: e.target.value })} /></label>
              <label className={field}><Eyebrow>Note</Eyebrow><Input aria-label="Filing note" value={evidence.note} onChange={e => setEvidence({ ...evidence, note: e.target.value })} /></label>
            </div>
            <Button variant="outline" disabled={busy || !evidence.arn.trim() || !evidence.filed_on} onClick={() => perform(async () => { await worksheetApi.filingEvidence(activeApproval.id, evidence); setEvidence({ arn: "", filed_on: "", note: "" }); })}>Record filing reference (user-reported)</Button>
            <div className="grid gap-3 border-t border-ledger-line pt-4 md:grid-cols-[1fr_auto] md:items-end">
              <label className={field}><Eyebrow>Reopen reason (required)</Eyebrow><Textarea aria-label="Reopen reason" value={reopenReason} onChange={e => setReopenReason(e.target.value)} /></label>
              <Button variant="destructive" disabled={busy || !reopenReason.trim()} onClick={() => perform(async () => { await worksheetApi.reopen(activeApproval.id, reopenReason); setReopenReason(""); })}>Reopen approval</Button>
            </div>
          </div>}

          {drafts.length > 1 && <details className="mt-8"><summary className="cursor-pointer"><Eyebrow>Earlier drafts ({drafts.length - 1})</Eyebrow></summary>
            <ul className="mt-3 border-t">{drafts.slice(1).map(d => <li key={d.id} className="grid grid-cols-[auto_1fr_auto] gap-4 border-b border-ledger-line py-2 text-sm"><span className="id-cell">{d.id.slice(0, 8).toUpperCase()}</span><span>{STATE_LABEL[d.state]}{d.approval?.reopen ? <span className="margin-note !m-0 !ml-2 inline-block text-base">reopened: {d.approval.reopen.reason}</span> : null}</span><span className="id-cell">{new Date(d.created_at).toLocaleString("en-IN")}</span></li>)}</ul>
          </details>}
          <p className="mt-8 text-xs text-muted-foreground">Set-off and rounding follow only the firm&apos;s CA-confirmed rules (Knowledge → Legal rules). No interest or late fee is included in cash payable.</p>
        </LedgerStep>}
      </div>
    </div>
    <AskLedger periodId={periodId} salesId={salesId} runId={runId} />
    <Link className="text-sm underline underline-offset-4" href={`/history?period_id=${periodId}`}>History for this period</Link>
  </div>;
}

function LedgerStep({ n, title, children, onNext }: { n: number; title: string; children: React.ReactNode; onNext?: () => void }) {
  const words = ["one", "two", "three", "four", "five"];
  return <section id={`step-${n}`}><Eyebrow className="text-primary">Step {words[n - 1]}</Eyebrow><h2 className="mb-5 mt-1 font-display text-4xl">{title}</h2>{children}
    {onNext && <div className="mt-8 flex justify-end"><Button onClick={onNext}>Continue <ArrowRight className="ml-2 h-4 w-4" /></Button></div>}</section>;
}

// Column totals in whole paise, so adding the displayed decimal strings involves no floating-point rounding.
function toPaise(v: string) { const m = /^(-?)(\d+)\.(\d{2})$/.exec(v || ""); return m ? (m[1] ? -1 : 1) * (Number(m[2]) * 100 + Number(m[3])) : 0; }
function fromPaise(p: number) { const a = Math.abs(p); return `${p < 0 ? "-" : ""}${Math.floor(a / 100)}.${String(a % 100).padStart(2, "0")}`; }

function HeadTable({ heads, prefix }: { heads: Record<string, Record<string, string>>; prefix: string }) {
  return <div className="table-wrap worksheet-table"><table className="min-w-[760px]"><thead><tr><th>Head</th>{COLUMNS.map(([, label]) => <th key={label} className="!text-right">{label}</th>)}</tr></thead>
    <tbody>{HEADS.map(h => <tr key={h}><td className="id-cell">{h.toUpperCase()}</td>{COLUMNS.map(([key]) => { const v = heads[h]?.[key] ?? ""; return <td key={key} data-testid={`${prefix}-${key}-${h}`} className={cn("font-figures text-right", key === "net" && "font-semibold", key === "net" && v.startsWith("-") && "text-status-done")} title={key === "net" && v.startsWith("-") ? "Excess credit" : undefined}>{v}</td>; })}</tr>)}</tbody>
    <tfoot><tr><td className="font-semibold">Total</td>{COLUMNS.map(([key]) => <td key={key} data-testid={`${prefix}-${key}-total`} className="font-figures text-right font-semibold">{fromPaise(HEADS.reduce((s, h) => s + toPaise(heads[h]?.[key] ?? ""), 0))}</td>)}</tr></tfoot></table></div>;
}
function SetoffPanel({ setoff, prefix }: { setoff?: SetoffResult; prefix: string }) {
  if (!setoff) return <p className="margin-note">Set-off: this draft was saved before set-off existed.</p>;
  if (setoff.status !== "computed") return <div data-testid={`${prefix}-setoff`} className="blocker-note !w-auto !items-start border-status-waiting text-muted-foreground"><Clock3 className="mt-0.5" /><span><b>Set-off not computed.</b> {setoff.reason} {setoff.reason?.includes("Legal rules") && <Link className="underline" href="/knowledge">Open Knowledge</Link>}</span></div>;
  const rules = setoff.rules || {};
  return <section data-testid={`${prefix}-setoff`} className="mt-6 space-y-3">
    <div className="flex flex-wrap items-end justify-between gap-2"><div><Eyebrow className="text-primary">Set-off · {setoff.version}</Eyebrow><h3 className="font-display text-2xl">Cash payable <span data-testid={`${prefix}-total-cash`} className="font-figures">₹{setoff.total_cash}</span></h3></div>
      <p className="text-xs text-muted-foreground">Order: {(rules.credit_utilisation_order?.value.steps as string[] | undefined)?.join(" · ")} — source: {rules.credit_utilisation_order?.source_reference}{rules.payment_rounding ? ` · rounding: ${rules.payment_rounding.value.multiple} ${rules.payment_rounding.value.direction}` : ""}</p></div>
    {setoff.rounding_note && <p className="text-xs text-muted-foreground">{setoff.rounding_note}</p>}
    <div className="table-wrap"><table className="min-w-[560px]"><thead><tr><th>Head</th><th className="!text-right">Liability</th><th className="!text-right">Credit</th><th className="!text-right">Cash (before rounding)</th><th className="!text-right">Rounding</th><th className="!text-right">Cash payable</th><th className="!text-right">Carry forward</th></tr></thead>
      <tbody>{HEADS.map(h => { const v = setoff.heads![h]; return <tr key={h}><td className="id-cell">{h.toUpperCase()}</td>{(["liability", "credit", "cash_before_rounding", "rounding_difference", "cash", "carry_forward"] as const).map(k => <td key={k} data-testid={`${prefix}-setoff-${k}-${h}`} className={cn("font-figures text-right", k === "cash" && "font-semibold")}>{v[k]}</td>)}</tr>; })}</tbody>
      <tfoot><tr><td className="font-semibold">Total</td><td /><td /><td className="font-figures text-right">{setoff.total_cash_before_rounding}</td><td /><td className="font-figures text-right font-semibold">{setoff.total_cash}</td><td className="font-figures text-right">{setoff.total_carry_forward}</td></tr></tfoot></table></div>
    {setoff.utilisation!.length > 0 && <p className="text-xs text-muted-foreground">Credit used: {setoff.utilisation!.map(u => `${u.credit_head.toUpperCase()}→${u.liability_head.toUpperCase()} ₹${u.amount}`).join(" · ")}</p>}
  </section>;
}
function CarryPanel({ periodId, refreshKey, busy, run }: { periodId: string; refreshKey: number; busy: boolean; run: (action: () => Promise<void>) => Promise<void> }) {
  const [cf, setCf] = useState<CarryForward | null>(null);
  useEffect(() => { let active = true; carryApi.get(periodId).then(v => { if (active) setCf(v); }).catch(() => { if (active) setCf(null); }); return () => { active = false; }; }, [periodId, refreshKey]);
  if (!cf) return null;
  const amounts = Object.entries(cf.amounts || {}).map(([h, a]) => `${h.toUpperCase()} ₹${a}`).join(" · ");
  return <div data-testid="carry-forward" className="mt-4 rounded-lg border border-dashed border-primary/60 bg-accent/30 p-4 text-sm">
    <Eyebrow className="text-primary">Opening credit · from {cf.from_period}</Eyebrow>
    {cf.status === "available" && <div className="mt-2 flex flex-wrap items-center justify-between gap-3"><p>Closing credit after set-off in the approved {cf.from_period} worksheet: <b className="font-figures">{amounts}</b>.</p>
      <Button size="sm" disabled={busy} onClick={() => run(async () => { await carryApi.apply(periodId); })}>Bring forward as opening credit</Button></div>}
    {cf.status === "already_entered" && <p className="mt-2">Opening credit already entered ({cf.existing.map(a => `${a.tax_head.toUpperCase()} ₹${a.amount}`).join(" · ")}). Void it below to bring forward again.</p>}
    {cf.status === "nothing_to_carry" && <p className="mt-2">The approved {cf.from_period} worksheet left no credit to carry forward.</p>}
    {cf.status === "not_available" && <p className="mt-2 text-muted-foreground">{cf.reason} You can still enter an opening credit balance by hand below.</p>}
  </div>;
}
function AssignPicker({ periodId }: { periodId: string }) {
  const [users, setUsers] = useState<FirmUser[]>([]);
  const [assignee, setAssignee] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([firmApi.get(), boardApi.get()]).then(([f, rows]) => { if (!active) return; setUsers(f.users.filter(u => u.is_active)); setAssignee(rows.find(r => r.period_id === periodId)?.assignee?.id ?? ""); }).catch(() => {});
    return () => { active = false; };
  }, [periodId]);
  async function change(id: string) { setError(""); try { await firmApi.assign(periodId, id || null); setAssignee(id); } catch (e) { setError(errorMessage(e)); } }
  return <label className="flex items-center gap-2 text-sm"><span className="font-label text-[0.68rem] font-bold uppercase tracking-wider">Assigned to</span>
    <select aria-label="Assigned to" className="native-field w-auto py-1" value={assignee} onChange={e => change(e.target.value)}><option value="">Nobody</option>{users.map(u => <option key={u.id} value={u.id}>{u.display_name} ({u.role})</option>)}</select>
    {error && <span className="red-ink text-xs">{error}</span>}</label>;
}
function Gstr3bPanel({ view }: { view?: Gstr3bView }) {
  if (!view || view.status !== "available") return null;
  const cell = (v: string | null) => v === null ? <span className="text-xs text-muted-foreground">not captured</span> : v;
  const table = (title: string, rows: G3Row[], taxable: boolean) => <div className="table-wrap"><table className="min-w-[720px]"><thead><tr><th>{title}</th>{taxable && <th className="!text-right">Taxable value</th>}{HEADS.map(h => <th key={h} className="!text-right">{h.toUpperCase()}</th>)}</tr></thead>
    <tbody>{rows.map(r => <tr key={r.label}><td className="text-sm">{r.label}</td>{taxable && <td className="font-figures text-right">{cell(r.taxable_value)}</td>}{HEADS.map(h => <td key={h} className="font-figures text-right">{cell(r[h as keyof G3Row] as string | null)}</td>)}</tr>)}</tbody></table></div>;
  return <details data-testid="gstr3b-view" className="rounded-lg border p-3"><summary className="cursor-pointer"><Eyebrow className="text-primary">GSTR-3B view (draft layout, for CA review)</Eyebrow></summary>
    <div className="mt-3 space-y-4 text-sm">
      <p className="text-xs text-muted-foreground">{view.notice}</p>
      {table("3.1 Outward and reverse-charge inward supplies", view.table_3_1!, true)}
      {table("4 Eligible ITC", view.table_4!, false)}
      {view.table_6_1 ? <div className="table-wrap"><table className="min-w-[720px]"><thead><tr><th>6.1 Payment of tax</th><th className="!text-right">Tax payable</th>{HEADS.map(h => <th key={h} className="!text-right">Paid via {h.toUpperCase()} credit</th>)}<th className="!text-right">Paid in cash</th></tr></thead>
        <tbody>{view.table_6_1.map(p => <tr key={p.head}><td className="id-cell">{p.head.toUpperCase()}</td><td className="font-figures text-right">{p.tax_payable}</td>{HEADS.map(h => <td key={h} className="font-figures text-right">{p.paid_through_itc[h]}</td>)}<td data-testid={`gstr3b-cash-${p.head}`} className="font-figures text-right font-semibold">{p.paid_in_cash}</td></tr>)}</tbody></table></div>
        : <p className="text-muted-foreground">6.1 Payment of tax: {view.table_6_1_note}</p>}
    </div>
  </details>;
}