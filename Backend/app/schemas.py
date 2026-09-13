from pydantic import BaseModel, ConfigDict, EmailStr, Field
from datetime import datetime


class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=120)


class UserCreate(UserBase):
    password: str = Field(min_length=8)


class UserPrivate(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: str


class DocumentUploadResponse(BaseModel):
    document_id: str
    status: str


class DocumentDetailResponse(BaseModel):
    id: str
    title: str
    file_url: str
    created_at: datetime

    class Config:
        from_attributes = True
