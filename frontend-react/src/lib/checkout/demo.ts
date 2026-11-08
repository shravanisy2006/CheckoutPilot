import type { FixResult, ScanResult, VerificationResult } from "./types";

export const SCAN_STAGES = [
  "Loading storefront",
  "Navigating to checkout",
  "Inspecting PayPal SDK",
  "Analyzing mobile layout",
  "Ranking issues",
];
export const FIX_STAGES = ["Reading repository", "Planning changes", "Upgrading PayPal SDK", "Patching checkout", "Opening pull request"];
export const VERIFY_STAGES = ["Deploying preview", "Launching sandbox buyer", "Creating sandbox order", "Capturing evidence"];

export const demoScan = (store_url: string): ScanResult => ({
  scan_id: "demo_scan_7f21",
  store_url,
  health_score: 58,
  created_at: new Date().toISOString(),
  screenshots: { desktop: null, mobile: null },
  issues: [
    {
      id: "i1",
      severity: "critical",
      title: "Deprecated checkout.js SDK in use",
      explanation: "The store loads PayPal's legacy checkout.js, which no longer receives updates and lacks Pay Later and Venmo support.",
      evidence: ["<script src=\"https://www.paypalobjects.com/api/checkout.js\">", "paypal.Button.render() called on /cart"],
      surface: "both",
    },
    {
      id: "i2",
      severity: "high",
      title: "PayPal button hidden below the fold on mobile",
      explanation: "On a 390px viewport the PayPal button renders 1,240px down the page, after a long form.",
      evidence: ["Button offsetTop: 1240px (viewport 844px)", "Requires 2 scrolls to reach"],
      surface: "mobile",
    },
    {
      id: "i3",
      severity: "high",
      title: "Pay Later messaging not shown",
      explanation: "No Pay Later messaging component is present on product or cart pages.",
      evidence: ["No data-pp-message elements found"],
      surface: "both",
    },
    {
      id: "i4",
      severity: "medium",
      title: "Intent set to authorize without capture handler",
      explanation: "Orders are created with intent=authorize but no capture step was detected in the client flow.",
      evidence: ["createOrder: { intent: 'AUTHORIZE' }", "No onApprove capture call"],
      surface: "both",
    },
    {
      id: "i5",
      severity: "low",
      title: "Button style inconsistent with brand",
      explanation: "Button uses default gold styling with a rectangular shape while the store uses pill buttons.",
      evidence: ["style.shape = 'rect'"],
      surface: "desktop",
    },
  ],
  recommendations: [
    { id: "r1", issue_id: "i1", priority: 1, severity: "critical", title: "Migrate to the PayPal JavaScript SDK", description: "Replace checkout.js with sdk/js and the Buttons component.", rationale: "Modern SDK enables Venmo, Pay Later and smart eligibility.", estimated_conversion_impact: "+3–6% (estimate)" },
    { id: "r2", issue_id: "i2", priority: 2, severity: "high", title: "Move PayPal button above the form on mobile", description: "Render express checkout at the top of cart and checkout on small screens.", rationale: "Express options above the fold reduce friction for returning PayPal buyers.", estimated_conversion_impact: "+2–4% (estimate)" },
    { id: "r3", issue_id: "i3", priority: 3, severity: "high", title: "Add Pay Later messaging", description: "Add the messages component to product and cart pages.", rationale: "Shows installment options earlier in the journey.", estimated_conversion_impact: null },
    { id: "r4", issue_id: "i4", priority: 4, severity: "medium", title: "Switch to capture intent", description: "Use intent=capture and call capture in onApprove.", rationale: "Prevents uncaptured authorizations from expiring.", estimated_conversion_impact: null },
    { id: "r5", issue_id: "i5", priority: 5, severity: "low", title: "Align button style with storefront", description: "Set shape: 'pill' and layout: 'vertical'.", rationale: "Visual consistency builds trust at checkout.", estimated_conversion_impact: null },
  ],
});

export const demoFix = (ids: string[]): FixResult => ({
  fix_id: "demo_fix_19ac",
  confirmed: false,
  summary: `Demo: ${ids.length} recommendation(s) drafted. No repository was modified.`,
  pull_request_url: null,
  files: [
    {
      path: "templates/cart.html",
      category: "sdk",
      before: `<script src="https://www.paypalobjects.com/api/checkout.js"></script>\n<div id="paypal-button"></div>`,
      after: `<script src="https://www.paypal.com/sdk/js?client-id={{ PAYPAL_CLIENT_ID }}&components=buttons,messages&enable-funding=venmo,paylater"></script>\n<div id="paypal-button-container"></div>\n<div data-pp-message data-pp-placement="cart"></div>`,
    },
    {
      path: "static/js/checkout.js",
      category: "checkout",
      before: `paypal.Button.render({\n  env: 'production',\n  style: { shape: 'rect' },\n  payment: function (data, actions) {\n    return actions.payment.create({ intent: 'authorize' });\n  }\n}, '#paypal-button');`,
      after: `paypal.Buttons({\n  style: { shape: 'pill', layout: 'vertical' },\n  createOrder: () => fetch('/api/orders', { method: 'POST' })\n    .then((r) => r.json()).then((o) => o.id),\n  onApprove: (data) => fetch('/api/orders/' + data.orderID + '/capture', { method: 'POST' })\n}).render('#paypal-button-container');`,
    },
  ],
});

export const demoVerification = (): VerificationResult => ({
  verification_id: "demo_ver_44d0",
  passed: true,
  environment: "sandbox",
  status: "Simulated — no PayPal Sandbox call was made",
  order_id: null,
  simulated: true,
  evidence: [
    "Buttons component rendered in 412ms (simulated)",
    "Pay Later message visible on cart (simulated)",
    "Mobile button within first viewport (simulated)",
  ],
  screenshots: { before: null, after: null },
});
