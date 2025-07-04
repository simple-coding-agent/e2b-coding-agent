# Backend README

This document provides an overview of the backend's file structure.

## File Structure

-   `src/`: This directory contains the main source code for the backend application.
    -   `agent/`: This directory contains the core logic for the coding agent.
        -   `agentic_loop.py`: This file contains the main loop that drives the agent's behavior.
    -   `api/`: This directory contains the FastAPI application that exposes the backend's functionality.
        -   `main.py`: This file is the entry point for the FastAPI application.
        -   `routers.py`: This file defines the API routes for the backend.
        -   `schemas.py`: This file defines the data models used by the API.
        -   `state.py`: This file manages the state of the application.
    -   `llms/`: This directory contains the code for interacting with different language models.
        -   `models.py`: This file provides a unified interface for different language models.
        -   `tools.py`: This file defines the tools that the agent can use.
    -   `sandbox_handling/`: This directory contains the code for managing the E2B sandbox.
        -   `repo_handling.py`: This file handles the cloning and management of GitHub repositories.
    -   `services/`: This directory contains the business logic for the application.
        -   `agent_runner.py`: This file runs the agent and manages its lifecycle.
-   `pyproject.toml`: This file defines the project's dependencies.
