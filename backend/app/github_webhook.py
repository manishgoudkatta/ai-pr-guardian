import logging

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .config import settings
from .utils import verify_github_signature
from .review_engine import run_review

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Webhook endpoint (called by GitHub) ─────────────────────────────────────

@router.post('')
async def handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """Handle incoming GitHub webhook events for pull requests."""
    raw_body = await request.body()
    sig = request.headers.get('X-Hub-Signature-256')

    if not verify_github_signature(settings.github_webhook_secret, raw_body, sig):
        logger.warning("Webhook received with invalid signature")
        raise HTTPException(status_code=401, detail='Invalid signature')

    event = request.headers.get('X-GitHub-Event', '')
    payload = await request.json()
    action = payload.get('action', '')

    logger.info("Webhook received: event=%s action=%s", event, action)

    REVIEW_ACTIONS = {'opened', 'synchronize', 'ready_for_review'}

    if event == 'pull_request' and action in REVIEW_ACTIONS:
        pr = payload['pull_request']
        repo = payload['repository']

        logger.info(
            "Queuing review for %s PR #%d",
            repo['full_name'], pr['number']
        )

        # Run in background so GitHub doesn't time out
        background_tasks.add_task(
            run_review,
            repo_full_name=repo['full_name'],
            pr_number=pr['number'],
            head_sha=pr['head']['sha'],
            installation_id=payload.get('installation', {}).get('id'),
        )

    return JSONResponse({'status': 'ok'})


# ── Action trigger endpoint (called by GitHub Actions workflow) ─────────────

class ActionTriggerPayload(BaseModel):
    repo: str
    pr_number: int
    head_sha: str


@router.post('/action')
async def handle_action_trigger(
    request: Request,
    payload: ActionTriggerPayload,
    background_tasks: BackgroundTasks,
):
    """Handle review trigger from GitHub Actions workflow."""
    api_key = request.headers.get('X-Api-Key', '')

    if settings.review_api_key and api_key != settings.review_api_key:
        raise HTTPException(status_code=401, detail='Invalid API key')

    logger.info(
        "Action trigger: reviewing %s PR #%d", payload.repo, payload.pr_number
    )

    background_tasks.add_task(
        run_review,
        repo_full_name=payload.repo,
        pr_number=payload.pr_number,
        head_sha=payload.head_sha,
        installation_id=None,
    )

    return JSONResponse({'status': 'review_queued'})
