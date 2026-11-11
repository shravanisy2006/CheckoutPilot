/**
 * Guidance for first-time visitors (and judges): where am I, what do I do next?
 *
 * - GuideBar: a 4-step tracker under the header + one "do this now" line + a button for it.
 * - HowItWorksDialog: the whole flow on one screen; opens by itself on the first visit.
 * - useStepToasts: a pop-up when a step finishes, with a button to the next step.
 * - EXAMPLE_STORES: stores anyone can scan (they run on the CheckoutPilot server).
 */
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  CircleHelp,
  FileCode2,
  Loader2,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCheckout } from "@/lib/checkout/store";
import { cn } from "@/lib/utils";

export const EXAMPLE_STORES = [
  {
    url: "http://localhost:8101",
    name: "Inkwell & Co.",
    label: "Old checkout (PayPal SDK v5)",
    hint: "Has the problems we fix: try this one first",
  },
  {
    url: "http://localhost:8102",
    name: "Inkwell & Co. upgraded",
    label: "After the upgrade (SDK v6)",
    hint: "Scan it to compare the health score",
  },
] as const;

/* ------------------------------------------------------------ storage --- */
// Browser storage can be missing or blocked (private windows, previews): never let it break the page.
export function readPref(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
export function writePref(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

/* ---------------------------------------------------------- next step --- */
type StepKey = "scan" | "choose" | "fix" | "prove";
const STEPS: { key: StepKey; label: string; to: "/audit" | "/recommendations" | "/fix" | "/proof"; icon: typeof ScanSearch }[] = [
  { key: "scan", label: "Scan a store", to: "/audit", icon: ScanSearch },
  { key: "choose", label: "Choose fixes", to: "/recommendations", icon: Sparkles },
  { key: "fix", label: "Review the fix", to: "/fix", icon: FileCode2 },
  { key: "prove", label: "Prove it", to: "/proof", icon: ShieldCheck },
];

type Route = (typeof STEPS)[number]["to"];

export interface NextStep {
  current: StepKey;
  done: Record<StepKey, boolean>;
  busy: boolean;
  text: string;
  cta?: { label: string; to: Route } | undefined;
}

/** Pure: what the visitor should do next, from the app state and the page they are on. */
export function nextStep(
  s: { scan: string; fix: string; verify: string; issues: number; selected: number; passed?: boolean | undefined },
  path: string,
  mode: "demo" | "live",
): NextStep {
  const done = {
    scan: s.scan === "success",
    choose: s.fix !== "idle",
    fix: s.fix === "success",
    prove: s.verify === "success",
  };
  // No button for the page the visitor is already on.
  const go = (label: string, to: Route): NextStep["cta"] => (path === to ? undefined : { label, to });

  if (s.scan === "running")
    return { current: "scan", done, busy: true, text: mode === "live" ? "Scanning the store like a shopper would (about 1 minute)..." : "Replaying the recorded scan..." };
  if (s.scan !== "success")
    return {
      current: "scan",
      done,
      busy: false,
      text:
        s.scan === "error"
          ? "The scan failed. Check the address, or try our example store below the box."
          : "Paste your store's address, or click an example store, then press Start scan.",
      cta: go("Go to scan", "/audit"),
    };
  if (s.fix === "idle")
    return {
      current: "choose",
      done,
      busy: false,
      text:
        path === "/recommendations"
          ? `Tick the fixes you want (${s.selected} selected), then press Generate fix.`
          : `Scan done: ${s.issues} issue${s.issues === 1 ? "" : "s"} found. Next, choose which ones CheckoutPilot should fix.`,
      cta: go("Choose fixes", "/recommendations"),
    };
  if (s.fix === "running")
    return { current: "fix", done, busy: true, text: "The code agent is writing the upgrade and test-driving it in a browser..." };
  if (s.fix === "error")
    return { current: "fix", done, busy: false, text: "The fix could not be made. Go back, change the selection and try again.", cta: go("Choose fixes", "/recommendations") };
  if (s.verify === "idle")
    return {
      current: "fix",
      done,
      busy: false,
      text:
        path === "/fix"
          ? "Read the changes file by file. Nothing is applied yet. Then press Verify in Sandbox."
          : "The fix is ready. Review the code changes, then prove it works.",
      cta: go("Review the fix", "/fix"),
    };
  if (s.verify === "running")
    return {
      current: "prove",
      done,
      busy: true,
      text:
        mode === "live"
          ? "Paying with a PayPal Sandbox account on the old store, then on the fixed copy (1-2 minutes)..."
          : "Replaying the recorded Sandbox payments...",
    };
  if (s.verify === "error")
    return { current: "prove", done, busy: false, text: "The verification could not run. Wait a moment and press Retry.", cta: go("See proof", "/proof") };
  return {
    current: "prove",
    done,
    busy: false,
    text: s.passed
      ? "All done: the fixed checkout took a Sandbox payment. Download the PDF report, or scan another store."
      : "The fixed checkout did not pass. Nothing should be approved; see the evidence for why.",
    cta: path === "/proof" ? { label: "Scan another store", to: "/audit" } : { label: "See proof", to: "/proof" },
  };
}

function useNextStep(): NextStep {
  const { scan, fix, verify, selected, mode } = useCheckout();
  const path = useRouterState({ select: (s) => s.location.pathname });
  return nextStep(
    {
      scan: scan.phase,
      fix: fix.phase,
      verify: verify.phase,
      issues: scan.data?.issues.length ?? 0,
      selected: selected.length,
      passed: verify.data?.passed,
    },
    path,
    mode,
  );
}

/* ------------------------------------------------------------ GuideBar --- */
export function GuideBar({ onHelp }: { onHelp: () => void }) {
  const step = useNextStep();
  const currentIndex = STEPS.findIndex((s) => s.key === step.current);
  const [hidden, setHidden] = useState(false);
  useEffect(() => setHidden(readPref("cp_guide_hidden") === "1"), []);

  if (hidden)
    return (
      <div className="max-w-6xl mx-auto px-4 pt-2 flex justify-end">
        <button
          className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
          onClick={() => {
            setHidden(false);
            writePref("cp_guide_hidden", "0");
          }}
        >
          Show step-by-step tips
        </button>
      </div>
    );

  return (
    <div className="max-w-6xl mx-auto px-4 pt-3" data-testid="guide-bar">
      <div className="rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <ol className="flex flex-wrap items-center gap-x-1 gap-y-2 text-xs" aria-label="Progress">
            {STEPS.map((s, i) => {
              const isDone = step.done[s.key] && (i < currentIndex || step.done.prove);
              const isCurrent = i === currentIndex && !isDone;
              return (
                <li key={s.key} className="flex items-center gap-1">
                  <Link
                    to={s.to}
                    className={cn(
                      "flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium transition",
                      isCurrent && "bg-primary text-primary-foreground",
                      isDone && "text-success",
                      !isCurrent && !isDone && "text-muted-foreground hover:text-foreground",
                    )}
                    aria-current={isCurrent ? "step" : undefined}
                  >
                    {isDone ? (
                      <Check className="h-3.5 w-3.5" />
                    ) : (
                      <span className="font-mono">{i + 1}</span>
                    )}
                    {s.label}
                  </Link>
                  {i < STEPS.length - 1 && <ArrowRight className="h-3 w-3 text-muted-foreground/60" />}
                </li>
              );
            })}
          </ol>
          <div className="flex items-center gap-2 shrink-0">
            <button onClick={onHelp} className="btn-outline h-8 px-3 text-xs">
              <CircleHelp className="h-3.5 w-3.5" /> How it works
            </button>
            <button
              aria-label="Hide tips"
              title="Hide tips"
              onClick={() => {
                setHidden(true);
                writePref("cp_guide_hidden", "1");
              }}
              className="text-muted-foreground hover:text-foreground p-1"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-t border-border pt-2">
          <p className="text-sm text-foreground flex items-center gap-2" data-testid="guide-next">
            {step.busy ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />
            ) : (
              <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground shrink-0">
                Next
              </span>
            )}
            <span>{step.text}</span>
          </p>
          {step.cta && !step.busy && (
            <Link to={step.cta.to} className="btn-primary h-8 px-3 text-xs shrink-0">
              {step.cta.label} <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------- How it works dialog --- */
const HOW = [
  {
    icon: ScanSearch,
    title: "1. Scan",
    you: "Paste a store's address (or click our example store) and press Start scan.",
    we: "A browser visits the product, cart and checkout pages on desktop and mobile. Rule checks and Gemini vision list the PayPal problems, and each gets an impact score with its source.",
  },
  {
    icon: Sparkles,
    title: "2. Choose fixes",
    you: "Tick the recommendations you want. Fixable ones are pre-selected.",
    we: "Ranks the fixes by impact and marks which ones the code agent can make.",
  },
  {
    icon: FileCode2,
    title: "3. Review the fix",
    you: "Read the code changes file by file. Nothing is applied to the store.",
    we: "The code agent upgrades a copy of the store (PayPal SDK v5 to v6, PayPal on the cart, PayPal first on mobile), then test-drives the copy in a browser.",
  },
  {
    icon: ShieldCheck,
    title: "4. Prove it",
    you: "Press Verify in Sandbox and wait 1-2 minutes. Download the PDF report.",
    we: "Pays with a PayPal Sandbox test account on the old store and on the fixed copy, and checks both orders with PayPal's Orders API.",
  },
];

export function HowItWorksDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { mode, setMode } = useCheckout();
  const navigate = useNavigate();
  const start = (m: "demo" | "live") => {
    if (m !== mode) setMode(m);
    onOpenChange(false);
    navigate({ to: "/audit" });
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto gap-3">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl font-normal">How CheckoutPilot works</DialogTitle>
          <DialogDescription>
            Find what is costing a store sales at PayPal checkout, fix it, and prove the fix with a real PayPal
            Sandbox payment. Four steps, about 3 minutes.
          </DialogDescription>
        </DialogHeader>

        <ol className="space-y-2">
          {HOW.map((h) => (
            <li key={h.title} className="flex gap-3 rounded-lg border border-border px-3 py-2">
              <h.icon className="h-5 w-5 shrink-0 text-muted-foreground mt-0.5" />
              <div className="text-[13px] leading-snug">
                <p className="font-medium text-foreground">{h.title}</p>
                <p className="mt-1">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mr-1">You</span>
                  {h.you}
                </p>
                <p className="mt-0.5 text-muted-foreground">
                  <span className="text-[10px] font-semibold uppercase tracking-wider mr-1">CheckoutPilot</span>
                  {h.we}
                </p>
              </div>
            </li>
          ))}
        </ol>

        <div className="grid gap-2 sm:grid-cols-2 text-[13px] leading-snug">
          <div className="rounded-lg bg-muted/60 p-3">
            <p className="font-medium">Demo or Live?</p>
            <p className="mt-1 text-muted-foreground">
              <b className="text-foreground">Demo</b> replays a real recorded run instantly.{" "}
              <b className="text-foreground">Live</b> runs everything for real, including the Sandbox payments. Switch
              with <span className="font-mono">demo | live</span> at the top right.
            </p>
          </div>
          <div className="rounded-lg bg-muted/60 p-3">
            <p className="font-medium">Which store can I scan?</p>
            <p className="mt-1 text-muted-foreground">
              <b className="text-foreground">Any public store</b> for the scan. Fix and Prove need the store's code, so
              they run on our example store, <b className="text-foreground">Inkwell &amp; Co.</b> (one click on the
              scan page).
            </p>
          </div>
        </div>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button className="btn-outline" onClick={() => start("demo")}>
            Watch the demo
          </button>
          <button className="btn-primary" onClick={() => start("live")}>
            Try it live with the example store <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Opens the dialog by itself the first time someone reaches an app page. */
export function useFirstVisitHelp(enabled = true): [boolean, (o: boolean) => void] {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (enabled && readPref("cp_seen_how_v1") !== "1") setOpen(true);
  }, [enabled]);
  const change = (o: boolean) => {
    setOpen(o);
    if (!o) writePref("cp_seen_how_v1", "1");
  };
  return [open, change];
}

/* -------------------------------------------------------------- toasts --- */
/** A pop-up when a step finishes, with a button to the next step. */
export function useStepToasts() {
  const { scan, fix, verify, mode } = useCheckout();
  const navigate = useNavigate();
  const path = useRouterState({ select: (s) => s.location.pathname });
  const prev = useRef({ scan: scan.phase, fix: fix.phase, verify: verify.phase, mode });

  useEffect(() => {
    const p = prev.current;
    prev.current = { scan: scan.phase, fix: fix.phase, verify: verify.phase, mode };
    if (p.mode !== mode) return; // switching modes resets everything: no pop-ups for that

    if (p.scan === "running" && scan.phase === "success" && scan.data) {
      const n = scan.data.issues.length;
      toast.success(`Scan finished: ${n} issue${n === 1 ? "" : "s"}, health ${scan.data.health_score}/100`, {
        description: "Next: choose which issues CheckoutPilot should fix.",
        action: path === "/recommendations" ? undefined : { label: "Choose fixes", onClick: () => navigate({ to: "/recommendations" }) },
        duration: 8000,
      });
    }
    if (p.scan === "running" && scan.phase === "error")
      toast.error("The scan failed", { description: scan.error ?? "Try the example store instead." });

    if (p.fix === "running" && fix.phase === "success" && fix.data) {
      toast.success(`Fix ready: ${fix.data.files.length} file${fix.data.files.length === 1 ? "" : "s"} changed`, {
        description: "Next: review the changes, then press Verify in Sandbox.",
        action: path === "/fix" ? undefined : { label: "Review fix", onClick: () => navigate({ to: "/fix" }) },
        duration: 8000,
      });
    }
    if (p.fix === "running" && fix.phase === "error")
      toast.error("The fix could not be made", { description: fix.error ?? "" });

    if (p.verify === "running" && verify.phase === "success" && verify.data) {
      const ok = verify.data.passed;
      (ok ? toast.success : toast.error)(ok ? "Verified: the fixed checkout took a Sandbox payment" : "Verification failed", {
        description: ok ? "Download the PDF report from the Proof page." : "See the evidence on the Proof page.",
        action: path === "/proof" ? undefined : { label: "See proof", onClick: () => navigate({ to: "/proof" }) },
        duration: 10000,
      });
    }
    if (p.verify === "running" && verify.phase === "error")
      toast.error("The verification could not run", { description: verify.error ?? "" });
  }, [scan.phase, fix.phase, verify.phase, mode]); // eslint-disable-line react-hooks/exhaustive-deps
}
