# CheckoutPilot Architecture

## How data flows

```
Store URL
   │
   ▼
scanner            → walks product → cart → checkout, saves screenshots, HTML, scripts
   │  (dict)
   ▼
ai_engine          → rule checks + vision-model checks → list of gaps
   │  (list[dict])
   ▼
impact_ranker      → sorts gaps by expected business impact (labelled assumptions)
   │  (list[dict])
   ▼
code_agent         → (needs repo access) writes the fix and opens a pull request
   │
   ▼
sandbox_verifier   → completes a PayPal Sandbox purchase before and after the fix
   │                 (uses paypal_integration for Orders API checks)
   ▼
Report shown in the Streamlit frontend
```

## Module contracts

Modules talk to each other only through **plain Python dictionaries and lists**.
No module imports another module's internals. This lets each teammate work on one
module without breaking the others.

| Module | Main function | Input | Output |
| --- | --- | --- | --- |
| `scanner` | `scan_store(store_url, include_mobile)` | URL | `{"store_url", "pages": [...]}` |
| `ai_engine` | `analyze_checkout(scan_data)` | scanner output | `[{"gap_id", "title", "severity", "description"}]` |
| `impact_ranker` | `rank_gaps(gaps)` | gaps | gaps + `"estimated_impact"`, sorted |
| `code_agent` | `create_upgrade_plan(repo, gaps)`, `generate_upgrade(repo, plan)` | repo + gaps | plan / PR info |
| `paypal_integration` | `PayPalClient` methods | order details | PayPal API responses |
| `sandbox_verifier` | `verify_checkout(store_url, label)` | URL | purchase result |

If you change a function's input or output shape, update this table, the docstring,
and `tests/test_modules.py` in the same pull request.

## Backend and frontend

- **Backend (FastAPI):** `backend/main.py` → `backend/api/router.py` → route files in
  `backend/api/routes/` → `backend/services/scan_service.py`, which calls the modules.
- **Frontend (Streamlit):** `frontend/app.py` calls the backend over HTTP using
  `frontend/api_client.py`. It never imports backend code, so both apps run independently.
