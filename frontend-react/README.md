# CheckoutPilot Frontend

React + TypeScript dashboard for PayPal checkout optimization. Built with TanStack Start, Tailwind CSS, and Lucide icons.

## Project Structure

```
frontend-react/
├── src/
│   ├── routes/           # TanStack Start file-based routes
│   │   ├── index.tsx     # Landing page
│   │   ├── audit.tsx     # Checkout audit (URL input, health score, issues)
│   │   ├── recommendations.tsx  # Selectable fixes with impact estimates
│   │   ├── fix.tsx       # Before/after code diff viewer
│   │   └── proof.tsx     # Sandbox verification report + PDF download
│   ├── components/
│   │   ├── app/          # Shell (top nav), shared UI (Panels, badges, etc.)
│   │   └── ui/           # shadcn/ui primitive components
│   ├── lib/checkout/     # State management, API client, demo data, types
│   │   ├── store.tsx     # CheckoutProvider (Demo/Live mode, scan/fix/verify)
│   │   ├── api.ts        # Backend API client (FastAPI integration)
│   │   ├── demo.ts       # Demo mode sample data
│   │   └── types.ts      # TypeScript interfaces
│   └── test/             # Vitest test files
├── public/               # Static assets (favicon, robots.txt)
├── vite.config.ts        # TanStack Start + Vite config
├── tsconfig.json         # TypeScript config
├── eslint.config.js      # ESLint config
├── components.json       # shadcn/ui config
├── package.json          # Dependencies
└── README.md             # This file
```

## Installation

### Prerequisites

- [Bun](https://bun.sh/) (recommended) or [Node.js](https://nodejs.org/) 18+

### Install Dependencies

From the `frontend-react/` directory:

```bash
# Using bun (recommended)
bun install

# Or using npm
npm install
```

## Starting the Frontend

### Development Mode

```bash
# Using bun
bun dev

# Or using npm
npm run dev
```

The frontend will be available at `http://localhost:5173` (default Vite port).

### Production Build

```bash
# Using bun
bun run build

# Or using npm
npm run build
```

### Preview Production Build

```bash
# Using bun
bun preview

# Or using npm
npm run preview
```

## Demo Mode vs Live Mode

The frontend supports two data sources, toggled via the top navigation:

### Demo Mode (default)
- Uses sample data for all scan, fix, and verification results
- No backend API calls are made
- Safe for demonstrations and hackathon presentations
- All results are clearly labeled as "Simulated" or "Demo Mode"
- **No real PayPal transactions occur**

### Live Mode
- Connects to the CheckoutPilot backend API
- Requires `VITE_API_BASE_URL` environment variable set to the backend URL
- Real scan, fix, and verification operations are performed
- Set the environment variable before starting:

```bash
# Using .env file
echo "VITE_API_BASE_URL=http://localhost:8000" > .env

# Or export directly
export VITE_API_BASE_URL=http://localhost:8000
```

## Backend Integration Points

The frontend communicates with the CheckoutPilot Python backend (FastAPI) via REST API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/scans` | POST | Create a checkout scan job |
| `/api/scans/{id}` | GET | Get scan results |
| `/api/jobs/{id}` | GET | Poll job status |
| `/api/fixes` | POST | Generate code fixes |
| `/api/verifications` | POST | Create Sandbox verification |
| `/api/verifications/{id}` | GET | Get verification results |

The backend is expected to run at `VITE_API_BASE_URL` (default: `http://localhost:8000`).

Configure CORS on the backend to allow requests from the frontend origin.

## Workflow

1. **Audit** (`/audit`): Enter a store URL, optionally enable mobile scan, and start the audit. View health score, severity summary, ranked issues, and checkout preview.
2. **Recommendations** (`/recommendations`): Select fixes to apply, view priority/severity/rationale/impact estimates, then generate a fix.
3. **Fix** (`/fix`): Review before/after code diffs for changed files, view fix status, then verify in Sandbox.
4. **Proof** (`/proof`): View verification results, evidence, and before/after comparison. Download a PDF report.

## Testing

```bash
# Using bun
bun run test

# Or using npm
npm run test
```

Runs Vitest tests for routing and checkout state management.

## Tech Stack

- React 19 + TypeScript
- TanStack Start (server-side rendering + file-based routing)
- Tailwind CSS (styling)
- Lucide React (icons)
- jspdf (PDF report generation)
- Vitest (testing)
- shadcn/ui (component primitives)
