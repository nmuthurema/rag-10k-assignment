
import torch
from typing import List, Dict
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb import PersistentClient
from rank_bm25 import BM25Okapi

EMBED_MODEL_NAME = "BAAI/bge-base-en"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"
COLLECTION_NAME = "sec_10k"

def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"

class Retriever:
    def __init__(self, persist_dir: str = "chroma_db"):
        print("Connecting to vector database...")
        self.client = PersistentClient(path=persist_dir)
        self.collection = self.client.get_collection(COLLECTION_NAME)
        print("Loading full corpus...")
        self.all_docs = self.collection.get(include=["documents", "metadatas"])
        if len(self.all_docs["documents"]) == 0:
            raise ValueError("Empty collection")
        self.bm25 = BM25Okapi([doc.split() for doc in self.all_docs["documents"]])
        print("Loading models...")
        self.embed_model = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())
        self.reranker = CrossEncoder(RERANK_MODEL_NAME, device=get_device())
        print("✅ Retriever ready")
    
    def dense_retrieve(self, query: str, top_k: int = 25):
        query_emb = self.embed_model.encode([query], convert_to_numpy=True).tolist()
        results = self.collection.query(query_embeddings=query_emb, n_results=top_k, include=["documents", "metadatas"])
        docs = []
        for i in range(len(results["documents"][0])):
            docs.append({"text": results["documents"][0][i], "metadata": results["metadatas"][0][i]})
        return docs
    
    def keyword_retrieve(self, query: str, top_k: int = 25):
        scores = self.bm25.get_scores(query.split())
        idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        docs = []
        for i in idx:
            docs.append({"text": self.all_docs["documents"][i], "metadata": self.all_docs["metadatas"][i]})
        return docs
    
    def rerank(self, query: str, docs: List[Dict], top_k: int = 8):
        if len(docs) == 0:
            return []
        seen = set()
        unique_docs = []
        for d in docs:
            if d["text"] not in seen:
                unique_docs.append(d)
                seen.add(d["text"])
        pairs = [(query, d["text"]) for d in unique_docs]
        scores = self.reranker.predict(pairs, batch_size=16)
        ranked = sorted(zip(unique_docs, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in ranked[:top_k]]
    
    def retrieve(self, query: str, top_k: int = 8):
        dense = self.dense_retrieve(query, top_k=25)
        keyword = self.keyword_retrieve(query, top_k=25)
        combined = dense + keyword
        return self.rerank(query, combined, top_k)
