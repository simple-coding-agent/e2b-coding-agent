from abc import ABC, abstractmethod
from e2b_desktop import Sandbox
from typing import Optional, Callable, Dict, Any
from datetime import datetime

class BaseTool(ABC):
    def __init__(self):
        self._event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    
    def set_event_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Set a callback function to be called when events occur"""
        self._event_callback = callback
    
    def emit_event(self, event_type: str, data: dict):
        """Emit a standardized, hierarchical event."""
        if self._event_callback:
            full_event_type = f"tool.{event_type}"
            event_data = {
                "tool_name": self.name,
                **data # merge the payload
            }
            self._event_callback({
                "type": full_event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "data": event_data
            })

    
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


class TaskFinished(Exception):
    """Custom exception raised by FinishTask tool to signal graceful task completion."""
    def __init__(self, summary: str):
        self.summary = summary
        super().__init__(f"Task finished with summary: {summary}")


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
                        "description": "Maximum depth to traverse in the directory tree. depth 1 is recommended initially."
                        " If more information needed, increase the depth in second call."
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
        super().__init__()
        self.repo = repo
    
    def execute(self, max_depth: int, show_hidden: bool):
        self.emit_event("start", {
            "max_depth": max_depth,
            "show_hidden": show_hidden
        })
        
        try:
            structure = self.repo.observe_repo_structure(max_depth=max_depth, show_hidden=show_hidden)
            
            self.emit_event("end", {
                "structure_preview": structure[:1000] + "..." if len(structure) > 1000 else structure,
                "total_length": len(structure),
                "lines_count": len(structure.split('\n'))
            })
            
            return structure
        except Exception as e:
            self.emit_event("error", {
                "error": str(e)
            })
            raise


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
        super().__init__()
        self.repo = repo
    
    def execute(self, file_path: str):
        self.emit_event("start", {"file_path": file_path})
        
        try:
            content = self.repo.read_file(file_path=file_path)
            self.emit_event("end", {
                "content_preview": content[:500] + "..." if len(content) > 500 else content,
                "content_length": len(content),
                "lines_count": len(content.split('\n')),
                "file_type": file_path.split('.')[-1] if '.' in file_path else "unknown"
            })
            
            return content
        except Exception as e:
            self.emit_event("error", {"error": str(e)})
            raise


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
        super().__init__()
        self.repo = repo
    
    def execute(self, file_path: str, content: str):
        self.emit_event("start", {
            "file_path": file_path,
            "content_length": len(content),
            "lines": len(content.split('\n'))
        })
        
        try:
            result = self.repo.write_file(file_path=file_path, content=content)
            self.emit_event("end", {
                "status": "file_written",
                "content_preview": content[:200] + "..." if len(content) > 200 else content,
                "bytes_written": len(content.encode('utf-8')),
                "file_type": file_path.split('.')[-1] if '.' in file_path else "unknown"
            })
            
            return result
        except Exception as e:
            self.emit_event("error", {"error": str(e)})
            raise


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
        super().__init__()
        self.repo = repo
    
    def execute(self, file_paths: list[str]):
        self.emit_event("start", {
            "file_paths": file_paths,
            "file_count": len(file_paths)
        })
        
        try:
            result = self.repo.delete_files(file_paths=file_paths)
            self.emit_event("end", {
                "status": "files_deleted",
                "deleted_count": len(file_paths),
                "operation_result": result
            })
            
            return result
        except Exception as e:
            self.emit_event("error", {"error": str(e)})
            raise


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
        super().__init__()
        self.repo = repo
    
    def execute(self, commit_message: str):
        self.emit_event("start", {
            "commit_message": commit_message
        })
        
        try:
            result = self.repo.commit_and_push_to_main(commit_message=commit_message)
            self.emit_event("end", {
                "status": "committed_and_pushed",
                "commit_result": result,
                "message_length": len(commit_message)
            })
            
            return result
        except Exception as e:
            self.emit_event("error", {"error": str(e)})
            raise


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
    
    def __init__(self):
        super().__init__()
    
    def execute(self, summary: str):
        self.emit_event("start", {
            "summary": summary
        })
        
        try:
            # The agent loop will be stopped by the exception handling
            result = (
                f"\n{'='*60}\nTask Completion Report\n{'='*60}\n"
                f"Summary: {summary}\n"
                f"{'='*60}\n"
            )
            self.emit_event("end", {
                "status": "task_finished",
                "final_report": result,
                "summary_length": len(summary)
            })
            

            raise TaskFinished(summary)
            
        except TaskFinished:
            raise # Re-raise to ensure it's caught by the agent loop
        except Exception as e:
            self.emit_event("error", {"error": str(e)})
            raise


class RunCommand(BaseTool):
    name = "run_bash_command"
    function_schema = {
        "type": "function",
        "function": {
            "name": name,
            "description": (
                "Executes a shell command in the root of the repository. "
                "Useful for running tests, build scripts, or other command-line tools like controlling git. "
                "Can execute multiple commands chained with '&&'. Returns the command output."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute (e.g., 'git --help' or 'pytest')."
                    }
                },
                "required": ["command"]
            }
        }
    }

    def __init__(self, repo):
        super().__init__()
        self.repo = repo

    def execute(self, command: str):
        self.emit_event("start", {"command": command})
        
        output = self.repo.run_bash_command_in_repo_root(command_to_run=command)
        
        self.emit_event("end", {
            "output_preview": output[:1000] + "..." if len(output) > 1000 else output,
            "output_length": len(output),
            "command": command
        })
        
        return output
