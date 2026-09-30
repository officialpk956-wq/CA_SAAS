"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Lightbulb, MessageSquareText, PiggyBank, Wand2 } from "lucide-react";
import { assistApi, errorMessage, AskAnswer, BriefItem, MappingProposal, OrgSavings, PeriodSavings } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Eyebrow, StatusChip } from "@/components/status-chip";

/** Label shown on every assistant surface: suggestions are pencil, not ink. */
export function AssistLabel({ children }: { children: React.ReactNode }) {
  return <Eyebrow className="flex items-center gap-1.5 text-primary"><Wand2 className="h-3.5 w-3.5" />{children}</Eyebrow>;
}

export function MorningBrief() {
  const [items, setItems] = useState<BriefItem[] | null>(null);
  const [savings, setSavings] = useState<OrgSavings | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([assistApi.brief(), assistApi.orgSavings()]).then(([b, s]) => { if (active) { setItems(b.items); setSavings(s); } }).catch(e => { if (active) setError(errorMessage(e)); });
    return () => { active = false; };
  }, []);
  if (error) return <p className="red-ink text-sm">{error}</p>;
  if (!items) return <p className="text-sm text-muted-foreground">Writing the morning brief…</p>;
  return <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
    <section className="paper-card" data-testid="morning-brief" aria-labelledby="brief-heading">
      <AssistLabel>Assistant · built from the board and audit trail</AssistLabel>
      <h3 id="brief-heading" className="mt-1 font-display text-2xl">Morning brief</h3>
      <ul className="mt-3 space-y-2">{items.map((b, i) => <li key={i} className="flex items-start gap-2 text-sm"><span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${b.tone === "blocked" ? "bg-destructive" : b.tone === "action" ? "bg-status-needs" : b.tone === "done" ? "bg-status-done" : "bg-status-waiting"}`} /><Link href={b.href} className="hover:underline">{b.text}</Link></li>)}</ul>
    </section>
    <section id="savings" className="paper-card" data-testid="credit-at-risk">
      <Eyebrow className="flex items-center gap-1.5 text-muted-foreground"><PiggyBank className="h-3.5 w-3.5" />Savings finder</Eyebrow>
      <p className="mt-2 font-display text-4xl">₹{Number(savings?.total || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}</p>
      <p className="text-xs text-muted-foreground">credit at risk or unclaimed, from recorded rows</p>
      <ul className="mt-3 space-y-1 text-sm">{(savings?.periods || []).slice(0, 4).map(p => <li key={p.period_id} className="flex justify-between gap-2"><Link href={`/periods/${p.period_id}/worksheet#savings`} className="truncate hover:underline">{p.client_name} · {p.period_code}</Link><span className="font-figures">{p.total}</span></li>)}</ul>
      {!savings?.periods.length && <p className="mt-3 text-sm text-muted-foreground">Nothing found yet.</p>}
    </section>
  </div>;
}

export function SavingsPanel({ periodId, refreshKey = 0 }: { periodId: string; refreshKey?: number }) {
  const [data, setData] = useState<PeriodSavings | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { let active = true; assistApi.periodSavings(periodId).then(d => { if (active) setData(d); }).catch(e => { if (active) setError(errorMessage(e)); }); return () => { active = false; }; }, [periodId, refreshKey]);
  return <section id="savings" className="paper-card scroll-mt-28" data-testid="savings-panel">
    <div className="flex flex-wrap items-end justify-between gap-2"><div><AssistLabel>Savings finder</AssistLabel><h3 className="mt-1 font-display text-2xl">Credit at risk or unclaimed</h3></div>
      {data && <p className="font-display text-3xl" data-testid="savings-total">₹{data.total}</p>}</div>
    {error && <p className="red-ink text-sm">{error}</p>}
    {data && !data.items.length && <p className="margin-note">Nothing found for this period.</p>}
    {data && data.items.length > 0 && <>
      <ul className="mt-3 divide-y divide-[var(--ledger-line)]">{data.items.map(i => <li key={i.kind} className="grid gap-1 py-3 md:grid-cols-[1fr_auto]" data-testid={`saving-${i.kind}`}>
        <div><p className="font-semibold">{i.title} {i.needs_ca && <StatusChip tone="action">Ask the CA</StatusChip>}</p><p className="text-sm text-muted-foreground">{i.detail}</p><p className="margin-note !m-0 text-lg">{i.action}</p></div>
        <span className="font-figures text-right text-lg">{i.amount === "0.00" ? "—" : `₹${i.amount}`}</span>
      </li>)}</ul>
      <p className="text-xs text-muted-foreground">{data.notice}</p>
    </>}
  </section>;
}

