import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ScanSearch, Sparkles, Wand2 } from "lucide-react";
import { useCheckout } from "@/lib/checkout/store";
import {
  EmptyState,
  PageHeader,
  Panel,
  ProgressBlock,
  RecommendationCard,
  SeverityBadge,
} from "@/components/app/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/recommendations")({
  head: () => ({
    meta: [
      { title: "Recommendations — CheckoutPilot" },
      { name: "description", content: "Prioritized PayPal checkout improvements for your store." },
      { property: "og:title", content: "Recommendations — CheckoutPilot" },
      {
        property: "og:description",
        content: "Prioritized PayPal checkout improvements for your store.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: RecsPage,
});

function RecsPage() {
  const { scan, selected, toggleSelected, setSelected, startFix, fix } = useCheckout();
  const navigate = useNavigate();
  const recs = [...(scan.data?.recommendations ?? [])].sort((a, b) => a.priority - b.priority);

  if (!scan.data)
    return (
      <>
        <PageHeader
          step="Step 2 · Plan"
          title="Recommendations"
          description="Prioritized improvements generated from your audit."
        />
        <EmptyState
          icon={Sparkles}
          title="Run an audit first"
          description="Recommendations appear once a checkout scan completes."
          action={
            <Link to="/audit" className="btn-primary">
              <ScanSearch className="h-4 w-4" /> Go to audit
            </Link>
          }
        />
      </>
    );

  const go = () => {
    startFix();
    navigate({ to: "/fix" });
  };

  return (
    <div className="space-y-8">
      <PageHeader
        step="Step 2 · Plan"
        title="Recommendations"
        description="Select the improvements CheckoutPilot should implement."
        action={
          <button
            disabled={!selected.length || fix.phase === "running"}
            onClick={go}
            className="btn-primary"
          >
            <Wand2 className="h-4 w-4" /> Generate fix ({selected.length})
          </button>
        }
      />

      <div className="mb-4 flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {recs.length} recommendations · {selected.length} selected
        </span>
        <div className="flex gap-3">
          <button className="btn-tertiary" onClick={() => setSelected(recs.map((r) => r.id))}>
            Select all
          </button>
          <button className="btn-tertiary" onClick={() => setSelected([])}>
            Clear
          </button>
        </div>
      </div>

      {fix.phase === "running" && (
        <ProgressBlock label="Generating fix" stage={fix.stage} progress={fix.progress} />
      )}

      <div className="space-y-3">
        {recs.map((r) => {
          const on = selected.includes(r.id);
          return (
            <RecommendationCard key={r.id} rec={r} on={on} onToggle={() => toggleSelected(r.id)} />
          );
        })}
      </div>

      <div className="mt-6">
        <Panel className="p-0 border-0 shadow-none bg-transparent">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-3">
            Unselected recommendations remain in draft.
          </p>
        </Panel>
      </div>
    </div>
  );
}
