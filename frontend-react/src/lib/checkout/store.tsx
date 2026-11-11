import type React from "react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, runFix, runRescan, runScan, runVerify } from "./api";
import { demoFix, demoRescan, demoScan, demoVerification, FIX_STAGES, RESCAN_STAGES, SCAN_STAGES, VERIFY_STAGES } from "./demo";
import type { FixResult, Mode, ScanResult, VerificationResult } from "./types";

export type Phase = "idle" | "running" | "success" | "error";
export interface Task<T> {
  phase: Phase;
  progress: number;
  stage?: string | undefined;
  error?: string | undefined;
  data?: T | undefined;
}
const idle = <T,>(): Task<T> => ({ phase: "idle", progress: 0 });

interface Ctx {
  mode: Mode;
  setMode: (m: Mode) => void;
  scan: Task<ScanResult>;
  fix: Task<FixResult>;
  verify: Task<VerificationResult>;
  /** The fixed copy, scanned again: health before -> after. */
  rescan: Task<ScanResult>;
  selected: string[];
  toggleSelected: (id: string) => void;
  setSelected: (ids: string[]) => void;
  startScan: (url: string, includeMobile: boolean) => Promise<void>;
  startFix: () => Promise<void>;
  startVerify: () => Promise<void>;
  startRescan: () => Promise<void>;
}
// Keep one context instance across hot reloads so provider and consumers always match.
const g = globalThis as unknown as { __checkoutCtx?: React.Context<Ctx | null> };
const C = (g.__checkoutCtx ??= createContext<Ctx | null>(null));

async function simulate(stages: string[], set: (p: number, s: string) => void, ms = 700) {
  for (let i = 0; i < stages.length; i++) {
    set(Math.round((i / stages.length) * 100), stages[i]!);
    await new Promise((r) => setTimeout(r, ms));
  }
}
const msg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Unexpected error");

