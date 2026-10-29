"""Заготовка серверной части для следующих лабораторных работ."""
from fastapi import FastAPI
app = FastAPI(title="Academy AI — IELTS Prep")


@app.get("/")
def home():
    return {"message": "Academy AI: IELTS preparation"}
