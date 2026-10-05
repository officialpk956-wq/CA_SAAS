"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import { errorMessage, api, requestsApi, Registration, Period, Client } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { ArrowLeft, FileText, Plus, ArrowRight } from "lucide-react";

export default function ClientWorkspace() {
  const router = useRouter();
  const params = useParams();
  const clientId = params.client_id as string;

  const [client, setClient] = useState<Client | null>(null);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [periods, setPeriods] = useState<Record<string, Period[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // New Registration Form
  const [newGstin, setNewGstin] = useState("");
  const [newLegalName, setNewLegalName] = useState("");
  const [creatingReg, setCreatingReg] = useState(false);

  // New Period Form
  const [newPeriodId, setNewPeriodId] = useState("");
  const [creatingPeriodFor, setCreatingPeriodFor] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [clients, regs] = await Promise.all([
        api.getClients(),
        api.getRegistrations(clientId)
      ]);
      setClient(clients.find((c: Client) => c.id === clientId) || null);
      setRegistrations(regs);

      const periodsMap: Record<string, Period[]> = {};
      for (const reg of regs) {
        const p = await api.getPeriods(reg.id);
        periodsMap[reg.id] = p;
      }
      setPeriods(periodsMap);

    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [clientId]);

  useEffect(() => { const timer=setTimeout(()=>void loadData(),0); return()=>clearTimeout(timer); }, [loadData]);

  async function handleCreateRegistration(e: React.FormEvent) {
    e.preventDefault();
    if (!newGstin.trim() || !newLegalName.trim()) return;
    try {
      setCreatingReg(true);
      await api.createRegistration(clientId, { gstin: newGstin, legal_name: newLegalName });
      setNewGstin("");
      setNewLegalName("");
      await loadData();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setCreatingReg(false);
    }
  }

  async function handleCreatePeriod(regId: string) {
    if (!newPeriodId.trim()) return;
    try {
      setCreatingPeriodFor(regId);
      await api.createPeriod(regId, newPeriodId);
      setNewPeriodId("");
      await loadData();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setCreatingPeriodFor(null);
    }
  }

  if (loading) return <div className="p-10">Loading workspace...</div>;
  if (!client) return <div role="alert" className="p-10 red-ink">{error || "Client not found."}</div>;

  return (
    <div className="console-content w-full space-y-8">
      <div className="flex items-center gap-4">
        <Button variant="outline" size="icon" aria-label="Back to clients" onClick={() => router.push("/clients")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h2 className="font-display text-4xl">{client.name}</h2>
          <p className="text-muted-foreground mt-2">Manage registrations and open filing periods.</p>
        </div>
      </div>

      {error && <p role="alert" className="red-ink">{error}</p>}
      <ContactCard client={client} />
      <div className="grid md:grid-cols-[1fr_350px] gap-6">
        <div className="space-y-6">
          {registrations.length === 0 ? (
            <Card className="border-dashed">
              <CardContent className="py-10 text-center text-muted-foreground">
                No GST registrations found for this client.
              </CardContent>
            </Card>
          ) : (
            registrations.map(reg => (
              <Card key={reg.id} className="overflow-hidden">
                <CardHeader className="bg-muted/30 border-b pb-4">
                  <div className="flex justify-between items-start">
                    <div>
                      <CardTitle>{reg.legal_name}</CardTitle>
                      <CardDescription className="mt-1 font-mono text-primary">{reg.gstin}</CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="p-0">
                  <div className="p-4 border-b bg-muted/10 flex gap-4 items-end">
                     <div className="flex-1 space-y-2">
                       <Label>Open New Period (YYYY-MM)</Label>
                       <Input 
                         placeholder="2026-08" 
                         value={newPeriodId} 
                         onChange={(e) => setNewPeriodId(e.target.value)} 
                       />
                     </div>
                     <Button 
                       onClick={() => handleCreatePeriod(reg.id)}
                       disabled={creatingPeriodFor === reg.id || !newPeriodId}
                     >
                       <Plus className="mr-2 h-4 w-4" /> Create Period
                     </Button>
                  </div>
                  <div className="p-4 space-y-3">
                    <h4 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-4">Filing Periods</h4>
                    {periods[reg.id]?.length === 0 ? (
                      <p className="text-sm text-muted-foreground">No periods created.</p>
                    ) : (
                      periods[reg.id]?.map(period => (
                        <div 
                          key={period.id}
                          className="flex items-center justify-between p-3 border rounded-md hover:border-primary/50 cursor-pointer group transition-all"
                          role="link" tabIndex={0} onKeyDown={e => { if(e.key === "Enter") router.push(`/periods/${period.id}/workspace`); }}
                          onClick={() => router.push(`/periods/${period.id}/workspace`)}
                        >
                          <div className="flex items-center gap-3">
                            <div className="p-2 bg-primary/10 text-primary rounded">
                              <FileText className="h-4 w-4" />
                            </div>
                            <span className="font-medium">{period.period_code}</span>
                            <Badge variant={period.status === "open" ? "default" : "secondary"}>
                              {period.status}
                            </Badge>
                          </div>
                          <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary transition-colors" />
                        </div>
                      ))
                    )}
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>

        <div>
          <Card className="sticky top-6">
            <CardHeader>
              <CardTitle className="text-lg">Add Registration</CardTitle>
              <CardDescription>Create a fictional registration for this demo.</CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreateRegistration} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="gstin">Demo registration reference</Label>
                  <Input 
                    id="gstin" 
                    placeholder="DEMO-REG-001" 
                    value={newGstin}
                    onChange={(e) => setNewGstin(e.target.value.toUpperCase())}
                    disabled={creatingReg}
                    maxLength={80}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="legal_name">Legal Name</Label>
                  <Input 
                    id="legal_name" 
                    placeholder="Acme Corp Pvt Ltd" 
                    value={newLegalName}
                    onChange={(e) => setNewLegalName(e.target.value)}
                    disabled={creatingReg}
                  />
                </div>
                <Button type="submit" className="w-full" disabled={!newGstin || !newLegalName || creatingReg}>
                  {creatingReg ? "Saving..." : "Add Registration"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ContactCard({ client }: { client: Client }) {
  const [email, setEmail] = useState(client.contact_email || "");
  const [phone, setPhone] = useState(client.contact_phone || "");
  const [state, setState] = useState("");
  async function save() { setState(""); try { await requestsApi.setContact(client.id, email.trim(), phone.trim()); setState("Saved."); } catch (e) { setState(errorMessage(e)); } }
  return <div className="paper-card space-y-2" data-testid="client-contact">
    <p className="font-label text-[0.68rem] font-bold uppercase tracking-[0.16em] text-primary">Contact for reminders</p>
    <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
      <Input aria-label="Client email" type="email" placeholder="name@client.example" value={email} onChange={e => setEmail(e.target.value)} />
      <Input aria-label="Client WhatsApp number" placeholder="+91 98765 43210" value={phone} onChange={e => setPhone(e.target.value)} />
      <Button variant="outline" onClick={save}>Save contact</Button>
    </div>
    {state && <p className="text-xs text-muted-foreground">{state}</p>}
  </div>;
}