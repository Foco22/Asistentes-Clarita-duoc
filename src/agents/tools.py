import os
from langchain.tools import tool
from langsmith import traceable
from pymongo import MongoClient
from dotenv import load_dotenv

from src.agents.utils.embeddings import EmbeddingClient

load_dotenv()

embedder = EmbeddingClient()
mongo_client = MongoClient(os.getenv("MONGODB_CONNECTION_STRING"))
collection = mongo_client["agent-rag-duoc-uc"]["embeddings"]


@traceable(name="retrieve")
def retrieve(query: str, top_k: int = 5) -> list[dict]:
    query_embedding = embedder.get_embedding(query)
    results = collection.aggregate([
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": top_k * 10,
                "limit": top_k,
            }
        },
        {
            "$project": {
                "_id": 0,
                "text": 1,
                "metadata": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        }
    ])
    return list(results)


@tool
def rag_search(query: str) -> str:
    """Search the class knowledge base to answer questions about the course content."""
    docs = retrieve(query)
    if not docs:
        return "No relevant information found."
    return "\n\n".join(doc["text"] for doc in docs)
