import type { ReactNode } from "react";
import { AlertTriangle, Loader2, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/checkout/types";

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("panel", className)}>{children}</div>;
}

export function PageHeader({
  step,
  title,
  description,
  action,
}: {
  step: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="eyebrow">{step}</p>
        <h1 className="mt-1 font-display text-3xl font-light tracking-tight text-foreground sm:text-[2rem] leading-[1.1]">
          {title}
        </h1>
        {description && (
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      {action && <div className="mt-4 sm:mt-0">{action}</div>}
    </div>
  );
}

const sevClass: Record<Severity, string> = {
  high: "severity-badge severity-high",
  medium: "severity-badge severity-medium",
  low: "severity-badge severity-low",
};
export function SeverityBadge({ severity }: { severity: Severity }) {
  return <span className={cn(sevClass[severity])}>{severity}</span>;
}

export function ProgressBlock({
  stage,
  progress,
  label,
}: {
  stage?: string | undefined;
  progress: number;
  label: string;
}) {
  return (
    <Panel className="p-5">
      <div className="flex items-center gap-3">
        <Loader2 className="h-5 w-5 animate-spin text-primary" />
        <div className="flex-1">
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="text-xs text-muted-foreground">{stage ?? "Working…"}</p>
        </div>
        <span className="font-mono text-sm tabular-nums text-muted-foreground">{progress}%</span>
      </div>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className="h-full rounded-full bg-primary transition-all duration-500"
          style={{ width: `${Math.max(progress, 4)}%` }}
        />
      </div>
    </Panel>
  );
}

export function ErrorBlock({
  title,
  message,
  onRetry,
}: {
  title: string;
  message?: string | undefined;
  onRetry?: () => void;
}) {
  return (
    <Panel className="border-destructive/30 bg-destructive/5 p-5">
      <div className="flex gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
        <div className="flex-1">
          <p className="text-sm font-semibold text-foreground">{title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{message}</p>
          <p className="mt-2 text-xs text-muted-foreground">No demo data was substituted.</p>
        </div>
        {onRetry && (
          <button onClick={onRetry} className="btn-outline h-9">
            Retry
          </button>
        )}
      </div>
    </Panel>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <Panel className="flex flex-col items-center px-6 py-12 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-secondary text-accent-foreground">
        <Icon className="h-5 w-5" />
      </div>
      <p className="mt-4 font-display text-lg font-light text-foreground">{title}</p>
      <p className="mt-1.5 max-w-sm text-sm text-muted-foreground">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </Panel>
  );
}

export function ScreenshotFrame({
  src,
  label,
  variant,
  caption,
}: {
  src?: string | null | undefined;
  label: string;
  variant: "desktop" | "mobile";
  caption?: string;
}) {
  return (
    <figure className="flex flex-col gap-2">
      <div
        className={cn(
          "shot-frame",
          variant === "mobile" ? "mx-auto aspect-[9/17] w-40" : "aspect-[16/9] w-full",
        )}
      >
        {src ? (
          <img src={src} alt={label} className="h-full w-full object-cover object-center" />
        ) : (
          <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-6">
            <div className="flex h-8 w-24 items-center justify-center rounded-lg bg-muted">
              <span className="text-[10px] font-medium text-muted-foreground">preview</span>
            </div>
            <p className="text-center text-[10px] text-muted-foreground">No screenshot provided</p>
          </div>
        )}
      </div>
      <figcaption className="text-center text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {caption ?? label}
      </figcaption>
    </figure>
  );
}

/* ---------------------------------------------------------------
   Design system components (design.md)
--------------------------------------------------------------- */

export function HealthScore({
  score,
  label,
  storeUrl,
}: {
  score: number;
  label?: string;
  storeUrl?: string;
}) {
  const tone = score >= 80 ? "text-success" : score >= 60 ? "text-warning" : "text-destructive";
  const fill = score >= 80 ? "bg-success" : score >= 60 ? "bg-warning" : "bg-destructive";
  return (
    <Panel className="p-6">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label ?? "Checkout health"}
      </p>
      <div className="mt-4 flex items-center gap-4">
        <div className="relative w-20 h-20">
          <svg className="w-full h-full transform -rotate-90">
            <circle
              cx="40"
              cy="40"
              r="36"
              stroke="var(--color-border)"
              strokeWidth="8"
              fill="none"
              className="text-muted-foreground/20"
            />
            <circle
              cx="40"
              cy="40"
              r="36"
              stroke="currentColor"
              strokeWidth="8"
              fill="none"
              className={cn("transition-all duration-700", fill)}
              strokeDasharray="226"
              strokeDashoffset={`${226 * ((100 - score) / 100)}`}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={cn("font-display text-2xl font-light tabular-nums", tone)}>
              {score}
            </span>
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider">/100</span>
          </div>
        </div>
      </div>
      {storeUrl && <p className="mt-4 truncate text-xs text-muted-foreground">{storeUrl}</p>}
    </Panel>
  );
}

export function SeveritySummary({ items }: { items: { severity: Severity; count: number }[] }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {items.map(({ severity, count }) => (
        <Panel key={severity} className="p-4">
          <SeverityBadge severity={severity} className="mb-3" />
          <p className="font-display text-2xl font-light tabular-nums text-foreground">{count}</p>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{severity}</p>
        </Panel>
      ))}
    </div>
  );
}

export function StorefrontPreview({
  desktopSrc,
  mobileSrc,
  heading,
}: {
  desktopSrc?: string | null | undefined;
  mobileSrc?: string | null | undefined;
  heading?: string;
}) {
  return (
    <div className="space-y-4">
      {heading && (
        <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {heading}
        </p>
      )}
      <div className="grid gap-4 md:grid-cols-2 items-start">
        <Panel className="p-0 min-w-0">
          <ScreenshotFrame variant="desktop" label="Desktop" src={desktopSrc} caption="Desktop" />
        </Panel>
        <Panel className="p-0 min-w-0">
          <ScreenshotFrame variant="mobile" label="Mobile" src={mobileSrc} caption="Mobile" />
        </Panel>
      </div>
    </div>
  );
}

export function CheckoutIssue({
  issue,
  index,
  onClick,
  selected = false,
}: {
  issue: {
    id: string;
    title: string;
    severity: Severity;
    explanation: string;
    evidence: string[];
    surface?: "desktop" | "mobile" | "both";
  };
  index: number;
  onClick?: () => void;
  selected?: boolean;
}) {
  return (
    <Panel
      className={cn(
        "p-5 transition group cursor-pointer border-transparent",
        selected && "ring-2 ring-primary/30 bg-primary/5 border-primary/10",
      )}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <span className="shrink-0 font-mono text-xs text-muted-foreground">
          {String(index + 1).padStart(2, "0")}
        </span>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <SeverityBadge severity={issue.severity} />
            {issue.surface && (
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                {issue.surface}
              </span>
            )}
          </div>
          <p className="font-medium text-foreground">{issue.title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{issue.explanation}</p>
          {issue.evidence.length > 0 && (
            <div className="mt-3 space-y-1.5 rounded-lg bg-muted p-3 border border-border/50">
              {issue.evidence.map((ev) => (
                <code key={ev} className="block break-all font-mono text-xs text-foreground/70">
                  {ev}
                </code>
              ))}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

export function RecommendationCard({
  rec,
  on,
  onToggle,
}: {
  rec: {
    id: string;
    priority: number;
    severity: Severity;
    title: string;
    description: string;
    rationale: string;
    estimated_conversion_impact?: string | null;
    impact_score?: number | null;
    impact_source?: string | null;
    assumption?: string | null;
  };
  on: boolean;
  onToggle: () => void;
}) {
  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onToggle();
  };

  return (
    <Panel
      className={cn(
        "p-5 transition group cursor-pointer border-transparent",
        on
          ? "ring-2 ring-primary/40 bg-primary/5 border-primary/10 shadow-sm"
          : "hover:border-border/50 hover:shadow-sm border",
      )}
      onClick={onToggle}
    >
      <div className="flex gap-3 items-start">
        <div
          role="checkbox"
          aria-checked={on}
          onClick={handleCheckboxClick}
          className={cn(
            "mt-0.5 shrink-0 flex h-6 w-6 items-center justify-center rounded-md border transition",
            on ? "border-primary bg-primary text-primary-foreground" : "border-border",
          )}
        >
          {on && <Check className="h-3.5 w-3.5" />}
        </div>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="font-mono text-xs text-muted-foreground">P{rec.priority}</span>
            <SeverityBadge severity={rec.severity} />
          </div>
          <p className="font-medium text-foreground">{rec.title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{rec.description}</p>
          <p className="mt-3 text-sm text-foreground/85">
            <span className="font-medium text-foreground">Why: </span>
            {rec.rationale}
          </p>
        </div>
        {typeof rec.impact_score === "number" && (
          <div className="shrink-0 max-w-[14rem] text-right">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              Impact score
            </p>
            <p className="font-display text-lg font-light text-foreground tabular-nums">
              {rec.impact_score}/100
            </p>
            {rec.impact_source && (
              <p className="text-[10px] text-muted-foreground" {...(rec.assumption ? { title: rec.assumption } : {})}>
                Source: {rec.impact_source}
              </p>
            )}
            <p className="text-[10px] text-muted-foreground">Effect not measured for this store</p>
          </div>
        )}
      </div>
    </Panel>
  );
}

function Check() {
  return (
    <svg
      className="h-3.5 w-3.5"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="3"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

export function DiffViewer({ file }: { file: { path: string; before: string; after: string } }) {
  const before = file.before.split("\n");
  const after = file.after.split("\n");
  return (
    <div className="diff-pane flex flex-col">
      <div className="flex items-center justify-between border-b border-border px-3 py-1.5 bg-muted/50">
        <p className="font-mono text-xs text-foreground">{file.path}</p>
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
          {before.length} → {after.length} lines
        </span>
      </div>
      <div className="flex overflow-hidden lg:flex-row flex-col">
        {[
          { t: "Before", lines: before, cls: "diff-del-bg diff-del", sign: "−" },
          { t: "After", lines: after, cls: "diff-add-bg diff-add", sign: "+" },
        ].map((side) => (
          <div
            key={side.t}
            className="min-w-0 flex flex-col border-l border-border first:border-l-0 lg:first:border-l-0 lg:first:border-r"
          >
            <div className="diff-pane-header">{side.t}</div>
            <div className="flex-1 overflow-x-auto overflow-y-auto">
              <pre className="diff-code">
                {side.lines.map((l, i) => (
                  <div key={i} className={cn("diff-line px-2", side.cls)}>
                    <span className="diff-sign shrink-0 text-muted-foreground/60">{side.sign}</span>
                    <span className="whitespace-pre">{l || " "}</span>
                  </div>
                ))}
              </pre>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function FixStatusBadge({ confirmed }: { confirmed: boolean }) {
  return (
    <span
      className={cn(
        "badge-pill",
        confirmed
          ? "bg-success/10 text-success border border-success/20"
          : "bg-warning/10 text-warning border border-warning/20",
      )}
    >
      {confirmed ? "Applied" : "Proposed"}
    </span>
  );
}

export function VerificationPill({ passed, status }: { passed: boolean; status: string }) {
  return (
    <div className="flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm">
      {passed ? (
        <>
          <span className="h-1.5 w-1.5 rounded-full bg-success" />
          <span className="font-medium text-foreground">Verification passed</span>
        </>
      ) : (
        <>
          <span className="h-1.5 w-1.5 rounded-full bg-destructive" />
          <span className="font-medium text-foreground">Verification failed</span>
        </>
      )}
      <span className="ml-auto text-[10px] font-medium text-muted-foreground">{status}</span>
    </div>
  );
}

export function SimulatedBanner() {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-warning/30 bg-warning/10 px-4 py-3 text-sm text-foreground/90">
      <span className="h-1.5 w-1.5 rounded-full bg-warning" />
      <span>Simulated — sample data. No PayPal transaction occurred, real or sandbox.</span>
    </div>
  );
}
