from app.routers import chats, documents, users
from fastapi import FastAPI

app = FastAPI()

app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(chats.router, prefix="/api/chats", tags=["chats"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
