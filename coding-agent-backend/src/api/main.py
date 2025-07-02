# src/api/main.py

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json
from typing import Dict, Any
import uuid
from datetime import datetime
from dotenv import load_dotenv
import os

from src.agent.agentic_loop import AgenticLoop
from src.llms.tools import *
from src.llms.models import OpenRouterModel
from src.sandbox_handling.repo_handling import GithubRepo
from e2b_code_interpreter import Sandbox

# Load environment variables
load_dotenv()
E2B_API_KEY = os.environ.get("E2B_API_KEY")

app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your Next.js frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active tasks
active_tasks: Dict[str, Dict[str, Any]] = {}

class TaskRequest(BaseModel):
    query: str
    max_iterations: int = 20
    model: str = "openai/gpt-4.1-turbo"

class TaskResponse(BaseModel):
    task_id: str


async def event_generator(task_id: str):
    """Generate server-sent events for a specific task using the new hierarchical event system."""
    task = active_tasks.get(task_id)
    if not task:
        # REFACTORED: Use 'task.error' for consistency
        yield f"data: {json.dumps({'type': 'task.error', 'timestamp': datetime.utcnow().isoformat(), 'data': {'message': 'Task not found'}})}\n\n"
        return
    
    queue = task['event_queue']
    
    while True:
        # Check if the background task has marked itself as complete
        if task.get('complete', False) and queue.empty():
            break
        
        try:
            # Wait for events with a timeout
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            yield f"data: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            # REFACTORED: Use namespaced 'stream.keepalive' event
            yield f"data: {json.dumps({'type': 'stream.keepalive', 'timestamp': datetime.utcnow().isoformat(), 'data': {}})}\n\n"
        
        await asyncio.sleep(0.1)

    # NEW: Send a final 'task.end' event to signal the stream is closing gracefully.
    yield f"data: {json.dumps({'type': 'task.end', 'timestamp': datetime.utcnow().isoformat(), 'data': {'task_id': task_id}})}\n\n"
    
    # Clean up the task from memory
    if task_id in active_tasks:
        del active_tasks[task_id]


@app.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """Create a new agent task."""
    task_id = str(uuid.uuid4())
    event_queue = asyncio.Queue()
    
    active_tasks[task_id] = {
        'id': task_id,
        'query': request.query,
        'status': 'starting',
        'event_queue': event_queue,
        'complete': False,
        'started_at': datetime.utcnow().isoformat()
    }
    
    background_tasks.add_task(run_agent_task, task_id, request)
    return TaskResponse(task_id=task_id)


@app.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str):
    """Stream events for a specific task."""
    return StreamingResponse(
        event_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no", # Important for Nginx proxying
            "Access-Control-Allow-Origin": "*",
        }
    )


async def run_agent_task(task_id: str, request: TaskRequest):
    """Run the agent loop for a specific task, emitting structured events."""
    task = active_tasks[task_id]
    queue = task['event_queue']
    
    # Create event callback that puts events onto the task's async queue
    def sync_event_callback(event):
        asyncio.run_coroutine_threadsafe(queue.put(event), asyncio.get_running_loop())

    try:
        # REFACTORED: Use 'task.start'
        await queue.put({
            "type": "task.start",
            "timestamp": datetime.utcnow().isoformat(),
            "data": { "task_id": task_id, "query": request.query, "max_iterations": request.max_iterations, "model": request.model }
        })
        
        # REFACTORED: Replace 'system_info' with specific, structured setup events
        await queue.put({"type": "setup.sandbox.start", "timestamp": datetime.utcnow().isoformat(), "data": {"message": "Initializing sandbox..."}})
        sbx = Sandbox(timeout=1200)
        await queue.put({"type": "setup.sandbox.end", "timestamp": datetime.utcnow().isoformat(), "data": {"message": "Sandbox initialized."}})
        
        await queue.put({"type": "setup.repo.start", "timestamp": datetime.utcnow().isoformat(), "data": {"message": "Cloning repository..."}})
        repo = GithubRepo(repo_name="playground_repo", repo_user="simple-coding-agent", sandbox=sbx)
        repo.clone_repo_and_auth()
        await queue.put({"type": "setup.repo.end", "timestamp": datetime.utcnow().isoformat(), "data": {"message": "Repository cloned."}})
        
        loop = AgenticLoop(max_iterations=request.max_iterations, llm_model=None, initial_query=request.query)
        loop.set_event_callback(sync_event_callback)
        
        available_tools = {
            "observe_repo_structure": ObserveRepoStructure(repo),
            "read_file": ReadFile(repo),
            "write_file": WriteFile(repo),
            "delete_files": DeleteFiles(repo),
            "commit_and_push": CommitAndPush(repo),
            "finish_task": FinishTask(loop)
        }
        
        for tool in available_tools.values():
            if hasattr(tool, 'set_event_callback'):
                tool.set_event_callback(sync_event_callback)
        
        await queue.put({"type": "setup.model.start", "timestamp": datetime.utcnow().isoformat(), "data": {"message": f"Initializing {request.model} model..."}})
        model = OpenRouterModel(tools=available_tools, model=request.model)
        if hasattr(model, 'set_event_callback'):
            model.set_event_callback(sync_event_callback)
        loop.llm_model = model
        await queue.put({"type": "setup.model.end", "timestamp": datetime.utcnow().isoformat(), "data": {"message": "Model initialized."}})

        # REFACTORED: Use 'agent.loop.start'
        await queue.put({"type": "agent.loop.start", "timestamp": datetime.utcnow().isoformat(), "data": {"message": "Agent is starting to work..."}})
        
        # Run the main agent loop
        final_response, conversation_history = await loop.run_async()
        
        # REFACTORED: Use 'task.finish' for successful completion
        await queue.put({
            "type": "task.finish",
            "timestamp": datetime.utcnow().isoformat(),
            "data": { "response": final_response, "total_iterations": loop.iteration_count }
        })
        
    except Exception as e:
        import traceback
        # REFACTORED: Use 'task.error' for exceptions
        await queue.put({
            "type": "task.error",
            "timestamp": datetime.utcnow().isoformat(),
            "data": { "error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc() }
        })
    finally:
        # Mark the task as complete so the event_generator can clean up
        task['complete'] = True


@app.get("/tasks")
async def list_active_tasks():
    """List all active tasks."""
    return {
        "active_tasks": [
            {
                "task_id": task_id,
                "query": task["query"],
                "status": task["status"],
                "started_at": task["started_at"]
            }
            for task_id, task in active_tasks.items()
        ]
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

