import { createFileRoute } from "@tanstack/react-router";
import { GstHelperApp } from "@/components/gst/app-shell";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "GST Helper — Monthly GST Work Console" },
      { name: "description", content: "A synthetic frontend prototype for monthly GST review, reconciliation and approval workflows." },
      { property: "og:title", content: "GST Helper — Monthly GST Work Console" },
      { property: "og:description", content: "A ledger-inspired monthly GST work console for small Indian CA firms." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  return <GstHelperApp />;
}
