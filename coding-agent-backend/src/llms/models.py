import os
from dotenv import load_dotenv
from typing import Dict, List, Tuple, Optional
import json
from abc import ABC, abstractmethod
from datetime import datetime

from openai import OpenAI
from .tools import BaseTool

load_dotenv()

class BaseModel(ABC):
    @abstractmethod
    def complete(self, **kwargs):
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
    
    def set_event_callback(self, callback):
        self._event_callback = callback
    
    def emit_event(self, event_type: str, data: dict):
        """Emit a standardized, hierarchical event for the LLM."""
        if self._event_callback:
            full_event_type = f"llm.{event_type}"
            self._event_callback({
                "type": full_event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data
            })

    def complete(self, messages: list):
        """
        Sends a conversation to the OpenAI API and processes responses,
        including tool calls when required.
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

        # Process any tool calls requested by the model
        if response_message.tool_calls:
            tool_responses = self._handle_tool_calls(response_message.tool_calls)
            # Append tool responses to messages
            messages.extend(tool_responses)

        return response_message.content, messages

    def _handle_tool_calls(self, tool_calls):
        """
        Handles execution of tool calls requested by the model.
        """
        tool_call_responses = []

        for tool_call in tool_calls:
            # REMOVED: No longer emit llm.tool_call events since we're simplifying the display
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
