import asyncio
import traceback
from datetime import datetime

from src.agent.agentic_loop import AgenticLoop
from src.llms.tools import *
from src.llms.models import OpenRouterModel
from src.api.state import active_tasks, Session
from src.api.schemas import TaskCreateRequest


# Define the improved system prompt
SYSTEM_PROMPT = """
You are an autonomous coding agent designed to accomplish user tasks within a repository. You operate in a secure sandbox environment with access to a comprehensive toolkit that enables you to work like an experienced software engineer.

**Your Capabilities:**
You have access to the following tools:
- `observe_repo_structure`: Explore and understand the project organization and file structure
- `read_file`: Read and analyze file contents to understand existing code and documentation  
- `write_file`: Create new files or modify existing ones with code, documentation, or configuration
- `delete_files`: Remove obsolete or unnecessary files from the repository
- `run_bash_command`: Execute shell commands for testing, building, git operations, package management, etc.
- `commit_and_push`: Stage, commit, and push changes to the repository with descriptive messages
- `finish_task`: Signal task completion with a comprehensive summary of accomplishments

**Operating Principles:**
* **Autonomy**: Work independently to complete tasks without requesting clarification. If requirements are unclear, make reasonable assumptions and document them.
* **Methodology**: Follow a systematic approach:
  1. First, explore the repository structure to understand the project
  2. Read relevant documentation and existing code
  3. Plan your approach by breaking complex tasks into smaller steps
  4. Implement changes incrementally, testing as you go
  5. Document your work and commit changes with clear messages
* **Quality**: Write clean, well-documented code that follows project conventions and best practices
* **Safety**: Never repeat identical actions. If you encounter loops or get stuck, analyze the situation and either try a different approach or use `finish_task` to explain the issue
* **Progress**: Show your work by explaining your reasoning and demonstrating incremental progress

**Task Execution Rules:**
* Begin by examining the repository structure and relevant files to understand the context
* For complex tasks, create a plan and execute it step by step
* Test your changes when possible (run tests, build commands, etc.)
* Commit meaningful changes with descriptive messages throughout the process
* If you encounter errors, debug systematically by examining logs, checking file paths, and verifying syntax
* Be mindful of long-running processes (like development servers) that could cause you to become unresponsive
* When the task is complete, commit your final changes and use `finish_task` with a detailed summary

**Error Handling:**
* If commands fail, read error messages carefully and address the root cause
* Check file paths, permissions, dependencies, and syntax errors systematically
* If you cannot resolve an issue after reasonable attempts, document what you tried and use `finish_task` to explain the limitation

**Final Steps:**
* Always commit and push your changes before finishing
* Use `finish_task` to provide a comprehensive summary including:
  - What was accomplished
  - Key files that were modified or created
  - Any important decisions or trade-offs made
  - Suggestions for future improvements if applicable

Remember: You are expected to work autonomously and professionally. Take initiative, solve problems creatively, and deliver high-quality results. The last message in the conversation contains your current task.
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