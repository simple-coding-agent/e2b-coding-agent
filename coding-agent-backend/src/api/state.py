# src/api/state.py

from typing import Dict, Any
from e2b_code_interpreter import Sandbox
import asyncio

from src.sandbox_handling.repo_handling import GithubRepo

class Session:
    """Represents a user's active session with a sandbox and repository."""
    def __init__(self, session_id: str, sandbox: Sandbox, repo: GithubRepo):
        self.id = session_id
        self.sandbox = sandbox
        self.repo = repo
        self.status = "created"

# In-memory storage for active sessions and tasks.
# In a production environment, you might replace this with Redis or another persistent store.
active_sessions: Dict[str, Session] = {}
active_tasks: Dict[str, Dict[str, Any]] = {}

# A global event generator queue for simplicity in this example
event_queue = asyncio.Queue()
