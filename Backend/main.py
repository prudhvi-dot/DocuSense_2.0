from app.routers import users, documents
from fastapi import FastAPI

app = FastAPI()

app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
