# Deploy for free: dashboard on Vercel, backend on Render

| Part | Where | Plan | What it runs |
|---|---|---|---|
| Dashboard | **Vercel** | Hobby (free) | the React dashboard: Demo mode works instantly, always on |
| Backend | **Render** | Free web service | API + scanner + PayPal Sandbox verifier + the two example stores |

```
judge's browser --> https://checkoutpilot.vercel.app   (dashboard, static files)
                         |  Live mode calls
                         v
                    https://checkoutpilot.onrender.com  (backend, Docker, FREE_TIER=true)
                         |  scans its own example stores on localhost:8101 / 8102
```

Cost: ₹0. Nothing changes for local runs: `python run_demo.py` works exactly as before.

## What the free backend means

- Render's free plan has 512 MB memory and 0.1 CPU. `FREE_TIER=true` (only set on Render) keeps every
  feature but runs the stores inside the backend process, starts Chromium with low-memory switches,
  runs one scan / fix / proof at a time, and waits longer. Measured peak: about 300 MB.
- Each Live step takes about 1–3 minutes. Long steps run as background jobs that the dashboard polls.
- The backend **sleeps after 15 minutes without visitors**; the first Live click then waits about a
  minute while it wakes. Before a demo, open `https://<backend>.onrender.com/api/health` once.
- When it sleeps or restarts, Live results kept in memory are cleared. Demo mode is never affected.

## Part 1: backend on Render (about 20 minutes, mostly waiting)

1. Make sure the code with `render.yaml` and `Dockerfile` is on `main` on GitHub.
2. <https://render.com> → sign in with GitHub → **New** → **Blueprint** → pick **CheckoutPilot** → **Apply**.
   Render reads `render.yaml` and creates the free web service `checkoutpilot`.
3. It asks for the secret values (typed only here, never in Git or chats):
   `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_SANDBOX_BUYER_EMAIL` (a **US Personal** Sandbox
   buyer), `PAYPAL_SANDBOX_BUYER_PASSWORD`, `GOOGLE_API_KEY`.
4. Wait for the first build and deploy (10–20 minutes: it builds the image and installs Chromium).
   Watch **Logs** until you see `Application startup complete`.
5. Copy the service URL from the top of the page, e.g. `https://checkoutpilot.onrender.com`.
   Check it: `https://checkoutpilot.onrender.com/api/health` shows `{"status":"ok", ...}`.

## Part 2: dashboard on Vercel (about 10 minutes)

1. <https://vercel.com> → **Add New…** → **Project** → import **CheckoutPilot** from GitHub.
2. **Project Name:** `checkoutpilot` (the backend only accepts calls from addresses that start with
   `checkoutpilot` and end in `.vercel.app`).
3. **Root Directory:** click **Edit** → choose `frontend-react`. The build settings come from
   `frontend-react/vercel.json`; leave the other fields as they are.
4. **Environment Variables:** add `VITE_API_BASE_URL` = the Render URL from Part 1 (no `/` at the end),
   e.g. `https://checkoutpilot.onrender.com`.
5. **Deploy**. After about 2 minutes Vercel shows the link, e.g. `https://checkoutpilot.vercel.app`.

## Part 3: try it

1. Open the Vercel link. **Demo mode** works straight away.
2. Switch to **Live** → Audit → *Try the example store* → Start scan → Choose fixes → Generate fix →
   Verify in Sandbox. (First click may wait ~1 minute if the backend was asleep.)
3. Put the Vercel link in the Devpost submission and the README.

## Changing things later

- Push to `main`: Vercel redeploys the dashboard by itself; Render redeploys the backend by itself.
- Changed the Render URL? Update `VITE_API_BASE_URL` on Vercel → **Deployments** → **Redeploy**
  (the address is built into the dashboard).

## If something goes wrong

| What you see | What to do |
|---|---|
| Live mode: "Could not reach backend" | Backend asleep or still deploying: open `<backend>/api/health`, wait a minute, retry. Check `VITE_API_BASE_URL` on Vercel (https, no `/` at the end), then Redeploy. |
| Browser console: "blocked by CORS policy" | The Vercel project name must start with `checkoutpilot`. Or add your exact Vercel URL as `CORS_ORIGINS` on Render. |
| Render build fails at `pip install` with a Playwright error | The Dockerfile's image tag (`v1.63.0`) and `playwright==1.63.0` must match. Change both together. |
| Render log: "out of memory", service restarts | Usually during the PayPal proof. Scan, fix and re-measure still work; Demo mode shows a recorded real proof. |
| A Live step is very slow | Normal on the free CPU (about 10x slower than a laptop). Record the demo video locally. |
| Proof fails at the PayPal login | Check the buyer secrets; the buyer must be a **US Personal** Sandbox account. PayPal sometimes asks extra questions on server logins. |
