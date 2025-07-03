# src/api/schemas.py

from pydantic import BaseModel, Field
from typing import List, Optional

# --- Session Schemas ---

class SessionCreateRequest(BaseModel):
    """Request to create a new session."""
    repo_url: str = Field(..., description="The full URL of the GitHub repository to be cloned or forked.")

class SessionResponse(BaseModel):
    """Response containing the details of a newly created session."""
    session_id: str
    status: str
    repo_owner: str
    repo_name: str

class ActiveSessionSummary(BaseModel):
    """Summary of an active session for listing."""
    session_id: str
    status: str
    repo_url: str


# --- Task Schemas ---

class TaskCreateRequest(BaseModel):
    """Request to run a new agent task within an existing session."""
    query: str
    max_iterations: int = 20
    model: str = "openai/gpt-4o"

class TaskResponse(BaseModel):
    """Response containing the ID of a newly created task."""
    task_id: str

class ActiveTaskSummary(BaseModel):
    """Summary of an active task for listing."""
    task_id: str
    session_id: str  # Link back to the session
    query: str
    status: str
    started_at: str


# --- General Schemas ---

class HealthResponse(BaseModel):
    """Response for the health check endpoint."""
    status: str
    timestamp: str

