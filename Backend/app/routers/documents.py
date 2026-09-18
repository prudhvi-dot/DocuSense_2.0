import uuid
from typing import Annotated
import cloudinary.uploader
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.auth import (
    CurrentUser,
)
from app.config.config import settings
from app.config.database import get_db
from app.models import models
from app.RAG.ingestion import ingest
from app.schemas import DocumentDetailResponse, DocumentUploadResponse
from app.RAG.config import get_pinecone_index

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
    db.flush()

    chat = models.Chat(document_id=document.id)
    db.add(chat)
    db.commit()
    db.refresh(document)

    return {"document_id": document.id, "status": "success", "title": document.title}


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):
    stmt = select(models.Document).where(
        models.Document.id == doc_id,
        models.Document.user_id == current_user.id,
    )

    document = db.execute(stmt).scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    print("at cloudinary")

    cloudinary.uploader.destroy(
        document.public_id,
        resource_type="raw",
    )

    print("At pinecone")

    index = get_pinecone_index()
    index.delete(
        namespace=current_user.id,
        filter={"doc_id": document.id},
    )

    db.delete(document)
    db.commit()

    return {"message": "Document deleted successfully"}


import time


@router.get(
    "/all",
    response_model=list[DocumentDetailResponse],
    status_code=status.HTTP_200_OK,
)
def get_all_documents(
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):
    stmt = (
        select(models.Document)
        .options(selectinload(models.Document.chat))
        .where(models.Document.user_id == current_user.id)
    )

    documents = db.execute(stmt).scalars().all()

    return [
        DocumentDetailResponse(
            id=doc.id,
            title=doc.title,
            file_url=doc.file_url,
            created_at=doc.created_at,
            chat_id=doc.chat.id,
        )
        for doc in documents
    ]


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

    return DocumentDetailResponse(
        id=document.id,
        title=document.title,
        file_url=document.file_url,
        created_at=document.created_at,
        chat_id=document.chat.id,
    )
