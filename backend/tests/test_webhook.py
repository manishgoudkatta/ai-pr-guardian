import hmac
import hashlib
import json
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Override settings BEFORE importing the app
os.environ['GITHUB_WEBHOOK_SECRET'] = 'test_secret'
os.environ['GITHUB_TOKEN'] = 'ghp_test_token'
os.environ['GROQ_API_KEY'] = 'gsk_test_key'

from app.main import app  # noqa: E402

client = TestClient(app)
SECRET = 'test_secret'


def make_sig(body: bytes, secret: str = SECRET) -> str:
    """Create a valid HMAC-SHA256 signature for testing."""
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    return f'sha256={mac.hexdigest()}'


# ── Health Check ────────────────────────────────────────────────────────────

def test_health_check():
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'healthy'
    assert data['service'] == 'ai-pr-guardian'


# ── Stats Endpoint ──────────────────────────────────────────────────────────

def test_stats_empty():
    resp = client.get('/stats')
    assert resp.status_code == 200
    data = resp.json()
    assert data['total_reviews'] == 0


# ── Reviews Endpoint ────────────────────────────────────────────────────────

def test_reviews_empty():
    resp = client.get('/reviews')
    assert resp.status_code == 200
    assert resp.json() == []


# ── Webhook: Valid PR Opened ────────────────────────────────────────────────

def test_valid_pr_opened():
    """A properly signed PR webhook should return 200 and queue a review."""
    payload = {
        'action': 'opened',
        'pull_request': {
            'number': 1,
            'head': {'sha': 'abc123'},
        },
        'repository': {'full_name': 'owner/repo'},
        'installation': {'id': 1},
    }
    body = json.dumps(payload).encode()

    with patch('app.github_webhook.run_review') as mock_review:
        resp = client.post('/webhooks/github', content=body, headers={
            'X-GitHub-Event': 'pull_request',
            'X-Hub-Signature-256': make_sig(body),
            'Content-Type': 'application/json',
        })

    assert resp.status_code == 200
    assert resp.json() == {'status': 'ok'}


def test_valid_pr_synchronize():
    """A synchronize action should also be accepted."""
    payload = {
        'action': 'synchronize',
        'pull_request': {
            'number': 2,
            'head': {'sha': 'def456'},
        },
        'repository': {'full_name': 'user/project'},
        'installation': {'id': 1},
    }
    body = json.dumps(payload).encode()

    with patch('app.github_webhook.run_review'):
        resp = client.post('/webhooks/github', content=body, headers={
            'X-GitHub-Event': 'pull_request',
            'X-Hub-Signature-256': make_sig(body),
            'Content-Type': 'application/json',
        })

    assert resp.status_code == 200


# ── Webhook: Invalid Signature ──────────────────────────────────────────────

def test_invalid_signature():
    """A webhook with the wrong signature should be rejected with 401."""
    body = b'{"action": "opened"}'
    resp = client.post('/webhooks/github', content=body, headers={
        'X-GitHub-Event': 'pull_request',
        'X-Hub-Signature-256': 'sha256=bad_sig',
    })
    assert resp.status_code == 401


def test_missing_signature():
    """A webhook with no signature header should be rejected."""
    body = b'{"action": "opened"}'
    resp = client.post('/webhooks/github', content=body, headers={
        'X-GitHub-Event': 'pull_request',
    })
    assert resp.status_code == 401


# ── Webhook: Non-PR Events ─────────────────────────────────────────────────

def test_non_pr_event():
    """Non-pull_request events should be accepted but not trigger a review."""
    payload = {'action': 'created'}
    body = json.dumps(payload).encode()

    with patch('app.github_webhook.run_review') as mock_review:
        resp = client.post('/webhooks/github', content=body, headers={
            'X-GitHub-Event': 'push',
            'X-Hub-Signature-256': make_sig(body),
            'Content-Type': 'application/json',
        })

    assert resp.status_code == 200
    mock_review.assert_not_called()


# ── Action Trigger Endpoint ─────────────────────────────────────────────────

def test_action_trigger():
    """The /action endpoint should accept a trigger and queue a review."""
    payload = {
        'repo': 'owner/repo',
        'pr_number': 5,
        'head_sha': 'abc123',
    }

    with patch('app.github_webhook.run_review'):
        resp = client.post('/webhooks/github/action', json=payload, headers={
            'X-Api-Key': '',
        })

    assert resp.status_code == 200
    assert resp.json() == {'status': 'review_queued'}