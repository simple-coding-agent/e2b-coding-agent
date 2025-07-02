from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json
from typing import Dict, Any, Coroutine
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
    model: str = "openai/gpt-4o"

class TaskResponse(BaseModel):
    task_id: str


async def event_generator(task_id: str):
    """Generate server-sent events for a specific task using the new hierarchical event system."""
    task = active_tasks.get(task_id)
    if not task:
        yield f"data: {json.dumps({'type': 'task.error', 'timestamp': datetime.utcnow().isoformat(), 'data': {'message': 'Task not found'}})}\n\n"
        return
    
    queue = task['event_queue']
    
    while True:
        if task.get('complete', False) and queue.empty():
            break
        
        try:
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            yield f"data: {json.dumps(event)}\n\n"
            queue.task_done()
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'stream.keepalive', 'timestamp': datetime.utcnow().isoformat(), 'data': {}})}\n\n"
        
    yield f"data: {json.dumps({'type': 'task.end', 'timestamp': datetime.utcnow().isoformat(), 'data': {'task_id': task_id}})}\n\n"
    
    if task_id in active_tasks:
        del active_tasks[task_id]


@app.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """Create a new agent task."""
    task_id = str(uuid.uuid4())
    event_queue = asyncio.Queue()

    # **REFACTOR FIX 1: Capture the main event loop.**
    # This is crucial because the background task will run in a separate thread.
    main_event_loop = asyncio.get_running_loop()
    
    active_tasks[task_id] = {
        'id': task_id,
        'query': request.query,
        'status': 'starting',
        'event_queue': event_queue,
        'complete': False,
        'started_at': datetime.utcnow().isoformat()
    }
    
    # **REFACTOR FIX 2: Pass the captured loop to the background task.**
    background_tasks.add_task(run_agent_task, task_id, request, main_event_loop)
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
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        }
    )

# **REFACTOR FIX 3: Modify the function signature to accept the loop.**
async def run_agent_task(task_id: str, request: TaskRequest, loop: asyncio.AbstractEventLoop):
    """Run the agent loop for a specific task, emitting structured events."""
    task = active_tasks[task_id]
    queue = task['event_queue']
    
    # Helper to put events on the queue from any thread
    def emit_event(event: Coroutine):
        asyncio.run_coroutine_threadsafe(event, loop)

    # Simplified callback
    def event_callback(event_data: dict):
        emit_event(queue.put(event_data))

    try:
        await queue.put({
            "type": "task.start",
            "timestamp": datetime.utcnow().isoformat(),
            "data": { "task_id": task_id, "query": request.query, "max_iterations": request.max_iterations, "model": request.model }
        })
        
        # **REFACTOR REFINEMENT: Run blocking I/O in a thread pool executor.**
        # This prevents blocking the background thread's own event loop.
        current_loop = asyncio.get_running_loop()

        def sync_init_sandbox():
            return Sandbox(timeout=1200)
        
        sbx = await current_loop.run_in_executor(None, sync_init_sandbox)
        await queue.put({"type": "setup.sandbox.end", "timestamp": datetime.utcnow().isoformat(), "data": {"message": "E2B Sandbox initialized."}})
        
        repo = GithubRepo(repo_name="playground_repo", repo_user="simple-coding-agent", sandbox=sbx)
        
        def sync_clone_repo():
            repo.clone_repo_and_auth()
            return True

        await current_loop.run_in_executor(None, sync_clone_repo)
        await queue.put({"type": "setup.repo.end", "timestamp": datetime.utcnow().isoformat(), "data": {"message": "Repository cloned."}})
        
        loop_instance = AgenticLoop(max_iterations=request.max_iterations, llm_model=None, initial_query=request.query)
        # **REFACTOR FIX 4: Use the safe callback.**
        loop_instance.set_event_callback(event_callback)
        
        available_tools = {
            "observe_repo_structure": ObserveRepoStructure(repo),
            "read_file": ReadFile(repo),
            "write_file": WriteFile(repo),
            "delete_files": DeleteFiles(repo),
            "commit_and_push": CommitAndPush(repo),
            "finish_task": FinishTask(loop_instance)
        }
        
        for tool in available_tools.values():
            tool.set_event_callback(event_callback)
        
        model = OpenRouterModel(tools=available_tools, model=request.model)
        model.set_event_callback(event_callback)
        loop_instance.llm_model = model
        
        await queue.put({"type": "setup.model.end", "timestamp": datetime.utcnow().isoformat(), "data": {"message": f"Initialized {request.model}."}})
        
        # The agent loop already emits its own start event.
        final_response, conversation_history = await loop_instance.run_async()
        
        await queue.put({
            "type": "task.finish",
            "timestamp": datetime.utcnow().isoformat(),
            "data": { "response": final_response, "total_iterations": loop_instance.iteration_count }
        })
        
    except Exception as e:
        import traceback
        await queue.put({
            "type": "task.error",
            "timestamp": datetime.utcnow().isoformat(),
            "data": { "error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc() }
        })
    finally:
        task['complete'] = True

# ... (rest of the file is fine)
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

