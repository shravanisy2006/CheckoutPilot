import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useRef } from "react";
import { useCheckout } from "@/lib/checkout/store";
import { Play, ScanSearch, ShieldCheck, Sparkles } from "lucide-react";
import { SimulatedBanner } from "@/components/app/ui";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "CheckoutPilot — PayPal checkout optimization" },
      {
        name: "description",
        content: "Scan, fix, and verify your PayPal checkout with AI-powered recommendations.",
      },
      { property: "og:title", content: "CheckoutPilot — PayPal checkout optimization" },
      {
        property: "og:description",
        content: "Find it. Fix it. Prove it. CheckoutPilot optimizes PayPal checkouts.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: LandingPage,
});

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
      <span className="font-display text-[17px] font-medium tracking-tight text-foreground">
        CheckoutPilot
      </span>
    </div>
  );
}

function LandingPage() {
  const { mode, setMode } = useCheckout();
  const navigate = useNavigate();
  const howWorksRef = useRef<HTMLDivElement>(null);

  const exploreDemo = () => {
    setMode("demo");
    navigate({ to: "/audit" });
  };

  const scrollToHowWorks = () => {
    howWorksRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-primary/30 selection:text-primary-foreground">
      {/* Navbar */}
      <nav className="border-b border-sidebar bg-background/80 px-4 py-3.5 backdrop-blur-sm sticky top-0 z-20">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link to="/">
            <Brand />
          </Link>
          <div className="hidden md:flex items-center gap-6 text-sm font-medium text-muted-foreground">
            <button
              onClick={exploreDemo}
              className="text-primary hover:text-primary/90 transition-colors font-medium"
            >
              Explore Demo
            </button>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="px-4 pt-16 pb-32 md:pt-24 md:pb-40 relative overflow-hidden">
        {/* Atmospheric gradient orbs */}
        <div className="landing-hero-glow landing-hero-glow-1" />
        <div className="landing-hero-glow landing-hero-glow-2" />
        <div className="landing-hero-glow landing-hero-glow-3" />

        <div className="max-w-6xl mx-auto relative z-10">
          <div className="grid lg:grid-cols-12 gap-12 items-start lg:items-center">
            {/* Content column */}
            <div className="lg:col-span-7 space-y-8">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3 block">
                Welcome to the future of checkout
              </p>

              <h1 className="font-display font-light text-[96px] leading-[1.02] tracking-tight sm:text-[88px] lg:text-[104px] xl:text-[104px] text-foreground mb-4">
                CheckoutPilot.
              </h1>

              <h2 className="section-heading text-2xl font-light tracking-tight leading-[1.15] text-foreground mb-6 sm:text-3xl">
                Find it. Fix it. Prove it.
              </h2>

              <p className="text-lg text-muted-foreground max-w-xl leading-relaxed">
                The AI-powered PayPal checkout optimization platform. Scan your storefront, receive
                ranked recommendations, generate production-ready code fixes, and verify results
                with PayPal Sandbox evidence.
              </p>

              <div className="flex flex-col sm:flex-row gap-4">
                <button
                  onClick={exploreDemo}
                  className="btn-primary flex-1 sm:flex-none justify-center"
                >
                  <Play className="h-4 w-4 mr-2" /> Explore Demo
                </button>
                <button
                  onClick={scrollToHowWorks}
                  className="btn-outline flex-1 sm:flex-none justify-center"
                >
                  How it works
                </button>
              </div>
            </div>

            {/* Dashboard preview column */}
            <div className="lg:col-span-5 relative">
              <div className="landing-card p-6 relative overflow-hidden">
                {/* Sample data label - separate layout area, no overlap */}
                <div className="flex justify-between items-start mb-5 pt-1">
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-destructive" />
                    <div className="h-2 w-2 rounded-full bg-warning" />
                    <div className="h-2 w-2 rounded-full bg-success" />
                  </div>
                  <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-2.5 py-0.5 text-[10px] font-semibold text-primary uppercase tracking-tighter">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary" /> Real demo result
                  </div>
                </div>

                <div className="flex items-center justify-between mb-5">
                  <span className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wider">
                    CheckoutPilot
                  </span>
                </div>

                {/* Health score mini-card */}
                <div className="flex items-center justify-between mb-5 p-4 rounded-xl bg-secondary border border-border/50">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Checkout health
                    </p>
                    <p className="font-display text-lg font-light tabular-nums">21 / 100</p>
                  </div>
                  <div className="relative w-12 h-12">
                    <svg className="w-full h-full transform -rotate-90">
                      <circle
                        cx="24"
                        cy="24"
                        r="20"
                        stroke="var(--color-border)"
                        strokeWidth="5"
                        fill="none"
                        className="text-muted-foreground/20"
                      />
                      <circle
                        cx="24"
                        cy="24"
                        r="20"
                        stroke="currentColor"
                        strokeWidth="5"
                        fill="none"
                        className="text-destructive transition-all duration-700"
                        strokeDasharray="125"
                        strokeDashoffset="99"
                      />
                    </svg>
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <span className="font-display text-[10px] font-light tabular-nums text-destructive">
                        21
                      </span>
                    </div>
                  </div>
                </div>

                {/* Issue list preview */}
                <div className="space-y-3">
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-background border border-border/50">
                    <div className="h-7 w-7 shrink-0 rounded-lg bg-secondary flex items-center justify-center">
                      <ScanSearch className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">PayPal SDK v5 is outdated</p>
                      <p className="text-xs text-muted-foreground">
                        Upgrade to JavaScript SDK v6
                      </p>
                    </div>
                    <span className="severity-badge severity-high">High</span>
                  </div>
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-background border border-border/50">
                    <div className="h-7 w-7 shrink-0 rounded-lg bg-secondary flex items-center justify-center">
                      <Sparkles className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">PayPal button below fold on mobile</p>
                      <p className="text-xs text-muted-foreground">
                        Move PayPal above the form
                      </p>
                    </div>
                    <span className="severity-badge severity-medium">Medium</span>
                  </div>
                  <div className="flex items-center gap-3 p-3 rounded-lg bg-background border border-border/50">
                    <div className="h-7 w-7 shrink-0 rounded-lg bg-secondary flex items-center justify-center">
                      <ShieldCheck className="h-3.5 w-3.5 text-primary" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium">Sandbox payment verified</p>
                      <p className="text-xs text-muted-foreground">
                        Real Sandbox order, status COMPLETED
                      </p>
                    </div>
                    <span className="severity-badge severity-low">Real</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Three steps */}
      <section ref={howWorksRef} id="how-it-works" className="px-4 py-24 bg-secondary">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="section-heading text-3xl font-light tracking-tight mb-4">
              How CheckoutPilot works
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
              From audit to proof in three steps. Demo Mode replays real results, no setup needed.
            </p>
          </div>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                number: "01",
                title: "Find",
                icon: ScanSearch,
                pill: "severity-medium",
                description:
                  "Scan a store's PayPal checkout on desktop and mobile, the way a shopper sees it. We detect an outdated PayPal SDK, PayPal missing from the cart or product page, and PayPal buttons hidden below the fold on phones.",
              },
              {
                number: "02",
                title: "Fix",
                icon: Sparkles,
                pill: "severity-high",
                description:
                  "Review recommendations ranked by impact, each tied to a cited PayPal source. Pick the fixes and get the code change (SDK v5 → v6, PayPal on the cart) as a reviewable diff.",
              },
              {
                number: "03",
                title: "Prove",
                icon: ShieldCheck,
                pill: "severity-medium",
                description:
                  "Prove the checkout still works with a real PayPal Sandbox payment before and after the fix. Download a PDF report with every finding and result.",
              },
            ].map((step, idx) => (
              <div
                key={step.title}
                className={cn(
                  "landing-card p-8",
                  idx === 0 && "ring-2 ring-primary/30 border-primary/20",
                )}
              >
                <div className="flex items-center gap-3 mb-6">
                  <div
                    className={cn(
                      "landing-feature-icon",
                      step.pill === "severity-medium"
                        ? "text-accent-foreground"
                        : "text-warning-foreground",
                    )}
                  >
                    <step.icon className="h-5 w-5" />
                  </div>
                  <span className="font-mono text-sm font-medium text-muted-foreground">
                    {step.number}
                  </span>
                </div>
                <h3 className="section-heading text-xl font-light mb-3">{step.title}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{step.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
