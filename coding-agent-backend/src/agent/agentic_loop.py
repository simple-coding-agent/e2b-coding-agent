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
        
        # Initialize messages with the user query
        self.messages = [
            {
                'role': 'user',
                'content': initial_query
            }
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
        
        while self.iteration_count < self.max_iterations and not self._should_stop:
            self.iteration_count += 1
            
            self.emit_event("agent.iteration.start", {
                "iteration": self.iteration_count,
                "max_iterations": self.max_iterations
            })
            
            try:
                # Call the LLM - USE THE ASYNC VERSION!
                response, self.messages = await self.llm_model.complete_async(self.messages)
                
                self.emit_event("agent.response", {
                    "iteration": self.iteration_count,
                    "response": response[:500] + "..." if len(response) > 500 else response,
                    "full_response": response
                })
                
                # Check if we should stop
                if self._should_stop:
                    self.emit_event("agent.loop.complete", {
                        "reason": "task_finished",
                        "iterations": self.iteration_count
                    })
                    return response, self.messages
                
                # Small delay to prevent overwhelming the client
                await asyncio.sleep(0.1)
                
            except Exception as e:
                self.emit_event("agent.error", {
                    "iteration": self.iteration_count,
                    "error": str(e)
                })
                
                self.messages.append({
                    'role': 'system',
                    'content': f"An error occurred: {str(e)}. Please handle this appropriately."
                })
                
                if self.iteration_count >= self.max_iterations:
                    return str(e), self.messages
        
        # Reached max iterations
        if not self._should_stop:
            self.emit_event("agent.loop.max_iterations", {
                "iterations": self.max_iterations
            })
            
            self.messages.append({
                'role': 'system',
                'content': "You have reached the maximum number of iterations. Please use the finish_task tool to summarize what was accomplished so far."
            })
            
            try:
                # USE THE ASYNC VERSION HERE TOO!
                response, self.messages = await self.llm_model.complete_async(self.messages)
                return response, self.messages
            except:
                return "Max iterations reached", self.messages
        
        return "Task completed", self.messages
