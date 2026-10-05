"use client";
import { useEffect, useState } from "react";
import { api, assistApi, errorMessage, Client, KnowledgeRule, LegalRuleEntry, RuleConfirmInput } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Eyebrow, StatusChip } from "@/components/status-chip";
import { AssistLabel, Hint } from "@/components/assist";

const TYPES = [["rcm_liability", "Reverse-charge liability"], ["other_liability", "Other liability"], ["itc_reversal", "ITC reversal"], ["other_credit", "Other credit"]];
const HEADS = ["igst", "cgst", "sgst", "cess"];
const FREQ: Record<string, string> = { monthly: "Every month", quarterly: "Every quarter", one_time: "One month only" };
const FIELD_LABEL: Record<string, string> = { day: "Day", month: "Month (1–12)", warn_days: "Warn this many days before", keywords: "Keywords (one per line)", rate_percent: "Rate % per year", due_day: "Due day of following month", per_day: "Per day (₹)", cap: "Maximum (₹)", steps: "Steps, in order (CREDIT>LIABILITY)", multiple: "Round to a multiple of (₹)", direction: "Direction", gstr1_day: "GSTR-1 due day (next month)", gstr3b_day: "GSTR-3B due day (next month)" };

function describe(r: KnowledgeRule) {
  const when = `${FREQ[r.frequency].toLowerCase()} from ${r.effective_from}${r.effective_to ? ` to ${r.effective_to}` : ""}`;
  return r.rule_kind === "reminder" ? `Reminder · ${when}` : `${r.adjustment_type?.replaceAll("_", " ")} · ${r.tax_head?.toUpperCase()} · ₹${r.amount} · ${when}`;
}

