import hmac
import hashlib
import re
import logging

logger = logging.getLogger(__name__)


def verify_github_signature(
    secret: str, body: bytes, header: str | None
) -> bool:
    """Verify the HMAC-SHA256 signature from GitHub webhooks."""
    if not header:
        return False
    try:
        algo, signature = header.split('=', 1)
    except ValueError:
        return False
    if algo != 'sha256':
        return False
    mac = hmac.new(secret.encode(), msg=body, digestmod=hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)


def diff_line_to_position(patch: str, target_line: int) -> int | None:
    """Convert absolute file line to diff position (1-indexed hunk offset).

    GitHub's review API uses 'position' which is the line's offset within
    the diff (not the file). This function maps a real file line number to
    that position value.
    """
    position = 0
    current_line = 0
    for line in patch.splitlines():
        if line.startswith('@@'):
            # Parse @@ -old +new,count @@
            m = re.search(r'\+(\d+)', line)
            if m:
                current_line = int(m.group(1)) - 1
            position += 1
        elif line.startswith('+'):
            current_line += 1
            position += 1
            if current_line == target_line:
                return position
        elif line.startswith('-'):
            position += 1
        else:
            current_line += 1
            position += 1
    return None
