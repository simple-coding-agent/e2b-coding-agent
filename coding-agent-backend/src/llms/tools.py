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


class ObserveRepoStructure(BaseTool):
    name = "observe_repo_structure"
    function_schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": "Observe the repository file structure to understand project organization",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_depth": {
                        "type": "integer",
                        "description": "Maximum depth to traverse in the directory tree. depth 3 is recommended."
                    },
                    "show_hidden": {
                        "type": "boolean",
                        "description": "Whether to show hidden files and directories (those starting with .)"
                    }
                },
                "required": ["max_depth", "show_hidden"]
            }
        }
    }

    def __init__(self, repo):
        self.repo = repo
    
    def execute(self, max_depth: int, show_hidden: bool):
        return self.repo.observe_repo_structure(max_depth=max_depth, show_hidden=show_hidden)


class ReadFile(BaseTool):
    name = "read_file"
    function_schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": "Read the contents of a specific file in the repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file relative to the repository root (e.g., 'src/main.py' or 'README.md')"
                    }
                },
                "required": ["file_path"]
            }
        }
    }

    def __init__(self, repo):
        self.repo = repo
    
    def execute(self, file_path: str):
        return self.repo.read_file(file_path=file_path)
