from abc import ABC, abstractmethod
from e2b_desktop import Sandbox

class BaseTool(ABC):
    @property
    @abstractmethod
    def name(self):
        pass

    @property
    @abstractmethod
    def function_schema(self):
        pass

    @abstractmethod
    def execute(self, **kwargs):
        pass


class Speak(BaseTool):
    name = "speak"
    # function_schema is a dictionary that describes the function and its parameters
    function_schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": "Say something to the user",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to be sent to the user." 
                    }
                },
                "required": ["key_sequence"]
            }
        }
    }
    
    def execute(self, message: str):
        print(f"The LLM used the speak tool with the message: {message}")
        return message
