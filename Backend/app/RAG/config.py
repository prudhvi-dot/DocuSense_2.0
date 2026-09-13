from functools import lru_cache

from app.config.config import settings
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone


@lru_cache
def get_embedding_model():
    return OpenAIEmbeddings(model="text-embedding-3-small")


@lru_cache
def get_pinecone_index():
    pc = Pinecone(api_key=settings.PINECONE_API_KEY)
    index = pc.Index("docusense2")
    return index


@lru_cache
def get_vectorstore():
    vector_store = PineconeVectorStore(
        index=get_pinecone_index(), embedding=get_embedding_model()
    )
    return vector_store
