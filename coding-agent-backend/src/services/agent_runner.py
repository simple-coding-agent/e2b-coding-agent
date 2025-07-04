import asyncio
import traceback
from datetime import datetime

from src.agent.agentic_loop import AgenticLoop
from src.llms.tools import *  # This will now include the TaskFinished exception
from src.llms.models import OpenRouterModel
from src.api.state import active_tasks, Session
from src.api.schemas import TaskCreateRequest

# Define the system prompt in one place
SYSTEM_PROMPT = """
You are a coding agent which accomplishes a user tasks. You are always working with a repository.
You can observe and control the repository using the tools. 
Rules: - You will always receive a single user message. Work autonomously to finish the task, never ask for clarifications. If there is no task, use the finish task tool.
Once you are finished with the task, use the finish_task tool call.
- You are encouraged to use planning steps, when the task is complex.
- If you get stuck on the task, consider either: do a planning step or use the finish_task tool and explain why you did not succeed.
Always make sure your solution is valid and document it properly.
- Previous turns in the conversation are provided for context. The last user message is the current task.
"""

async def run_agent_task(
    session: Session,
    task_id: str,
    request: TaskCreateRequest,
    loop: asyncio.AbstractEventLoop
):
    """
    Run the agent loop for a specific task, managing conversation history for context.
    """
    task = active_tasks[task_id]
    queue = task['event_queue']

    def emit_event_threadsafe(event_data: dict):
        asyncio.run_coroutine_threadsafe(queue.put(event_data), loop)

    try:
        await queue.put({
            "type": "task.start",
            "timestamp": datetime.utcnow().isoformat(),
            "data": { "task_id": task_id, "query": request.query, "model": request.model }
        })

        repo = session.repo
        repo.set_event_callback(emit_event_threadsafe)

        # --- CONTEXT MANAGEMENT ---
        # 1. Start with the base system prompt.
        initial_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        # 2. Add the history from the session object.
        initial_messages.extend(session.message_history)
        # 3. Add the new user query for this specific task.
        initial_messages.append({"role": "user", "content": request.query})

        # Instantiate the loop with the full, ordered message history.
        loop_instance = AgenticLoop(
            max_iterations=request.max_iterations,
            llm_model=None, # Will be set shortly
            initial_messages=initial_messages,
            initial_query_for_event=request.query
        )
        loop_instance.set_event_callback(emit_event_threadsafe)

        available_tools = {
            "observe_repo_structure": ObserveRepoStructure(repo),
            "read_file": ReadFile(repo),
            "write_file": WriteFile(repo),
            "delete_files": DeleteFiles(repo),
            "run_bash_command": RunCommand(repo),
            "commit_and_push": CommitAndPush(repo),
            "finish_task": FinishTask() # No longer needs the loop instance
        }

        for tool in available_tools.values():
            tool.set_event_callback(emit_event_threadsafe)

        model = OpenRouterModel(tools=available_tools, model=request.model)
        model.set_event_callback(emit_event_threadsafe)
        loop_instance.llm_model = model

        # final_response is now guaranteed to be the summary from the FinishTask tool.
        final_summary, conversation_history = await loop_instance.run_async()

        # --- UPDATE SESSION HISTORY ---
        # Persist the just-completed turn in the session's memory for the next task.
        session.message_history.append({"role": "user", "content": request.query})
        session.message_history.append({"role": "assistant", "content": f"Task completed. Summary: {final_summary}"})

        await queue.put({
            "type": "task.finish",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"response": final_summary, "total_iterations": loop_instance.iteration_count}
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

