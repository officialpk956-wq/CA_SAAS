"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { errorMessage, api, Client } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Eyebrow } from "@/components/status-chip";
import { ArrowRight, Plus, Search } from "lucide-react";

export default function Clients() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [newClientName, setNewClientName] = useState("");
  const [creating, setCreating] = useState(false);

  async function loadClients() {
    try { setLoading(true); setClients(await api.getClients()); }
    catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  }
  useEffect(() => { const t = setTimeout(() => void loadClients(), 0); return () => clearTimeout(t); }, []);

  async function handleCreateClient(e: React.FormEvent) {
    e.preventDefault();
    if (!newClientName.trim()) return;
    try { setCreating(true); await api.createClient({ name: newClientName }); setNewClientName(""); await loadClients(); }
    catch (e) { setError(errorMessage(e)); }
    finally { setCreating(false); }
  }

  const shown = clients.filter(c => c.name.toLowerCase().includes(query.toLowerCase()));
  return <div className="console-content w-full space-y-6">
    {error && <p role="alert" className="red-ink">{error}</p>}
    <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
      <section className="space-y-5">
        <label className="relative block max-w-md"><span className="sr-only">Search clients</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search client folders…" value={query} onChange={e => setQuery(e.target.value)} />
        </label>
        {loading ? <p className="text-sm text-muted-foreground">Opening the cabinet…</p>
          : !clients.length ? <div className="paper-card py-12 text-center"><h3 className="font-display text-2xl">The cabinet is empty</h3><p className="mt-1 text-sm text-muted-foreground">Add a fictional client to open its first folder.</p></div>
          : !shown.length ? <p className="text-sm text-muted-foreground">No folders match “{query}”.</p>
          : <div className="grid gap-5 md:grid-cols-2">
            {shown.map(client => <Link key={client.id} href={`/clients/${client.id}`} className="folder-card block">
              <div className="folder-tab">{client.id.slice(0, 8).toUpperCase()}</div>
              <div className="folder-body">
                <Eyebrow className="text-muted-foreground">Client folder</Eyebrow>
                <h2 className="mt-1 truncate font-display text-2xl">{client.name}</h2>
                <div className="mt-4 flex items-center justify-between text-sm">
                  <span className="font-figures text-xs text-muted-foreground">Opened {new Date(client.created_at).toLocaleDateString("en-IN")}</span>
                  <span className="inline-flex items-center gap-1 font-medium text-primary">Open folder <ArrowRight className="h-4 w-4" /></span>
                </div>
              </div>
            </Link>)}
          </div>}
      </section>
      <aside className="paper-card h-fit">
        <Eyebrow className="text-primary">New folder</Eyebrow>
        <h2 className="mt-1 font-display text-2xl">Add a client</h2>
        <form onSubmit={handleCreateClient} className="mt-4 space-y-3">
          <div className="space-y-1.5"><Label htmlFor="name">Client name</Label><Input id="name" placeholder="Fictional Client A" value={newClientName} onChange={e => setNewClientName(e.target.value)} disabled={creating} /></div>
          <Button type="submit" className="w-full" disabled={!newClientName.trim() || creating}>{creating ? "Creating…" : <><Plus className="mr-2 h-4 w-4" />Add Client</>}</Button>
        </form>
      </aside>
    </div>
  </div>;
}
