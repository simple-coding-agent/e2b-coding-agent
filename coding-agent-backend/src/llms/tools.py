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
        if self._event_callback:
            self._event_callback({
                "type": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "tool": self.name,  # Add this line
                "data": data
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
        super().__init__()
        self.repo = repo
    
    def execute(self, max_depth: int, show_hidden: bool):
        # Emit start event
        self.emit_event("tool_start", {
            "action": "observing_repository_structure",
            "max_depth": max_depth,
            "show_hidden": show_hidden
        })
        
        try:
            structure = self.repo.observe_repo_structure(max_depth=max_depth, show_hidden=show_hidden)
            
            # Emit success event
            self.emit_event("tool_complete", {
                "action": "repository_structure_observed",
                "structure_preview": structure[:1000] + "..." if len(structure) > 1000 else structure,
                "total_length": len(structure)
            })
            
            return structure
        except Exception as e:
            # Emit error event
            self.emit_event("tool_error", {
                "action": "observing_repository_structure",
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
        # Emit start event
        self.emit_event("tool_start", {
            "action": "reading_file",
            "file_path": file_path
        })
        
        try:
            content = self.repo.read_file(file_path=file_path)
            
            # Emit success event
            self.emit_event("tool_complete", {
                "action": "file_read",
                "file_path": file_path,
                "content_preview": content[:500] + "..." if len(content) > 500 else content,
                "content_length": len(content),
                "lines": len(content.split('\n'))
            })
            
            return content
        except Exception as e:
            # Emit error event
            self.emit_event("tool_error", {
                "action": "reading_file",
                "file_path": file_path,
                "error": str(e)
            })
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
        # Emit start event
        self.emit_event("tool_start", {
            "action": "writing_file",
            "file_path": file_path,
            "content_length": len(content),
            "lines": len(content.split('\n'))
        })
        
        try:
            result = self.repo.write_file(file_path=file_path, content=content)
            
            # Emit success event
            self.emit_event("tool_complete", {
                "action": "file_written",
                "file_path": file_path,
                "content_length": len(content),
                "lines": len(content.split('\n')),
                "content_preview": content[:200] + "..." if len(content) > 200 else content
            })
            
            return result
        except Exception as e:
            # Emit error event
            self.emit_event("tool_error", {
                "action": "writing_file",
                "file_path": file_path,
                "error": str(e)
            })
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
        # Emit start event
        self.emit_event("tool_start", {
            "action": "deleting_files",
            "file_paths": file_paths,
            "file_count": len(file_paths)
        })
        
        try:
            result = self.repo.delete_files(file_paths=file_paths)
            
            # Emit success event
            self.emit_event("tool_complete", {
                "action": "files_deleted",
                "file_paths": file_paths,
                "file_count": len(file_paths)
            })
            
            return result
        except Exception as e:
            # Emit error event
            self.emit_event("tool_error", {
                "action": "deleting_files",
                "file_paths": file_paths,
                "error": str(e)
            })
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
        # Emit start event
        self.emit_event("tool_start", {
            "action": "committing_and_pushing",
            "commit_message": commit_message
        })
        
        try:
            result = self.repo.commit_and_push_to_main(commit_message=commit_message)
            
            # Emit success event
            self.emit_event("tool_complete", {
                "action": "committed_and_pushed",
                "commit_message": commit_message,
                "result": result
            })
            
            return result
        except Exception as e:
            # Emit error event
            self.emit_event("tool_error", {
                "action": "committing_and_pushing",
                "commit_message": commit_message,
                "error": str(e)
            })
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

    def __init__(self, agentic_loop):
        super().__init__()
        self.agentic_loop = agentic_loop
    
    def execute(self, summary: str):
        # Emit start event
        self.emit_event("tool_start", {
            "action": "finishing_task",
            "summary": summary
        })
        
        try:
            # Signal the loop to stop
            self.agentic_loop.stop()
            
            # Format the final message
            result = f"\n{'='*60}\nTask Completion Report\n{'='*60}\n"
            result += f"Summary: {summary}\n"
            result += f"{'='*60}\n"
            
            # Emit completion event
            self.emit_event("tool_complete", {
                "action": "task_finished",
                "summary": summary,
                "final_report": result
            })
            
            return result
        except Exception as e:
            # Emit error event
            self.emit_event("tool_error", {
                "action": "finishing_task",
                "error": str(e)
            })
            raise
