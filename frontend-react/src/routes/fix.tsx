import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { ExternalLink, FileCode2, GitPullRequest, Info, ShieldCheck, Sparkles } from "lucide-react";
import { useCheckout } from "@/lib/checkout/store";
import {
  DiffViewer,
  EmptyState,
  ErrorBlock,
  FixStatusBadge,
  PageHeader,
  Panel,
  ProgressBlock,
} from "@/components/app/ui";
import type { FileChange } from "@/lib/checkout/types";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/fix")({
  head: () => ({
    meta: [
      { title: "Fix — CheckoutPilot" },
      { name: "description", content: "Review AI-generated PayPal checkout code changes." },
      { property: "og:title", content: "Fix — CheckoutPilot" },
      { property: "og:description", content: "Review AI-generated PayPal checkout code changes." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: FixPage,
});

function FixPage() {
  const { fix, scan, startFix, startVerify, selected, verify } = useCheckout();
  const navigate = useNavigate();
  const [active, setActive] = useState(0);
  const data = fix.data;

  return (
    <div className="space-y-6">
      <PageHeader
        step="Step 3 · Fix"
        title="Code upgrade"
        description="Review changes generated for the selected recommendations."
      />

      {fix.phase === "idle" && (
        <EmptyState
          icon={FileCode2}
          title="No fix generated"
          description={
            scan.data
              ? "Choose recommendations and generate a fix."
              : "Run an audit, then pick recommendations to fix."
          }
          action={
            <Link to={scan.data ? "/recommendations" : "/audit"} className="btn-primary">
              <Sparkles className="h-4 w-4" />{" "}
              {scan.data ? "Choose recommendations" : "Start audit"}
            </Link>
          }
        />
      )}
      {fix.phase === "running" && (
        <ProgressBlock
          label={`Generating fix for ${selected.length} recommendation(s)`}
          stage={fix.stage}
          progress={fix.progress}
        />
      )}
      {fix.phase === "error" && (
        <ErrorBlock title="Fix generation failed" message={fix.error} onRetry={startFix} />
      )}

      {data && fix.phase === "success" && (
        <div className="space-y-6 animate-in fade-in duration-500">
          <Panel className="p-5">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-lg",
                    data.confirmed ? "bg-success/10 text-success" : "bg-warning/10 text-warning",
                  )}
                >
                  {data.confirmed ? (
                    <GitPullRequest className="h-5 w-5" />
                  ) : (
                    <Info className="h-5 w-5" />
                  )}
                </div>
                <div>
                  <p className="font-medium text-foreground">
                    {data.confirmed
                      ? "Backend confirmed code changes"
                      : "Proposed changes — not applied"}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {data.summary ?? `${data.files.length} file(s) changed`}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <FixStatusBadge confirmed={data.confirmed} />
                {data.pull_request_url && (
                  <a
                    href={data.pull_request_url}
                    target="_blank"
                    rel="noreferrer"
                    className="btn-outline"
                  >
                    View pull request <ExternalLink className="h-4 w-4" />
                  </a>
                )}
                <button
                  className="btn-primary"
                  disabled={verify.phase === "running"}
                  onClick={() => {
                    // Go to the Proof page straight away; it shows the progress while the payment runs.
                    void startVerify();
                    navigate({ to: "/proof" });
                  }}
                >
                  <ShieldCheck className="h-4 w-4" />{" "}
                  {verify.phase === "running" ? "Verification running..." : "Verify in Sandbox"}
                </button>
              </div>
            </div>
          </Panel>

          <div className="grid gap-5 lg:grid-cols-[250px_1fr]">
            <div className="space-y-1">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Changed files
              </p>
              {data.files.map((f, i) => (
                <button
                  key={f.path}
                  onClick={() => setActive(i)}
                  className={cn(
                    "flex items-center gap-2.5 w-full text-left rounded-lg border px-3 py-2.5 text-sm transition",
                    active === i
                      ? "border-primary bg-primary/5 text-foreground shadow-sm"
                      : "border-transparent text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <FileCode2 className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate font-mono text-xs">{f.path}</span>
                  {f.category && f.category !== "other" && (
                    <span
                      className={cn(
                        "badge-pill shrink-0",
                        f.category === "sdk"
                          ? "bg-secondary text-foreground"
                          : "bg-success/10 text-success border border-success/20",
                      )}
                    >
                      {f.category}
                    </span>
                  )}
                </button>
              ))}
            </div>
            {data.files[active] && (
              <Panel className="min-w-0 p-0">
                <div className="overflow-hidden border-b border-border">
                  <p className="px-4 py-2 font-mono text-xs text-foreground bg-muted/50">
                    {data.files[active].path}
                  </p>
                </div>
                <div className="p-4 md:p-6">
                  <DiffViewer file={data.files[active]} />
                </div>
              </Panel>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
