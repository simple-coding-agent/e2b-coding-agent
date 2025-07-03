# src/api/routers.py

import asyncio
import uuid
import traceback
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException, Path
from fastapi.responses import StreamingResponse
import json  # <--- IMPORT THE JSON LIBRARY

from e2b_code_interpreter import Sandbox
from src.sandbox_handling.repo_handling import GithubRepo
from src.services.agent_runner import run_agent_task
from .schemas import (
    SessionCreateRequest, SessionResponse, TaskCreateRequest, TaskResponse,
    HealthResponse, ActiveSessionSummary, ActiveTaskSummary
)
from .state import active_sessions, active_tasks, Session

router = APIRouter()

# --- Event Streaming ---

async def event_generator(task_id: str):
    """Generate server-sent events for a specific task."""
    task = active_tasks.get(task_id)
    if not task:
        # Manually crafted JSON is fine here for simple error messages
        yield f"data: {json.dumps({'type': 'task.error', 'timestamp': datetime.utcnow().isoformat(), 'data': {'message': 'Task not found'}})}\n\n"
        return

    queue = task.get('event_queue')
    if not queue:
        yield f"data: {json.dumps({'type': 'task.error', 'timestamp': datetime.utcnow().isoformat(), 'data': {'message': 'Event queue not found for task'}})}\n\n"
        return

    while True:
        if task.get('complete', False) and queue.empty():
            break

        try:
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            # THE FIX: Use json.dumps to properly serialize the dictionary to a JSON string.
            yield f"data: {json.dumps(event)}\n\n"
            queue.task_done()
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'stream.keepalive', 'timestamp': datetime.utcnow().isoformat(), 'data': {}})}\n\n"

    yield f"data: {json.dumps({'type': 'task.end', 'timestamp': datetime.utcnow().isoformat(), 'data': {'task_id': task_id}})}\n\n"


# --- Session Endpoints ---

@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(request: SessionCreateRequest):
    """
    Creates a new session, which includes a dedicated sandbox
    and a cloned repository. This is a long-running, one-time setup.
    """
    session_id = str(uuid.uuid4())
    sandbox = None
    try:
        sandbox = await asyncio.to_thread(Sandbox, timeout=1200)

        repo = GithubRepo(repo_url=request.repo_url, sandbox=sandbox)
        original_owner, _ = repo._parse_url()

        # The setup_repository method is synchronous, so we run it in an executor
        # to avoid blocking the event loop. This is crucial for long I/O operations.
        await asyncio.to_thread(repo.setup_repository)

        new_session = Session(session_id=session_id, sandbox=sandbox, repo=repo)
        active_sessions[session_id] = new_session

        is_fork = original_owner.lower() != repo.repo_owner.lower()
        return SessionResponse(
            session_id=session_id,
            status="ready",
            repo_owner=repo.repo_owner,
            repo_name=repo.repo_name,
            is_fork=is_fork, 
        )
    except Exception as e:

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@router.get("/sessions", response_model=list[ActiveSessionSummary])
async def list_sessions():
    """List all currently active sessions."""
    return [
        ActiveSessionSummary(
            session_id=sid,
            status=session.status,
            repo_url=session.repo.repo_url
        ) for sid, session in active_sessions.items()
    ]


@router.delete("/sessions/{session_id}", status_code=204)
async def close_session(session_id: str = Path(..., description="The ID of the session to close.")):
    """Closes a session and shuts down its associated sandbox."""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = active_sessions.pop(session_id)
    await asyncio.to_thread(session.sandbox.close)
    return None


# --- Task Endpoints ---

@router.post("/sessions/{session_id}/tasks", response_model=TaskResponse, status_code=202)
async def create_task_in_session(
    request: TaskCreateRequest,
    background_tasks: BackgroundTasks,
    session_id: str = Path(..., description="The session ID in which to run the task.")
):
    """
    Creates and runs a new agent task within an existing session.
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please create a session first.")
    
    session = active_sessions[session_id]
    task_id = str(uuid.uuid4())
    event_queue = asyncio.Queue()
    main_event_loop = asyncio.get_running_loop()

    active_tasks[task_id] = {
        'id': task_id,
        'session_id': session_id,
        'query': request.query,
        'status': 'starting',
        'event_queue': event_queue,
        'complete': False,
        'started_at': datetime.utcnow().isoformat()
    }

    background_tasks.add_task(run_agent_task, session, task_id, request, main_event_loop)
    return TaskResponse(task_id=task_id)


@router.get("/tasks/{task_id}/events", summary="Stream events for a task")
async def get_task_events(task_id: str = Path(..., description="The ID of the task to monitor.")):
    """
    Streams server-sent events (SSE) for a specific agent task.
    """
    return StreamingResponse(
        event_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@router.get("/tasks", response_model=list[ActiveTaskSummary])
async def list_active_tasks():
    """List all currently active or recently completed tasks."""
    return [
        ActiveTaskSummary(
            task_id=tid,
            session_id=task["session_id"],
            query=task["query"],
            status=task["status"],
            started_at=task["started_at"]
        ) for tid, task in active_tasks.items()
    ]


# --- Health Check ---

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Provides a simple health check of the API."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

