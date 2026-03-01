"""Tests for utility functions and static analyzers."""
import os

os.environ.setdefault('GITHUB_WEBHOOK_SECRET', 'test')
os.environ.setdefault('GITHUB_TOKEN', 'test')

from app.utils import diff_line_to_position, verify_github_signature
from app.analyzers import _extract_added_lines


# ── diff_line_to_position ──────────────────────────────────────────────────

SAMPLE_PATCH = """\
@@ -0,0 +1,5 @@
+def hello():
+    print("Hello")
+
+def world():
+    print("World")"""


def test_diff_line_to_position_first_line():
    """Line 1 should be at position 2 (after the @@ header)."""
    pos = diff_line_to_position(SAMPLE_PATCH, 1)
    assert pos == 2


def test_diff_line_to_position_last_line():
    pos = diff_line_to_position(SAMPLE_PATCH, 5)
    assert pos == 6


def test_diff_line_to_position_nonexistent():
    """A line not in the diff should return None."""
    pos = diff_line_to_position(SAMPLE_PATCH, 99)
    assert pos is None


MULTI_HUNK_PATCH = """\
@@ -10,3 +10,4 @@
 existing_line_10
 existing_line_11
+added_at_12
 existing_line_12
@@ -20,2 +21,3 @@
 existing_line_21
+added_at_22
 existing_line_22"""


def test_diff_multi_hunk():
    """Lines in a second hunk should compute correct positions."""
    pos = diff_line_to_position(MULTI_HUNK_PATCH, 12)
    assert pos is not None
    pos2 = diff_line_to_position(MULTI_HUNK_PATCH, 22)
    assert pos2 is not None


# ── _extract_added_lines ───────────────────────────────────────────────────

def test_extract_added_lines():
    lines = _extract_added_lines(SAMPLE_PATCH)
    assert len(lines) == 5
    assert lines[0] == (1, 'def hello():')
    assert lines[1] == (2, '    print("Hello")')


def test_extract_added_lines_empty_patch():
    lines = _extract_added_lines('')
    assert lines == []


def test_extract_added_lines_context_only():
    """A patch with only context lines has no added lines."""
    patch = "@@ -1,2 +1,2 @@\n existing1\n existing2\n"
    lines = _extract_added_lines(patch)
    assert lines == []


# ── verify_github_signature ────────────────────────────────────────────────

def test_verify_valid_signature():
    import hmac, hashlib
    secret = 'my_secret'
    body = b'test body'
    mac = hmac.new(secret.encode(), body, hashlib.sha256)
    header = f'sha256={mac.hexdigest()}'
    assert verify_github_signature(secret, body, header) is True


def test_verify_invalid_signature():
    assert verify_github_signature('secret', b'body', 'sha256=wrong') is False


def test_verify_missing_header():
    assert verify_github_signature('secret', b'body', None) is False


def test_verify_bad_algo():
    assert verify_github_signature('secret', b'body', 'sha1=abc') is False
