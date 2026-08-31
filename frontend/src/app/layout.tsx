import type { Metadata } from "next";
import { IBM_Plex_Sans, Tektur } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { SiteNav } from "@/components/site-nav";
import { UserMenu } from "@/components/user-menu";

const tektur = Tektur({
  variable: "--font-tektur",
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
});

const plex = IBM_Plex_Sans({
  variable: "--font-plex",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://bsbr.pro"),
  title: {
    default: "BSBR — Beat Saber Brasil Ranking",
    template: "%s | BSBR",
  },
  description:
    "Ranking brasileiro de Beat Saber: jogadores, mapas rankeados e pontuações.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR" className={`${tektur.variable} ${plex.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-background font-sans text-foreground">
        <header className="sticky top-0 z-40 border-b border-border-subtle bg-background/80 backdrop-blur">
          <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4">
            <Link href="/" className="group flex items-center gap-2">
              <span className="flex h-8 w-8 items-center justify-center rounded bg-accent text-sm font-black tracking-tight text-white transition-shadow group-hover:glow-accent">
                BS
              </span>
              <span className="font-display text-lg font-bold tracking-tight text-glow-accent">
                BSBR
              </span>
            </Link>
            <div className="flex items-center gap-3">
              <SiteNav />
              <UserMenu />
            </div>
          </div>
        </header>
        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          {children}
        </main>
        <footer className="border-t border-border-subtle py-6">
          <p className="mx-auto w-full max-w-5xl px-4 text-sm text-muted">
            BSBR — Beat Saber Brasil Ranking · Projeto da Comunidade
          </p>
        </footer>
      </body>
    </html>
  );
}
