import { Link, useRouterState } from "@tanstack/react-router";
import { useState, type ReactNode } from "react";
import { FileCode2, Menu, ScanSearch, ShieldCheck, Sparkles, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCheckout } from "@/lib/checkout/store";
import { API_BASE_URL } from "@/lib/checkout/api";

const HomeIcon = () => (
  <svg
    viewBox="0 0 24 24"
    className="h-4 w-4"
    fill="none"
    stroke="currentColor"
    strokeWidth="2.2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <polyline points="9 22 9 12 15 12 15 22" />
  </svg>
);

const NAV = [
  { to: "/", label: "Home", icon: HomeIcon },
  { to: "/audit", label: "Audit", icon: ScanSearch },
  { to: "/recommendations", label: "Recommendations", icon: Sparkles },
  { to: "/fix", label: "Fix", icon: FileCode2 },
  { to: "/proof", label: "Proof", icon: ShieldCheck },
] as const;

function Brand({ className = "" }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
        <svg
          viewBox="0 0 24 24"
          className="h-5 w-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 12l6 6L21 6" />
        </svg>
      </div>
      <span className="font-display text-[18px] font-medium tracking-tight text-foreground">
        CheckoutPilot
      </span>
    </div>
  );
}

function ModeToggle() {
  const { mode, setMode } = useCheckout();
  return (
    <div className="flex items-center gap-1 rounded-xl border border-border bg-card p-1">
      {(["demo", "live"] as const).map((m) => (
        <button
          key={m}
          onClick={() => m !== mode && setMode(m)}
          className={cn(
            "rounded-md py-1 px-2.5 text-xs font-medium transition",
            mode === m
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {m}
        </button>
      ))}
    </div>
  );
}

function NavTabs() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const { scan, fix, verify } = useCheckout();
  const done: Record<string, boolean> = {
    "/audit": scan.phase === "success",
    "/recommendations": fix.phase !== "idle",
    "/fix": fix.phase === "success",
    "/proof": verify.phase === "success",
  };
  return (
    <div className="flex items-center gap-1">
      {NAV.map(({ to, label, icon: Icon }) => {
        const active = path === to || path.startsWith(to + "/");
        return (
          <Link
            key={to}
            to={to}
            className={cn(
              "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition",
              active
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            <Icon className="h-4 w-4" />
            <span>{label}</span>
            {done[to] && <span className="h-1.5 w-1.5 rounded-full bg-success"></span>}
          </Link>
        );
      })}
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const { mode } = useCheckout();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const isLanding = path === "/";

  return (
    <div className="min-h-screen bg-background">
      {!isLanding && (
        <header className="border-b border-sidebar sticky top-0 z-20 bg-background/90 backdrop-blur-sm">
          <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-8">
              <Link to="/">
                <Brand />
              </Link>
              <NavTabs />
            </div>
            <div className="flex items-center gap-4">
              <ModeToggle />
              <button
                aria-label="Open menu"
                onClick={() => setOpen(true)}
                className="md:hidden btn-outline h-8 w-8 p-0"
              >
                <Menu className="h-4 w-4" />
              </button>
            </div>
          </div>
        </header>
      )}

      {!isLanding && open && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-foreground/10" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 right-0 flex w-72 flex-col bg-sidebar p-4 shadow-xl animate-in slide-in-from-right">
            <div className="flex items-center justify-between mb-4">
              <Link to="/">
                <Brand />
              </Link>
              <button
                aria-label="Close menu"
                onClick={() => setOpen(false)}
                className="text-muted-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <NavTabs />
            <div className="mt-6">
              <ModeToggle />
            </div>
          </div>
        </div>
      )}

      <main>
        {!isLanding && mode === "demo" && (
          <div className="max-w-6xl mx-auto px-4 py-2">
            <div className="demo-banner">
              <span className="font-semibold">Demo Mode</span> — replays real results recorded on our
              demo store (Inkwell &amp; Co., localhost:8101). No new scan is run.
            </div>
          </div>
        )}
        <div className="mx-auto max-w-6xl px-4 py-6 md:px-8 md:py-10">{children}</div>
      </main>
    </div>
  );
}
