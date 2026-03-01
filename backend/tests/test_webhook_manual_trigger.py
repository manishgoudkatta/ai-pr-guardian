"""
Manual simulation script — run a local review without needing a real GitHub PR.

Usage:
    cd backend
    python -m tests.test_webhook_manual_trigger
"""
import asyncio
import json
import os
from unittest.mock import patch, AsyncMock

# Set env vars before importing app modules
os.environ.setdefault('GITHUB_WEBHOOK_SECRET', 'test')
os.environ.setdefault('GITHUB_TOKEN', 'test')
os.environ.setdefault('GROQ_API_KEY', 'test')

from app.review_engine import run_review  # noqa: E402


async def simulate_pr():
    print("🚀 Triggering AI PR Guardian Local Simulation...")
    print("=" * 60)

    mock_files = [{
        "filename": "demo.py",
        "patch": (
            "@@ -0,0 +1,8 @@\n"
            "+import os\n"
            "+def risky_function():\n"
            "+    eval('print(\"Hello\")')  # security issue\n"
            "+    password = 'hardcoded_secret_123'\n"
            "+    return None\n"
            "+    print('unreachable code')  # dead code\n"
            "+\n"
            "+x=1+2  # style issue\n"
        ),
    }]

    captured_review = {}

    async def mock_post_review(owner, repo, pr_number, commit_sha, comments, body, token):
        captured_review['comments'] = comments
        captured_review['body'] = body
        return {"id": 12345}

    with (
        patch('app.review_engine.get_pr_files', new_callable=AsyncMock, return_value=mock_files),
        patch('app.review_engine.get_file_content', new_callable=AsyncMock, return_value="# Rules\n- No eval()\n- No hardcoded secrets"),
        patch('app.review_engine.post_pr_review', side_effect=mock_post_review),
    ):
        await run_review("local/demo-repo", 1, "mock_sha_abc123", None)

    print("\n✅ Simulation Complete!")
    print("=" * 60)

    if captured_review.get('body'):
        print("\n📝 SUMMARY POSTED TO GITHUB:")
        print(captured_review['body'])

    comments = captured_review.get('comments', [])
    if comments:
        print(f"\n🔍 {len(comments)} INLINE COMMENTS:")
        for c in comments:
            print(f"\n  📄 {c['path']} (position {c['position']})")
            print(f"  {c['body'][:200]}")
            print("  ---")
    else:
        print("\n⚠️  No inline comments were generated.")
        print("    (This is normal if flake8/bandit aren't installed or Groq API key is invalid)")


if __name__ == "__main__":
    asyncio.run(simulate_pr())
