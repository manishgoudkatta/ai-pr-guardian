from pydantic import BaseModel
from enum import Enum
from typing import Optional

class Severity(str, Enum):
    critical = 'critical'
    high     = 'high'
    medium   = 'medium'
    low      = 'low'
    info     = 'info'

class ReviewCategory(str, Enum):
    bug_risk     = 'bug_risk'
    security     = 'security'
    readability  = 'readability'
    performance  = 'performance'
    tests        = 'tests'
    style        = 'style'

class ReviewComment(BaseModel):
    path: str                     # file path in the PR
    line: int                     # line number in the diff
    severity: Severity
    category: ReviewCategory
    message: str                  # human-readable explanation
    suggestion: Optional[str]     # concrete fix / code snippet
    rule: Optional[str]           # e.g. 'flake8:E501', 'bandit:B101'

class PRReview(BaseModel):
    pr_number: int
    repo_full_name: str
    comments: list[ReviewComment]
    summary: str
    merge_safety_score: int       # 0-100
    analyzer_findings: int        # raw count before LLM
    llm_tokens_used: int = 0