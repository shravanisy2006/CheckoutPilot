import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowRight, Globe, ScanSearch, Smartphone } from "lucide-react";
import { useCheckout } from "@/lib/checkout/store";
import { isValidStoreUrl } from "@/lib/checkout/api";
import {
  EmptyState,
  ErrorBlock,
  HealthScore,
  PageHeader,
  Panel,
  ProgressBlock,
  SeverityBadge,
  SeveritySummary,
  ScreenshotFrame,
  StorefrontPreview,
} from "@/components/app/ui";
import type { Severity } from "@/lib/checkout/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/audit")({
  head: () => ({
    meta: [
      { title: "Audit — CheckoutPilot" },
      {
        name: "description",
        content: "Scan a store's checkout and find PayPal integration issues.",
      },
      { property: "og:title", content: "Audit — CheckoutPilot" },
      {
        property: "og:description",
        content: "Scan a store's checkout and find PayPal integration issues.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: AuditPage,
});

const SEVS: Severity[] = ["high", "medium", "low"];

function AuditPage() {
  const { scan, startScan, mode } = useCheckout();
  const [url, setUrl] = useState(mode === "demo" ? "https://shop.example.com" : "");
  const [mobile, setMobile] = useState(true);
  const [touched, setTouched] = useState(false);
  const valid = isValidStoreUrl(url);
  const running = scan.phase === "running";
  const data = scan.data;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    if (valid && !running) startScan(url.trim(), mobile);
  };

  return (
    <div className="space-y-8">
      <PageHeader
        step="Step 1 · Scan"
        title="Checkout audit"
        description="Crawl a storefront's checkout and detect PayPal integration problems on desktop and mobile."
      />

      <Panel className="p-5">
        <form onSubmit={submit} className="flex flex-col gap-5 sm:flex-row sm:items-end">
          <div className="flex-1 min-w-0">
            <label
              htmlFor="url"
              className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground block mb-2"
            >
              Store URL
            </label>
            <div className={cn("input-wrap", touched && !valid && "border-destructive/50")}>
              <Globe className="h-4 w-4 text-muted-foreground" />
              <input
                id="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onBlur={() => setTouched(true)}
                placeholder="https://yourstore.com"
                className="flex-1 min-w-0 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              />
            </div>
            {touched && !valid && (
              <p className="mt-2 text-xs text-destructive">
                Enter a full URL starting with http:// or https://
              </p>
            )}
          </div>
          <div className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5 bg-card shrink-0">
            <Smartphone className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-foreground">Mobile scan</span>
            <button
              type="button"
              role="switch"
              aria-checked={mobile}
              onClick={() => setMobile(!mobile)}
              className={cn("toggle", mobile && "toggle-on")}
            >
              <span className="toggle-knob" />
            </button>
          </div>
          <button type="submit" disabled={running} className="btn-primary shrink-0">
            <ScanSearch className="h-4 w-4" /> {running ? "Scanning…" : "Start scan"}
          </button>
        </form>
      </Panel>

      <div className="space-y-8">
        {scan.phase === "idle" && (
          <EmptyState
            icon={ScanSearch}
            title="No scan yet"
            description="Enter a store URL above to audit its PayPal checkout."
          />
        )}
        {running && (
          <ProgressBlock label="Auditing checkout" stage={scan.stage} progress={scan.progress} />
        )}
        {scan.phase === "error" && (
          <ErrorBlock
            title="Scan failed"
            message={scan.error}
            onRetry={() => startScan(url.trim(), mobile)}
          />
        )}

        {data && scan.phase === "success" && (
          <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
            {/* Health score + severity summary side by side */}
            <div className="grid gap-5 lg:grid-cols-[1.35fr_2fr]">
              <Panel className="p-5">
                <HealthScore
                  score={data.health_score}
                  label="Checkout health"
                  storeUrl={data.store_url}
                />
              </Panel>
              <Panel className="p-5">
                <SeveritySummary
                  items={SEVS.map((s) => ({
                    severity: s,
                    count: data.issues.filter((i) => i.severity === s).length,
                  }))}
                />
              </Panel>
            </div>

            <div className="grid gap-5 lg:grid-cols-[2fr_1.2fr]">
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <h2 className="font-display text-lg font-light text-foreground">
                    Ranked findings
                  </h2>
                  <span className="badge-pill bg-muted text-foreground border border-border/50">
                    {data.issues.length} issues
                  </span>
                </div>
                {[...data.issues]
                  .sort((a, b) => SEVS.indexOf(a.severity) - SEVS.indexOf(b.severity))
                  .map((i, idx) => (
                    <div
                      key={i.id}
                      className="rounded-lg border border-border bg-card p-4 transition group hover:border-primary/30 hover:shadow-sm"
                    >
                      <div className="flex items-start gap-3">
                        <span className="shrink-0 font-mono text-xs text-muted-foreground">
                          {String(idx + 1).padStart(2, "0")}
                        </span>
                        <div className="flex-1">
                          <div className="flex flex-wrap items-center gap-2 mb-1.5">
                            <SeverityBadge severity={i.severity} />
                            {i.surface && (
                              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                                {i.surface}
                              </span>
                            )}
                          </div>
                          <p className="font-medium text-foreground">{i.title}</p>
                          <p className="mt-1 text-sm text-muted-foreground">{i.explanation}</p>
                          {i.evidence.length > 0 && (
                            <div className="mt-3 space-y-1 rounded-lg bg-muted p-3 border border-border/50">
                              {i.evidence.map((ev) => (
                                <code
                                  key={ev}
                                  className="block break-all font-mono text-xs text-foreground/70"
                                >
                                  {ev}
                                </code>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
              </div>
              <div className="space-y-4">
                <StorefrontPreview
                  heading="Captured checkout"
                  desktopSrc={data.screenshots?.desktop}
                  mobileSrc={data.screenshots?.mobile}
                />
                <Link to="/recommendations" className="btn-primary w-full">
                  View recommendations <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
