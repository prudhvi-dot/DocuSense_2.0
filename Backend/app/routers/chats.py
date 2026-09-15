import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
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

    result = db.execute(select(models.Chat).where(models.Chat.doc_id == doc_id))
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

    chat_result = db.execute(select(models.Document).where(models.Document == doc_id))
    fetched_chat = chat_result.scalars().first()

    human_message = models.Message(
        chat_id=fetched_chat.id, role="human", message=question
    )
    db.add(human_message)

    result = db.execute(select(models.Document).where(models.Document.id == doc_id))
    doc = result.scalars().first()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found"
        )

    if doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this chat",
        )

    result = chatbot.invoke(
        {"question": question, "messages": [HumanMessage(content=question)]},
        config={
            "configurable": {
                "thread_id": fetched_chat.id,
                "user_id": current_user.id,
                "doc_id": doc_id,
            }
        },
    )

    ai_message = models.Message(
        chat_id=fetched_chat.id, role="ai", message=result["messages"][-1].content
    )
    db.add(ai_message)

    db.commit()

    return {"ai_response": result["messages"][-1].content}
