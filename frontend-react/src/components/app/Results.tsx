/**
 * After the proof: what changed (re-measured), and what it could be worth.
 *
 * - BeforeAfter: the original store vs the code agent's fixed copy, both scanned by the same
 *   scanner: health score, which issues are fixed, and the mobile checkout side by side.
 * - ImpactEstimator: the merchant's own numbers -> scenario table. Not a forecast: CheckoutPilot
 *   does not measure the store's traffic, so it shows what small changes would be worth, with the
 *   published research for context.
 */
import { useMemo, useState } from "react";
import { ArrowRight, CheckCircle2, CircleDot, RefreshCw } from "lucide-react";
import type { ScanResult } from "@/lib/checkout/types";
import type { Task } from "@/lib/checkout/store";
import { cn } from "@/lib/utils";
import { Panel, ProgressBlock, ScreenshotFrame } from "./ui";

/* --------------------------------------------------------- before/after --- */
export interface Change {
  id: string;
  title: string;
  fixed: boolean;
}

/** Pure: which of the original issues are gone in the re-scan (tested). */
export function compareScans(before: ScanResult, after: ScanResult) {
  const remaining = new Set(after.issues.map((i) => i.id));
  const changes: Change[] = before.issues.map((i) => ({ id: i.id, title: i.title, fixed: !remaining.has(i.id) }));
  return {
    changes,
    fixedCount: changes.filter((c) => c.fixed).length,
    delta: after.health_score - before.health_score,
  };
}

function Score({ value, label }: { value: number; label: string }) {
  const tone = value >= 80 ? "text-success" : value >= 60 ? "text-warning" : "text-destructive";
  return (
    <div className="text-center">
      <p className={cn("font-display text-5xl font-light tabular-nums", tone)}>{value}</p>
      <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
    </div>
  );
}