export function CheckoutProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>("demo");
  const [scan, setScan] = useState<Task<ScanResult>>(idle);
  const [fix, setFix] = useState<Task<FixResult>>(idle);
  const [verify, setVerify] = useState<Task<VerificationResult>>(idle);
  const [rescan, setRescan] = useState<Task<ScanResult>>(idle);
  const rescanning = useRef(false);
  const [selected, setSelected] = useState<string[]>([]);
  const gen = useRef(0);
  // A Sandbox verification makes real test payments and takes 1-2 minutes: never start a second one.
  const verifying = useRef(false);

  // Remember Demo/Live between visits (read after load, so server and browser render the same first).
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("cp_mode");
      if (saved === "live" || saved === "demo") setModeState(saved);
    } catch {
      /* storage blocked: keep Demo */
    }
  }, []);

  const setMode = (m: Mode) => {
    gen.current++; // invalidate in-flight work so results never cross modes
    setModeState(m);
    try {
      window.localStorage.setItem("cp_mode", m);
    } catch {
      /* ignore */
    }
    setScan(idle());
    setFix(idle());
    setVerify(idle());
    setRescan(idle());
    setSelected([]);
  };

  const startScan = useCallback(
    async (url: string, includeMobile: boolean) => {
      const g = ++gen.current;
      const ok = () => g === gen.current;
      setScan({ phase: "running", progress: 0, stage: "Queued" });
      setFix(idle());
      setVerify(idle());
      setRescan(idle());
      setSelected([]);
      try {
        let data: ScanResult;
        if (mode === "demo") {
          await simulate(includeMobile ? SCAN_STAGES : SCAN_STAGES.filter((s) => !s.includes("mobile")), (p, s) => ok() && setScan((t) => ({ ...t, progress: p, stage: s })));
          data = demoScan(url);
        } else {
          data = await runScan(url, includeMobile, (p, s) => ok() && setScan((t) => ({ ...t, progress: p ?? t.progress, stage: s ?? t.stage })));
        }
        if (!ok()) return;
        setScan({ phase: "success", progress: 100, data });
        // Pre-select what the code agent can actually fix.
        setSelected(data.recommendations.filter((r) => r.fixable_by_agent ?? r.severity === "high").map((r) => r.id));
      } catch (e) {
        if (ok()) setScan({ phase: "error", progress: 0, error: msg(e) });
      }
    },
    [mode],
  );

  const startFix = useCallback(async () => {
    if (!scan.data) return;
    const g = ++gen.current;
    const ok = () => g === gen.current;
    setFix({ phase: "running", progress: 0, stage: "Queued" });
    setVerify(idle());
    setRescan(idle());
    try {
      let data: FixResult;
      if (mode === "demo") {
        await simulate(FIX_STAGES, (p, s) => ok() && setFix((t) => ({ ...t, progress: p, stage: s })));
        data = demoFix(selected);
      } else {
        data = await runFix(scan.data.scan_id, selected, (p, s) => ok() && setFix((t) => ({ ...t, progress: p ?? t.progress, stage: s ?? t.stage })));
      }
      if (ok()) setFix({ phase: "success", progress: 100, data });
    } catch (e) {
      if (ok()) setFix({ phase: "error", progress: 0, error: msg(e) });
    }
  }, [mode, scan.data, selected]);

  const startVerify = useCallback(async () => {
    if (!scan.data || !fix.data || verifying.current) return;
    verifying.current = true;
    const g = ++gen.current;
    const ok = () => g === gen.current;
    setVerify({ phase: "running", progress: 0, stage: "Paying in the PayPal Sandbox (about 1-2 minutes)" });
    try {
      let data: VerificationResult;
      if (mode === "demo") {
        await simulate(VERIFY_STAGES, (p, s) => ok() && setVerify((t) => ({ ...t, progress: p, stage: s })));
        data = demoVerification();
      } else {
        data = await runVerify(fix.data.fix_id, (p, s) => ok() && setVerify((t) => ({ ...t, progress: p ?? t.progress, stage: s ?? t.stage })));
      }
      if (ok()) setVerify({ phase: "success", progress: 100, data });
    } catch (e) {
      if (ok()) setVerify({ phase: "error", progress: 0, error: msg(e) });
    } finally {
      verifying.current = false;
    }
  }, [mode, scan.data, fix.data]);

  const startRescan = useCallback(async () => {
    if (!fix.data || rescanning.current) return;
    rescanning.current = true;
    const g = gen.current; // a re-scan never cancels the proof; a new scan or fix cancels it
    const ok = () => g === gen.current;
    setRescan({ phase: "running", progress: 0, stage: "Starting the fixed copy" });
    try {
      let data: ScanResult;
      if (mode === "demo") {
        await simulate(RESCAN_STAGES, (p, s) => ok() && setRescan((t) => ({ ...t, progress: p, stage: s })));
        data = demoRescan();
      } else {
        data = await runRescan(fix.data.fix_id, (p, s) => ok() && setRescan((t) => ({ ...t, progress: p ?? t.progress, stage: s ?? t.stage })));
      }
      if (ok()) setRescan({ phase: "success", progress: 100, data });
    } catch (e) {
      if (ok()) setRescan({ phase: "error", progress: 0, error: msg(e) });
    } finally {
      rescanning.current = false;
    }
  }, [mode, fix.data]);

  // Re-measure automatically once the proof passes: Find -> Fix -> Prove -> Re-measure.
  useEffect(() => {
    if (verify.phase === "success" && verify.data?.passed && rescan.phase === "idle") void startRescan();
  }, [verify.phase, verify.data?.passed, rescan.phase, startRescan]);

  const toggleSelected = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <C.Provider value={{ mode, setMode, scan, fix, verify, rescan, selected, toggleSelected, setSelected, startScan, startFix, startVerify, startRescan }}>
      {children}
    </C.Provider>
  );
}

export function useCheckout() {
  const c = useContext(C);
  if (!c) throw new Error("useCheckout must be used inside CheckoutProvider");
  return c;
}
