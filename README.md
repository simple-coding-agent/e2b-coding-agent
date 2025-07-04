# Coding Agent

![Image Placeholder](https://via.placeholder.com/800x400.png?text=Coding+Agent+In+Action)

This repository contains a coding agent that can clone a GitHub repository, plan and execute tasks, and interact with the user through a web interface. The agent is built with the E2B Python SDK and the frontend is a Next.js application.

The agent works in a secure E2B sandbox environment, so you don't need to have Docker installed on your machine.

## Getting Started

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/e2b-dev/coding-agent.git
    ```

2.  **Set up environment variables:**

    Create a `.env` file in the `coding-agent-backend` directory and add the following:

    ```
    E2B_API_KEY="Your E2B API key"
    OPENROUTER_API_KEY="Your OpenRouter API key"
    GITHUB_TOKEN="Your GitHub personal access token"
    GITHUB_EMAIL="Your GitHub email"
    GITHUB_USERNAME="Your GitHub username"
    ```

3.  **Run the backend:**

    ```bash
    cd coding-agent/coding-agent-backend
    pip install -r requirements.txt
    uvicorn src.api.main:app --reload
    ```

4.  **Run the frontend:**

    ```bash
    cd coding-agent/coding-agent-frontend
    npm install
    npm run dev
    ```

5.  **Open your browser:**

    Navigate to [http://localhost:3000](http://localhost:3000) to start using the coding agent.
