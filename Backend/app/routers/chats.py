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


@router.get("/{chat_id}/get_messages", status_code=status.HTTP_200_OK)
def get_all_messages(
    chat_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):

    result = db.execute(select(models.Message).where(models.Message.chat_id == chat_id))
    messages = result.scalars().all()

    return {"messages": messages}


@router.put("/{chat_id}")
def chat(
    chat: ChatMessageRequest,
    chat_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
):
    question = chat.question
    doc_id = chat.doc_id

    human_message = models.Message(chat_id=chat_id, role="human", message=question)
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
                "thread_id": chat_id,
                "user_id": current_user.id,
                "doc_id": doc_id,
            }
        },
    )

    ai_message = models.Message(
        chat_id=chat_id, role="ai", message=result["messages"][-1].content
    )
    db.add(ai_message)

    db.commit()

    return {"ai_response": result["messages"][-1].content}
