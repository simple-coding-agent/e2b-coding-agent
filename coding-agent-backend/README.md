# Coding Agent Backend

This backend provides the core logic for the coding agent, including the agentic loop, API, and sandbox handling.

## File Structure
```
coding-agent-backend/
├── pyproject.toml
└── src/
    ├── agent/
    │   ├── __init__.py
    │   └── agentic_loop.py
    ├── api/
    │   ├── __init__.py
    │   ├── main.py
    │   ├── routers.py
    │   ├── schemas.py
    │   └── state.py
    ├── llms/
    │   ├── __init__.py
    │   ├── models.py
    │   └── tools.py
    ├── sandbox_handling/
    │   ├── __init__.py
    │   └── repo_handling.py
    └── services/
        ├── __init__.py
        └── agent_runner.py
```

- **`src/agent/agentic_loop.py`**: Manages the agentic loop, which is the main driver of the agent's behavior.
- **`src/api/`**: Contains the FastAPI application, including the main entrypoint, routers, and schemas.
- **`src/llms/`**: Handles interactions with the language models, including models and tools.
- **`src/sandbox_handling/`**: Manages the repository and file system operations.
- **`src/services/`**: Contains the agent runner, which is responsible for executing the agent's tasks.

## How it Works

The backend is a FastAPI application that exposes an API for interacting with the coding agent. The main logic is contained in the `agentic_loop.py` file, which implements the agentic loop.

When a new task is received, the `agent_runner` creates an `AgenticLoop` instance and runs it in a separate thread. The `AgenticLoop` then repeatedly calls the language model to get the next action to perform. The actions are defined in the `tools.py` file and include things like reading and writing files and running shell commands.

The `repo_handling.py` file provides a safe way to interact with the file system, by sandboxing the agent's operations to a specific directory.