export function AskLedger({ periodId, salesId, runId }: { periodId: string; salesId?: string; runId?: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AskAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const suggestions = ["Why is CGST net what it is?", "What is blocking approval?", "What changed after approval?", "Who approved this period?", "How much credit is at risk?", "Which suppliers should we follow up?"];
  async function ask(q: string) { setQuestion(q); setBusy(true); setError(""); try { setAnswer(await assistApi.ask(periodId, q, salesId, runId)); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  return <section className="paper-card" data-testid="ask-ledger">
    <AssistLabel>Ask the ledger · answers only from this period&apos;s records</AssistLabel>
    <h3 className="mt-1 flex items-center gap-2 font-display text-2xl"><MessageSquareText className="h-5 w-5" />Ask the ledger</h3>
    <div className="mt-3 flex flex-wrap gap-2">{suggestions.map(s => <button key={s} type="button" className="category-chip hover:bg-accent" disabled={busy} onClick={() => ask(s)}>{s}</button>)}</div>
    <form className="mt-3 flex gap-2" onSubmit={e => { e.preventDefault(); if (question.trim()) void ask(question); }}>
      <Input aria-label="Ask the ledger" placeholder="Ask about this period…" value={question} maxLength={500} onChange={e => setQuestion(e.target.value)} />
      <Button type="submit" disabled={busy || !question.trim()}>{busy ? "…" : "Ask"}</Button>
    </form>
    {error && <p className="red-ink mt-2 text-sm">{error}</p>}
    {answer && <div className="mt-4 border-t border-ledger-line pt-3" data-testid="ask-answer">
      <p className="text-sm leading-relaxed">{answer.answer}</p>
      {answer.citations.length > 0 && <><Eyebrow className="mt-3 block text-muted-foreground">Sources</Eyebrow><ul className="mt-1 space-y-0.5">{answer.citations.map((c, i) => <li key={i} className="id-cell">{c.label}</li>)}</ul></>}
    </div>}
  </section>;
}

/** Map an unfamiliar CSV layout onto the template. Values are copied verbatim; normal validation still runs. */
export function ColumnMapper({ template, file, onReady, onCancel }: { template: "purchase" | "statement" | "sales"; file: File; onReady: (converted: File) => Promise<void>; onCancel: () => void }) {
  const [proposal, setProposal] = useState<MappingProposal | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { let active = true; assistApi.proposeMapping(template, file).then(p => { if (active) { setProposal(p); setMapping(p.mapping); } }).catch(e => { if (active) setError(errorMessage(e)); }); return () => { active = false; }; }, [template, file]);
  const missing = proposal ? proposal.fields.filter(f => !proposal.optional.includes(f) && !mapping[f]) : [];
  async function apply() { setBusy(true); setError(""); try { await onReady(await assistApi.applyMapping(template, mapping, file)); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  return <div className="rounded-lg border border-dashed border-primary/60 bg-accent/30 p-4 space-y-3" data-testid="column-mapper">
    <AssistLabel>Column mapper</AssistLabel>
    <p className="text-sm">“{file.name}” doesn&apos;t use the template headers. Check the suggested mapping, then convert. Values are copied as they are — validation still reports every problem.</p>
    {error && <p className="red-ink text-sm">{error}</p>}
    {!proposal && !error && <p className="text-sm text-muted-foreground">Reading headers…</p>}
    {proposal && <div className="table-wrap"><table className="min-w-[420px]"><thead><tr><th>Template field</th><th>Column in your file</th></tr></thead><tbody>
      {proposal.fields.map(f => <tr key={f}><td className="id-cell">{f}{proposal.optional.includes(f) ? " (optional)" : ""}</td><td>
        <select aria-label={`Source column for ${f}`} className="native-field py-1" value={mapping[f] || ""} onChange={e => setMapping({ ...mapping, [f]: e.target.value || null })}>
          <option value="">— not mapped —</option>{proposal.source_headers.map(h => <option key={h} value={h}>{h}</option>)}
        </select></td></tr>)}
    </tbody></table></div>}
    {missing.length > 0 && <p className="red-ink text-sm">Map these required fields: {missing.join(", ")}</p>}
    <div className="flex flex-wrap gap-2"><Button disabled={busy || !proposal || missing.length > 0} onClick={apply}>{busy ? "Converting…" : "Convert and upload"}</Button><Button variant="outline" onClick={onCancel}>Cancel</Button></div>
  </div>;
}

export function Hint({ children }: { children: React.ReactNode }) {
  return <p className="flex items-start gap-2 text-sm text-muted-foreground"><Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-primary" />{children}</p>;
}

/** Explains one finding and looks for likely counterparts inside the same run. Never pairs records itself. */
export function Investigator({ runId, resultId, onUseNote }: { runId: string; resultId: string; onUseNote: (note: string) => void }) {
  const [data, setData] = useState<import("@/lib/api").Investigation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run() { setBusy(true); setError(""); try { setData(await assistApi.investigate(runId, resultId)); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  return <div className="rounded-lg border border-dashed border-primary/60 bg-accent/30 p-4 space-y-3" data-testid="investigator">
    <div className="flex flex-wrap items-center justify-between gap-2"><AssistLabel>Exception investigator</AssistLabel>
      <Button size="sm" variant="outline" disabled={busy} onClick={run}>{busy ? "Investigating…" : data ? "Investigate again" : "Investigate this finding"}</Button></div>
    {error && <p className="red-ink text-sm">{error}</p>}
    {data && <>
      <ul className="list-disc space-y-1 pl-5 text-sm">{data.findings.map((f, i) => <li key={i}>{f}</li>)}</ul>
      {data.candidates.map(c => <div key={c.record.record_id} className="ledger-page !min-h-0 !py-3 text-sm" data-testid="investigator-candidate">
        <Eyebrow>Likely counterpart · {c.record.side}</Eyebrow>
        <p className="id-cell mt-1">{c.record.record_id} · {c.record.supplier_ref} · {c.record.invoice_number} · {c.record.invoice_date} · {c.record.invoice_total}</p>
        <p className="mt-1">{c.reasons.join("; ")}</p>
        {Object.keys(c.differences).length > 0 && <p className="red-ink">Differences: {Object.entries(c.differences).map(([k, v]) => `${k} ${v}`).join(", ")}</p>}
      </div>)}
      <Button size="sm" onClick={() => onUseNote(data.suggested_note)}>Use as resolution note</Button>
      <p className="text-xs text-muted-foreground">The finding itself does not change. You decide and save the resolution below.</p>
    </>}
  </div>;
}

export function SupplierFollowups({ runId }: { runId: string }) {
  const [drafts, setDrafts] = useState<import("@/lib/api").FollowupDraft[] | null>(null);
  const [copied, setCopied] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { let active = true; assistApi.followups(runId).then(d => { if (active) setDrafts(d.drafts); }).catch(e => { if (active) setError(errorMessage(e)); }); return () => { active = false; }; }, [runId]);
  async function copy(d: import("@/lib/api").FollowupDraft) { try { await navigator.clipboard.writeText(d.message); setCopied(d.supplier_ref); } catch { setCopied(""); } }
  return <section className="paper-card" data-testid="supplier-followups">
    <AssistLabel>Supplier follow-up drafts</AssistLabel>
    <h3 className="mt-1 font-display text-2xl">Messages to send</h3>
    <p className="text-sm text-muted-foreground">For invoices missing from the statement or with different amounts. GST Helper never sends anything — copy and send it yourself.</p>
    {error && <p className="red-ink text-sm">{error}</p>}
    {drafts && !drafts.length && <p className="margin-note">No follow-ups needed for this run.</p>}
    <div className="mt-3 grid gap-3 lg:grid-cols-2">{(drafts || []).map(d => <article key={d.supplier_ref} className="rounded-lg border bg-card p-4" data-testid="followup-draft">
      <div className="flex items-start justify-between gap-2"><div><p className="font-semibold">{d.supplier_name}</p><p className="id-cell">{d.supplier_ref} · {d.invoices} invoice(s) · credit waiting ₹{d.credit_at_risk}</p></div>
        <Button size="sm" variant="outline" onClick={() => copy(d)}>{copied === d.supplier_ref ? "Copied" : "Copy message"}</Button></div>
      <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-muted/50 p-3 font-ui text-xs leading-relaxed">{d.message}</pre>
    </article>)}</div>
  </section>;
}
