# 🛡️ AI Pull Request Guardian

An automated code review system that uses **AI + static analysis** to review GitHub pull requests and post structured, inline feedback — directly on the PR.



## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔗 **GitHub Webhook Integration** | Listens for PR events (opened, synchronize, ready_for_review) |
| 🔍 **Static Analysis** | Runs **flake8** (style) and **bandit** (security) on Python diffs |
| 🤖 **LLM-Powered Review** | Uses **Groq** (Llama 3) or **OpenAI** for intelligent code review |
| 💬 **Inline PR Comments** | Posts review comments directly on the PR with severity levels |
| 📊 **Merge Safety Score** | 0–100 score based on issue severity (critical/high/medium/low) |
| 📋 **RULES.md Support** | Per-repo coding rules fed into the LLM prompt |

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
│   │   └── utils.py            
│   ├── tests/
│   │   ├── test_webhook.py      # Webhook endpoint tests
│   │   └── test_analyzers.py    # Utility + analyzer tests
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                     # Your local config (git-ignored)
├── dashboard/
│   └── app.py                
├── .github/workflows/
│   └── pr-review.yml         
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


Edit `.env` with your credentials:


## 🛠️ Tech Stack

| Area | Technology |
|------|------------|
| Backend API | FastAPI, async/await, Pydantic v2, BackgroundTasks |
| GitHub Integration | Webhooks, REST API, PR Review API, Actions |
| LLM | Groq (Llama 3), structured JSON output |
| Static Analysis | flake8 (style), bandit (security) |


