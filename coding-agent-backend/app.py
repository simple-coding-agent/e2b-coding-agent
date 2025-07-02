# app.py
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/ping")
def ping():
    return {"message": "pong from FastAPI with Python 3.12"}
