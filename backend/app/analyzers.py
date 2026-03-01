import subprocess
import tempfile
import os
import json
import re
import logging

from .models import ReviewComment, Severity, ReviewCategory

logger = logging.getLogger(__name__)


def _write_temp(code: str, suffix='.py') -> str:
    """Write code to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, code.encode())
    os.close(fd)
    return path


def run_flake8(patch: str, filepath: str) -> list[ReviewComment]:
    """Extract added lines from patch, run flake8, return comments."""
    added_lines = _extract_added_lines(patch)
    if not added_lines:
        return []
    code = '\n'.join(line for _, line in added_lines)
    tmp = _write_temp(code)
    try:
        result = subprocess.run(
            ['flake8', '--format=%(row)d:%(col)d:%(code)s:%(text)s', tmp],
            capture_output=True, text=True, timeout=30
        )
        comments = []
        for line in result.stdout.splitlines():
            parts = line.split(':', 3)
            if len(parts) < 4:
                continue
            try:
                local_line = int(parts[0])
            except ValueError:
                continue
            code_id, msg = parts[2], parts[3].strip()
            # Map local line back to original file line
            real_line = added_lines[local_line - 1][0] if local_line <= len(added_lines) else 1
            comments.append(ReviewComment(
                path=filepath, line=real_line,
                severity=Severity.low, category=ReviewCategory.style,
                message=msg, suggestion=None, rule=f'flake8:{code_id}'
            ))
        return comments
    except FileNotFoundError:
        logger.warning("flake8 not found in PATH — skipping style analysis")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("flake8 timed out for %s", filepath)
        return []
    finally:
        os.unlink(tmp)


def run_bandit(patch: str, filepath: str) -> list[ReviewComment]:
    """Extract added lines from patch, run bandit security scan, return comments."""
    added_lines = _extract_added_lines(patch)
    if not added_lines:
        return []
    code = '\n'.join(line for _, line in added_lines)
    tmp = _write_temp(code)
    try:
        result = subprocess.run(
            ['bandit', '-f', 'json', '-q', tmp],
            capture_output=True, text=True, timeout=30
        )
        comments = []
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []

        severity_map = {
            'HIGH': Severity.high,
            'MEDIUM': Severity.medium,
            'LOW': Severity.low,
        }
        for issue in data.get('results', []):
            local_line = issue.get('line_number', 1)
            real_line = added_lines[local_line - 1][0] if local_line <= len(added_lines) else 1
            comments.append(ReviewComment(
                path=filepath, line=real_line,
                severity=severity_map.get(issue.get('issue_severity', ''), Severity.medium),
                category=ReviewCategory.security,
                message=issue.get('issue_text', 'Security issue detected'),
                suggestion=None,
                rule=f'bandit:{issue.get("test_id", "unknown")}',
            ))
        return comments
    except FileNotFoundError:
        logger.warning("bandit not found in PATH — skipping security analysis")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("bandit timed out for %s", filepath)
        return []
    finally:
        os.unlink(tmp)


def _extract_added_lines(patch: str) -> list[tuple[int, str]]:
    """Return [(file_line_num, code)] for lines added in the patch."""
    result = []
    current_line = 0
    for line in patch.splitlines():
        if line.startswith('@@'):
            m = re.search(r'\+(\d+)', line)
            if m:
                current_line = int(m.group(1)) - 1
        elif line.startswith('+') and not line.startswith('+++'):
            current_line += 1
            result.append((current_line, line[1:]))
        elif not line.startswith('-'):
            current_line += 1
    return result
