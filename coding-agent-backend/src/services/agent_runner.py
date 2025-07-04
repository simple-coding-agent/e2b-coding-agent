import asyncio
import traceback
from datetime import datetime

from src.agent.agentic_loop import AgenticLoop
from src.llms.tools import *
from src.llms.models import OpenRouterModel
from src.api.state import active_tasks, Session
from src.api.schemas import TaskCreateRequest


# Define the system prompt in one place
SYSTEM_PROMPT = """
You are a coding agent designed to accomplish user tasks within a repository. You have access to a terminal and are expected to work like a real software engineer.

**Rules:**
* You will receive a single user message. Work autonomously to complete the task without asking for clarification. If no task is specified, use the `finish_task` tool.
* Make a diligent effort to accomplish the user's goal. Do not be lazy.
* Never repeat the same action twice in a row. If you find yourself in a loop or unable to make progress, you must terminate by using the `finish_task` tool and explain the issue. Do not get stuck in a continuous loop.
* Be mindful of commands that create persistent processes or loops (e.g., `npm run dev`). Avoid running them in a way that will cause you to get stuck waiting for output.
* Once the task is successfully completed, commit your changes with a clear message and push them to the repository, then use the `finish_task` tool.
* You are encouraged to use planning steps for complex tasks.
* If you get stuck, you can either perform a planning step to re-evaluate or use the `finish_task` tool to explain why you could not succeed.
* Ensure your final solution is valid and well-documented.
* Previous turns in the conversation are provided for context; the last user message is the current task.
"""

async def run_agent_task(
    session: Session,
    task_id: str,
    request: TaskCreateRequest,
    loop: asyncio.AbstractEventLoop
):
    task = active_tasks[task_id]
    event_queue = task['event_queue']
    # Create and store a control queue for this specific task
    control_queue = asyncio.Queue(maxsize=1)
    task['control_queue'] = control_queue

    def emit_event_threadsafe(event_data: dict):
        asyncio.run_coroutine_threadsafe(event_queue.put(event_data), loop)
    
    loop_instance = None
    try:
        await event_queue.put({
            "type": "task.start",
            "timestamp": datetime.utcnow().isoformat(),
            "data": { "task_id": task_id, "query": request.query, "model": request.model }
        })

        repo = session.repo
        repo.set_event_callback(emit_event_threadsafe)
        
        initial_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        initial_messages.extend(session.message_history)
        initial_messages.append({"role": "user", "content": request.query})

        loop_instance = AgenticLoop(
            max_iterations=request.max_iterations,
            llm_model=None,
            initial_messages=initial_messages,
            initial_query_for_event=request.query
        )
        loop_instance.set_event_callback(emit_event_threadsafe)

        available_tools = {
            "observe_repo_structure": ObserveRepoStructure(repo),
            "read_file": ReadFile(repo), "write_file": WriteFile(repo),
            "delete_files": DeleteFiles(repo), "run_bash_command": RunCommand(repo),
            "commit_and_push": CommitAndPush(repo), "finish_task": FinishTask()
        }
        for tool in available_tools.values():
            tool.set_event_callback(emit_event_threadsafe)

        model = OpenRouterModel(tools=available_tools, model=request.model)
        model.set_event_callback(emit_event_threadsafe)
        loop_instance.llm_model = model

        # --- CONCURRENT EXECUTION & CANCELLATION LOGIC ---
        control_listener_task = asyncio.create_task(control_queue.get())
        agent_loop_task = asyncio.create_task(loop_instance.run_async())

        done, pending = await asyncio.wait(
            {agent_loop_task, control_listener_task},
            return_when=asyncio.FIRST_COMPLETED
        )

        final_summary = "Task stopped by user."
        
        # If the control listener finishes first, it means a stop was requested.
        if control_listener_task in done:
            print(f"Task {task_id} - Stop signal received.")
            # We must cancel the still-running agent loop
            agent_loop_task.cancel()
            try:
                # Await the agent loop to ensure it acknowledges cancellation
                await agent_loop_task
            except asyncio.CancelledError:
                print(f"Task {task_id} - Agent loop successfully cancelled.")
            
            task['status'] = 'stopped'
            # The final_summary is already set to the user stop message
        
        # If the agent loop finishes first, it completed normally or with an error.
        else: # agent_loop_task in done
            control_listener_task.cancel() # Clean up the listener
            # This will raise an exception if the agent loop failed
            final_summary, conversation_history = agent_loop_task.result()
            
            # Update session history ONLY on successful, natural completion
            session.message_history.append({"role": "user", "content": request.query})
            session.message_history.append({"role": "assistant", "content": f"Task completed. Summary: {final_summary}"})
            task['status'] = 'complete'

        # This block now runs for BOTH normal completion and manual stop
        await event_queue.put({
            "type": "task.finish",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"response": final_summary, "total_iterations": loop_instance.iteration_count}
        })

    except Exception as e:
        await event_queue.put({
            "type": "task.error",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()}
        })
        task['status'] = 'error'
        
    finally:
        # Ensure the other listener is always cancelled if it's still pending
        if 'control_listener_task' in locals() and not control_listener_task.done():
            control_listener_task.cancel()
        task['complete'] = True