"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { BookOpenText, LockKeyhole } from "lucide-react";
import { authApi, errorMessage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// Only same-site paths are allowed as a post-login destination (no open redirects).
function safeNext(value: string | null) {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\") && !value.startsWith("/login") ? value : "/";
}

function LoginForm() {
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try { await authApi.login(email, password); setPassword(""); window.location.assign(next); }
    catch (err) { setError(errorMessage(err)); setBusy(false); }
  }
  return <form onSubmit={submit} className="paper-card w-full max-w-md space-y-5 p-8" aria-labelledby="login-heading">
    <div className="flex items-center gap-3">
      <span className="grid h-11 w-11 place-items-center rounded-full border border-primary/60 text-primary"><BookOpenText className="h-5 w-5" /></span>
      <div><p className="font-display text-2xl leading-none">GST Helper</p><p className="text-xs text-muted-foreground">Monthly work console</p></div>
    </div>
    <div><h1 id="login-heading" className="font-display text-3xl">Sign in to your firm</h1>
      <p className="mt-1 text-sm text-muted-foreground">Access is limited to your CA firm&apos;s accounts.</p></div>
    <div className="space-y-1.5"><Label htmlFor="email">Email</Label><Input id="email" type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></div>
    <div className="space-y-1.5"><Label htmlFor="password">Password</Label><Input id="password" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></div>
    {error && <p role="alert" className="red-ink text-sm">{error}</p>}
    <Button type="submit" className="w-full" disabled={busy || !email || !password}><LockKeyhole className="mr-2 h-4 w-4" />{busy ? "Signing in…" : "Sign in"}</Button>
    <p className="text-center text-[11px] text-muted-foreground">Synthetic demo — not for filing. Sessions end after 12 hours or when you sign out.</p>
  </form>;
}

export default function LoginPage() {
  return <div className="flex min-h-screen w-full items-center justify-center p-4"><Suspense fallback={null}><LoginForm /></Suspense></div>;
}
