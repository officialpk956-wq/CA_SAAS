"use client";
import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { Eyebrow } from "@/components/status-chip";

/** Right-side sheet for evidence and review forms. Escape or the Close button closes it. */
export function Drawer({ open, onClose, eyebrow, title, description, children, testId }: {
  open: boolean; onClose: () => void; eyebrow?: string; title: string; description?: string; children: React.ReactNode; testId?: string;
}) {
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return <div className="fixed inset-0 z-50 flex justify-end">
    <button aria-label="Close panel" tabIndex={-1} className="absolute inset-0 bg-black/40" onClick={onClose} />
    <div ref={panel} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} data-testid={testId}
      className="relative flex h-full w-full max-w-3xl flex-col overflow-y-auto border-l bg-card shadow-2xl outline-none">
      <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b bg-card px-6 py-4">
        <div className="min-w-0">{eyebrow && <Eyebrow className="text-primary">{eyebrow}</Eyebrow>}<h2 className="font-display text-3xl leading-tight">{title}</h2>{description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}</div>
        <button type="button" onClick={onClose} aria-label="Close" className="grid h-9 w-9 shrink-0 place-items-center rounded-md border hover:bg-muted"><X className="h-4 w-4" /></button>
      </div>
      <div className="space-y-6 px-6 py-6">{children}</div>
    </div>
  </div>;
}
