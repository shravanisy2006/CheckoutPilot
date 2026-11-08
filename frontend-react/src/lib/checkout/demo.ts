/**
 * Demo Mode data: the REAL results CheckoutPilot recorded on its demo store
 * (Inkwell & Co., legacy store on http://localhost:8101), from
 * docs/sample_result.json in the main repo. Nothing here is invented:
 *   - scan: real scanner + AI rules + impact ranker (health 21/100, 4 issues)
 *   - fix: the real v5 -> v6 code change (legacy_store -> upgraded_store)
 *   - verification: two real PayPal Sandbox payments made by sandbox_verifier
 * Demo Mode replays these results; it does not scan the URL you type.
 */
import { adaptFix, adaptScan, adaptVerification } from "./adapt";
import sample from "./sample_result.json";
import type { FixResult, ScanResult, VerificationResult } from "./types";

export const SCAN_STAGES = [
  "Opening the store in a browser",
  "Walking product → cart → checkout",
  "Checking the PayPal SDK version",
  "Measuring the mobile layout",
  "Ranking issues by impact",
];
export const FIX_STAGES = ["Reading the store's code", "Planning changes", "Upgrading PayPal SDK v5 → v6", "Adding PayPal to the cart", "Preparing the pull request"];
export const VERIFY_STAGES = ["Starting the store", "Logging in as the Sandbox buyer", "Paying in the PayPal window", "Confirming with the Orders API"];

/** Where Demo Mode's recorded results come from. */
export const DEMO_STORE_URL = "http://localhost:8101";

export const demoScan = (_storeUrl?: string): ScanResult => ({
  ...adaptScan(sample.scan),
  screenshots: { desktop: "/demo/legacy_checkout_desktop.png", mobile: "/demo/legacy_checkout_mobile.png" },
});

export const demoFix = (ids: string[]): FixResult => {
  const fix = adaptFix(sample.fix);
  return {
    ...fix,
    summary: `${sample.fix.summary} (Recorded result for ${ids.length} selected recommendation(s); no repository was modified in Demo Mode.)`,
  };
};

export const demoVerification = (): VerificationResult => ({
  ...adaptVerification(sample.verify),
  screenshots: { before: "/demo/proof_before_v5.png", after: "/demo/proof_after_v6.png" },
});
