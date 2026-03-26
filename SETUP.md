# Life Admin Autonomous System — Setup Guide

## Quick Start (Docker)

```bash
# 1. Copy env file and fill in your keys
cp .env.example .env

# 2. Start everything
docker-compose up --build

# 3. Open dashboard
open http://localhost:3000
# API docs at http://localhost:8000/docs
```

---

## Manual Setup (Local Dev)

### Prerequisites
- Python 3.12+
- Node.js 20+
- PostgreSQL 16
- Redis 7

### Backend

```bash
cd backend

# Create virtualenv
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install deps
pip install -r requirements.txt

# Copy env
cp ../.env.example .env
# → Fill in ANTHROPIC_API_KEY, GOOGLE_CLIENT_ID, etc.

# Run server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

npm install
npm run dev
# → http://localhost:3000
```

---

## Configuration

### Required API Keys

| Key | Where to get |
|-----|-------------|
| `ANTHROPIC_API_KEY` | https://console.anthropic.com |
| `GOOGLE_CLIENT_ID` | https://console.cloud.google.com → APIs → Gmail API → OAuth2 credentials |
| `GOOGLE_CLIENT_SECRET` | Same as above |

### Gmail OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project → Enable Gmail API
3. Create OAuth2 credentials (Desktop application type)
4. Set the redirect URI to `http://localhost:8000/api/ingestion/oauth/callback`
5. Add your email to test users (OAuth consent screen)
6. Visit `http://localhost:8000/api/ingestion/oauth/start` to authorize
7. Copy the `refresh_token` from the response into your `.env`

### SMTP (Email Notifications)

For Gmail SMTP:
1. Enable 2FA on your Google account
2. Create an App Password: Google Account → Security → App passwords
3. Use that password as `SMTP_PASSWORD`

---

## Usage

### Sync Gmail Bills
```
POST /api/ingestion/sync
```
Scans your Gmail for bill-related emails → Claude extracts bill info → LangGraph agent decides action.

### Run Agent on All Pending Bills
```
POST /api/bills/run-all-pending
```

### Manually Add a Bill
```
POST /api/ingestion/manual?provider=Airtel&amount=999&due_date=2024-12-01&bill_type=phone
```

### Mark a Bill as Paid
```
POST /api/bills/{id}/mark-paid
```

---

## Architecture

```
Gmail API ──→ Ingestion Service ──→ Claude Opus 4.6 (bill extraction)
                                         │
                                         ▼
                                    PostgreSQL (bills table)
                                         │
                                         ▼
                              LangGraph Agent Workflow
                            ┌──────────────────────────┐
                            │ load_bill → check_urgency │
                            │ → analyze_pricing         │
                            │ → decide_action           │
                            │ → execute_action (SMTP)   │
                            └──────────────────────────┘
                                         │
                                         ▼
                              React Dashboard (port 3000)
```

### Agent Decision Logic
| Condition | Action |
|-----------|--------|
| Overdue or ≤2 days to due | `PAY_NOW` → urgent reminder |
| Amount > threshold | `OPTIMIZE` → flag for review |
| Normal (>2 days) | `REMIND` → standard reminder |
| Already paid/ignored | `IGNORE` → no action |

---

## Roadmap

- [ ] Phase 2: UPI autopay integration
- [ ] Phase 2: WhatsApp notifications (Twilio)
- [ ] Phase 2: SMS ingestion (Android bridge or Twilio)
- [ ] Phase 3: Historical bill comparison (detect overpricing via trend)
- [ ] Phase 3: Subscription cancellation via browser automation
- [ ] Phase 3: Bank statement parsing (PDF)
- [ ] Phase 4: Multi-user support with per-user Gmail OAuth
