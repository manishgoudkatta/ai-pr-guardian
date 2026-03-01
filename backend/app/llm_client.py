import json
import logging

from groq import AsyncGroq
from openai import AsyncOpenAI

from .config import settings
from .models import ReviewComment, Severity, ReviewCategory

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a world-class senior software engineer performing an in-depth pull request review.
You will receive: a file path, the full diff patch, static analyzer findings, and optional project-specific RULES.

Perform a THOROUGH review covering ALL of the following areas:

1. **Bug Risk** — logic errors, off-by-one, null/undefined access, race conditions, incorrect return values
2. **Security** — injection, hardcoded secrets, unsafe deserialization, missing auth checks, XSS, CSRF
3. **Error Handling** — missing try/catch, bare except, unhandled edge cases, silent failures
4. **Performance** — N+1 queries, unnecessary loops, blocking calls, memory leaks, missing caching
5. **Readability** — unclear naming, overly complex logic, missing type hints, magic numbers
6. **Best Practices** — SOLID violations, code duplication, missing validation, deprecated API usage
7. **Testing** — missing test coverage, untestable code, hardcoded test data

For EACH issue found, provide a specific, actionable comment with a concrete suggestion.

Respond ONLY with a JSON object matching this schema:
{
  "comments": [
    {
      "line": <int, the line number in the NEW file>,
      "severity": "critical|high|medium|low|info",
      "category": "bug_risk|security|readability|performance|tests|style",
      "message": "<detailed explanation of the issue and WHY it matters>",
      "suggestion": "<concrete improved code snippet or fix>"
    }
  ],
  "file_score": <int 0-100, higher = safer to merge>,
  "file_verdict": "<one of: EXCELLENT|GOOD|NEEDS_IMPROVEMENT|RISKY|CRITICAL>",
  "file_summary": "<2-3 sentence explanation of the overall file quality, what's good, what needs work>"
}

IMPORTANT RULES:
- Be thorough — review EVERY meaningful line of code, not just obvious issues
- Provide at least 1-2 comments even for good code (can be 'info' severity praise)
- The file_summary MUST explain what the file does well AND what needs improvement
- Do NOT repeat issues already caught by static analyzers unless you have additional context
- Focus on issues that a human reviewer would catch in a real code review"""


async def review_file_with_llm(
    filepath: str,
    patch: str,
    analyzer_issues: list[dict],
    rules_md: str = '',
) -> tuple[list[ReviewComment], int, int, str, str]:
    """Returns (comments, file_score, tokens_used, file_verdict, file_summary)."""

    user_content = f"""File: {filepath}

Patch (full diff):
```
{patch[:8000]}
```

Static analyzer findings (JSON):
{json.dumps(analyzer_issues, indent=2, default=str)[:3000]}

Project RULES:
{rules_md[:1500] if rules_md else 'No RULES.md found.'}
"""

    try:
        if settings.llm_provider == 'groq':
            client = AsyncGroq(api_key=settings.groq_api_key)
            response = await client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': user_content},
                ],
                response_format={'type': 'json_object'},
                max_tokens=4000,
            )
            text = response.choices[0].message.content
            usage = response.usage.total_tokens

        elif settings.llm_provider == 'openai':
            client = AsyncOpenAI(api_key=settings.openai_api_key)
            response = await client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT},
                    {'role': 'user', 'content': user_content},
                ],
                response_format={'type': 'json_object'},
                max_tokens=4000,
            )
            text = response.choices[0].message.content
            usage = response.usage.total_tokens
        else:
            raise ValueError(f'Unknown LLM provider: {settings.llm_provider}')

        data = json.loads(text)
        comments = []
        for c in data.get('comments', []):
            try:
                comments.append(ReviewComment(
                    path=filepath,
                    line=c.get('line', 1),
                    severity=Severity(c.get('severity', 'medium')),
                    category=ReviewCategory(c.get('category', 'readability')),
                    message=c.get('message', 'LLM review comment'),
                    suggestion=c.get('suggestion'),
                    rule='llm',
                ))
            except (ValueError, KeyError) as e:
                logger.warning("Skipping malformed LLM comment: %s — %s", c, e)
                continue

        file_verdict = data.get('file_verdict', 'GOOD')
        file_summary = data.get('file_summary', 'No summary provided.')

        return comments, data.get('file_score', 80), usage, file_verdict, file_summary

    except json.JSONDecodeError as e:
        logger.error("LLM returned invalid JSON for %s: %s", filepath, e)
        return [], 80, 0, 'UNKNOWN', 'LLM returned invalid response.'
    except Exception as e:
        logger.error("LLM review failed for %s: %s", filepath, e)
        return [], 80, 0, 'UNKNOWN', f'Review failed: {e}'
