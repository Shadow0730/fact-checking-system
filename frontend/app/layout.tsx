import type { Metadata } from "next";
import Link from "next/link";
import HealthBadge from "@/components/HealthBadge";
import "./globals.css";

export const metadata: Metadata = {
  title: "Legal Fact Checker",
  description: "Checks AI-written legal drafts for fabricated citations, misquotes and unsupported claims.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="border-b border-[var(--border)] bg-[var(--panel)]">
          <div className="mx-auto max-w-7xl px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
            <Link href="/" className="font-bold tracking-tight text-lg">
              ⚖ Legal Fact Checker
            </Link>
            <nav className="flex gap-4 text-sm font-medium text-[var(--muted)]">
              <Link href="/" className="hover:text-[var(--fg)]">Check</Link>
              <Link href="/sources" className="hover:text-[var(--fg)]">Sources</Link>
              <Link href="/eval" className="hover:text-[var(--fg)]">Evaluation</Link>
            </nav>
            <div className="ml-auto">
              <HealthBadge />
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
