import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    CurrentUser,
)
from app.config.config import settings
from app.config.database import get_db
from app.models import models
from app.RAG.ingestion import ingest
from app.schemas import DocumentDetailResponse, DocumentUploadResponse

router = APIRouter()

import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
)


@router.post("/upload", response_model=DocumentUploadResponse)
def upload_document(
    file: UploadFile,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
    title: str = Form(...),
):
    file_bytes = file.file.read()

    doc_id = str(uuid.uuid4())
    ingest(file_bytes, doc_id, current_user.id)

    upload_result = cloudinary.uploader.upload(
        file_bytes,
        resource_type="raw",
        public_id=doc_id,
        folder="documents",
    )

    document = models.Document(
        id=doc_id,
        title=title,
        file_url=upload_result["secure_url"],
        public_id=upload_result["public_id"],
        user_id=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return {"document_id": document.id, "status": "success"}


@router.get("/{doc_id}", response_model=DocumentDetailResponse)
def get_document(
    doc_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):
    user_id = current_user.id

    result = db.execute(select(models.Document).where(models.Document.id == doc_id))
    document = result.scalars().first()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )

    if document.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you are not Authorized to access this document",
        )

    return document
