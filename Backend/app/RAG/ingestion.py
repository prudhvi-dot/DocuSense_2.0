import os
import tempfile

from app.RAG.config import get_vectorstore
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langsmith import traceable

load_dotenv()


@traceable()
def load_documents(file_bytes: bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_file.write(file_bytes)
        temp_path = temp_file.name

    try:
        loader = PyPDFLoader(temp_path)
        documents = loader.load()
        return documents
    finally:
        os.remove(temp_path)


@traceable()
def split_docs(docs):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(docs)
    return chunks


@traceable()
def add_to_vector_store(chunks, doc_id):
    vector_store = get_vectorstore()
    vector_store.add_documents(chunks, namespace=doc_id)


def ingest(file, doc_id: str):

    docs = load_documents(file)
    chunks = split_docs(docs)

    chunks = [
        Document(
            page_content=chunk.page_content,
            id=f"{doc_id}_{i}",
        )
        for i, chunk in enumerate(chunks)
    ]

    add_to_vector_store(chunks, doc_id)
    return {"status": "success", "chunks_added": len(chunks)}
