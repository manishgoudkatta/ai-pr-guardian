import logging
from datetime import datetime, timezone

from .config import settings
from .models import PRReview, ReviewComment, Severity
from .github_api import get_pr_files, get_file_content, post_pr_review
from .analyzers import run_flake8, run_bandit
from .llm_client import review_file_with_llm
from .utils import diff_line_to_position
from .user_store import user_store

logger = logging.getLogger(__name__)

# ── In-memory review history (production would use a database) ──────────────
review_history: list[dict] = []

SEVERITY_EMOJI = {
    Severity.critical: '🔴',
    Severity.high:     '🟠',
    Severity.medium:   '🟡',
    Severity.low:      '🔵',
    Severity.info:     '⚪',
}

VERDICT_EMOJI = {
    'EXCELLENT': '🟢',
    'GOOD': '🔵',
    'NEEDS_IMPROVEMENT': '🟡',
    'RISKY': '🟠',
    'CRITICAL': '🔴',
    'UNKNOWN': '⚪',
}

# File extensions we can review
REVIEWABLE_EXTENSIONS = (
    '.py', '.js', '.jsx', '.ts', '.tsx',
    '.html', '.css', '.java', '.cpp', '.c', '.go', '.rs',
    '.rb', '.php', '.swift', '.kt', '.scala', '.sh',
)


