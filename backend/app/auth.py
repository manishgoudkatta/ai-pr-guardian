"""GitHub OAuth + user API routes."""
import logging

import httpx
from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import RedirectResponse, JSONResponse

from .config import settings
from .user_store import user_store
from .github_api import BASE, TIMEOUT

logger = logging.getLogger(__name__)

router = APIRouter()


# ── OAuth Login Flow ────────────────────────────────────────────────────────

@router.get('/login')
async def github_login():
    """Redirect user to GitHub OAuth authorization page."""
    if not settings.github_client_id:
        raise HTTPException(400, "GitHub OAuth not configured. Set GITHUB_CLIENT_ID in .env")

    scope = 'repo read:user'
    url = (
        f'https://github.com/login/oauth/authorize'
        f'?client_id={settings.github_client_id}'
        f'&scope={scope}'
        f'&redirect_uri={settings.app_url}/auth/callback'
    )
    return RedirectResponse(url)


@router.get('/callback')
async def github_callback(code: str = ''):
    """Handle OAuth callback from GitHub — exchange code for token."""
    if not code:
        raise HTTPException(400, "Missing authorization code")

    # Exchange code for access token
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(
            'https://github.com/login/oauth/access_token',
            json={
                'client_id': settings.github_client_id,
                'client_secret': settings.github_client_secret,
                'code': code,
            },
            headers={'Accept': 'application/json'},
        )
        data = resp.json()

    access_token = data.get('access_token')
    if not access_token:
        logger.error("OAuth token exchange failed: %s", data)
        raise HTTPException(400, f"OAuth failed: {data.get('error_description', 'Unknown error')}")

    # Fetch user profile
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            'https://api.github.com/user',
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/vnd.github+json',
            },
        )
        profile = resp.json()

    login = profile.get('login', '')
    name = profile.get('name', login)
    avatar = profile.get('avatar_url', '')

    # Store user
    user_store.upsert_user(login, name, avatar, access_token)
    session_token = user_store.create_session(login)

    logger.info("User logged in: %s (%s)", login, name)

    # Redirect to dashboard with session cookie
    response = RedirectResponse(url='/')
    response.set_cookie(
        key='session',
        value=session_token,
        httponly=True,
        max_age=30 * 24 * 3600,  # 30 days
        samesite='lax',
    )
    return response


@router.get('/logout')
async def logout(response: Response):
    """Clear session and redirect to landing page."""
    resp = RedirectResponse(url='/')
    resp.delete_cookie('session')
    return resp


# ── User API ────────────────────────────────────────────────────────────────

@router.get('/me')
async def get_current_user(request: Request):
    """Get current logged-in user info."""
    session = request.cookies.get('session', '')
    user = user_store.get_user_by_session(session)
    if not user:
        return JSONResponse({'logged_in': False})

    return JSONResponse({
        'logged_in': True,
        'login': user['login'],
        'name': user['name'],
        'avatar_url': user['avatar_url'],
        'repos': user.get('repos', []),
    })


@router.get('/repos')
async def list_user_repos(request: Request):
    """List the user's GitHub repos (for selection)."""
    session = request.cookies.get('session', '')
    user = user_store.get_user_by_session(session)
    if not user:
        raise HTTPException(401, "Not logged in")

    token = user['access_token']
    repos = []
    page = 1

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while True:
            resp = await client.get(
                f'{BASE}/user/repos',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/vnd.github+json',
                },
                params={
                    'per_page': 100,
                    'page': page,
                    'sort': 'updated',
                    'affiliation': 'owner',
                },
            )
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            for r in batch:
                repos.append({
                    'full_name': r['full_name'],
                    'name': r['name'],
                    'private': r['private'],
                    'language': r.get('language', ''),
                    'updated_at': r.get('updated_at', ''),
                    'enabled': r['full_name'] in user.get('repos', []),
                })
            page += 1
            if len(batch) < 100:
                break

    return JSONResponse(repos)


@router.post('/repos/{owner}/{repo}/enable')
async def enable_repo(owner: str, repo: str, request: Request):
    """Enable AI review for a repo — auto-registers the webhook."""
    session = request.cookies.get('session', '')
    user = user_store.get_user_by_session(session)
    if not user:
        raise HTTPException(401, "Not logged in")

    full_name = f'{owner}/{repo}'
    token = user['access_token']

    # Register the webhook on the repo
    webhook_url = f'{settings.app_url}/webhooks/github'
    webhook_payload = {
        'name': 'web',
        'active': True,
        'events': ['pull_request'],
        'config': {
            'url': webhook_url,
            'content_type': 'json',
            'secret': settings.github_webhook_secret,
            'insecure_ssl': '0',
        },
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # Check existing webhooks first
        resp = await client.get(
            f'{BASE}/repos/{full_name}/hooks',
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/vnd.github+json',
            },
        )

        # Don't duplicate if webhook already exists
        already_exists = False
        if resp.status_code == 200:
            for hook in resp.json():
                if hook.get('config', {}).get('url') == webhook_url:
                    already_exists = True
                    break

        if not already_exists:
            resp = await client.post(
                f'{BASE}/repos/{full_name}/hooks',
                headers={
                    'Authorization': f'Bearer {token}',
                    'Accept': 'application/vnd.github+json',
                },
                json=webhook_payload,
            )
            if resp.status_code not in (201, 200):
                logger.error("Failed to create webhook: %s %s", resp.status_code, resp.text)
                raise HTTPException(400, f"Could not create webhook: {resp.json().get('message', 'Unknown error')}")

    user_store.add_repo(user['login'], full_name)
    logger.info("User %s enabled repo %s", user['login'], full_name)

    return JSONResponse({'status': 'enabled', 'repo': full_name})


@router.post('/repos/{owner}/{repo}/disable')
async def disable_repo(owner: str, repo: str, request: Request):
    """Disable AI review for a repo — removes the webhook."""
    session = request.cookies.get('session', '')
    user = user_store.get_user_by_session(session)
    if not user:
        raise HTTPException(401, "Not logged in")

    full_name = f'{owner}/{repo}'
    token = user['access_token']
    webhook_url = f'{settings.app_url}/webhooks/github'

    # Find and delete the webhook
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(
            f'{BASE}/repos/{full_name}/hooks',
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/vnd.github+json',
            },
        )
        if resp.status_code == 200:
            for hook in resp.json():
                if hook.get('config', {}).get('url') == webhook_url:
                    await client.delete(
                        f'{BASE}/repos/{full_name}/hooks/{hook["id"]}',
                        headers={
                            'Authorization': f'Bearer {token}',
                            'Accept': 'application/vnd.github+json',
                        },
                    )
                    break

    user_store.remove_repo(user['login'], full_name)
    logger.info("User %s disabled repo %s", user['login'], full_name)

    return JSONResponse({'status': 'disabled', 'repo': full_name})
