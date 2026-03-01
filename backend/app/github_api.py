import base64
import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)

BASE = 'https://api.github.com'
TIMEOUT = 30.0  # seconds


def _headers(token: str) -> dict:
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }


async def get_pr_files(owner: str, repo: str, pr_number: int, token: str) -> list[dict]:
    """Return list of {filename, patch, status} dicts for a PR."""
    url = f'{BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files'
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(url, headers=_headers(token), params={'per_page': 100})
        resp.raise_for_status()
        return resp.json()


async def get_file_content(
    owner: str, repo: str, path: str, ref: str, token: str
) -> str:
    """Fetch raw file content at a given ref (used for RULES.md)."""
    url = f'{BASE}/repos/{owner}/{repo}/contents/{path}'
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url, headers=_headers(token), params={'ref': ref})
            if resp.status_code == 404:
                return ''
            resp.raise_for_status()
            return base64.b64decode(resp.json()['content']).decode('utf-8')
    except Exception as e:
        logger.warning("Could not fetch %s from %s/%s: %s", path, owner, repo, e)
        return ''


async def post_pr_review(
    owner: str, repo: str, pr_number: int,
    commit_sha: str, comments: list[dict], body: str, token: str
) -> dict:
    """Post a batch review with inline comments to GitHub."""
    url = f'{BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews'
    payload = {
        'commit_id': commit_sha,
        'body': body,
        'event': 'COMMENT',
        'comments': comments,  # [{path, position, body}]
    }
    logger.info(
        "Posting review to %s/%s PR #%d with %d inline comments",
        owner, repo, pr_number, len(comments)
    )
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(url, headers=_headers(token), json=payload)
        resp.raise_for_status()
        return resp.json()
