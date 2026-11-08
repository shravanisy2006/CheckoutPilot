# API contract: backend ↔ dashboard

The backend (FastAPI) and the dashboard must use **exactly these field names**.
A complete real example of every response is in [`sample_result.json`](sample_result.json):
use it for the dashboard's Demo Mode, and make the backend return the same shape in Live Mode.

Base URL: `http://localhost:8000` (from `BACKEND_URL`). All routes start with `/api`.
Severity is always `"high"`, `"medium"` or `"low"` (there is no "critical").

| Step | Endpoint | Sample in `sample_result.json` |
|---|---|---|
| Health check | `GET /api/health` | — |
| 1. FIND | `POST /api/scan` | `scan` |
| 2. FIX | `POST /api/fix` | `fix` |
| 3. PROVE | `POST /api/verify` | `verify` |
| Re-scan after fix | `POST /api/scan` on the patched store | `rescan_after_fix` |
| Saved report | `GET /api/reports/{scan_id}` | `scan` + `fix` + `verify` together |
| Screenshots | `GET /files/{path}` | every `screenshot_url` |

---

## 1. `POST /api/scan`: find issues

**Request**
```json
{ "store_url": "http://localhost:8101", "include_mobile": true }
```

**Response** (`sample_result.json → scan`)

| Field | Type | Meaning |
|---|---|---|
| `scan_id` | string | Made by the backend, e.g. `scan_20261108_132000_ab12` |
| `store_url` | string | The URL that was scanned |
| `scanned_at` | string | ISO time |
| `status` | `"completed"` \| `"partial"` \| `"failed"` | From the scanner |
| `paypal_sdk_version` | `"v4"` \| `"v5"` \| `"v6"` \| `"none"` | Scanner's `detected_sdk_version` (`"unknown"` → `"none"`) |
| `health_score` | int 0–100 | `impact_ranker.health_score(issues)` |
| `health_label` | `"poor"` (<50) \| `"fair"` (50–79) \| `"good"` (80+) | |
| `issue_counts` | `{high, medium, low}` | For the summary cards |
| `issues` | list | Ranked, most important first (below) |
| `pages` | list | One per page × viewport (below) |
| `warnings` | list of strings | Show them; never hide them |

**Each issue** (from `rank_issues(analyze_checkout_detailed(scan)["issues"])`):

| Field | Example |
|---|---|
| `issue_id` | `"sdk_outdated"` |
| `title` | `"PayPal JavaScript SDK v5 is outdated"` |
| `category` | `"sdk"`, `"presentment"`, `"mobile"`, `"vaulting"`, `"messaging"` |
| `severity` | `"high"` |
| `source` | `"rule"`, `"vision"` or `"rule+vision"` |
| `confidence` | `1.0` |
| `evidence` | Why we think so (one sentence) |
| `screenshot_url` | `/files/scans/<scan_id>/mobile_checkout.png` or `""` |
| `fixable_by_agent` | `true` only for `sdk_outdated`, `no_paypal_on_cart` (and the layout fix shown with them) |
| `impact.score` | int 0–100, show as "Impact 100/100" |
| `impact.rank` | 1, 2, 3… |
| `impact.rationale` | One sentence |
| `impact.assumption` | Cited text, ends with "Effect not measured for this store." |
| `impact.assumption_source` | e.g. `"PayPal developer docs: Upgrade from JavaScript SDK v5 to v6"` |

**Never show invented conversion percentages.** Show `impact.score` plus `impact.assumption_source`.

**Each page**: `step` (`product`, `cart`, `checkout`), `viewport` (`desktop`, `mobile`), `url`, `screenshot_url`, `paypal_found` (bool), `paypal_visible_without_scroll` (bool).

The scanner itself returns more (`html`, `scripts`, raw `paypal_elements`); the backend keeps that in the saved report but should **not** send `html` to the dashboard.

---

## 2. `POST /api/fix`: write the upgrade

**Request**
```json
{ "scan_id": "scan_demo_legacy", "issue_ids": ["sdk_outdated", "no_paypal_on_cart", "button_below_fold_mobile"] }
```

**Response** (`sample_result.json → fix`)

| Field | Meaning |
|---|---|
| `fix_id` | Made by the backend |
| `scan_id` | The scan it fixes |
| `status` | `"proposed"` (not applied) → `"verified"` → `"approved"` / `"rejected"` |
| `issue_ids` | What it fixes |
| `summary` | One paragraph for the merchant |
| `explanation` | List of `{issue_id, what_changed, files}` |
| `files` | List of `{path, change_type ("modified"/"added"/"deleted"), diff (unified diff text), lines_added, lines_removed}` |
| `branch` | `"feature/paypal-checkout-upgrade"` |
| `pr_url` | Link once the pull request exists, else `""` |
| `patched_store_dir` | The **copy** that was patched (the original is never touched) |

The upgrade goes **v5 → v6**: `https://www.sandbox.paypal.com/web-sdk/v6/core`, `paypal.createInstance(...)`,
`createPayPalOneTimePaymentSession(...)`, `<paypal-button>`. Not `paypal.com/sdk/js` (that is v5).

---

## 3. `POST /api/verify`: prove it with a Sandbox payment

**Request**
```json
{ "fix_id": "fix_demo_legacy" }
```
The backend starts the original store and the patched copy (`demo_stores.serve.start_store`), runs
`sandbox_verifier.verify_checkout` on each, and compares them with `compare_runs`.
This takes 1–2 minutes: show a progress state.

**Response** (`sample_result.json → verify`)

| Field | Meaning |
|---|---|
| `verification_id`, `fix_id` | IDs |
| `before`, `after` | One verifier result each (below) |
| `safe_to_approve` | `true` only if the **after** payment completed |
| `summary` | e.g. "Checkout works before and after the upgrade." |
| `changes` | e.g. `["PayPal SDK v5 -> v6"]`; a `"REGRESSION…"` entry means do not approve |

**Each verifier result**: `purchase_succeeded`, `order_id`, `order_status` (`"COMPLETED"`), `amount`, `currency`,
`paypal_sdk`, `api_confirmed`, `screenshots` (list of `/files/...` URLs), `steps` (list of `{name, ok, detail, at_seconds}`),
`error_code`, `error_message`, `warnings`, `duration_seconds`.

Label a result **"Real PayPal Sandbox payment"** when `api_confirmed` is true, and **"Simulated"** only when the
backend runs with `MOCK_VERIFIER=true`.

---

## Screenshots: `GET /files/{path}`

The scanner and verifier save PNGs under `outputs/`. The backend serves that folder:
```python
app.mount("/files", StaticFiles(directory="outputs"), name="files")
```
and turns every saved path into a URL, e.g. `outputs/scans/<scan_id>/mobile_checkout.png` → `/files/scans/<scan_id>/mobile_checkout.png`.

In **Demo Mode** (no backend) the dashboard uses the images committed in `docs/images/`
(`before_after_mobile_checkout.png`, `before_after_cart.png`, `sandbox_proof.png`) instead of `/files/...` URLs.

## Errors

Any failure returns HTTP 4xx/5xx with:
```json
{ "detail": { "code": "PAYPAL_NOT_CONFIGURED", "message": "Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET (Sandbox) in .env." } }
```
The dashboard shows `message` and keeps the user's input.

## CORS

The dashboard's address must be in `CORS_ORIGINS` in `.env` (e.g. `http://localhost:8080,http://localhost:5173`
for a Vite/Lovable app), or the browser will block the calls.
