# src/services/agent_runner.py

import asyncio
import traceback
from datetime import datetime

from src.agent.agentic_loop import AgenticLoop
from src.llms.tools import *
from src.llms.models import OpenRouterModel
from src.api.state import active_tasks, Session
from src.api.schemas import TaskCreateRequest

async def run_agent_task(
    session: Session,
    task_id: str,
    request: TaskCreateRequest,
    loop: asyncio.AbstractEventLoop
):
    """
    Run the agent loop for a specific task within a given session.
    This function contains the core business logic for executing an agentic task.
    """
    task = active_tasks[task_id]
    queue = task['event_queue']

    def emit_event(event: asyncio.Future):
        asyncio.run_coroutine_threadsafe(event, loop)

    def event_callback(event_data: dict):
        emit_event(queue.put(event_data))

    try:
        await queue.put({
            "type": "task.start",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "task_id": task_id,
                "session_id": session.id,
                "query": request.query,
                "max_iterations": request.max_iterations,
                "model": request.model
            }
        })

        repo = session.repo
        repo.set_event_callback(event_callback)

        loop_instance = AgenticLoop(
            max_iterations=request.max_iterations,
            llm_model=None,
            initial_query=request.query
        )
        loop_instance.set_event_callback(event_callback)

        available_tools = {
            "observe_repo_structure": ObserveRepoStructure(repo),
            "read_file": ReadFile(repo),
            "write_file": WriteFile(repo),
            "delete_files": DeleteFiles(repo),
            "run_bash_command": RunCommand(repo), 
            "commit_and_push": CommitAndPush(repo),
            "finish_task": FinishTask(loop_instance)
        }

        for tool in available_tools.values():
            tool.set_event_callback(event_callback)

        model = OpenRouterModel(tools=available_tools, model=request.model)
        model.set_event_callback(event_callback)
        loop_instance.llm_model = model

        await queue.put({
            "type": "setup.model.end",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"message": f"Initialized {request.model} for this task."}
        })

        final_response, conversation_history = await loop_instance.run_async()

        await queue.put({
            "type": "task.finish",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"response": final_response, "total_iterations": loop_instance.iteration_count}
        })
        
        task['status'] = 'complete'

    except Exception as e:
        await queue.put({
            "type": "task.error",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()}
        })
        task['status'] = 'error'
        
    finally:
        task['complete'] = True

