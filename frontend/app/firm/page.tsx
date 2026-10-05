"use client";
import { useEffect, useState } from "react";
import { authApi, errorMessage, firmApi, Firm, Me, Role } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Eyebrow, StatusChip } from "@/components/status-chip";

const ROLE_HELP: Record<Role, string> = {
  owner: "Everything, including people and firm settings",
  reviewer: "Approves worksheets and confirms legal values",
  preparer: "Prepares the month; cannot approve, reopen or confirm legal values",
};

export default function FirmPage() {
  const [firm, setFirm] = useState<Firm | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [form, setForm] = useState({ email: "", display_name: "", role: "preparer" as Role, initial_password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load() { const [f, m] = await Promise.all([firmApi.get(), authApi.me()]); setFirm(f); setMe(m); }
  useEffect(() => { const t = setTimeout(() => load().catch(e => setError(errorMessage(e))), 0); return () => clearTimeout(t); }, []);
  async function act(action: () => Promise<unknown>) { setBusy(true); setError(""); try { await action(); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  const owner = me?.role === "owner";
  if (!firm) return <div className="console-content">{error ? <p role="alert" className="red-ink">{error}</p> : <p className="text-sm text-muted-foreground">Loading the firm…</p>}</div>;

  return <div className="console-content w-full max-w-5xl space-y-6">
    {error && <p role="alert" className="red-ink">{error}</p>}
    {!owner && <p className="paper-card text-sm text-muted-foreground">Only an owner can change people or settings. You are a <b>{me?.role}</b>.</p>}

    <section className="paper-card space-y-3">
      <Eyebrow className="text-primary">Approval policy</Eyebrow>
      <label className="flex items-start gap-3 text-sm">
        <input type="checkbox" aria-label="Require a separate approver" disabled={!owner || busy} checked={firm.require_separate_approver} onChange={e => act(() => firmApi.settings(e.target.checked))} />
        <span><b>Require a separate approver.</b> The person who saved a draft worksheet cannot approve it; another owner or reviewer must. Recommended once the firm has two or more reviewers.</span>
      </label>
    </section>

    <section className="paper-card space-y-4">
      <Eyebrow className="text-primary">Team</Eyebrow>
      <div className="table-wrap"><table className="min-w-[640px]"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th></tr></thead>
        <tbody>{firm.users.map(u => <tr key={u.id} data-testid="team-member">
          <td><b>{u.display_name}</b>{u.id === me?.id && <span className="ml-2 text-xs text-muted-foreground">(you)</span>}</td>
          <td className="id-cell">{u.email}</td>
          <td><select aria-label={`Role for ${u.email}`} className="native-field py-1" disabled={!owner || busy} value={u.role} title={ROLE_HELP[u.role]} onChange={e => act(() => firmApi.changeUser(u.id, { role: e.target.value as Role }))}>{(["owner", "reviewer", "preparer"] as Role[]).map(r => <option key={r} value={r}>{r}</option>)}</select></td>
          <td className="flex items-center gap-2">{u.is_active ? <StatusChip tone="done">Active</StatusChip> : <StatusChip tone="waiting">Disabled</StatusChip>}
            {owner && u.id !== me?.id && <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => firmApi.changeUser(u.id, { is_active: !u.is_active }))}>{u.is_active ? "Disable" : "Enable"}</Button>}</td>
        </tr>)}</tbody></table></div>
      <ul className="text-xs text-muted-foreground">{(Object.keys(ROLE_HELP) as Role[]).map(r => <li key={r}><b>{r}</b> — {ROLE_HELP[r]}</li>)}</ul>
    </section>

    {owner && <section className="paper-card space-y-3">
      <Eyebrow className="text-primary">Add a person</Eyebrow>
      <div className="grid gap-3 md:grid-cols-2">
        <label className="space-y-1 text-sm"><Eyebrow>Name</Eyebrow><Input aria-label="New member name" value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} /></label>
        <label className="space-y-1 text-sm"><Eyebrow>Email</Eyebrow><Input aria-label="New member email" type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} /></label>
        <label className="space-y-1 text-sm"><Eyebrow>Role</Eyebrow><select aria-label="New member role" className="native-field" value={form.role} onChange={e => setForm({ ...form, role: e.target.value as Role })}>{(["preparer", "reviewer", "owner"] as Role[]).map(r => <option key={r} value={r}>{r}</option>)}</select></label>
        <label className="space-y-1 text-sm"><Eyebrow>Initial password (min 10 characters)</Eyebrow><Input aria-label="New member initial password" type="password" autoComplete="new-password" value={form.initial_password} onChange={e => setForm({ ...form, initial_password: e.target.value })} /></label>
      </div>
      <p className="text-xs text-muted-foreground">Share the initial password with them privately; they can change it with <code>scripts/firm_admin.py set-password</code>. It is never shown again or logged.</p>
      <Button disabled={busy || !form.email.trim() || !form.display_name.trim() || form.initial_password.length < 10} onClick={() => act(async () => { await firmApi.addUser(form); setForm({ email: "", display_name: "", role: "preparer", initial_password: "" }); })}>Add to firm</Button>
    </section>}
  </div>;
}
