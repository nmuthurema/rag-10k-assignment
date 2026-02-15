
import torch
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb import PersistentClient

EMBED_MODEL_NAME = "BAAI/bge-base-en"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"
COLLECTION_NAME = "sec_10k"

def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"

class QueryRouter:
    def analyze(self, query: str):
        q = query.lower()
        return {
            "company": "apple" if "apple" in q else ("tesla" if "tesla" in q else None),
            "numerical": any(k in q for k in ["revenue", "debt", "shares", "income", "assets", "percentage"]),
            "query_type": "financial" if any(k in q for k in ["revenue", "debt", "shares"]) else None,
            "is_shares_question": "shares" in q and "outstanding" in q,
            "is_debt_question": "debt" in q and "term" in q
        }

class ImprovedRetriever:
    def __init__(self, persist_dir="chroma_db"):
        print("Connecting to vector database...")
        self.client = PersistentClient(path=persist_dir)
        self.collection = self.client.get_collection(COLLECTION_NAME)
        print("Loading models...")
        self.embed = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())
        self.reranker = CrossEncoder(RERANK_MODEL_NAME, device=get_device())
        self.router = QueryRouter()
        print("✅ Retriever ready")
    
    def retrieve(self, query: str, top_k=10) -> Tuple[List[Dict], Dict]:
        analysis = self.router.analyze(query)
        emb = self.embed.encode([query]).tolist()
        
        where = None
        if analysis.get("company"):
            doc_map = {"apple": "10-Q4-2024-As-Filed.pdf", "tesla": "tsla-20231231-gen.pdf"}
            where = {"document": doc_map[analysis["company"]]}
        
        n_results = 100
        
        results = self.collection.query(
            query_embeddings=emb,
            n_results=n_results,
            where=where,
            include=["documents", "metadatas"]
        )
        
        docs = [{"text": results["documents"][0][i], "metadata": results["metadatas"][0][i]} 
                for i in range(len(results["documents"][0]))]
        
        # CRITICAL: Force cover page for shares questions
        if analysis.get("is_shares_question") and where:
            print(f"  🎯 Shares question - fetching cover page")
            
            # Get page 2 specifically (cover page with shares outstanding)
            cover_page = self.collection.get(
                where={
                    "$and": [
                        where,
                        {"page": 2}
                    ]
                },
                include=["documents", "metadatas"],
                limit=5
            )
            
            if cover_page["documents"]:
                cover_docs = [{"text": doc, "metadata": meta} 
                             for doc, meta in zip(cover_page["documents"], cover_page["metadatas"])]
                docs = cover_docs + docs
            
            # Also get early pages 1-5
            early_pages = self.collection.get(
                where={
                    "$and": [
                        where,
                        {"page": {"$lte": 5}}
                    ]
                },
                include=["documents", "metadatas"],
                limit=20
            )
            
            early_docs = [{"text": doc, "metadata": meta} 
                         for doc, meta in zip(early_pages["documents"], early_pages["metadatas"])]
            
            docs = early_docs + docs
        
        # CRITICAL: Force balance sheet pages for debt questions
        if analysis.get("is_debt_question") and where:
            print(f"  🎯 Term debt question - fetching balance sheet")
            
            # Get balance sheet section pages
            balance_sheets = self.collection.get(
                where={
                    "$and": [
                        where,
                        {"section": "balance_sheet"}
                    ]
                },
                include=["documents", "metadatas"],
                limit=15
            )
            
            if balance_sheets["documents"]:
                bs_docs = [{"text": doc, "metadata": meta} 
                          for doc, meta in zip(balance_sheets["documents"], balance_sheets["metadatas"])]
                docs = bs_docs + docs
            
            # Also try fetching pages 30-40 where balance sheets typically are
            balance_area = self.collection.get(
                where={
                    "$and": [
                        where,
                        {"page": {"$gte": 30}},
                        {"page": {"$lte": 40}}
                    ]
                },
                include=["documents", "metadatas"],
                limit=20
            )
            
            if balance_area["documents"]:
                ba_docs = [{"text": doc, "metadata": meta} 
                          for doc, meta in zip(balance_area["documents"], balance_area["metadatas"])]
                docs = ba_docs + docs
        
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
        
        boosted_scores = []
        for i, (doc, score) in enumerate(zip(unique_docs, scores)):
            boost = 0.0
            
            if analysis.get("numerical") and doc["metadata"].get("is_table"):
                boost += 0.15
            
            if analysis.get("is_shares_question"):
                page = doc["metadata"]["page"]
                if page == 2:
                    boost += 2.0  # Highest boost for cover page
                elif page <= 3:
                    boost += 1.0
                elif page <= 5:
                    boost += 0.5
                
                if "october 18" in doc["text"].lower():
                    boost += 1.0
            
            if analysis.get("is_debt_question"):
                # Boost balance sheet pages
                if doc["metadata"].get("section") == "balance_sheet":
                    boost += 1.5
                
                # Boost if contains term debt keywords
                text_lower = doc["text"].lower()
                if "term debt" in text_lower and "current" in text_lower:
                    boost += 1.0
            
            boosted_scores.append(score + boost)
        
        ranked = sorted(zip(unique_docs, boosted_scores), key=lambda x: x[1], reverse=True)
        
        if analysis.get("is_shares_question") or analysis.get("is_debt_question"):
            top_pages = [d["metadata"]["page"] for d, _ in ranked[:top_k]]
            print(f"  📄 Top pages: {top_pages[:5]}")
        
        return [doc for doc, _ in ranked[:top_k]], analysis
        
