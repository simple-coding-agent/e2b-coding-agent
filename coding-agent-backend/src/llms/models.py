import os
from dotenv import load_dotenv
from typing import Dict, List, Tuple, Optional
import json
from abc import ABC, abstractmethod
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
from .tools import BaseTool

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
                model: str = "anthropic/claude-sonnet-4",
                api_key_name: str = "OPENROUTER_API_KEY"
                ):

        self.model = model
        open_router_api_key = os.environ.get(api_key_name)
        self.client = OpenAI(base_url="https://openrouter.ai/api/v1",
                             api_key=open_router_api_key)
        
        self.tools = tools
        self._event_callback = None
        # Using a shared executor can be more efficient
        self._executor = ThreadPoolExecutor(max_workers=5)
    
    def set_event_callback(self, callback):
        self._event_callback = callback
    
    def emit_event(self, event_type: str, data: dict):
        """Emit a standardized, hierarchical event for the LLM."""
        if self._event_callback:
            full_event_type = f"llm.{event_type}"
            # The callback now expects the full event dictionary
            self._event_callback({
                "type": full_event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            })

    async def complete_async(self, messages: list):
        """
        Async version that allows events to be sent in real-time.
        """
        self.emit_event("start", {
            "model": self.model,
            "message_count": len(messages)
        })

        # **REFACTOR REFINEMENT: Use get_running_loop() for robustness.**
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

        # Append assistant response before processing tools
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
        Handles execution of tool calls asynchronously to allow real-time event streaming.
        """
        tool_call_responses = []
        
        # **REFACTOR REFINEMENT: Use get_running_loop() for robustness.**
        loop = asyncio.get_running_loop()

        for tool_call in tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments)
                tool_name = tool_call.function.name
                
                self.emit_event("tool_call.start", {
                    "tool_name": tool_name,
                    "arguments": arguments
                })

                if tool_name in self.tools:
                    # Run tool execution in thread pool to avoid blocking
                    tool_response = await loop.run_in_executor(
                        self._executor,
                        lambda: self.tools[tool_name].execute(**arguments)
                    )
                    
                    self.emit_event("tool_call.end", {
                        "tool_name": tool_name,
                        "response_preview": tool_response[:200] if isinstance(tool_response, str) else str(tool_response)[:200]
                    })
                    
                    tool_call_responses.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": tool_response
                    })
                else:
                    error_msg = f"Tool '{tool_name}' not found."
                    self.emit_event("tool_call.error", {"tool_name": tool_name, "error": error_msg})
                    tool_call_responses.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_name, "content": error_msg})
            
            except json.JSONDecodeError as e:
                error_msg = f"Invalid JSON in arguments for tool '{tool_call.function.name}': {e}"
                self.emit_event("tool_call.error", {"tool_name": tool_call.function.name, "error": error_msg})
                tool_call_responses.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_call.function.name, "content": error_msg})
            except Exception as e:
                import traceback
                error_msg = f"Error executing tool '{tool_call.function.name}': {e}"
                self.emit_event("tool_call.error", {"tool_name": tool_call.function.name, "error": error_msg, "traceback": traceback.format_exc()})
                tool_call_responses.append({"role": "tool", "tool_call_id": tool_call.id, "name": tool_call.function.name, "content": error_msg})


        return tool_call_responses

    def complete(self, messages: list):
        """
        Synchronous version for backward compatibility.
        Note: This won't stream events in real-time.
        """
        self.emit_event("start", {
            "model": self.model,
            "message_count": len(messages)
        })

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=[tool.function_schema for tool in self.tools.values()],
            tool_choice="auto"
        )

        response_message = response.choices[0].message

        self.emit_event("end", {
            "model": self.model,
            "finish_reason": response.choices[0].finish_reason,
            "has_tool_calls": bool(response_message.tool_calls)
        })

        messages.append({
            "role": "assistant",
            "content": response_message.content,
            "tool_calls": response_message.tool_calls
        })

        if response_message.tool_calls:
            tool_responses = self._handle_tool_calls(response_message.tool_calls)
            messages.extend(tool_responses)

        return response_message.content, messages

    def _handle_tool_calls(self, tool_calls):
        """Original synchronous version."""
        tool_call_responses = []

        for tool_call in tool_calls:
            self.emit_event("tool_call", {
                "tool_name": tool_call.function.name,
                "arguments": json.loads(tool_call.function.arguments)
            })

            tool_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)

            if tool_name in self.tools:
                tool_response = self.tools[tool_name].execute(**arguments)

                tool_call_responses.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": tool_response
                })
            else:
                print(f"The tool {tool_name} has been hallucinated by the LLM.")
                tool_call_responses.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": f"The tool does not exist."
                })

        return tool_call_responses
