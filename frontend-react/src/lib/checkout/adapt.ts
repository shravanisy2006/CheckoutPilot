/**
 * Translates CheckoutPilot backend responses into the dashboard's own types.
 *
 * Accepts both the current backend shape (`gaps` / `gap_id`) and the shape in
 * docs/api_contract.md (`issues` / `issue_id`), so the dashboard keeps working
 * while the backend moves to the contract. Demo Mode runs the real recorded
 * result (sample_result.json) through these same functions, so Demo and Live
 * can never show different kinds of data.
 */
import type { FileChange, FixResult, Issue, Recommendation, ScanResult, Severity, VerificationResult } from "./types";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Raw = Record<string, any>;

/** What the merchant should do for each issue the AI can report. */
const FIX_TEXT: Record<string, { title: string; description: string; surface: Issue["surface"] }> = {
  sdk_outdated: {
    title: "Upgrade to PayPal JavaScript SDK v6",
    description: "Replace the v5 script (paypal.com/sdk/js) and paypal.Buttons() with web-sdk/v6: createInstance, a one-time payment session and <paypal-button>.",
    surface: "both",
  },
  no_paypal_on_cart: {
    title: "Add PayPal to the cart page",
    description: "Show a PayPal express button under the cart total so shoppers can pay without going through the checkout form.",
    surface: "both",
  },
  no_paypal_on_product: {
    title: "Offer PayPal on the product page",
    description: "Add a PayPal button or message near Add to cart so PayPal is visible earlier in the journey.",
    surface: "both",
  },
  button_below_fold_mobile: {
    title: "Move PayPal above the form on mobile",
    description: "On small screens, place the order summary and PayPal button before the shipping form.",
    surface: "mobile",
  },
  paypal_button_not_prominent: {
    title: "Make the PayPal button easier to see",
    description: "Give the PayPal button a clear, uncluttered spot near the order total.",
    surface: "both",
  },
  paypal_button_cluttered: {
    title: "Reduce clutter around the PayPal button",
    description: "Separate PayPal from competing buttons and banners.",
    surface: "both",
  },
  checkout_layout_cramped_mobile: {
    title: "Give the mobile checkout more room",
    description: "Simplify the mobile checkout layout so the payment step is easy to reach.",
    surface: "mobile",
  },
};

const SOURCE_LABEL: Record<string, string> = {
  rule: "Found by: rule check",
  vision: "Found by: AI vision",
  "rule+vision": "Found by: rule check + AI vision",
};

export function normalizeSeverity(value: unknown): Severity {
  const s = String(value ?? "").toLowerCase();
  if (s === "critical" || s === "high") return "high";
  if (s === "medium") return "medium";
  return "low";
}

