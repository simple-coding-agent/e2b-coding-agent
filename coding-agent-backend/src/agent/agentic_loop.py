# src/agent/agentic_loop.py

from typing import List, Dict, Any, Tuple
from ..llms.models import OpenRouterModel

class AgenticLoop:
    """
    Manages an agentic loop that processes a user query through multiple LLM iterations
    until the task is completed or max iterations is reached.
    """
    
    def __init__(self, llm_model: "OpenRouterModel", initial_query: str, max_iterations: int = 50):
        """
        Initialize the agentic loop.
        
        Args:
            max_iterations: Maximum number of LLM calls allowed
            llm_model: The LLM model instance to use for completions (already configured with tools)
            initial_query: The initial user query to process
        """
        self.max_iterations = max_iterations
        self.llm_model = llm_model
        self.initial_query = initial_query
        self._should_stop = False
        
        # Initialize messages with the user query
        self.messages = [
            {
                'role': 'user',
                'content': initial_query
            }
        ]
        
        self.iteration_count = 0
    
    def stop(self):
        """Method to be called by FinishTask to stop the loop"""
        self._should_stop = True
    
    def run(self) -> Tuple[str, List[Dict[str, str]]]:
        """
        Run the agentic loop until completion or max iterations.
        
        Returns:
            Tuple of (final_response, conversation_history)
        """
        print(f"Starting agentic loop with query: {self.initial_query}")
        print(f"Maximum iterations: {self.max_iterations}")
        print("="*60)
        
        while self.iteration_count < self.max_iterations and not self._should_stop:
            self.iteration_count += 1
            print(f"\n--- Iteration {self.iteration_count}/{self.max_iterations} ---")
            
            try:
                response, self.messages = self.llm_model.complete(self.messages)
                
                # Print the response for debugging
                print(f"LLM Response: {response[:200]}..." if len(response) > 200 else f"LLM Response: {response}")
                
                # Check if we should stop (finish_task was called)
                if self._should_stop:
                    print("\nTask completed - finish_task was called")
                    return response, self.messages
                
            except Exception as e:
                error_msg = f"Error during iteration {self.iteration_count}: {str(e)}"
                print(f"\n{error_msg}")
                
                # Add error message to conversation
                self.messages.append({
                    'role': 'system',
                    'content': f"An error occurred: {str(e)}. Please handle this appropriately."
                })
                
                # Continue to next iteration unless this was the last one
                if self.iteration_count >= self.max_iterations:
                    return error_msg, self.messages
        
        # Reached max iterations without completing
        if not self._should_stop:
            timeout_msg = f"\n⚠️  Reached maximum iterations ({self.max_iterations}) without completing the task."
            print(timeout_msg)
            
            # Give the model one last chance to summarize
            self.messages.append({
                'role': 'system',
                'content': "You have reached the maximum number of iterations. Please use the finish_task tool to summarize what was accomplished so far."
            })
            
            # One final call
            try:
                response, self.messages = self.llm_model.complete(self.messages)
                return response, self.messages
            except:
                return timeout_msg, self.messages
        
        return "Task completed", self.messages
