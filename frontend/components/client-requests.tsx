"use client";
import { useCallback, useEffect, useState } from "react";
import { errorMessage, ReminderDraft, requestsApi, UploadLinkView } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Eyebrow, StatusChip, Tone } from "@/components/status-chip";

const STATE_TONE: Record<UploadLinkView["state"], Tone> = { active: "done", used_up: "waiting", expired: "waiting", revoked: "blocked" };

/** Upload links for this period and a reminder draft. Nothing is sent from the app. */
export function ClientRequests({ periodId }: { periodId: string }) {
  const [links, setLinks] = useState<UploadLinkView[]>([]);
  const [fresh, setFresh] = useState<string | null>(null);
  const [draft, setDraft] = useState<ReminderDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => setLinks(await requestsApi.links(periodId)), [periodId]);
  useEffect(() => { const t = setTimeout(() => load().catch(() => {}), 0); return () => clearTimeout(t); }, [load]);
  async function act(action: () => Promise<void>) { setBusy(true); setError(""); try { await action(); await load(); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  const origin = typeof window === "undefined" ? "" : window.location.origin;

  return <section data-testid="client-requests" className="paper-card space-y-3">
    <Eyebrow className="text-primary">Client requests</Eyebrow>
    <p className="text-sm text-muted-foreground">Send the client a link to upload files themselves (no login; expires; you review before committing), or draft a reminder for what is still missing. GST Helper never sends messages: drafts open in your own mail or WhatsApp.</p>
    {error && <p role="alert" className="red-ink text-sm">{error}</p>}
    <div className="flex flex-wrap gap-2">
      {(["sales", "purchase"] as const).map(kind => <Button key={kind} size="sm" variant="outline" disabled={busy} onClick={() => act(async () => { const l = await requestsApi.createLink(periodId, kind); setFresh(`${origin}${l.path}`); })}>New {kind} upload link</Button>)}
      <Button size="sm" disabled={busy} onClick={() => act(async () => setDraft(await requestsApi.reminder(periodId, origin)))}>Draft reminder</Button>
    </div>
    {fresh && <div className="rounded border border-dashed p-2 text-sm"><p className="text-xs text-muted-foreground">Copy it now — it is shown only once:</p><p data-testid="fresh-link" className="font-figures break-all">{fresh}</p>
      <Button size="sm" variant="outline" className="mt-1" onClick={() => navigator.clipboard?.writeText(fresh)}>Copy link</Button></div>}
    {draft && <div data-testid="reminder-draft" className="space-y-2 rounded border border-dashed p-3 text-sm">
      {draft.body ? <>
        <p><b>{draft.subject}</b></p>
        <pre className="whitespace-pre-wrap font-ui text-sm">{draft.body}</pre>
        <div className="flex flex-wrap gap-2">
          {draft.mailto && <a className="rounded-md border bg-card px-3 py-1.5 text-sm" href={draft.mailto}>Open in email{draft.to_email ? "" : " (no address saved)"}</a>}
          {draft.whatsapp && <a className="rounded-md border bg-card px-3 py-1.5 text-sm" href={draft.whatsapp} target="_blank" rel="noopener noreferrer">Open in WhatsApp{draft.to_phone ? "" : " (no number saved)"}</a>}
          <Button size="sm" variant="outline" onClick={() => navigator.clipboard?.writeText(draft.body || "")}>Copy text</Button>
        </div>
      </> : null}
      <p className="text-xs text-muted-foreground">{draft.note}</p>
    </div>}
    {links.length > 0 && <ul className="space-y-1 text-sm">{links.map(l => <li key={l.id} data-testid="upload-link" className="flex flex-wrap items-center gap-2">
      <StatusChip tone={STATE_TONE[l.state]}>{l.state.replace("_", " ")}</StatusChip><span>{l.kind} link · used {l.uses}/{l.max_uses} · expires {new Date(l.expires_at).toLocaleDateString("en-IN")}</span>
      {l.state === "active" && <Button size="sm" variant="outline" disabled={busy} onClick={() => act(async () => { await requestsApi.revoke(l.id); })}>Revoke</Button>}
    </li>)}</ul>}
  </section>;
}
