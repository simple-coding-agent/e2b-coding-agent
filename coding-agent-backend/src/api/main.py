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
    model: str = "openai/gpt-4.1"

class TaskResponse(BaseModel):
    task_id: str


async def event_generator(task_id: str):
    """Generate server-sent events for a specific task"""
    task = active_tasks.get(task_id)
    if not task:
        yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Task not found'}})}\n\n"
        return
    
    # Send events from the queue
    queue = task['event_queue']
    
    while True:
        # Check if task is complete
        if task.get('complete', False):
            yield f"data: {json.dumps({'type': 'task_complete', 'data': {'task_id': task_id}})}\n\n"
            break
        
        # Send queued events
        try:
            # Wait for events with a timeout
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
            yield f"data: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            # Send keepalive
            yield f"data: {json.dumps({'type': 'keepalive', 'data': {}})}\n\n"
        
        await asyncio.sleep(0.1)
    
    # Clean up
    if task_id in active_tasks:
        del active_tasks[task_id]


@app.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """Create a new agent task"""
    task_id = str(uuid.uuid4())
    
    # Create event queue for this task
    event_queue = asyncio.Queue()
    
    # Store task info
    active_tasks[task_id] = {
        'id': task_id,
        'query': request.query,
        'status': 'starting',
        'event_queue': event_queue,
        'complete': False,
        'started_at': datetime.utcnow().isoformat()
    }
    
    # Run the agent loop in background
    background_tasks.add_task(run_agent_task, task_id, request)
    
    return TaskResponse(task_id=task_id)


@app.get("/tasks/{task_id}/events")
async def get_task_events(task_id: str):
    """Stream events for a specific task"""
    return StreamingResponse(
        event_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )


async def run_agent_task(task_id: str, request: TaskRequest):
    """Run the agent loop for a specific task"""
    task = active_tasks[task_id]
    queue = task['event_queue']
    
    try:
        # Send initial event
        await queue.put({
            "type": "task_started",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "task_id": task_id,
                "query": request.query,
                "max_iterations": request.max_iterations,
                "model": request.model
            }
        })
        
        # Initialize sandbox and repo
        await queue.put({
            "type": "system_info",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"message": "Initializing sandbox and repository..."}
        })
        
        sbx = Sandbox(timeout=1200)
        repo = GithubRepo(
            repo_name="playground_repo",
            repo_user="simple-coding-agent",
            sandbox=sbx
        )
        repo.clone_repo_and_auth()
        
        await queue.put({
            "type": "system_info",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"message": "Repository cloned and authenticated successfully"}
        })
        
        # Create the agentic loop
        loop = AgenticLoop(
            max_iterations=request.max_iterations,
            llm_model=None,
            initial_query=request.query
        )
        
        # Create event callback that adds to queue
        async def event_callback(event):
            await queue.put(event)
        
        # Set up event callback for the loop
        loop.set_event_callback(lambda event: asyncio.create_task(event_callback(event)))
        
        # Initialize tools
        available_tools = {
            "observe_repo_structure": ObserveRepoStructure(repo),
            "read_file": ReadFile(repo),
            "write_file": WriteFile(repo),
            "delete_files": DeleteFiles(repo),
            "commit_and_push": CommitAndPush(repo),
            "finish_task": FinishTask(loop)
        }
        
        # Set event callbacks for all tools
        for tool in available_tools.values():
            if hasattr(tool, 'set_event_callback'):
                tool.set_event_callback(lambda event: asyncio.create_task(event_callback(event)))
        
        await queue.put({
            "type": "system_info",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"message": f"Initializing {request.model} model with tools..."}
        })
        
        # Create model
        model = OpenRouterModel(tools=available_tools, model=request.model)
        loop.llm_model = model
        
        await queue.put({
            "type": "system_info",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"message": "Starting agent loop..."}
        })
        
        # Run the loop
        final_response, conversation_history = await loop.run_async()
        
        # Send final event
        await queue.put({
            "type": "final_response",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "response": final_response,
                "total_iterations": loop.iteration_count
            }
        })
        
    except Exception as e:
        await queue.put({
            "type": "error",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "error": str(e),
                "error_type": type(e).__name__
            }
        })
    finally:
        task['complete'] = True
        # Clean up sandbox
        try:
            if 'sbx' in locals():
                sbx.close()
        except:
            pass


@app.get("/tasks")
async def list_active_tasks():
    """List all active tasks"""
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
