from dotenv import load_dotenv
from e2b_code_interpreter import Sandbox
import os

load_dotenv()

def run_command_at_path(command_to_run: str, sandbox: "Sandbox", path: str = None):
    # Prepend directory change if path is provided
    if path:
        full_command = f'cd {path} && {command_to_run}'
    else:
        full_command = command_to_run

    result = sandbox.commands.run(full_command)

    if result.exit_code != 0 or result.stderr:
        print(result.stderr or result.error or f"Exit code: {result.exit_code}")
    else:
        lines = result.stdout.strip().split('\n')
        print("Output:")
        for line in lines:
            print(line)


class GithubRepo:
    def __init__(self, 
                 repo_name: str, 
                 repo_user: str, 
                 sandbox: "Sandbox"):
        
        self.repo = repo_name
        self.repo_user = repo_user
        self.sandbox = sandbox
    
    def clone_repo_and_auth(self):
        print("Setting up GitHub repository...")
        
        github_token = os.environ.get("GITHUB_TOKEN")
        email = os.environ.get("GITHUB_EMAIL")
        username = os.environ.get("GITHUB_USERNAME")

        print(f"Cloning repository: {self.repo}")
        command_clone_repo = f"git clone https://{self.repo_user}:{github_token}@github.com/{self.repo_user}/{self.repo}.git"
        result = self.sandbox.commands.run(command_clone_repo)
        print(result)
        
        print("Configuring Git user settings...")
        print(f"Setting username: {username}")
        result = self.sandbox.commands.run(f"git config --global user.name '{username}'")
        print(result)
        
        print(f"Setting email: {email}")
        result = self.sandbox.commands.run(f"git config --global user.email '{email}'")
        print(result)
        
        print("Repository setup complete!")

    def run_bash_command_in_repo_root(self, command_to_run):
        run_command_at_path(command_to_run, self.sandbox, self.repo)


    def commit_and_push_to_main(self, commit_message: str):
        """
        Commit and push changes to the main branch.
        
        Args:
            commit_message: The commit message describing the changes
            
        Returns:
            A status message indicating success or failure
        """
        print(f"Committing and pushing changes: {commit_message}")
        
        try:
            # Stage all changes
            print("Staging all changes...")
            add_result = self.sandbox.commands.run(f"cd {self.repo} && git add .")
            if add_result.exit_code != 0:
                return f"Error staging changes: {add_result.stderr}"
            
            # Check if there are changes to commit
            status_result = self.sandbox.commands.run(f"cd {self.repo} && git status --porcelain")
            if not status_result.stdout.strip():
                return "No changes to commit"
            
            # Commit changes
            print("Creating commit...")
            commit_command = f"cd {self.repo} && git commit -m '{commit_message}'"
            commit_result = self.sandbox.commands.run(commit_command)
            if commit_result.exit_code != 0:
                return f"Error creating commit: {commit_result.stderr}"
            
            # Push to main
            print("Pushing to main branch...")
            push_result = self.sandbox.commands.run(f"cd {self.repo} && git push origin main")
            if push_result.exit_code != 0:
                return f"Error pushing to remote: {push_result.stderr}"
            
            # Get the commit hash for reference
            hash_result = self.sandbox.commands.run(f"cd {self.repo} && git rev-parse HEAD")
            commit_hash = hash_result.stdout.strip()[:7] if hash_result.exit_code == 0 else "unknown"
            
            return f"Successfully committed and pushed changes to main branch.\nCommit: {commit_hash} - {commit_message}"
            
        except Exception as e:
            return f"Unexpected error during commit and push: {str(e)}"



    ### The rest of the functions is AI generated:
    def observe_repo_structure(self, max_depth: int = 3, show_hidden: bool = False) -> str:
        """
        Observe the repository structure with detailed information.
        
        Args:
            max_depth: Maximum depth to traverse in the directory tree
            show_hidden: Whether to show hidden files/directories
            
        Returns:
            A detailed string representation of the repository structure
        """
        print(f"Observing repository structure (max depth: {max_depth}, show hidden: {show_hidden})...")
        
        # Build the find command based on parameters
        if show_hidden:
            command = f"cd {self.repo} && find . -maxdepth {max_depth} | sort"
        else:
            command = f"cd {self.repo} && find . -maxdepth {max_depth} -not -path '*/\\.*' | sort"
        
        result = self.sandbox.commands.run(command)
        
        if result.exit_code != 0:
            return f"Error observing repository structure: {result.stderr}"
        
        # Get file sizes and types
        tree_output = ["Repository Structure:"]
        tree_output.append("=" * 50)
        
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if not line or line == '.':
                continue
                
            # Remove leading './' if present
            clean_path = line[2:] if line.startswith('./') else line
            
            # Get file info
            stat_command = f"cd {self.repo} && stat -c '%s' '{line}' 2>/dev/null || echo 'N/A'"
            stat_result = self.sandbox.commands.run(stat_command)
            
            if stat_result.exit_code == 0 and stat_result.stdout.strip() != 'N/A':
                size = stat_result.stdout.strip()
                
                # Check if directory
                is_dir_command = f"cd {self.repo} && test -d '{line}' && echo 'dir' || echo 'file'"
                is_dir_result = self.sandbox.commands.run(is_dir_command)
                is_dir = is_dir_result.stdout.strip() == 'dir'
                
                # Format output
                depth = clean_path.count('/')
                indent = "  " * depth
                basename = clean_path.split('/')[-1] if '/' in clean_path else clean_path
                
                if is_dir:
                    tree_output.append(f"{indent}{basename}/ (directory)")
                else:
                    # Convert size to human readable
                    size_int = int(size)
                    if size_int < 1024:
                        size_str = f"{size_int}B"
                    elif size_int < 1024 * 1024:
                        size_str = f"{size_int/1024:.1f}KB"
                    else:
                        size_str = f"{size_int/(1024*1024):.1f}MB"
                    
                    tree_output.append(f"{indent}{basename} ({size_str})")
        
        tree_output.append("=" * 50)
        tree_output.append(f"Total items: {len(lines) - 1}")
        
        return "\n".join(tree_output)


    def read_file(self, file_path: str) -> str:
        """
        Read the contents of a single file in the repository.
        
        Args:
            file_path: Path to the file relative to the repository root
            
        Returns:
            The contents of the file as a string
        """
        print(f"Reading file: {file_path}")
        
        # Construct the full path
        full_path = f"{self.repo}/{file_path}"
        
        # Check if file exists
        check_command = f"test -f {full_path} && echo 'exists' || echo 'not found'"
        check_result = self.sandbox.commands.run(check_command)
        
        if check_result.stdout.strip() == 'not found':
            return f"Error: File '{file_path}' not found in repository"
        
        # Read the file contents
        read_command = f"cat {full_path}"
        result = self.sandbox.commands.run(read_command)
        
        if result.exit_code != 0:
            return f"Error reading file: {result.stderr}"
        
        return result.stdout

    def write_file(self, file_path: str, content: str) -> str:
        """
        Write content to a file (creates new file or replaces existing one).
        
        Args:
            file_path: Path to the file relative to the repository root
            content: Content to write to the file
            
        Returns:
            Success message or error message
        """
        print(f"Writing to file: {file_path}")
        
        # Construct the full path
        full_path = f"{self.repo}/{file_path}"
        
        # Create directories if they don't exist
        dir_path = os.path.dirname(file_path)
        if dir_path:
            mkdir_command = f"cd {self.repo} && mkdir -p {dir_path}"
            mkdir_result = self.sandbox.commands.run(mkdir_command)
            if mkdir_result.exit_code != 0:
                return f"Error creating directory: {mkdir_result.stderr}"
        
        # Write content to file using echo with proper escaping
        # Using base64 to handle special characters and multiline content
        import base64
        encoded_content = base64.b64encode(content.encode()).decode()
        write_command = f"cd {self.repo} && echo '{encoded_content}' | base64 -d > '{file_path}'"
        
        result = self.sandbox.commands.run(write_command)
        
        if result.exit_code != 0:
            return f"Error writing file: {result.stderr}"
        
        # Verify file was written
        verify_command = f"test -f {full_path} && echo 'success' || echo 'failed'"
        verify_result = self.sandbox.commands.run(verify_command)
        
        if verify_result.stdout.strip() == 'success':
            # Get file size for confirmation
            size_command = f"stat -c '%s' {full_path}"
            size_result = self.sandbox.commands.run(size_command)
            file_size = size_result.stdout.strip() if size_result.exit_code == 0 else "unknown"
            return f"Successfully wrote {file_size} bytes to {file_path}"
        else:
            return f"Failed to write file {file_path}"


    def delete_files(self, file_paths: list[str]) -> str:
        """
        Delete a list of files from the repository.
        
        Args:
            file_paths: List of file paths relative to the repository root
            
        Returns:
            Summary of deletion results
        """
        print(f"Deleting {len(file_paths)} file(s)...")
        
        results = []
        deleted_count = 0
        not_found_count = 0
        error_count = 0
        
        for file_path in file_paths:
            full_path = f"{self.repo}/{file_path}"
            
            # Check if file exists
            check_command = f"test -f {full_path} && echo 'exists' || echo 'not found'"
            check_result = self.sandbox.commands.run(check_command)
            
            if check_result.stdout.strip() == 'not found':
                results.append(f"  ❌ {file_path}: File not found")
                not_found_count += 1
                print(f"Warning: File '{file_path}' does not exist")
            else:
                # Delete the file
                delete_command = f"rm {full_path}"
                delete_result = self.sandbox.commands.run(delete_command)
                
                if delete_result.exit_code == 0:
                    results.append(f"  ✓ {file_path}: Deleted successfully")
                    deleted_count += 1
                    print(f"Deleted: {file_path}")
                else:
                    results.append(f"  ❌ {file_path}: Error - {delete_result.stderr}")
                    error_count += 1
                    print(f"Error deleting '{file_path}': {delete_result.stderr}")
        
        # Build summary
        summary_lines = [
            "File Deletion Summary:",
            "=" * 50,
            f"Total files: {len(file_paths)}",
            f"Successfully deleted: {deleted_count}",
            f"Not found: {not_found_count}",
            f"Errors: {error_count}",
            "",
            "Details:"
        ]
        summary_lines.extend(results)
        summary_lines.append("=" * 50)
        
        return "\n".join(summary_lines)

