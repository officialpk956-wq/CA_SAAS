import { AlertTriangle, CheckCircle2, Clock3, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

export type Tone = "done" | "action" | "blocked" | "waiting";

const CLASS: Record<Tone, string> = { done: "status-done", action: "status-needs", blocked: "status-blocked", waiting: "status-waiting" };
const ICON = { done: CheckCircle2, action: AlertTriangle, blocked: ShieldAlert, waiting: Clock3 };

export function StatusChip({ tone, children, className }: { tone: Tone; children: React.ReactNode; className?: string }) {
  const Icon = ICON[tone];
  return <span data-tone={tone} className={cn("status-chip", CLASS[tone], className)}><Icon aria-hidden />{children}</span>;
}

export function Eyebrow({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("font-label text-[0.68rem] font-bold uppercase tracking-[0.16em]", className)}>{children}</span>;
}
