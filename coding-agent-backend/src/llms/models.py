import os
from dotenv import load_dotenv
from typing import Dict, List, Tuple, Optional, Callable
import json
from abc import ABC, abstractmethod
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from .tools import BaseTool, TaskFinished

load_dotenv()

class BaseModel(ABC):
    @abstractmethod
    def complete(self, **kwargs):
        pass
    
    @abstractmethod
    async def complete_async(self, **kwargs):
        pass


class OpenRouterModel(BaseModel):
    def __init__(self, 
                tools: Dict[str, BaseTool] = {},
                model: str = "openai/gpt-4o",
                api_key_name: str = "OPENROUTER_API_KEY"
                ):

        self.model = model
        open_router_api_key = os.environ.get(api_key_name)
        if not open_router_api_key:
            raise ValueError(f"API key '{api_key_name}' not found in environment variables.")
        self.client = OpenAI(base_url="https://openrouter.ai/api/v1",
                             api_key=open_router_api_key)
        
        self.tools = tools

        self._event_callback: Optional[Callable[[Dict], None]] = None
        self._executor = ThreadPoolExecutor(max_workers=5)
    
    def set_event_callback(self, callback: Callable[[Dict], None]):
        self._event_callback = callback
    
    def emit_event(self, event_type: str, data: dict):
        """Emit a standardized, hierarchical event, namespaced with 'llm.'."""
        if self._event_callback:
            # All events from this class are prefixed to ensure clear origin.
            full_event_type = f"llm.{event_type}"
            self._event_callback({
                "type": full_event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            })

    async def complete_async(self, messages: list) -> Tuple[Optional[str], list]:
        """
        Async version that emits granular events for thoughts and tool calls.
        """
        self.emit_event("start", {
            "model": self.model,
            "message_count": len(messages)
        })

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            self._executor,
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[tool.function_schema for tool in self.tools.values()],
                tool_choice="auto"
            )
        )

        response_message = response.choices[0].message

        self.emit_event("end", {
            "model": self.model,
            "finish_reason": response.choices[0].finish_reason,
            "has_tool_calls": bool(response_message.tool_calls)
        })

        if response_message.content:
            self.emit_event("thought", {
                "text": response_message.content
            })

        messages.append({
            "role": "assistant",
            "content": response_message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in response_message.tool_calls
            ] if response_message.tool_calls else None,
        })

        if response_message.tool_calls:
            tool_responses = await self._handle_tool_calls_async(response_message.tool_calls)
            messages.extend(tool_responses)

        return response_message.content, messages

    async def _handle_tool_calls_async(self, tool_calls):
        """
        Handles execution of tool calls asynchronously, emitting events for each step.
        """
        tool_call_responses = []
        loop = asyncio.get_running_loop()

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments)

                self.emit_event("tool_call.start", {
                    "tool_name": tool_name,
                    "arguments": arguments
                })

                if tool_name in self.tools:
                    tool_response_content = await loop.run_in_executor(
                        self._executor,
                        lambda: self.tools[tool_name].execute(**arguments)
                    )
                    
                    response_str = str(tool_response_content)
                    self.emit_event("tool_call.end", {
                        "tool_name": tool_name,
                        "was_successful": True,
                        "response_preview": response_str[:250] + "..." if len(response_str) > 250 else response_str
                    })
                    
                    tool_call_responses.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": response_str # Ensure content is a string
                    })
                else:
                    error_msg = f"Tool '{tool_name}' not found or is not available."
                    self.emit_event("tool_call.end", {"tool_name": tool_name, "was_successful": False, "error": error_msg})
                    tool_call_responses.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": error_msg})


            except TaskFinished:
                # We re-raise it immediately so the AgenticLoop can catch it and stop gracefully.
                raise

            
            except Exception as e:
                import traceback
                error_msg = f"Failed to execute tool '{tool_name}': {str(e)}"
                self.emit_event("tool_call.end", {"tool_name": tool_name, "was_successful": False, "error": error_msg, "traceback": traceback.format_exc()})
                tool_call_responses.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": error_msg})

        return tool_call_responses

    # --- Synchronous methods for fallback/testing ---

    def complete(self, messages: list):
        # Note: This won't stream events in real-time. It's a blocking call.
        return asyncio.run(self.complete_async(messages))

    def _handle_tool_calls(self, tool_calls):

        tool_call_responses = []

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            self.emit_event("tool_call.start", {
                "tool_name": tool_name,
                "arguments": arguments
            })

            if tool_name in self.tools:
                tool_response = self.tools[tool_name].execute(**arguments)
                tool_call_responses.append({
                    "role": "tool", "tool_call_id": tool_call.id,
                    "name": tool_name, "content": str(tool_response)
                })
            else:
                error_msg = f"The tool '{tool_name}' does not exist."
                tool_call_responses.append({
                    "role": "tool", "tool_call_id": tool_call.id,
                    "name": tool_name, "content": error_msg
                })
            
            self.emit_event("tool_call.end", {
                "tool_name": tool_name,
                "was_successful": tool_name in self.tools
            })
                
        return tool_call_responses
