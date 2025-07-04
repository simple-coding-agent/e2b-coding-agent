from typing import List, Dict, Any, Tuple, Optional, Callable
import asyncio
from datetime import datetime
# Import the new exception from tools
from src.llms.tools import TaskFinished

class AgenticLoop:
    """
    Manages an agentic loop that processes a user query through multiple LLM iterations
    until the task is completed or max iterations is reached.
    """
    
    def __init__(self, max_iterations: int, llm_model, initial_messages: List[Dict[str, Any]], initial_query_for_event: str):
        self.max_iterations = max_iterations
        self.llm_model = llm_model
        # The initial_query is now only used for event logging
        self.initial_query = initial_query_for_event
        self._event_callback: Optional[Callable[[Dict[str, Any]], None]] = None

        # The loop now receives its entire message history from the runner
        self.messages = initial_messages
        
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
    
    async def run_async(self) -> Tuple[str, List[Dict[str, str]]]:
        """
        Run the agentic loop asynchronously, handling exceptions for control flow.
        """
        self.emit_event("agent.loop.start", {
            "query": self.initial_query,
            "max_iterations": self.max_iterations
        })
        
        try:
            while self.iteration_count < self.max_iterations:
                self.iteration_count += 1
                
                self.emit_event("agent.iteration.start", {
                    "iteration": self.iteration_count,
                    "max_iterations": self.max_iterations
                })
                
                # This llm_model call can now raise TaskFinished, which will be caught below
                response_content, self.messages = await self.llm_model.complete_async(self.messages)
                
                self.emit_event("agent.iteration.end", {
                    "iteration": self.iteration_count,
                    "stop_condition_met": False
                })
                
                await asyncio.sleep(0.1)
            
            # This part is reached only if max_iterations is hit
            self.emit_event("agent.loop.max_iterations", {
                "iterations": self.max_iterations
            })
            self.messages.append({'role': 'system', 'content': "You have reached the maximum number of iterations. Please use the finish_task tool to summarize what was accomplished."})
            
            response_content, self.messages = await self.llm_model.complete_async(self.messages)
            return response_content or "Max iterations reached.", self.messages

        except TaskFinished as e:
            # This is the primary, successful exit condition
            self.emit_event("agent.loop.complete", {
                "reason": "task_finished_by_tool",
                "iterations": self.iteration_count
            })
            # The summary from the tool is the definitive final response
            return e.summary, self.messages
        
        except Exception as e:
            import traceback
            self.emit_event("agent.error", {
                "iteration": self.iteration_count,
                "error": str(e),
                "traceback": traceback.format_exc()
            })
            self.messages.append({'role': 'system', 'content': f"An error occurred: {str(e)}."})
            return str(e), self.messages
