# 🛡️ AI Pull Request Guardian

An automated code review system that uses **AI + static analysis** to review GitHub pull requests and post structured, inline feedback — directly on the PR.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green?logo=fastapi)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔗 **GitHub Webhook Integration** | Listens for PR events (opened, synchronize, ready_for_review) |
| 🔍 **Static Analysis** | Runs **flake8** (style) and **bandit** (security) on Python diffs |
| 🤖 **LLM-Powered Review** | Uses **Groq** (Llama 3) or **OpenAI** for intelligent code review |
| 💬 **Inline PR Comments** | Posts review comments directly on the PR with severity levels |
| 📊 **Merge Safety Score** | 0–100 score based on issue severity (critical/high/medium/low) |
| 📋 **RULES.md Support** | Per-repo coding rules fed into the LLM prompt |
| 📈 **Dashboard** | Streamlit UI showing review history, metrics, and token usage |
| ⚡ **GitHub Actions** | CI workflow to trigger reviews via Actions |

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     GITHUB PLATFORM                          │
│  PR opened/updated ──webhook──► GitHub App ──► Actions       │
└────────────────────────────┬─────────────────────────────────┘
                             │ HTTPS POST /webhooks/github
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND                          │
│  1. Verify HMAC signature (X-Hub-Signature-256)              │
│  2. Parse PR metadata (repo, number, author, head SHA)       │
│  3. Fetch diff via GitHub REST API                           │
│  4. Fetch RULES.md from repo (if exists)                     │
│  5. Queue background review task                             │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     REVIEW ENGINE                            │
│  Per-file loop:                                              │
│    a) Run flake8 → style issues                              │
│    b) Run bandit → security issues                           │
│    c) Build LLM prompt with diff + findings + RULES.md       │
│    d) Parse structured JSON response → ReviewComment[]       │
└────────────────────────────┬─────────────────────────────────┘
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                  GITHUB REVIEW API                           │
│  POST /repos/{owner}/{repo}/pulls/{n}/reviews                │
│  Inline comments with severity + merge safety score          │
└──────────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
ai-pr-guardian/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Environment settings (Pydantic)
│   │   ├── github_webhook.py    # Webhook + Action trigger routers
│   │   ├── github_api.py        # GitHub REST API client
│   │   ├── review_engine.py     # Orchestrates analyzers + LLM
│   │   ├── analyzers.py         # flake8, bandit wrappers
│   │   ├── llm_client.py        # Groq/OpenAI abstraction
│   │   ├── models.py            # Pydantic data models
│   │   └── utils.py             # Signature verification, helpers
│   ├── tests/
│   │   ├── test_webhook.py      # Webhook endpoint tests
│   │   └── test_analyzers.py    # Utility + analyzer tests
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                     # Your local config (git-ignored)
├── dashboard/
│   └── app.py                   # Streamlit review dashboard
├── .github/workflows/
│   └── pr-review.yml            # GitHub Actions workflow
├── RULES.md                     # Example project rules template
└── README.md
```

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/ai-pr-guardian.git
cd ai-pr-guardian/backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

| Variable | Description |
|----------|-------------|
| `GITHUB_WEBHOOK_SECRET` | Secret for webhook HMAC verification |
| `GITHUB_TOKEN` | GitHub Personal Access Token (PAT) with `repo` scope |
| `LLM_PROVIDER` | `groq` or `openai` |
| `GROQ_API_KEY` | Your Groq API key ([console.groq.com](https://console.groq.com)) |
| `OPENAI_API_KEY` | Your OpenAI API key (if using OpenAI) |

### 3. Run the API Server

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Visit **http://localhost:8000/docs** to see the Swagger API docs.

### 4. Expose to GitHub (Local Development)

```bash
ngrok http 8000
```

Copy the HTTPS URL and add it as a webhook in your GitHub repo:
- **URL**: `https://your-ngrok-url/webhooks/github`
- **Content type**: `application/json`
- **Secret**: same as `GITHUB_WEBHOOK_SECRET`
- **Events**: Pull requests

### 5. Run the Dashboard

```bash
cd dashboard
streamlit run app.py
```

Visit **http://localhost:8501** to see the review dashboard.

### 6. Run Tests

```bash
cd backend
python -m pytest tests/ -v
```

## 🧪 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/webhooks/github` | GitHub webhook receiver |
| `POST` | `/webhooks/github/action` | GitHub Actions trigger |
| `GET`  | `/health` | Health check |
| `GET`  | `/stats` | Review statistics |
| `GET`  | `/reviews` | Review history |

## 📝 RULES.md

Place a `RULES.md` file in the root of any repo you want to guard. The AI will read it and enforce your project-specific conventions during reviews. See the included [RULES.md](RULES.md) for a template.

## 🛠️ Tech Stack

| Area | Technology |
|------|------------|
| Backend API | FastAPI, async/await, Pydantic v2, BackgroundTasks |
| GitHub Integration | Webhooks, REST API, PR Review API, Actions |
| LLM | Groq (Llama 3), OpenAI (GPT-4o-mini), structured JSON output |
| Static Analysis | flake8 (style), bandit (security) |
| Dashboard | Streamlit |
| Testing | pytest, FastAPI TestClient |
| Security | HMAC-SHA256 signature verification |

## 📄 License

MIT
