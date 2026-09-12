from app.routers import users
from fastapi import FastAPI

app = FastAPI()

app.include_router(users.router, prefix="/api/users", tags=["users"])
