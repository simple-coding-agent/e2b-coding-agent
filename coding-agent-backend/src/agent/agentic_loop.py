from typing import List, Dict, Any, Tuple, Optional, Callable
import asyncio
from datetime import datetime

class AgenticLoop:
    """
    Manages an agentic loop that processes a user query through multiple LLM iterations
    until the task is completed or max iterations is reached.
    """
    
    def __init__(self, max_iterations: int, llm_model, initial_query: str):
        self.max_iterations = max_iterations
        self.llm_model = llm_model
        self.initial_query = initial_query
        self._should_stop = False
        self._event_callback: Optional[Callable[[Dict[str, Any]], None]] = None

        self.system_prompt = """
        You are a coding agent which accomplishes a user tasks. You are always working with a repository.
        You can observe and control the repository using the tools. 
        Rules: - You will always receive a single user message. Work autonomously to finish the task, never ask for clarifications. If there is no task, use the finish task tool.
        Once you are finished with the task, use the finish_task tool call.
        - You are encouraged to use planning steps, when the task is complex.
        - If you get stuck on the task, consider either: do a planning step or use the finish_task tool and explain why you did not succeed.
        Always make sure your solution is valid and document it properly.
        """
        
        self.messages = [
            {'role': 'system', 'content': self.system_prompt},
            {'role': 'user', 'content': initial_query}
        ]
        
        self.iteration_count = 0
    
    def set_event_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set a callback for streaming events"""
        self._event_callback = callback
    
    def emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit an event if callback is set"""
        if self._event_callback:
            event = {
                "type": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            }
            self._event_callback(event)
    
    def stop(self):
        """Method to be called by FinishTask to stop the loop"""
        self._should_stop = True
    
    async def run_async(self) -> Tuple[str, List[Dict[str, str]]]:
        """
        Run the agentic loop asynchronously to support streaming.
        """
        self.emit_event("agent.loop.start", {
            "query": self.initial_query,
            "max_iterations": self.max_iterations
        })
        
        final_response_content = "Loop ended without a final response."

        while self.iteration_count < self.max_iterations and not self._should_stop:
            self.iteration_count += 1
            
            self.emit_event("agent.iteration.start", {
                "iteration": self.iteration_count,
                "max_iterations": self.max_iterations
            })
            
            try:
                # The llm_model will now emit its own granular events (`llm.thought`, `llm.tool_call`, etc.)
                response_content, self.messages = await self.llm_model.complete_async(self.messages)
                
                if response_content:
                    final_response_content = response_content

                # **FIX: Remove the old `agent.response` event and add a clear `iteration.end` event.**
                # This provides a clean structural signal to the frontend that a full cycle is complete.
                self.emit_event("agent.iteration.end", {
                    "iteration": self.iteration_count,
                    "stop_condition_met": self._should_stop
                })
                
                if self._should_stop:
                    self.emit_event("agent.loop.complete", {
                        "reason": "task_finished_by_tool",
                        "iterations": self.iteration_count
                    })
                    # The `finish_task` tool provides the final response content
                    return final_response_content, self.messages
                
                await asyncio.sleep(0.1) # Small delay to allow event queue to process
                
            except Exception as e:
                import traceback
                self.emit_event("agent.error", {
                    "iteration": self.iteration_count,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })
                self.messages.append({'role': 'system', 'content': f"An error occurred: {str(e)}."})
                if self.iteration_count >= self.max_iterations:
                    return str(e), self.messages
        
        if not self._should_stop:
            self.emit_event("agent.loop.max_iterations", {
                "iterations": self.max_iterations
            })
            self.messages.append({'role': 'system', 'content': "You have reached the maximum number of iterations. Please use the finish_task tool to summarize what was accomplished."})
            
            try:
                response_content, self.messages = await self.llm_model.complete_async(self.messages)
                return response_content or "Max iterations reached.", self.messages
            except Exception as e:
                return f"Max iterations reached, and a final error occurred: {str(e)}", self.messages
        
        return final_response_content, self.messages