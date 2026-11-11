# Deploy CheckoutPilot on Azure (Azure for Students)

One Azure **Web App** runs the whole app from one link: the dashboard (Demo and Live mode),
the API, and the two example stores. Nothing is cut: scan, fix, real PayPal Sandbox proof and
re-measure all work.

**Cost:** paid from the free **Azure for Students** credit (USD 100, no credit card). The
Basic B1 plan costs roughly USD 13 a month from that credit. If the credit ever runs out,
Azure switches the app off; it does not charge you. Check the balance at
<https://www.microsoftazuresponsorships.com/balance>.

How it fits together:

```
GitHub (main branch) --GitHub Action builds the image--> ghcr.io/shravanisy2006/checkoutpilot:latest
                                                                     |
                                              Azure Web App (Linux, B1) runs that image
                                                                     |
                                         https://<your-app-name>.azurewebsites.net
```

## Part 1: build the image on GitHub (about 15 minutes, once)

1. Merge your branch into `main`. That starts **Actions → Build container image**
   (`.github/workflows/docker-image.yml`). Wait for the green tick (10–15 minutes the first time).
2. Make the image public so Azure can download it:
   GitHub → your profile picture → **Your profile** → **Packages** → **checkoutpilot** →
   **Package settings** → **Danger Zone** → **Change visibility** → **Public** → type the name → confirm.
   (Only the app image becomes public. It contains no keys: those live in Azure.)

## Part 2: create the Web App (about 10 minutes)

1. Sign up at <https://azure.microsoft.com/free/students> with your college email.
2. Open <https://portal.azure.com> → **Create a resource** → **Web App** → **Create**.
3. **Basics** tab:
   - Subscription: **Azure for Students**
   - Resource group: **Create new** → `checkoutpilot-rg`
   - Name: e.g. `checkoutpilot-team` (this becomes `checkoutpilot-team.azurewebsites.net`)
   - Publish: **Container** · Operating System: **Linux**
   - Region: **Central India** (if Azure says the region is not allowed, pick another one from the list)
   - Pricing plan: **Create new** → **Basic B1** (1 core, 1.75 GB). B2 is faster if B1 feels slow.
4. **Container** tab:
   - Image source: **Other container registries** · Access type: **Public**
   - Registry server URL: `https://ghcr.io`
   - Image and tag: `shravanisy2006/checkoutpilot:latest`
   - Startup command: leave empty
5. **Review + create** → **Create**. Wait for "Your deployment is complete" → **Go to resource**.

## Part 3: settings and secrets (about 5 minutes)

1. Web App → **Settings → Environment variables** → **App settings** → **+ Add** for each row,
   then **Apply** (the app restarts):

| Name | Value |
|---|---|
| `WEBSITES_PORT` | `10000` |
| `WEBSITES_CONTAINER_START_TIME_LIMIT` | `1800` (the image is large; first start is slow) |
| `PAYPAL_CLIENT_ID` | your Sandbox client ID |
| `PAYPAL_CLIENT_SECRET` | your Sandbox secret |
| `PAYPAL_SANDBOX_BUYER_EMAIL` | the US **Personal** Sandbox buyer |
| `PAYPAL_SANDBOX_BUYER_PASSWORD` | its password |
| `GOOGLE_API_KEY` | your Gemini key |
| `PAYPAL_ENVIRONMENT` | `sandbox` |
| `PAYPAL_API_BASE` | `https://api-m.sandbox.paypal.com` |
| `AI_PROVIDER` | `gemini` |
| `AI_MODEL` | `gemini-3.8-flash` |
| `AI_FALLBACK_MODEL` | `gemini-3.5-flash-lite` |
| `MOCK_PAYPAL` | `false` |
| `MOCK_VERIFIER` | `false` |

   Type the secrets only here. Never in GitHub, chats or screenshots.
2. **Settings → Configuration → General settings** → **Always on: On** → **Save**
   (otherwise the app sleeps when nobody visits).
3. Optional: **Monitoring → Health check** → path `/api/health` → **Save**.

## Part 4: open it

Open `https://<your-app-name>.azurewebsites.net`. The very first start downloads the image and can
take 5–10 minutes; watch **Monitoring → Log stream** until you see `Application startup complete`.

Then: **Demo mode** works straight away. **Live mode** → Audit → *Try the example store* → Start scan
→ Choose fixes → Generate fix → Verify in Sandbox (two real PayPal Sandbox payments).

Long steps run as background jobs (`ASYNC_JOBS=true`, set in the Dockerfile): Azure cuts any
single request after 230 seconds, so the dashboard polls for progress instead of waiting on one request.

## Updating after a code change

Push to `main` → wait for the Action's green tick → Web App → **Overview** → **Restart**
(it downloads the new `latest` image).

## After judging

To stop using credit: Azure portal → **Resource groups** → `checkoutpilot-rg` → **Delete resource group**.

## If something goes wrong

| What you see | What to do |
|---|---|
| "RequestDisallowedByPolicy" or region not allowed | Azure for Students allows only some regions. Pick another region in Part 2. |
| "Application Error" page | **Log stream**. `ImagePullFailure` / unauthorized = the package is still private (Part 1, step 2) or the image name has a typo. |
| Site loads forever the first time | Normal for the first pull (large image). Check that `WEBSITES_CONTAINER_START_TIME_LIMIT` is `1800`. |
| Action fails at `pip install` with a Playwright error | The Dockerfile's image tag (`v1.63.0`) and `playwright==1.63.0` must match. Change both together. |
| Restarts / "out of memory" in the log | Scale up: **Settings → Scale up** → **B2**. |
| Proof fails at the PayPal login | Check the buyer settings; the buyer must be a **US Personal** Sandbox account. PayPal sometimes asks extra questions on server logins; scan, fix and re-measure still work, and Demo mode shows a recorded real proof. |
| "This public demo allows 30 ..." | The per-visitor limit. Add `RATE_LIMIT_PER_HOUR` with a higher number. |
