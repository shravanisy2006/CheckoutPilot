# 🧭 CheckoutPilot

**An AI agent that audits a store's PayPal checkout, ranks the fixes by business impact, writes the upgrade, and proves it works with a PayPal Sandbox purchase.**

Built for the *Build What's Next with PayPal and AI* hackathon (2026).

> **Status:** initial boilerplate. All modules contain placeholder functions with TODOs. The frontend and backend run, but no real scanning, AI or PayPal calls happen yet.

---

## 1. Introduction

CheckoutPilot starts from a single store URL. It walks the checkout the way a shopper would, finds what is holding PayPal conversion back, and helps the merchant fix it — then verifies the fix with a real sandbox payment.

## 2. Problem statement

PayPal has built a faster, better-converting checkout: saved PayPal accounts, biometric login, Pay Later messaging and the newer JavaScript SDK v6. But each feature only helps when a merchant changes their own code, and many stores still run older integrations. PayPal has reported that branded checkout volume grew only 1–2% for four consecutive quarters, and that merchants needed far more integration help than expected. Shoppers get a clunkier checkout and stores lose sales.

## 3. Proposed solution

CheckoutPilot works in four stages: **find → rank → fix → prove**.

1. **Scan** the store's checkout in a headless browser (desktop and mobile).
2. **Detect** gaps with rule checks and a vision-capable AI model.
3. **Rank** fixes by expected impact, using PayPal's published figures as labelled assumptions.
4. **Upgrade** the code with an AI agent that opens a pull request (when repo access is given).
5. **Verify** with an automated PayPal Sandbox test purchase, before and after.

## 4. Key features (planned)

- Outside-in audit from just a store URL — no code access needed.
- PayPal-specific checks: SDK version, button placement, saved accounts, Pay Later, Venmo.
- Impact-ranked recommendations with clearly labelled assumptions.
- AI-generated upgrade as a pull request.
- Before/after proof with a PayPal Sandbox purchase.

## 5. Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | Streamlit |
| Backend | FastAPI + Uvicorn |
| Browser automation | Playwright (Python) |
| AI | Vision-capable LLM API (provider to be chosen) |
| Payments | PayPal REST APIs (Sandbox): Orders v2, Payment Method Tokens, Webhooks |
| Testing | pytest |
| Config | python-dotenv |

## 6. Project structure

```
CheckoutPilot/
├── backend/                  # FastAPI application
│   ├── main.py               # entry point (creates the app, CORS, routes)
│   ├── core/config.py        # settings read from .env
│   ├── api/
│   │   ├── router.py         # combines all route files
│   │   └── routes/           # health.py, scan.py, reports.py
│   ├── services/scan_service.py  # calls the modules in order
│   └── schemas/scan.py       # request/response models
├── frontend/                 # Streamlit application
│   ├── app.py                # homepage: URL input, scan button, result tabs
│   └── api_client.py         # HTTP calls to the backend
├── scanner/                  # Playwright checkout scanner
├── ai_engine/                # rule + vision-model gap detection
├── impact_ranker/            # business impact ranking
├── code_agent/               # AI code upgrade agent
├── paypal_integration/       # PayPal Sandbox API client
├── sandbox_verifier/         # sandbox test purchase verification
├── tests/                    # pytest tests
├── docs/architecture.md      # data flow and module contracts
├── .streamlit/config.toml    # Streamlit theme
├── .env.example              # template for your .env file
├── requirements.txt
├── pytest.ini
├── LICENSE                   # MIT
└── README.md
```

## 7. Installation

You need **Python 3.10 or newer** and **Git**.

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/CheckoutPilot.git
cd CheckoutPilot

# 2. Create a virtual environment
python -m venv venv

# 3. Activate it
#    Windows (Command Prompt):   venv\Scripts\activate
#    Windows (PowerShell):       venv\Scripts\Activate.ps1
#    macOS / Linux:              source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Install the browser Playwright uses (one time only)
playwright install chromium
```

## 8. Run the frontend

From the project root folder (with the virtual environment active):

```bash
streamlit run frontend/app.py
```

Open http://localhost:8501. The page works even if the backend is off — the sidebar will just show a warning.

## 9. Run the backend

Open a **second terminal**, activate the virtual environment, and from the project root run:

```bash
uvicorn backend.main:app --reload
```

- Health check: http://localhost:8000/api/health
- Interactive API docs: http://localhost:8000/docs

Run the tests with:

```bash
pytest
```

## 10. Environment variables

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

Then open `.env` and fill in your own values:

| Variable | What it is |
| --- | --- |
| `BACKEND_URL` | Where the frontend finds the backend (default `http://localhost:8000`) |
| `CORS_ORIGINS` | Origins allowed to call the backend |
| `AI_PROVIDER` and `*_API_KEY` | Your chosen AI provider and its key |
| `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` | From developer.paypal.com → Apps & Credentials → **Sandbox** |
| `PAYPAL_SANDBOX_BUYER_EMAIL` / `PASSWORD` | A sandbox personal (buyer) test account |
| `GITHUB_TOKEN` | For the code agent to open pull requests |

⚠️ **Never commit `.env` or real keys.** It is already listed in `.gitignore`. Use Sandbox credentials only.

## 11. Contributing (Git workflow)

`main` always holds working code. Nobody pushes to `main` directly.

**1. Get the latest code before starting work**

```bash
git checkout main
git pull origin main
```

**2. Create a branch for your module or feature**

Name it `feature/<module>-<short-description>`, for example:

```bash
git checkout -b feature/scanner-playwright-walk
```

**3. Commit small, clear changes**

```bash
git add .
git commit -m "scanner: save screenshots for each checkout step"
```

**4. Push your branch**

```bash
git push -u origin feature/scanner-playwright-walk
```

**5. Open a pull request** on GitHub from your branch into `main`. In the description, say what changed and how to test it. Ask one teammate to review.

**6. Before opening a PR, make sure:**

- `pytest` passes.
- Both apps still start.
- You only changed files in your own module, unless the team agreed otherwise.
- If you changed a module's input/output shape, you updated `docs/architecture.md` and the tests.
- No API keys or `.env` files are included.

**7. Keep your branch up to date** if `main` changes while you work:

```bash
git checkout main
git pull origin main
git checkout feature/your-branch
git merge main
```

## License

MIT — see [LICENSE](LICENSE).