async def run_review(
    repo_full_name: str,
    pr_number: int,
    head_sha: str,
    installation_id: int | None = None,
):
    """Main review orchestrator — fetches PR, runs analysis, posts review."""
    logger.info(
        "Starting review for %s PR #%d (sha: %s)",
        repo_full_name, pr_number, head_sha[:8]
    )

    # Multi-user: look up the user who owns this repo, use their token
    repo_owner = user_store.find_user_by_repo(repo_full_name)
    token = (repo_owner or {}).get('access_token', '') or settings.github_token
    if not token:
        logger.error("No token available for %s — cannot review PR", repo_full_name)
        return

    owner, repo = repo_full_name.split('/')

    try:
        # 1. Fetch PR files
        files = await get_pr_files(owner, repo, pr_number, token)
        reviewable_files = [
            f for f in files
            if f['filename'].endswith(REVIEWABLE_EXTENSIONS) and f.get('patch')
        ]

        if not reviewable_files:
            logger.info("No reviewable files found in PR #%d", pr_number)
            return

        # 2. Fetch project rules
        rules_md = await get_file_content(owner, repo, 'RULES.md', head_sha, token)

        all_comments: list[ReviewComment] = []
        file_scores: list[int] = []
        file_reports: list[dict] = []
        total_tokens = 0

        # 3. Per-file analysis (cap at 15 files per review)
        for f in reviewable_files[:15]:
            patch = f['patch']
            filepath = f['filename']

            # Static analysis (only for Python files)
            static_issues: list[ReviewComment] = []
            if filepath.endswith('.py'):
                static_issues = run_flake8(patch, filepath) + run_bandit(patch, filepath)

            issues_json = [c.model_dump(mode='json') for c in static_issues]

            # LLM review (now returns verdict and summary)
            llm_comments, file_score, tokens, file_verdict, file_summary = (
                await review_file_with_llm(filepath, patch, issues_json, rules_md)
            )

            all_comments.extend(static_issues)
            all_comments.extend(llm_comments)
            file_scores.append(file_score)
            total_tokens += tokens

            # Store per-file report
            file_reports.append({
                'file': filepath,
                'score': file_score,
                'verdict': file_verdict,
                'summary': file_summary,
                'issues': len(static_issues) + len(llm_comments),
                'static_issues': len(static_issues),
                'llm_issues': len(llm_comments),
            })

        # 4. Compute merge safety score
        critical_count = sum(1 for c in all_comments if c.severity == Severity.critical)
        high_count = sum(1 for c in all_comments if c.severity == Severity.high)
        medium_count = sum(1 for c in all_comments if c.severity == Severity.medium)
        low_count = sum(1 for c in all_comments if c.severity == Severity.low)
        info_count = sum(1 for c in all_comments if c.severity == Severity.info)
        base_score = int(sum(file_scores) / len(file_scores)) if file_scores else 80
        safety_score = max(0, base_score - critical_count * 20 - high_count * 10 - medium_count * 3)

        # 5. Build GitHub review payload
        gh_comments = []
        for comment in all_comments:
            file_data = next(
                (f for f in files if f['filename'] == comment.path), None
            )
            if not file_data or not file_data.get('patch'):
                continue

            position = diff_line_to_position(file_data['patch'], comment.line)
            if position is None:
                continue

            emoji = SEVERITY_EMOJI.get(comment.severity, '⚪')
            body = f'{emoji} **[{comment.severity.value.upper()}] {comment.category.value}**\n\n'
            body += f'{comment.message}\n'

            if comment.suggestion:
                body += f'\n**Suggestion:**\n```python\n{comment.suggestion}\n```'
            if comment.rule:
                body += f'\n\n_Rule: `{comment.rule}`_'

            gh_comments.append({
                'path': comment.path,
                'position': position,
                'body': body,
            })

        # 6. Build detailed summary with per-file breakdown
        score_bar = '🟩' * (safety_score // 10) + '⬜' * (10 - safety_score // 10)

        # Overall verdict
        if safety_score >= 80:
            overall_verdict = '✅ **SAFE TO MERGE** — Code looks good overall'
        elif safety_score >= 60:
            overall_verdict = '⚠️ **REVIEW RECOMMENDED** — Some issues should be addressed'
        elif safety_score >= 40:
            overall_verdict = '🟡 **NEEDS IMPROVEMENT** — Several issues found that should be fixed'
        else:
            overall_verdict = '🔴 **DO NOT MERGE** — Critical issues must be resolved first'

        summary = (
            f'## 🛡️ AI PR Guardian — In-Depth Review\n\n'
            f'**Merge Safety Score: {safety_score}/100** {score_bar}\n\n'
            f'{overall_verdict}\n\n'
            f'---\n\n'
            f'### 📊 Issue Summary\n\n'
            f'| Severity | Count |\n|----------|-------|\n'
            f'| 🔴 Critical | {critical_count} |\n'
            f'| 🟠 High | {high_count} |\n'
            f'| 🟡 Medium | {medium_count} |\n'
            f'| 🔵 Low | {low_count} |\n'
            f'| ⚪ Info | {info_count} |\n'
            f'| **Total** | **{len(all_comments)}** |\n\n'
            f'---\n\n'
            f'### 📁 Per-File Analysis\n\n'
            f'| File | Score | Verdict | Issues | Summary |\n'
            f'|------|-------|---------|--------|---------|\n'
        )

        for fr in file_reports:
            v_emoji = VERDICT_EMOJI.get(fr['verdict'], '⚪')
            summary += (
                f"| `{fr['file']}` | {fr['score']}/100 | "
                f"{v_emoji} {fr['verdict']} | {fr['issues']} | "
                f"{fr['summary'][:100]}{'...' if len(fr['summary']) > 100 else ''} |\n"
            )

        summary += (
            f'\n---\n\n'
            f'### 📝 Detailed File Reviews\n\n'
        )

        for fr in file_reports:
            v_emoji = VERDICT_EMOJI.get(fr['verdict'], '⚪')
            summary += (
                f'<details>\n'
                f'<summary>{v_emoji} <b>{fr["file"]}</b> — {fr["score"]}/100 — '
                f'{fr["verdict"]} ({fr["issues"]} issues)</summary>\n\n'
                f'{fr["summary"]}\n\n'
                f'- Static analyzer issues: {fr["static_issues"]}\n'
                f'- AI-detected issues: {fr["llm_issues"]}\n\n'
                f'</details>\n\n'
            )

        summary += (
            f'---\n\n'
            f'| Metric | Value |\n|--------|-------|\n'
            f'| Files reviewed | {len(reviewable_files)} |\n'
            f'| Total issues | {len(all_comments)} |\n'
            f'| Tokens used | {total_tokens} |\n\n'
            f'*Powered by AI PR Guardian 🛡️*'
        )

        # 7. Post to GitHub
        await post_pr_review(
            owner, repo, pr_number, head_sha,
            gh_comments, summary, token
        )

        # 8. Store review in history
        review_record = {
            'pr_number': pr_number,
            'repo': repo_full_name,
            'score': safety_score,
            'verdict': overall_verdict,
            'summary': summary,
            'total_issues': len(all_comments),
            'critical': critical_count,
            'high': high_count,
            'medium': medium_count,
            'low': low_count,
            'info': info_count,
            'tokens': total_tokens,
            'files_reviewed': len(reviewable_files),
            'file_reports': file_reports,
            'comments': [c.model_dump(mode='json') for c in all_comments],
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        review_history.append(review_record)

        # Also store in the user's personal history
        if repo_owner:
            user_store.add_review(repo_owner['login'], review_record)

        logger.info(
            "Review complete for %s PR #%d — safety score: %d/100, %d issues, %d files",
            repo_full_name, pr_number, safety_score, len(all_comments), len(reviewable_files)
        )

    except Exception as e:
        logger.error("Review failed for %s PR #%d: %s", repo_full_name, pr_number, e)
        raise