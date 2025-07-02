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

from src.agent.agentic_loop import AgenticLoop
from src.llms.tools import *
from src.llms.models import OpenRouterModel
from src.sandbox_handling.repo_handling import GithubRepo

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
    repo_url: str

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
        while not queue.empty():
            event = await queue.get()
            yield f"data: {json.dumps(event)}\n\n"
        
        await asyncio.sleep(0.1)
    
    # Clean up
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
        }
    )


async def run_agent_task(task_id: str, request: TaskRequest):
    """Run the agent loop for a specific task"""
    task = active_tasks[task_id]
    queue = task['event_queue']
    
    try:
        # Initialize GitHub repo
        repo = GithubRepo(request.repo_url)
        
        # Create the agentic loop
        loop = AgenticLoop(
            max_iterations=request.max_iterations,
            llm_model=None,
            initial_query=request.query
        )
        
        # Create event callback that adds to queue
        async def event_callback(event):
            await queue.put(event)
        
        # Set up event callback
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
            tool.set_event_callback(lambda event: asyncio.create_task(event_callback(event)))
        
        # Create model
        model = OpenRouterModel(tools=available_tools, model=request.model)
        loop.llm_model = model
        
        # Run the loop
        final_response, conversation_history = await loop.run_async()
        
        # Send final event
        await queue.put({
            "type": "final_response",
            "data": {
                "response": final_response,
                "conversation_history": conversation_history
            }
        })
        
    except Exception as e:
        await queue.put({
            "type": "error",
            "data": {
                "error": str(e)
            }
        })
    finally:
        task['complete'] = True


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
