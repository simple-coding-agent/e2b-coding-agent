import os
import re
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
from e2b_code_interpreter import Sandbox
from typing import Callable, Optional

load_dotenv()

def run_command_at_path(command_to_run: str, sandbox: "Sandbox", path: str = None) -> str:
    """
    Runs a command at a specific path in the sandbox and returns its output.
    """
    # Prepend directory change if path is provided
    if path:
        full_command = f'cd {path} && {command_to_run}'
    else:
        full_command = command_to_run

    print(f"Executing in sandbox: {full_command}")
    result = sandbox.commands.run(full_command, timeout=300)

    # Consolidate output for the agent
    output_parts = []
    if result.stdout:
        output_parts.append("---STDOUT---")
        output_parts.append(result.stdout)
    
    if result.stderr:
        output_parts.append("---STDERR---")
        output_parts.append(result.stderr)

    if result.exit_code != 0:
        output_parts.append(f"---SYSTEM---\nCommand failed with exit code {result.exit_code}.")
    
    if not output_parts:
        return "Command executed successfully with no output."
    
    return "\n".join(output_parts)


class GithubRepo:
    def __init__(self, repo_url: str, sandbox: "Sandbox"):
        self.repo_url = repo_url
        self.sandbox = sandbox
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.auth_user_email = os.environ.get("GITHUB_EMAIL")
        self.auth_user_name = os.environ.get("GITHUB_USERNAME")
        
        if not all([self.github_token, self.auth_user_email, self.auth_user_name]):
            raise ValueError("GITHUB_TOKEN, GITHUB_EMAIL, and GITHUB_USERNAME must be set in .env file")
            
        self.repo_owner: Optional[str] = None
        self.repo_name: Optional[str] = None
        self._event_callback: Optional[Callable] = None

    def set_event_callback(self, callback: Callable):
        self._event_callback = callback

    def _emit_event(self, event_type: str, data: dict):
        if self._event_callback:
            event = {
                "type": f"repo.{event_type}",
                "timestamp": datetime.utcnow().isoformat(),
                "data": data,
                "source": "GithubRepo"
            }
            self._event_callback(event)

    def _parse_url(self) -> tuple[str, str]:
        patterns = [
            r"https://github\.com/([^/]+)/([^/.]+)(?:\.git)?/?$",
            r"git@github\.com:([^/]+)/([^/.]+)(?:\.git)?/?$"
        ]
        for pattern in patterns:
            match = re.match(pattern, self.repo_url)
            if match:
                owner, name = match.group(1), match.group(2)
                self._emit_event("parse.success", {"owner": owner, "name": name})
                return owner, name
        
        error_msg = f"Could not parse repository URL: {self.repo_url}"
        self._emit_event("parse.error", {"message": error_msg})
        raise ValueError(error_msg)

    def _fork_repo(self, original_owner: str, repo_name: str) -> bool:
        self._emit_event("fork.start", {"owner": original_owner, "name": repo_name})
        headers = {"Authorization": f"token {self.github_token}", "Accept": "application/vnd.github.v3+json"}
        
        fork_url = f"https://api.github.com/repos/{self.auth_user_name}/{repo_name}"
        response = requests.get(fork_url, headers=headers)
        if response.status_code == 200:
            self._emit_event("fork.exist", {"message": "Fork already exists on your account."})
            return True

        fork_api_url = f"https://api.github.com/repos/{original_owner}/{repo_name}/forks"
        response = requests.post(fork_api_url, headers=headers)
        
        if response.status_code not in [202]: # 202 Accepted
            error_msg = f"Failed to fork repository. Status: {response.status_code}, Body: {response.json()}"
            self._emit_event("fork.error", {"message": error_msg})
            raise Exception(error_msg)

        self._emit_event("fork.request_sent", {"message": "Forking repository... This may take a moment."})

        max_retries, retry_delay = 15, 5
        for i in range(max_retries):
            time.sleep(retry_delay)
            check_response = requests.get(fork_url, headers=headers)
            if check_response.status_code == 200:
                self._emit_event("fork.success", {"message": f"Fork created at {fork_url}"})
                return True
            self._emit_event("fork.wait", {"message": f"Waiting for fork creation... (attempt {i+1}/{max_retries})"})
        
        error_msg = "Fork not available after waiting. Please check your GitHub account."
        self._emit_event("fork.error", {"message": error_msg})
        raise TimeoutError(error_msg)

    def _clone_repo(self, owner: str, name: str):
        self._emit_event("clone.start", {"owner": owner, "name": name})
        # Use the authenticated user for clone URL to ensure write access
        clone_url = f"https://{self.auth_user_name}:{self.github_token}@github.com/{owner}/{name}.git"
        result = self.sandbox.commands.run(f"git clone {clone_url}", timeout=300)

        if result.exit_code != 0:
            error_msg = f"Failed to clone repository: {result.stderr or result.error}"
            self._emit_event("clone.error", {"message": error_msg})
            raise Exception(error_msg)

        self.repo_name = name
        self._emit_event("clone.success", {"message": f"Successfully cloned {owner}/{name} as '{name}'."})
    
    def _configure_git_credentials(self):
        self._emit_event("auth.start", {})
        self.sandbox.commands.run(f"git config --global user.name '{self.auth_user_name}'", timeout=60)
        self.sandbox.commands.run(f"git config --global user.email '{self.auth_user_email}'", timeout=60)
        self._emit_event("auth.success", {"message": "Git credentials configured."})

    def setup_repository(self):
        self._emit_event("setup.start", {"url": self.repo_url})
        original_owner, repo_name = self._parse_url()

        print(original_owner, repo_name)
        
        if original_owner.lower() == self.auth_user_name.lower():
            print("The user owns the repo ")
            self._emit_event("ownership.check", {"is_owner": True, "message": "You are the owner. Cloning directly."})
            self.repo_owner = original_owner
            self._clone_repo(self.repo_owner, repo_name)
        else:
            print("The user does not own the repo ")
            self._emit_event("ownership.check", {"is_owner": False, "message": "Not the owner. Forking to your account..."})
            self._fork_repo(original_owner, repo_name)
            self.repo_owner = self.auth_user_name
            self._clone_repo(self.repo_owner, repo_name)
            
        self._configure_git_credentials()
        self._emit_event("setup.end", {"message": "Repository setup complete."})

    def run_bash_command_in_repo_root(self, command_to_run: str) -> str:
        """
        Runs a shell command in the root directory of the repository and returns the output.
        """
        print(f"Running command in repo '{self.repo_name}': {command_to_run}")
        return run_command_at_path(command_to_run, self.sandbox, self.repo_name)

    def commit_and_push_to_main(self, commit_message: str):
        print(f"Committing and pushing changes: {commit_message}")
        try:
            print("Staging all changes...")
            add_result = self.sandbox.commands.run(f"cd {self.repo_name} && git add .")
            if add_result.exit_code != 0: return f"Error staging changes: {add_result.stderr}"
            
            status_result = self.sandbox.commands.run(f"cd {self.repo_name} && git status --porcelain")
            if not status_result.stdout.strip(): return "No changes to commit"
            
            print("Creating commit...")
            commit_result = self.sandbox.commands.run(f"cd {self.repo_name} && git commit -m '{commit_message}'")
            if commit_result.exit_code != 0: return f"Error creating commit: {commit_result.stderr}"
            
            print("Pushing to main branch...")
            push_result = self.sandbox.commands.run(f"cd {self.repo_name} && git push origin HEAD:main")
            if push_result.exit_code != 0: return f"Error pushing to remote: {push_result.stderr}"
            
            hash_result = self.sandbox.commands.run(f"cd {self.repo_name} && git rev-parse HEAD")
            commit_hash = hash_result.stdout.strip()[:7] if hash_result.exit_code == 0 else "unknown"
            
            return f"Successfully committed and pushed changes to main.\nCommit: {commit_hash} - {commit_message}"
        except Exception as e:
            return f"Unexpected error during commit and push: {str(e)}"

    def observe_repo_structure(self, max_depth: int = 3, show_hidden: bool = False) -> str:
        print(f"Observing structure (max depth: {max_depth}, show hidden: {show_hidden})...")
        if show_hidden:
            command = f"cd {self.repo_name} && find . -maxdepth {max_depth} | sort"
        else:
            command = f"cd {self.repo_name} && find . -maxdepth {max_depth} -not -path '*/\\.*' | sort"
        result = self.sandbox.commands.run(command)
        if result.exit_code != 0: return f"Error observing structure: {result.stderr}"
        
        tree_output = ["Repository Structure:", "="*50]
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if not line or line == '.': continue
            clean_path = line[2:] if line.startswith('./') else line
            stat_command = f"cd {self.repo_name} && stat -c '%s' '{line}' 2>/dev/null || echo 'N/A'"
            stat_result = self.sandbox.commands.run(stat_command)
            
            if stat_result.exit_code == 0 and stat_result.stdout.strip() != 'N/A':
                size = stat_result.stdout.strip()
                is_dir_command = f"cd {self.repo_name} && test -d '{line}' && echo 'dir' || echo 'file'"
                is_dir_result = self.sandbox.commands.run(is_dir_command)
                is_dir = is_dir_result.stdout.strip() == 'dir'
                depth, basename = clean_path.count('/'), os.path.basename(clean_path)
                indent = "  " * depth
                if is_dir:
                    tree_output.append(f"{indent}{basename}/ (directory)")
                else:
                    size_int = int(size)
                    if size_int < 1024: size_str = f"{size_int}B"
                    elif size_int < 1024 * 1024: size_str = f"{size_int/1024:.1f}KB"
                    else: size_str = f"{size_int/(1024*1024):.1f}MB"
                    tree_output.append(f"{indent}{basename} ({size_str})")
        
        tree_output.extend(["="*50, f"Total items: {len(lines) - 1}"])
        return "\n".join(tree_output)

    def read_file(self, file_path: str) -> str:
        print(f"Reading file: {file_path}")
        full_path = f"{self.repo_name}/{file_path}"
        check_command = f"test -f {full_path} && echo 'exists' || echo 'not found'"
        if self.sandbox.commands.run(check_command).stdout.strip() == 'not found':
            return f"Error: File '{file_path}' not found in repository"
        
        result = self.sandbox.commands.run(f"cat {full_path}")
        return result.stdout if result.exit_code == 0 else f"Error reading file: {result.stderr}"

    def write_file(self, file_path: str, content: str) -> str:
        print(f"Writing to file: {file_path}")
        full_path = f"{self.repo_name}/{file_path}"
        dir_path = os.path.dirname(file_path)
        if dir_path:
            mkdir_result = self.sandbox.commands.run(f"cd {self.repo_name} && mkdir -p {dir_path}")
            if mkdir_result.exit_code != 0: return f"Error creating directory: {mkdir_result.stderr}"
        
        import base64
        encoded_content = base64.b64encode(content.encode()).decode()
        write_command = f"cd {self.repo_name} && echo '{encoded_content}' | base64 -d > '{file_path}'"
        
        result = self.sandbox.commands.run(write_command)
        if result.exit_code != 0: return f"Error writing file: {result.stderr}"
        
        verify_result = self.sandbox.commands.run(f"test -f {full_path} && echo 'success' || echo 'failed'")
        if verify_result.stdout.strip() == 'success':
            size_result = self.sandbox.commands.run(f"stat -c '%s' {full_path}")
            file_size = size_result.stdout.strip() if size_result.exit_code == 0 else "unknown"
            return f"Successfully wrote {file_size} bytes to {file_path}"
        return f"Failed to write file {file_path}"

    def delete_files(self, file_paths: list[str]) -> str:
        print(f"Deleting {len(file_paths)} file(s)...")
        results, deleted_count, not_found_count, error_count = [], 0, 0, 0
        
        for file_path in file_paths:
            full_path = f"{self.repo_name}/{file_path}"
            check_result = self.sandbox.commands.run(f"test -f {full_path} && echo 'exists' || echo 'not found'")
            if check_result.stdout.strip() == 'not found':
                results.append(f"  - {file_path}: File not found")
                not_found_count += 1
            else:
                delete_result = self.sandbox.commands.run(f"rm {full_path}")
                if delete_result.exit_code == 0:
                    results.append(f"  ✓ {file_path}: Deleted successfully")
                    deleted_count += 1
                else:
                    results.append(f"  ✗ {file_path}: Error - {delete_result.stderr}")
                    error_count += 1
        
        summary = [
            "File Deletion Summary:", "="*50,
            f"Total files to delete: {len(file_paths)}",
            f"Successfully deleted: {deleted_count}",
            f"Not found: {not_found_count}",
            f"Errors: {error_count}", "", "Details:", *results, "="*50
        ]
        return "\n".join(summary)
