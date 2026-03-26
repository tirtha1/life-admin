# Life Admin — Autonomous Bill & Expense Management

> Connect your Gmail. Let AI handle the rest.

Life Admin automatically detects bills and bank transactions from your inbox, extracts key details with Claude AI, and gives you a unified dashboard for your finances — with smart alerts before anything goes overdue.

---

## Screenshots

### Dashboard
<!-- Add screenshot: main dashboard showing bill summary cards -->
![Dashboard](docs/screenshots/dashboard.png)

### Bills
<!-- Add screenshot: bills list with status badges (pending, overdue, paid) -->
![Bills](docs/screenshots/bills.png)

### Bill Detail & Agent Actions
<!-- Add screenshot: single bill view with AI-extracted details and action buttons -->
![Bill Detail](docs/screenshots/bill-detail.png)

### Spending Tracker
<!-- Add screenshot: spending page with category breakdown and daily chart -->
![Spending](docs/screenshots/spending.png)

### AI Insights
<!-- Add screenshot: AI-generated spending insights panel -->
![Insights](docs/screenshots/insights.png)

---

## Features

- **Gmail sync** — scans your inbox for bills, invoices, bank alerts, and UPI transactions
- **AI extraction** — Claude Opus 4.6 parses amounts, due dates, merchants, and categories
- **Smart agent** — LangGraph workflow decides when to remind, flag, or escalate each bill
- **Spend analytics** — daily/weekly/monthly breakdowns by category and merchant
- **AI insights** — personalised spending analysis powered by Claude
- **Row-level security** — PostgreSQL RLS ensures each user only sees their own data

---

## Architecture

```
Gmail API
    │
    ▼
Ingestion Service (Celery)
    │  fetches emails, keyword filters, stores to S3
    ▼
Processor Service (Kafka consumer)
    │  Claude Opus 4.6 → structured bill/transaction extraction
    ▼
PostgreSQL  ←──  FastAPI (REST + JWT auth)  ←──  React Dashboard
    │
    ▼
Agent Service (LangGraph)
    assess_urgency → check_overpriced → decide_action → queue_action
    │
    ▼
Action Service
    SendGrid (email) · Twilio (SMS/WhatsApp)
```

### Agent Decision Logic

| Condition | Action |
|-----------|--------|
| Overdue or ≤ 1 day to due | `PAY_NOW` — urgent reminder |
| 2–3 days to due | `REMIND` — standard reminder |
| Amount above threshold | `OPTIMIZE` — flag for review |
| Needs manual review | `ESCALATE` — no auto action |
| Low priority | `IGNORE` |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 async |
| AI | Claude Opus 4.6 (Anthropic) |
| Agent | LangGraph StateGraph |
| Queue | Celery + Redis, Kafka (confluent-kafka) |
| Database | PostgreSQL 16 with RLS |
| Auth | JWT (RS256 prod / HS256 dev), Google OAuth2 |
| Storage | MinIO (S3-compatible) |
| Secrets | HashiCorp Vault (AES-256-GCM token encryption) |
| Observability | OpenTelemetry, Prometheus, Grafana, Tempo |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Infra | Docker Compose |

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- An [Anthropic API key](https://console.anthropic.com)
- A [Google Cloud OAuth2 client](https://console.cloud.google.com) with Gmail API enabled

### 1. Clone & configure

```bash
git clone https://github.com/tirtha1/life-admin.git
cd life-admin

cp .env.example .env
# Fill in ANTHROPIC_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
```

### 2. Start everything

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

### 3. Connect Gmail

```
GET http://localhost:8000/api/v1/auth/google
```

Complete the OAuth flow, then trigger a sync:

```
POST http://localhost:8000/api/v1/ingestion/sync
POST http://localhost:8000/api/v1/ingestion/transactions/sync
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/bills` | List all bills |
| `POST` | `/api/v1/bills/run-all-pending` | Run AI agent on all pending bills |
| `POST` | `/api/v1/bills/{id}/mark-paid` | Mark a bill as paid |
| `POST` | `/api/v1/ingestion/sync` | Trigger Gmail bill sync |
| `POST` | `/api/v1/ingestion/transactions/sync` | Sync bank/UPI transactions |
| `GET` | `/api/v1/transactions` | List transactions |
| `GET` | `/api/v1/transactions/stats` | Spend stats (daily, category) |
| `GET` | `/api/v1/transactions/insights` | AI-generated spending insights |

Full interactive docs at `/docs` (Swagger) or `/redoc`.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `GOOGLE_CLIENT_ID` | Yes | OAuth2 client ID |
| `GOOGLE_CLIENT_SECRET` | Yes | OAuth2 client secret |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `SECRET_KEY` | Yes | JWT signing key (run `openssl rand -hex 32`) |
| `SMTP_USERNAME` | Optional | Gmail address for notifications |
| `SMTP_PASSWORD` | Optional | Gmail app password |
| `TWILIO_ACCOUNT_SID` | Optional | For SMS/WhatsApp alerts |

---

## Roadmap

- [x] Gmail bill detection & AI extraction
- [x] LangGraph agent with urgency/pricing decisions
- [x] Bank/UPI transaction tracking
- [x] Spend analytics & category breakdown
- [x] AI spending insights
- [ ] WhatsApp bot — ask "what did I spend this week?"
- [ ] Parallel Claude extraction (faster sync)
- [ ] PDF bank statement parsing
- [ ] Subscription cancellation automation
- [ ] Mobile app

---

## Development

```bash
# Run tests
pytest tests/unit/

# Get a dev JWT token
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email": "dev@lifeadmin.local"}'

# Apply DB migrations
docker compose exec postgres psql -U lifeadmin -d lifeadmin -f /migrations/002_transactions.sql
```

---

## License

MIT
