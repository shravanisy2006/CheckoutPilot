# Deploy CheckoutPilot on Render

One Render **web service** runs everything from one link:

| Address | What it is |
|---|---|
| `https://<your-service>.onrender.com/` | the dashboard (Demo and Live mode) |
| `/api/...` and `/docs` | the backend API and its interactive docs |
| `localhost:8101` / `localhost:8102` *inside the service* | the example stores Inkwell & Co. (before / after) |

In Live mode, "Try the example store" scans `http://localhost:8101`. That is the store running
**inside the CheckoutPilot server**, so it works for every visitor.

## What you need

- A Render account (render.com) connected to GitHub. **No card needed: it runs on the free plan.**
- Your PayPal **Sandbox** keys, a **US Personal** Sandbox buyer account, and a Gemini key.

### How it fits into the free plan (512 MB memory, 0.1 CPU)

`FREE_TIER=true` (set in `render.yaml`) keeps every feature but uses the small machine carefully:

- the two example stores run inside the backend process (saves ~100 MB),
- Chromium starts with low-memory switches,
- only one scan / fix / proof / re-scan runs at a time (the next visitor waits their turn),
- waits are longer, because the CPU is about 10x slower than a laptop.

Measured: a full scan + fix + re-measure peaks at about 300 MB (limit 512 MB).
Expect each step to take about 1–3 minutes on the free CPU.

Free-plan limits to know:

- The service **sleeps after 15 minutes without visitors** and takes about a minute to wake up.
  Optional: a free uptime pinger (for example cron-job.org) calling `/api/health` every 10 minutes
  keeps it awake. One always-on service uses ~720–744 of the 750 free hours a month.
- When it sleeps or restarts, results kept in memory are cleared (Demo mode is never affected).

## Steps

1. Push the branch with `Dockerfile` and `render.yaml` to GitHub (merge it into `main`).
2. On Render: **New → Blueprint** → pick the CheckoutPilot repository → **Apply**.
   Render reads `render.yaml` and creates the service `checkoutpilot`.
3. Render asks for the secret values (they are never stored in Git):
   `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_SANDBOX_BUYER_EMAIL`,
   `PAYPAL_SANDBOX_BUYER_PASSWORD`, `GOOGLE_API_KEY`.
   Type them in. Never paste them anywhere else.
4. Wait for the first build (about 10–15 minutes: it builds the dashboard and installs Chromium).
5. Open the service URL, then:
   - **Demo mode** works straight away (a recorded real run).
   - **Live mode** → Audit → *Try the example store* → Start scan → Choose fixes → Generate fix
     → Verify in Sandbox. The proof makes two real PayPal Sandbox payments (1–2 minutes).
6. Put the link in the Devpost submission and the README.

## Built-in protection for a public demo

| Setting | Default | What it does |
|---|---|---|
| `RATE_LIMIT_PER_HOUR` | 30 | scans + fixes + proofs per visitor per hour (`0` = off) |
| `OUTPUTS_MAX_AGE_HOURS` | 24 | deletes old screenshots and patched copies |
| `VERIFY_HEADLESS` | true | the Sandbox verifier's browser runs without a window |
| `START_DEMO_STORES` | true | starts the two example stores inside the service |
| `FREE_TIER` | true (render.yaml) | low-memory mode for Render's free plan |
| `DASHBOARD_DIR` | /app/dashboard | serves the built dashboard from the same URL |

Only one browser job runs at a time; others wait up to 5 minutes, then get "busy, try again". Scans of real stores visit public
pages only, with the honest user agent `CheckoutPilot/1.0`.

## Run the same container on your computer (optional)

```bash
docker build -t checkoutpilot .
docker run -p 10000:10000 --env-file .env checkoutpilot
# open http://localhost:10000
```

## If something goes wrong

| What you see | What to do |
|---|---|
| Build fails at `pip install` with a Playwright version error | The base image tag in `Dockerfile` (`v1.63.0`) must match `playwright==1.63.0` on the same file. Change both together. |
| Service restarts, "out of memory" in the logs | Usually during the PayPal proof. Scan, fix and re-measure still work; for live proofs change `plan: free` to `plan: standard` (2 GB, paid). |
| A step is slow or times out | The free CPU is slow. Try again once the server is awake (open the link a minute before showing it). |
| Proof fails at the PayPal login | Check the buyer secrets on Render; the buyer must be a **US Personal** Sandbox account. PayPal sometimes asks extra security questions on server logins: the scan, fix and re-measure still work, and Demo mode shows a recorded real proof. |
| "This public demo allows 30 ..." | The per-visitor limit. Raise `RATE_LIMIT_PER_HOUR` on Render if needed. |