export function BeforeAfter({
  before,
  rescan,
  onRetry,
}: {
  before: ScanResult;
  rescan: Task<ScanResult>;
  onRetry: () => void;
}) {
  const after = rescan.data;
  const result = useMemo(() => (after ? compareScans(before, after) : null), [before, after]);

  return (
    <div data-testid="before-after">
    <Panel className="p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          Re-measured: before vs after the fix
        </p>
        <p className="text-xs text-muted-foreground">Same scanner, run on the code agent's fixed copy</p>
      </div>

      {rescan.phase === "running" && (
        <div className="mt-4">
          <ProgressBlock label="Scanning the fixed copy" stage={rescan.stage} progress={rescan.progress} />
        </div>
      )}
      {rescan.phase === "error" && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
          <span className="text-destructive">{rescan.error}</span>
          <button className="btn-outline h-8 px-3 text-xs" onClick={onRetry}>
            <RefreshCw className="h-3.5 w-3.5" /> Try again
          </button>
        </div>
      )}
      {rescan.phase === "idle" && (
        <div className="mt-4 flex items-center justify-between gap-3 text-sm text-muted-foreground">
          <span>Scan the fixed copy to see how much the checkout improved.</span>
          <button className="btn-primary h-8 px-3 text-xs" onClick={onRetry}>
            Re-measure
          </button>
        </div>
      )}

      {after && result && (
        <div className="mt-5 grid gap-6 lg:grid-cols-[1.1fr_1fr]">
          <div>
            <div className="flex items-center justify-center gap-6 rounded-xl bg-muted/50 py-5">
              <Score value={before.health_score} label="Before" />
              <ArrowRight className="h-6 w-6 text-muted-foreground" />
              <Score value={after.health_score} label="After the fix" />
            </div>
            <p className="mt-3 text-center text-sm text-foreground" data-testid="before-after-headline">
              Health {result.delta >= 0 ? "up" : "down"} <b>{Math.abs(result.delta)} points</b>, {result.fixedCount} of{" "}
              {result.changes.length} issues fixed
              {after.paypal_sdk_version ? `, now on PayPal SDK ${after.paypal_sdk_version}` : ""}.
            </p>
            <ul className="mt-4 space-y-2">
              {result.changes.map((c) => (
                <li key={c.id} className="flex items-start gap-2 text-sm">
                  {c.fixed ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
                  ) : (
                    <CircleDot className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className={cn(c.fixed ? "text-foreground" : "text-muted-foreground")}>
                    {c.title}
                    <span className="ml-1 text-xs text-muted-foreground">{c.fixed ? "· fixed" : "· still open"}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <ScreenshotFrame variant="mobile" label="Before: phone checkout" src={before.screenshots?.mobile} />
            <ScreenshotFrame variant="mobile" label="After: phone checkout" src={after.screenshots?.mobile} />
          </div>
        </div>
      )}
    </Panel>
    </div>
  );
}

/* ------------------------------------------------------- cost estimator --- */
export const SCENARIOS = [1, 3, 5]; // % more PayPal orders: scenarios, not predictions

/** Pure: monthly PayPal revenue and the scenario rows (tested). */
export function estimate(ordersPerMonth: number, averageOrder: number, paypalSharePct: number) {
  const clean = (n: number) => (Number.isFinite(n) && n > 0 ? n : 0);
  const orders = clean(ordersPerMonth);
  const aov = clean(averageOrder);
  const share = Math.min(clean(paypalSharePct), 100) / 100;
  const paypalMonthly = orders * aov * share;
  return {
    paypalMonthly,
    rows: SCENARIOS.map((pct) => ({ pct, monthly: (paypalMonthly * pct) / 100, yearly: (paypalMonthly * pct * 12) / 100 })),
  };
}

const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: n < 100 ? 2 : 0 });

function NumberField({
  id,
  label,
  value,
  onChange,
  suffix,
  prefix,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  suffix?: string;
  prefix?: string;
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-xs text-muted-foreground">
      {label}
      <span className="flex items-center rounded-lg border border-border bg-background px-2 focus-within:ring-2 focus-within:ring-primary/30">
        {prefix && <span className="text-sm text-muted-foreground">{prefix}</span>}
        <input
          id={id}
          inputMode="decimal"
          className="w-full bg-transparent px-1 py-2 text-sm text-foreground outline-none"
          value={value}
          onChange={(e) => onChange(e.target.value.replace(/[^0-9.]/g, ""))}
        />
        {suffix && <span className="text-sm text-muted-foreground">{suffix}</span>}
      </span>
    </label>
  );
}

export function ImpactEstimator() {
  // Example values so the table isn't empty; the merchant replaces them with their own.
  const [orders, setOrders] = useState("400");
  const [aov, setAov] = useState("45");
  const [share, setShare] = useState("30");
  const result = estimate(Number(orders), Number(aov), Number(share));

  return (
    <div data-testid="impact-estimator">
    <Panel className="p-5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        What could this be worth? (your numbers)
      </p>
      <p className="mt-2 text-sm text-muted-foreground">
        Enter your store's own figures. The table shows what <b className="text-foreground">a few more completed PayPal
        orders</b> would be worth. These are scenarios, not a forecast: CheckoutPilot does not measure your traffic.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <NumberField id="est-orders" label="Orders per month" value={orders} onChange={setOrders} />
        <NumberField id="est-aov" label="Average order value" value={aov} onChange={setAov} prefix="$" />
        <NumberField id="est-share" label="Paid with PayPal" value={share} onChange={setShare} suffix="%" />
      </div>

      <div className="mt-4 overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/60 text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 text-left font-medium">If PayPal orders grow by</th>
              <th className="px-3 py-2 text-right font-medium">Per month</th>
              <th className="px-3 py-2 text-right font-medium">Per year</th>
            </tr>
          </thead>
          <tbody>
            {result.rows.map((r) => (
              <tr key={r.pct} className="border-t border-border">
                <td className="px-3 py-2">+{r.pct}%</td>
                <td className="px-3 py-2 text-right tabular-nums">{money(r.monthly)}</td>
                <td className="px-3 py-2 text-right tabular-nums font-medium">{money(r.yearly)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Your PayPal revenue today: about <b className="text-foreground">{money(result.paypalMonthly)}</b> a month.
      </p>

      <p className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
        Why it matters: shoppers abandon about 70% of online carts on average, and 17% of US shoppers abandoned an order
        in the past quarter because checkout was too long or complicated (
        <a
          className="underline underline-offset-2 hover:text-foreground"
          href="https://baymard.com/research-articles/ecommerce-checkout-usability-report-and-benchmark"
          target="_blank"
          rel="noreferrer"
        >
          Baymard Institute, 2026 data
        </a>
        ). The fixes above shorten the path to PayPal; how much they help depends on your store.
      </p>
    </Panel>
    </div>
  );
}
