from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# Import the new router
from src.api.routers import router

# Load environment variables from .env file
load_dotenv()

# We can validate essential env vars at startup
E2B_API_KEY = os.environ.get("E2B_API_KEY")
if not E2B_API_KEY:
    raise RuntimeError("E2B_API_KEY not found in .env file. Please add it.")

# --- App Initialization ---
app = FastAPI(
    title="Coding Agent Backend",
    description="An API for running an agentic coding assistant with stateful sessions.",
    version="1.0.0",
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your Next.js frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
# Include all the endpoints from our new router file
app.include_router(router, prefix="/api")


# --- Root Endpoint ---
@app.get("/", tags=["Root"])
async def read_root():
    return {
        "message": "Welcome to the Coding Agent API. See /docs for available endpoints."
    }

