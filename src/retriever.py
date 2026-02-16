
import torch
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb import PersistentClient

EMBED_MODEL_NAME = "BAAI/bge-base-en"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"
COLLECTION_NAME = "sec_10k"

def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"

def remove_toc_chunks(chunks: List[Dict]) -> List[Dict]:
    """Remove table of contents noise"""
    filtered = []
    for c in chunks:
        text = c["text"].lower().strip()
        if "table of contents" in text or text.startswith("table of contents"):
            continue
        filtered.append(c)
    return filtered

def rerank_reasoning(chunks: List[Dict]) -> List[Dict]:
    """Boost reasoning-relevant chunks"""
    reasoning_terms = ["strategy", "innovation", "leadership","disrupt", "success", "vision", "risk", 
                       "dependent", "central", "critical"]
    
    def score(chunk):
        t = chunk["text"].lower()
        return sum(1 for r in reasoning_terms if r in t)
    
    return sorted(chunks, key=score, reverse=True)

class QueryRouter:
    """Routes queries to appropriate retrieval strategies"""
    
    def analyze(self, query: str) -> Dict:
        q = query.lower()
        
        analysis = {
            "company": None,
            "numerical": False,
            "query_type": None,
            "keywords": []
        }
        
        # Company detection
        if "apple" in q:
            analysis["company"] = "apple"
        elif "tesla" in q:
            analysis["company"] = "tesla"
        
        # Numerical
        if any(k in q for k in ["revenue", "debt", "shares", "percentage", "income", "assets"]):
            analysis["numerical"] = True
        
        # Shares
        if "shares" in q and "outstanding" in q:
            analysis["query_type"] = "financial"
            analysis["keywords"].extend(["shares", "outstanding", "common stock"])
        
        # Debt
        if "term debt" in q:
            analysis["query_type"] = "financial"
            analysis["keywords"].extend(["term debt", "current", "non-current"])
        
        # Revenue
        if "revenue" in q and "total" in q:
            analysis["query_type"] = "financial"
            analysis["keywords"].extend(["total net sales", "revenue"])
        
        if "automotive" in q and "sales" in q:
            analysis["query_type"] = "financial"
            analysis["keywords"].extend(["automotive sales", "total revenues"])
        
        # Calculation
        if "percentage" in q and "automotive" in q:
            analysis["query_type"] = "calculation"
            analysis["keywords"].extend(["automotive sales", "total revenues"])
        
        # Vehicles
        if "vehicles" in q or "produce" in q:
            analysis["query_type"] = "factual"
            analysis["keywords"].extend(["model s", "model 3", "model x", "model y", "cybertruck"])
        
        # Reasoning
        if "elon musk" in q or "dependent" in q:
            analysis["query_type"] = "reasoning"
            analysis["keywords"].extend(["elon musk", "dependent", "leadership"])
        
        return analysis

class ImprovedRetriever:
    """Enhanced retriever with query routing and reranking"""
    
    def __init__(self, persist_dir="chroma_db"):
        print("Connecting to vector database...")
        self.client = PersistentClient(path=persist_dir)
        self.collection = self.client.get_collection(COLLECTION_NAME)
        
        print("Loading embedding + reranker models...")
        self.embed = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())
        self.reranker = CrossEncoder(RERANK_MODEL_NAME, device=get_device())
        self.router = QueryRouter()
        
        print("✅ Retriever ready")
    
    def retrieve(self, query: str, top_k: int = 10) -> Tuple[List[Dict], Dict]:
        """Retrieve with query routing"""
        analysis = self.router.analyze(query)
        query_emb = self.embed.encode([query]).tolist()
        
        # Document filter
        where = None
        if analysis.get("company"):
            doc_map = {
                "apple": "10-Q4-2024-As-Filed.pdf",
                "tesla": "tsla-20231231-gen.pdf"
            }
            where = {"document": doc_map[analysis["company"]]}
        
        # Retrieve more for filtering
        results = self.collection.query(
            query_embeddings=query_emb,
            n_results=150,
            where=where,
            include=["documents", "metadatas"]
        )
        
        docs = [
            {
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i]
            }
            for i in range(len(results["documents"][0]))
        ]
        
        # Keyword filtering
        keywords = analysis.get("keywords", [])
        if keywords:
            print(f"  🔍 Filtering for keywords: {keywords}")
            filtered = [
                d for d in docs
                if any(k.lower() in d["text"].lower() for k in keywords)
            ]
            if filtered:
                print(f"  ✅ Filtered {len(docs)} → {len(filtered)}")
                docs = filtered

        if analysis.get("numerical"):
            tables = [d for d in docs if d["metadata"].get("is_table")]
            if tables:
                print(f"  📊 Prioritizing {len(tables)} table chunks")
                docs = tables + docs

        # Remove TOC noise
        docs = remove_toc_chunks(docs)
        
        # Deduplicate
        seen = set()
        unique_docs = []
        for d in docs:
            if d["text"] not in seen:
                unique_docs.append(d)
                seen.add(d["text"])
        
        # Rerank
        pairs = [(query, d["text"]) for d in unique_docs]
        scores = self.reranker.predict(pairs, batch_size=16)
        
        ranked = sorted(zip(unique_docs, scores), key=lambda x: x[1], reverse=True)
        ranked_docs = [doc for doc, _ in ranked]
        
        # Reasoning boost
        if analysis.get("query_type") == "reasoning":
            ranked_docs = rerank_reasoning(ranked_docs)
        
        top_pages = [d["metadata"]["page"] for d in ranked_docs[:top_k]]
        print(f"  📄 Top pages: {top_pages[:5]}")
        
        # DEBUG: Show top chunks
        print()
        print("🔎 TOP RETRIEVED CHUNKS:")
        
        for i, d in enumerate(ranked_docs[:3]):
            print()
            print(f"--- Chunk {i+1} (Page {d['metadata']['page']}) ---")
            print(d["text"][:400])

            
        return ranked_docs[:top_k], analysis
