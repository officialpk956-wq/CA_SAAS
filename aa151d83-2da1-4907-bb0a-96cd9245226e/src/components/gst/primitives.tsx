import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Clock3, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

export function DemoPill() {
  return <span className="demo-pill">Synthetic demo — not for filing</span>;
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("font-label text-[0.68rem] font-bold uppercase tracking-[0.16em]", className)}>{children}</span>;
}

export function Money({ value, className }: { value: number; className?: string }) {
  return <span className={cn("font-figures block text-right tabular-nums", className)}>{value.toFixed(2)}</span>;
}

export function StatusChip({ children, tone = "waiting" }: { children: ReactNode; tone?: "done" | "needs" | "blocked" | "waiting" }) {
  const Icon = tone === "done" ? CheckCircle2 : tone === "blocked" ? ShieldAlert : tone === "needs" ? AlertTriangle : Clock3;
  return <span className={cn("status-chip", `status-${tone}`)}><Icon />{children}</span>;
}

export function PaperSection({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn("paper-card", className)}>{children}</section>;
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="py-14 text-center"><div className="mx-auto mb-4 h-12 w-12 rounded-full border border-dashed border-primary/50 p-3 font-display text-xl">∅</div><h3 className="font-display text-xl">{title}</h3><p className="mt-1 text-sm text-muted-foreground">{detail}</p></div>;
}