"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { errorMessage, publicUploadApi, PublicLink } from "@/lib/api";
import { Button } from "@/components/ui/button";

// Client-facing upload page. No login: the link's token is the credential, checked by the API on every request.
export default function ClientUpload() {
  const token = useParams().token as string;
  const [link, setLink] = useState<PublicLink | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [done, setDone] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true; publicUploadApi.get(token).then(l => { if (active) setLink(l); }).catch(e => { if (active) setError(errorMessage(e)); }); return () => { active = false; }; }, [token]);
  async function send() {
    if (!file) return;
    setBusy(true); setError("");
    try { const r = await publicUploadApi.send(token, file); setDone(r.message); setFile(null); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return <main className="mx-auto max-w-lg space-y-5 p-6 pt-16">
    <div className="flex items-center gap-3"><span className="brand-seal !h-10 !w-10 border-primary text-primary">GH</span><div><p className="font-display text-2xl">GST Helper</p><p className="text-xs text-muted-foreground">Secure document upload</p></div></div>
    {error && <p role="alert" className="paper-card red-ink">{error}</p>}
    {!link && !error && <p className="text-sm text-muted-foreground">Checking your link…</p>}
    {link && !done && <section className="paper-card space-y-4">
      <p className="text-sm"><b>{link.firm}</b> asks <b>{link.client}</b> for the <b>{link.what}</b> for <span className="font-figures">{link.period_code}</span>.</p>
      <p className="text-xs text-muted-foreground">CSV file, up to 5 MiB. This link can be used {link.uses_left} more time(s) and expires {new Date(link.expires_at).toLocaleDateString("en-IN")}. Your accountant reviews every file before using it.</p>
      <input aria-label="File to upload" type="file" accept=".csv,text/csv" className="block w-full rounded border p-2" onChange={e => setFile(e.target.files?.[0] ?? null)} />
      <Button className="w-full" disabled={!file || busy} onClick={send}>{busy ? "Uploading…" : "Upload"}</Button>
    </section>}
    {done && <p data-testid="upload-done" className="paper-card">{done}</p>}
  </main>;
}