function ProposedRule({ rule, onDone }: { rule: KnowledgeRule; onDone: () => Promise<void> }) {
  const [form, setForm] = useState<RuleConfirmInput>({ rule_kind: rule.rule_kind, frequency: rule.frequency, adjustment_type: rule.adjustment_type || "", tax_head: rule.tax_head || "", amount: rule.amount || "", effective_from: rule.effective_from || "", effective_to: rule.effective_to || "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const reminder = form.rule_kind === "reminder";
  const firmWide = !rule.client_id;
  const complete = /^\d{4}-\d{2}$/.test(form.effective_from) && (reminder || (form.adjustment_type && form.tax_head && /^\d+\.\d{2}$/.test(form.amount || "")));
  async function act(action: () => Promise<unknown>) { setBusy(true); setError(""); try { await action(); await onDone(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  const payload = (): RuleConfirmInput => reminder ? { rule_kind: "reminder", frequency: form.frequency, effective_from: form.effective_from, effective_to: form.effective_to || null } : { ...form, effective_to: form.effective_to || null };
  return <article className="rounded-lg border border-dashed border-primary/60 bg-accent/30 p-4 space-y-3" data-testid="proposed-rule">
    <div className="flex flex-wrap items-center justify-between gap-2"><AssistLabel>Proposed from your note · {rule.client_name}</AssistLabel><StatusChip tone="action">Awaiting confirmation</StatusChip></div>
    <blockquote className="margin-note !m-0">{rule.note}</blockquote>
    <div className="grid gap-3 md:grid-cols-4">
      <label className="space-y-1 text-sm"><Eyebrow>Kind</Eyebrow><select aria-label="Rule kind" className="native-field" value={form.rule_kind} onChange={e => setForm({ ...form, rule_kind: e.target.value as RuleConfirmInput["rule_kind"] })}><option value="adjustment" disabled={firmWide}>Adjustment{firmWide ? " (needs a client)" : ""}</option><option value="reminder">Reminder — check before approval</option></select></label>
      <label className="space-y-1 text-sm"><Eyebrow>Frequency</Eyebrow><select aria-label="Rule frequency" className="native-field" value={form.frequency} onChange={e => setForm({ ...form, frequency: e.target.value })}>{Object.entries(FREQ).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
      <label className="space-y-1 text-sm"><Eyebrow>From period</Eyebrow><Input aria-label="Rule effective from" type="month" value={form.effective_from} onChange={e => setForm({ ...form, effective_from: e.target.value })} /></label>
      <label className="space-y-1 text-sm"><Eyebrow>Until (optional)</Eyebrow><Input aria-label="Rule effective to" type="month" value={form.effective_to || ""} onChange={e => setForm({ ...form, effective_to: e.target.value })} /></label>
      {!reminder && <>
        <label className="space-y-1 text-sm"><Eyebrow>Type</Eyebrow><select aria-label="Rule type" className="native-field" value={form.adjustment_type || ""} onChange={e => setForm({ ...form, adjustment_type: e.target.value })}><option value="">Choose…</option>{TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label className="space-y-1 text-sm"><Eyebrow>Tax head</Eyebrow><select aria-label="Rule tax head" className="native-field" value={form.tax_head || ""} onChange={e => setForm({ ...form, tax_head: e.target.value })}><option value="">Choose…</option>{HEADS.map(h => <option key={h} value={h}>{h.toUpperCase()}</option>)}</select></label>
        <label className="space-y-1 text-sm"><Eyebrow>Amount each time</Eyebrow><Input aria-label="Rule amount" className="font-figures text-right" placeholder="0.00" value={form.amount || ""} onChange={e => setForm({ ...form, amount: e.target.value })} /></label>
      </>}
    </div>
    {rule.missing && rule.missing.length > 0 && <p className="text-sm text-muted-foreground">Not found in the note — please fill: {rule.missing.map(m => m.replace("_", " ")).join(", ")}.</p>}
    {error && <p className="red-ink text-sm">{error}</p>}
    <div className="flex gap-2"><Button disabled={busy || !complete} onClick={() => act(() => assistApi.confirmRule(rule.id, payload()))}>Confirm rule</Button><Button variant="outline" disabled={busy} onClick={() => act(() => assistApi.closeRule(rule.id, "dismiss"))}>Dismiss</Button></div>
  </article>;
}

function LegalRuleCard({ entry, onDone }: { entry: LegalRuleEntry; onDone: () => Promise<void> }) {
  const initial = Object.fromEntries(Object.entries(entry.fields).map(([f, kind]) => { const v = entry.active?.value[f]; return [f, v === undefined ? (kind === "choice" ? entry.options?.[f]?.[0] ?? "" : "") : kind === "list" || kind === "steps" ? (v as string[]).join("\n") : String(v)]; }));
  const [values, setValues] = useState<Record<string, string>>(initial);
  const [source, setSource] = useState(entry.active?.source_reference || "");
  const [from, setFrom] = useState(entry.active?.effective_from || "");
  const [checked, setChecked] = useState(false);
  const [editing, setEditing] = useState(!entry.active);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function act(action: () => Promise<unknown>) { setBusy(true); setError(""); try { await action(); setChecked(false); await onDone(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  const filled = Object.values(values).every(v => v.trim()) && source.trim().length >= 3 && /^\d{4}-\d{2}$/.test(from) && checked;
  return <article className="rounded-lg border bg-card p-4 space-y-3" data-testid={`legal-${entry.key}`}>
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div><p className="font-semibold">{entry.title}</p><p className="text-sm text-muted-foreground">{entry.help}</p></div>
      {entry.active ? <StatusChip tone="done">Confirmed · from {entry.active.effective_from}</StatusChip> : <StatusChip tone="waiting">Not configured — check off</StatusChip>}
    </div>
    {entry.active && !editing && <div className="text-sm space-y-1">
      <p className="font-figures text-xs">{Object.entries(entry.active.value).map(([k, v]) => `${FIELD_LABEL[k] || k}: ${Array.isArray(v) ? v.join(entry.fields[k] === "steps" ? " → then " : ", ") : v}`).join(" · ")}</p>
      <p className="text-muted-foreground">Source: {entry.active.source_reference} · confirmed {new Date(entry.active.confirmed_at).toLocaleDateString("en-IN")}{entry.history.length > 1 ? ` · ${entry.history.length - 1} earlier version(s)` : ""}</p>
      <div className="flex gap-2 pt-1"><Button size="sm" variant="outline" onClick={() => setEditing(true)}>New version</Button><Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => assistApi.retireLegal(entry.key))}>Retire</Button></div>
    </div>}
    {editing && <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-3">{Object.entries(entry.fields).map(([f, kind]) => <label key={f} className="space-y-1 text-sm"><Eyebrow>{FIELD_LABEL[f] || f}</Eyebrow>
        {kind === "choice" ? <select aria-label={`${entry.title} ${f}`} className="native-field" value={values[f]} onChange={e => setValues({ ...values, [f]: e.target.value })}>{(entry.options?.[f] || []).map(o => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}</select> : kind === "list" || kind === "steps" ? <Textarea aria-label={`${entry.title} ${f}`} className={kind === "steps" ? "font-figures" : undefined} placeholder={kind === "steps" ? "One step per line, e.g. IGST>IGST" : undefined} value={values[f]} onChange={e => setValues({ ...values, [f]: e.target.value })} /> : <Input aria-label={`${entry.title} ${f}`} className="font-figures" inputMode="decimal" value={values[f]} onChange={e => setValues({ ...values, [f]: e.target.value })} />}</label>)}</div>
      <div className="grid gap-3 md:grid-cols-[1fr_180px]">
        <label className="space-y-1 text-sm"><Eyebrow>Source reference (section, notification or circular)</Eyebrow><Input aria-label={`${entry.title} source`} value={source} onChange={e => setSource(e.target.value)} /></label>
        <label className="space-y-1 text-sm"><Eyebrow>Applies from</Eyebrow><Input aria-label={`${entry.title} applies from`} type="month" value={from} onChange={e => setFrom(e.target.value)} /></label>
      </div>
      <label className="flex items-start gap-2 text-sm"><input type="checkbox" aria-label={`${entry.title} checked`} checked={checked} onChange={e => setChecked(e.target.checked)} />I have checked these values against current law and the source above.</label>
      {error && <p className="red-ink text-sm">{error}</p>}
      <div className="flex gap-2"><Button disabled={busy || !filled} onClick={() => act(() => assistApi.confirmLegal(entry.key, Object.fromEntries(Object.entries(values).map(([k, v]) => [k, entry.fields[k] === "list" || entry.fields[k] === "steps" ? v.split("\n") : v])), source, from))}>Confirm {entry.active ? "new version" : "rule"}</Button>
        {entry.active && <Button variant="outline" onClick={() => setEditing(false)}>Cancel</Button>}</div>
    </div>}
  </article>;
}

export default function Knowledge() {
  const [clients, setClients] = useState<Client[]>([]);
  const [rules, setRules] = useState<KnowledgeRule[] | null>(null);
  const [legal, setLegal] = useState<LegalRuleEntry[]>([]);
  const [clientId, setClientId] = useState("");
  const [note, setNote] = useState("");
  const [drafted, setDrafted] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  async function load() { const [c, r, l] = await Promise.all([api.getClients(), assistApi.rules(), assistApi.legalRules()]); setClients(c); setRules(r); setLegal(l.rules); setVersion(v => v + 1); }
  useEffect(() => { let active = true; const t = setTimeout(() => load().catch(e => { if (active) setError(errorMessage(e)); }), 0); return () => { active = false; clearTimeout(t); }; }, []);
  async function draft() {
    setBusy(true); setError("");
    try { const r = await assistApi.draftRule(clientId === "firm" ? null : clientId, note); setDrafted(d => ({ ...d, [r.id]: r.missing || [] })); setNote(""); await load(); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  const by = (s: string[]) => (rules || []).filter(r => s.includes(r.status));
  return <div className="console-content w-full space-y-6">
    <section className="paper-card space-y-3">
      <Eyebrow className="text-primary">Teach GST Helper a client quirk</Eyebrow>
      <h2 className="font-display text-3xl">Write it the way you&apos;d tell a junior.</h2>
      <Hint>Examples: “Rent to unregistered landlord: RCM ₹4,500 CGST monthly from Aug 2026” · “Quarterly RCM on legal fees Rs. 9,000.00 SGST from 2026-06 until Mar 2027” · “Confirm cash payment received before filing, from Aug 2026” (a reminder). Nothing is applied on its own: adjustments get an Apply button in each period; reminders must be acknowledged before approval.</Hint>
      <div className="grid gap-3 md:grid-cols-[260px_1fr_auto] md:items-end">
        <label className="space-y-1 text-sm"><Eyebrow>Client</Eyebrow><select aria-label="Rule client" className="native-field" value={clientId} onChange={e => setClientId(e.target.value)}><option value="">Choose…</option><option value="firm">All clients (firm-wide reminder)</option>{clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label className="space-y-1 text-sm"><Eyebrow>Note</Eyebrow><Textarea aria-label="Rule note" className="min-h-[44px]" maxLength={2000} value={note} onChange={e => setNote(e.target.value)} placeholder="What should always happen for this client?" /></label>
        <Button disabled={busy || !clientId || note.trim().length < 3} onClick={draft}>Draft rule</Button>
      </div>
      {error && <p className="red-ink text-sm">{error}</p>}
    </section>

    {!rules && !error && <p className="text-sm text-muted-foreground">Loading rules…</p>}
    {by(["proposed"]).length > 0 && <section className="space-y-3"><Eyebrow>Proposed — confirm to use</Eyebrow>{by(["proposed"]).map(r => <ProposedRule key={r.id} rule={{ ...r, missing: drafted[r.id] ?? r.missing }} onDone={load} />)}</section>}

    <section className="paper-card">
      <Eyebrow>Active rules</Eyebrow>
      {by(["active"]).length === 0 ? <p className="margin-note">No active rules yet.</p> :
        <ul className="mt-2 divide-y divide-[var(--ledger-line)]">{by(["active"]).map(r => <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3" data-testid="active-rule">
          <div><p className="font-semibold">{r.client_name} · {describe(r)}</p><p className="text-sm text-muted-foreground">{r.note}</p></div>
          <Button size="sm" variant="outline" disabled={busy} onClick={async () => { setBusy(true); try { await assistApi.closeRule(r.id, "retire"); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }}>Retire</Button>
        </li>)}</ul>}
    </section>

    <section className="space-y-3" aria-labelledby="legal-heading">
      <div><Eyebrow className="text-primary">Legal rule register · firm-wide</Eyebrow><h2 id="legal-heading" className="font-display text-3xl">Statutory values, confirmed by your CA</h2>
        <p className="max-w-3xl text-sm text-muted-foreground">GST Helper ships no statutory dates, rates or lists. Each check below stays off until someone enters the value, cites the source, and confirms it was checked against current law. Changing a value creates a new version; the old one stays in history.</p></div>
      <div className="grid gap-3 lg:grid-cols-2">{legal.map(e => <LegalRuleCard key={`${e.key}-${version}`} entry={e} onDone={load} />)}</div>
    </section>

    {by(["dismissed", "retired"]).length > 0 && <details className="paper-card"><summary className="cursor-pointer"><Eyebrow>Closed rules ({by(["dismissed", "retired"]).length})</Eyebrow></summary>
      <ul className="mt-2 space-y-1 text-sm">{by(["dismissed", "retired"]).map(r => <li key={r.id}><StatusChip tone="waiting">{r.status}</StatusChip> {r.client_name}: {r.note}</li>)}</ul></details>}
  </div>;
}
