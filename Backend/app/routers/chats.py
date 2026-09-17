import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import (
    CurrentUser,
)
from app.config.database import get_db
from app.models import models
from app.RAG.retrieve import chatbot
from app.schemas import ChatMessageRequest

router = APIRouter()


@router.get("/{doc_id}/get_messages", status_code=status.HTTP_200_OK)
def get_all_messages(
    doc_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):

    result = db.execute(select(models.Chat).where(models.Chat.document_id == doc_id))
    chat = result.scalars().first()

    messages_result = db.execute(
        select(models.Message).where(models.Message.chat_id == chat.id)
    )
    messages = messages_result.scalars().all()

    return {"messages": messages}


@router.put("/{doc_id}")
def chat(
    chat: ChatMessageRequest,
    doc_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):
    question = chat.question

    doc = (
        db.execute(select(models.Document).where(models.Document.id == doc_id))
        .scalars()
        .first()
    )

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this chat",
        )

    chat_id = doc.chat.id

    result = chatbot.invoke(
        {
            "question": question,
            "messages": [HumanMessage(content=question)],
        },
        config={
            "configurable": {
                "thread_id": chat_id,
                "user_id": current_user.id,
                "doc_id": doc_id,
            }
        },
    )

    full_answer = result["answer"]

    try:
        human_message = models.Message(
            chat_id=chat_id,
            role="human",
            message=question,
        )

        ai_message = models.Message(
            chat_id=chat_id,
            role="ai",
            message=full_answer,
        )

        db.add_all([human_message, ai_message])
        db.commit()

        print("Messages saved successfully")

    except Exception as e:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )

    return {
        "message": full_answer,
    }
