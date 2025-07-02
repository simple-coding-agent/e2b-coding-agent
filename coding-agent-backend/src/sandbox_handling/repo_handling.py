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
        self.run_bash_command_in_repo_root("git add .")
        self.run_bash_command_in_repo_root(f"git commit -m '{commit_message}'")
        self.run_bash_command_in_repo_root("git push origin main")


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

