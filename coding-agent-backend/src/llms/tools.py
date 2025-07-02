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
    

class WriteFile(BaseTool):
    name = "write_file"
    function_schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": "Write content to a file in the repository (creates new file or replaces existing one)",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file relative to the repository root (e.g., 'src/main.py' or 'README.md')"
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file"
                    }
                },
                "required": ["file_path", "content"]
            }
        }
    }

    def __init__(self, repo):
        self.repo = repo
    
    def execute(self, file_path: str, content: str):
        return self.repo.write_file(file_path=file_path, content=content)


class DeleteFiles(BaseTool):
    name = "delete_files"
    function_schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": "Delete one or more files from the repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_paths": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "List of file paths to delete, relative to the repository root (e.g., ['old_file.txt', 'src/deprecated.py'])"
                    }
                },
                "required": ["file_paths"]
            }
        }
    }

    def __init__(self, repo):
        self.repo = repo
    
    def execute(self, file_paths: list[str]):
        return self.repo.delete_files(file_paths=file_paths)


class CommitAndPush(BaseTool):
    name = "commit_and_push"
    function_schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": "Stage all changes, commit them with a message, and push to the main branch",
            "parameters": {
                "type": "object",
                "properties": {
                    "commit_message": {
                        "type": "string",
                        "description": "The commit message describing the changes made"
                    }
                },
                "required": ["commit_message"]
            }
        }
    }

    def __init__(self, repo):
        self.repo = repo
    
    def execute(self, commit_message: str):
        return self.repo.commit_and_push_to_main(commit_message=commit_message)
    


class FinishTask(BaseTool):
    name = "finish_task"
    function_schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": "Use this tool when you have completed the requested task. Provide a summary of what was accomplished.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "A detailed summary of what was accomplished in this task"
                    }
                },
                "required": ["summary"]
            }
        }
    }

    def __init__(self, agentic_loop):
        self.agentic_loop = agentic_loop
    
    def execute(self, summary: str):
        # Signal the loop to stop
        self.agentic_loop.stop()
        
        # Format the final message
        result = f"\n{'='*60}\nTask Completion Report\n{'='*60}\n"
        result += f"Summary: {summary}\n"
        result += f"{'='*60}\n"
        
        return result
