"use client";
import { useEffect, useState } from "react";
import { authApi, errorMessage, Me } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Eyebrow } from "@/components/status-chip";

export default function Account() {
  const [me, setMe] = useState<Me | null>(null);
  const [form, setForm] = useState({ current: "", next: "", repeat: "" });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { let active = true; authApi.me().then(m => { if (active) setMe(m); }).catch(() => {}); return () => { active = false; }; }, []);
  const mismatch = form.repeat.length > 0 && form.next !== form.repeat;
  async function change() {
    setBusy(true); setError(""); setMessage("");
    try { const r = await authApi.changePassword(form.current, form.next); setForm({ current: "", next: "", repeat: "" }); setMessage(`Password changed. ${r.other_sessions_ended} other session(s) were signed out; this one stays signed in.`); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <div className="console-content w-full max-w-xl space-y-5">
    {me && <p className="text-sm text-muted-foreground">Signed in as <b>{me.email}</b> · {me.role} · {me.firm}</p>}
    <section className="paper-card space-y-3">
      <Eyebrow className="text-primary">Change password</Eyebrow>
      <label className="block space-y-1 text-sm"><Eyebrow>Current password</Eyebrow><Input aria-label="Current password" type="password" autoComplete="current-password" value={form.current} onChange={e => setForm({ ...form, current: e.target.value })} /></label>
      <label className="block space-y-1 text-sm"><Eyebrow>New password (at least 10 characters)</Eyebrow><Input aria-label="New password" type="password" autoComplete="new-password" value={form.next} onChange={e => setForm({ ...form, next: e.target.value })} /></label>
      <label className="block space-y-1 text-sm"><Eyebrow>Repeat new password</Eyebrow><Input aria-label="Repeat new password" type="password" autoComplete="new-password" value={form.repeat} onChange={e => setForm({ ...form, repeat: e.target.value })} /></label>
      {mismatch && <p className="red-ink text-xs">The new passwords do not match.</p>}
      {error && <p role="alert" className="red-ink text-sm">{error}</p>}
      {message && <p data-testid="password-changed" className="text-sm">{message}</p>}
      <Button disabled={busy || !form.current || form.next.length < 10 || form.next !== form.repeat} onClick={change}>Change password</Button>
      <p className="text-xs text-muted-foreground">Forgot it? Ask a firm owner to set a temporary password from Firm &amp; team.</p>
    </section>
  </div>;
}