/** Turn "/files/..." into a full backend URL; keep absolute and /demo/ paths; drop local file paths. */
export function toImageUrl(value: unknown, apiBase: string): string | null {
  const path = String(value ?? "");
  if (!path) return null;
  if (/^https?:\/\//.test(path) || path.startsWith("/demo/")) return path;
  if (path.startsWith("/files/")) return apiBase ? `${apiBase}${path}` : null;
  return null; // e.g. C:\...\screenshots\x.png - the browser cannot open it
}

export function adaptScan(raw: Raw, apiBase = ""): ScanResult {
  const list: Raw[] = raw["issues"] ?? raw["gaps"] ?? [];
  const issues: Issue[] = [];
  const recommendations: Recommendation[] = [];

  list.forEach((item, index) => {
    const id = String(item["issue_id"] ?? item["gap_id"] ?? `issue_${index + 1}`);
    const impact: Raw = item["impact"] ?? {};
    const text = FIX_TEXT[id];
    const severity = normalizeSeverity(item["severity"]);
    const source = String(item["source"] ?? "");
    const confidence = typeof item["confidence"] === "number" ? item["confidence"] : null;
    const evidence = [
      SOURCE_LABEL[source] ?? (source ? `Found by: ${source}` : ""),
      confidence !== null ? `Confidence ${Math.round(confidence * 100)}%` : "",
      item["fixable_by_agent"] ? "Auto-fixable" : "",
    ].filter(Boolean);

    issues.push({
      id,
      title: String(item["title"] ?? id),
      severity,
      explanation: String(item["evidence"] || item["description"] || ""),
      evidence,
      surface: text?.surface ?? (String(item["category"]) === "mobile" ? "mobile" : "both"),
    });

    recommendations.push({
      id: `r_${id}`,
      issue_id: id,
      title: text?.title ?? `Fix: ${String(item["title"] ?? id)}`,
      description: text?.description ?? String(item["evidence"] ?? ""),
      severity,
      priority: Number(impact["rank"] ?? index + 1),
      rationale: String(impact["rationale"] ?? ""),
      estimated_conversion_impact: null, // never show invented percentages
      impact_score: typeof impact["score"] === "number" ? impact["score"] : null,
      impact_source: impact["assumption_source"] ? String(impact["assumption_source"]) : null,
      assumption: impact["assumption"] ? String(impact["assumption"]) : null,
      fixable_by_agent: Boolean(item["fixable_by_agent"]),
    });
  });

  const pages: Raw[] = raw["pages"] ?? [];
  const shot = (viewport: string) =>
    toImageUrl(pages.find((p) => p["step"] === "checkout" && p["viewport"] === viewport)?.["screenshot_url"], apiBase);

  return {
    scan_id: String(raw["scan_id"] ?? ""),
    store_url: String(raw["store_url"] ?? ""),
    health_score: Number(raw["health_score"] ?? 0),
    issues,
    recommendations,
    screenshots: { desktop: shot("desktop"), mobile: shot("mobile") },
    created_at: raw["scanned_at"] ?? new Date().toISOString(),
    paypal_sdk_version: raw["paypal_sdk_version"] ?? raw["detected_sdk_version"] ?? null,
    warnings: (raw["warnings"] ?? []).map(String),
  };
}

/** Split a unified diff into the "before" and "after" text the diff viewer shows. */
export function diffToBeforeAfter(diff: string): { before: string; after: string } {
  const before: string[] = [];
  const after: string[] = [];
  for (const line of diff.split("\n")) {
    if (line.startsWith("---") || line.startsWith("+++")) continue;
    if (line.startsWith("@@")) {
      if (before.length || after.length) {
        before.push("⋯");
        after.push("⋯");
      }
      continue;
    }
    if (line.startsWith("-")) before.push(line.slice(1));
    else if (line.startsWith("+")) after.push(line.slice(1));
    else if (line.startsWith(" ")) {
      before.push(line.slice(1));
      after.push(line.slice(1));
    }
  }
  return { before: before.join("\n"), after: after.join("\n") };
}

const SDK_FILES = /checkout\.html|paypal\.js|checkout\.js|app\.py/;

export function adaptFix(raw: Raw): FixResult {
  const files: FileChange[] = (raw["files"] ?? []).map((f: Raw) => {
    const path = String(f["path"] ?? "");
    const { before, after } = f["diff"] ? diffToBeforeAfter(String(f["diff"])) : { before: String(f["before"] ?? ""), after: String(f["after"] ?? "") };
    const label = f["change_type"] === "added" ? " (new file)" : f["change_type"] === "deleted" ? " (removed)" : "";
    return { path: `${path}${label}`, category: SDK_FILES.test(path) ? "sdk" : "checkout", before, after };
  });
  const result: FixResult = {
    fix_id: String(raw["fix_id"] ?? ""),
    confirmed: raw["status"] === "approved" || raw["status"] === "applied",
    files,
    pull_request_url: raw["pr_url"] || raw["pull_request_url"] || null,
  };
  if (raw["summary"]) result.summary = String(raw["summary"]);
  return result;
}

function runLine(label: string, run: Raw): string {
  if (!run) return "";
  if (run["purchase_succeeded"]) {
    return `${label} (SDK ${run["paypal_sdk"] || "?"}): order ${run["order_id"]} ${run["order_status"] || "captured"}, ${run["amount"]} ${run["currency"]} in ${run["duration_seconds"]}s`;
  }
  return `${label}: payment failed (${run["error_code"] || "unknown"}) ${run["error_message"] || ""}`.trim();
}

export function adaptVerification(raw: Raw, apiBase = ""): VerificationResult {
  const before: Raw = raw["before"] ?? {};
  const after: Raw = raw["after"] ?? raw;
  // The backend says it directly ("simulated"); a FAILED real payment is not a simulation.
  const simulated = typeof raw["simulated"] === "boolean"
    ? raw["simulated"]
    : (after["warnings"] ?? []).some((w: string) => /mock/i.test(w)) || after["is_real_sandbox_payment"] === false;
  const passed = Boolean(raw["safe_to_approve"] ?? after["purchase_succeeded"]);
  const lastShot = (run: Raw) => {
    const shots: string[] = run["screenshots"] ?? [];
    return toImageUrl(shots[shots.length - 1], apiBase);
  };
  return {
    verification_id: String(raw["verification_id"] ?? after["verification_id"] ?? ""),
    passed,
    environment: "sandbox",
    status: simulated
      ? "Simulated — no PayPal Sandbox call was made"
      : passed
        ? "Real PayPal Sandbox payment completed and confirmed with the Orders API"
        : String(raw["summary"] ?? after["error_message"] ?? "Sandbox payment did not complete"),
    order_id: after["order_id"] || null,
    simulated,
    evidence: [
      runLine("Before", before),
      runLine("After", after),
      after["api_confirmed"] ? "Status double-checked with the PayPal Orders API" : "",
      ...(raw["changes"] ?? []).map(String),
      raw["summary"] ? String(raw["summary"]) : "",
    ].filter(Boolean),
    screenshots: { before: lastShot(before), after: lastShot(after) },
  };
}
