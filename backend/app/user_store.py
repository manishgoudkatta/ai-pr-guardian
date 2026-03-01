"""User management — in-memory store with JSON persistence."""
import json
import logging
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent.parent / "data" / "users.json"


class UserStore:
    """Simple in-memory user store with JSON file persistence."""

    def __init__(self):
        self.users: dict[str, dict] = {}     # github_login -> user data
        self.sessions: dict[str, str] = {}   # session_token -> github_login
        self._load()

    def _load(self):
        """Load users from disk."""
        if DATA_FILE.exists():
            try:
                data = json.loads(DATA_FILE.read_text(encoding='utf-8'))
                self.users = data.get('users', {})
                logger.info("Loaded %d users from disk", len(self.users))
            except Exception as e:
                logger.warning("Could not load users: %s", e)

    def _save(self):
        """Persist users to disk."""
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps({'users': self.users}, indent=2, default=str),
            encoding='utf-8',
        )

    def create_session(self, login: str) -> str:
        """Create a new session token for a user."""
        token = secrets.token_urlsafe(32)
        self.sessions[token] = login
        return token

    def get_user_by_session(self, token: str) -> dict | None:
        """Look up user from session token."""
        login = self.sessions.get(token)
        if login:
            return self.users.get(login)
        return None

    def upsert_user(
        self, login: str, name: str, avatar_url: str, access_token: str
    ) -> dict:
        """Create or update a user after OAuth login."""
        if login in self.users:
            user = self.users[login]
            user['access_token'] = access_token
            user['name'] = name
            user['avatar_url'] = avatar_url
            user['last_login'] = datetime.now(timezone.utc).isoformat()
        else:
            user = {
                'login': login,
                'name': name,
                'avatar_url': avatar_url,
                'access_token': access_token,
                'repos': [],
                'reviews': [],
                'created_at': datetime.now(timezone.utc).isoformat(),
                'last_login': datetime.now(timezone.utc).isoformat(),
            }
            self.users[login] = user

        self._save()
        return user

    def add_repo(self, login: str, repo_full_name: str):
        """Track a repo for a user."""
        user = self.users.get(login)
        if user and repo_full_name not in user['repos']:
            user['repos'].append(repo_full_name)
            self._save()

    def remove_repo(self, login: str, repo_full_name: str):
        """Stop tracking a repo for a user."""
        user = self.users.get(login)
        if user and repo_full_name in user['repos']:
            user['repos'].remove(repo_full_name)
            self._save()

    def add_review(self, login: str, review: dict):
        """Store a review for a user."""
        user = self.users.get(login)
        if user:
            user['reviews'].append(review)
            # Keep only last 50 reviews per user
            if len(user['reviews']) > 50:
                user['reviews'] = user['reviews'][-50:]
            self._save()

    def find_user_by_repo(self, repo_full_name: str) -> dict | None:
        """Find the user who owns a repo."""
        for user in self.users.values():
            if repo_full_name in user.get('repos', []):
                return user
        return None

    def get_all_users_count(self) -> int:
        return len(self.users)


# Singleton
user_store = UserStore()
