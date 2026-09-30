import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = {
  title: "GST Helper",
  description: "Monthly GST preparation, reconciliation and approval — synthetic demo",
};

// Applies the saved or system theme before first paint to avoid a light flash in dark mode.
const themeScript = `try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.classList.add('dark')}catch(e){}`;
// One family per role: display, UI, figures, labels, board tiles, stamps, margin notes.
const fonts = "https://fonts.googleapis.com/css2?family=Caveat:wght@400..700&family=Chivo+Mono:wght@400;600&family=Fraunces:opsz,wght,SOFT,WONK@9..144,400..800,0..100,0..1&family=Instrument+Sans:wght@400..700&family=JetBrains+Mono:wght@400;600&family=Space+Grotesk:wght@500;700&family=Special+Elite&display=swap";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link rel="stylesheet" href={fonts} />
      </head>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
