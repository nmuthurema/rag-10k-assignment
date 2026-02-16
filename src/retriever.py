
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

def boost_early_pages(chunks: List[Dict], query: str) -> List[Dict]:
    """Boost early pages for certain queries"""
    
    # Q2: Shares outstanding as of specific date -> boost early pages (cover page, Part II)
    if "shares" in query.lower() and "outstanding" in query.lower():
        # Boost pages 1-25
        boosted = []
        others = []
        
        for chunk in chunks:
            page = chunk["metadata"].get("page", 999)
            if page <= 25:
                boosted.append(chunk)
            else:
                others.append(chunk)
        
        return boosted + others
    
    return chunks

def boost_balance_sheet_pages(chunks: List[Dict], query: str) -> List[Dict]:
    """Boost balance sheet pages for debt queries"""
    
    # Q3: Term debt -> boost balance sheet pages (typically 30-40)
    if "term debt" in query.lower():
        # Prioritize chunks marked as balance_sheet
        balance_sheets = []
        others = []
        
        for chunk in chunks:
            section = chunk["metadata"].get("section", "")
            page = chunk["metadata"].get("page", 0)
            
            # Boost balance sheet sections or pages 30-40
            if section == "balance_sheet" or (30 <= page <= 40):
                balance_sheets.append(chunk)
            else:
                others.append(chunk)
        
        return balance_sheets + others
    
    return chunks

class QueryRouter:
    """Routes queries to appropriate retrieval strategies"""
    
    def analyze(self, query: str) -> Dict:
        q = query.lower()
        
        analysis = {
            "company": None,
            "numerical": False,
            "query_type": None,
            "keywords": [],
            "prefer_tables": False,
            "prefer_early_pages": False,
            "prefer_balance_sheet": False
        }
        
        # Company detection
        if "apple" in q:
            analysis["company"] = "apple"
        elif "tesla" in q:
            analysis["company"] = "tesla"
        
        # Query type detection
        if any(k in q for k in ["revenue", "debt", "shares", "percentage", "income", "assets"]):
            analysis["numerical"] = True
        
        # Q2: Shares outstanding - prefer EARLY pages (cover page)
        if "shares" in q and "outstanding" in q:
            analysis["query_type"] = "financial"
            analysis["keywords"].extend(["shares", "outstanding", "common stock", "issued"])
            analysis["prefer_early_pages"] = True
        
        # Q3: Debt - prefer BALANCE SHEET pages
        if "term debt" in q or "debt" in q:
            analysis["query_type"] = "financial"
            analysis["keywords"].extend(["term debt", "current", "non-current", "balance sheet", "liabilities"])
            analysis["prefer_tables"] = True
            analysis["prefer_balance_sheet"] = True
        
        # Revenue
        if "revenue" in q:
            analysis["query_type"] = "financial"
            analysis["keywords"].extend(["total net sales", "revenue", "consolidated statements"])
            analysis["prefer_tables"] = True
        
        # Percentage calculation
        if "percentage" in q:
            analysis["query_type"] = "calculation"
            analysis["keywords"].extend(["automotive sales", "total revenues", "consolidated"])
            analysis["prefer_tables"] = True
        
        # Vehicles
        if "vehicles" in q or "produce" in q:
            analysis["query_type"] = "factual"
            analysis["keywords"].extend(["model s", "model 3", "model x", "model y", "cybertruck"])
        
        # Reasoning
        if any(w in q for w in ["reason", "dependent", "why", "purpose"]):
            analysis["query_type"] = "reasoning"
            if "elon musk" in q:
                analysis["keywords"].extend(["elon musk", "dependent", "leadership", "risk", "services"])
            else:
                analysis["keywords"].extend(["lease", "solar", "ppa", "power purchase"])
        
        return analysis

class ImprovedRetriever:
    """Enhanced retriever with better ranking"""
    
    def __init__(self, persist_dir="chroma_db"):
        print("Connecting to vector database...")
        self.client = PersistentClient(path=persist_dir)
        self.collection = self.client.get_collection(COLLECTION_NAME)
        
        print("Loading embedding + reranker models...")
        self.embed = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())
        self.reranker = CrossEncoder(RERANK_MODEL_NAME, device=get_device())
        self.router = QueryRouter()
        
        print("✅ Retriever ready")
    
    def retrieve(self, query: str, top_k: int = 20) -> Tuple[List[Dict], Dict]:
        """Retrieve with improved ranking"""
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
        
        # Retrieve MORE chunks initially
        results = self.collection.query(
            query_embeddings=query_emb,
            n_results=300,  # Increased from 200
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

        # Apply query-specific boosts BEFORE reranking
        if analysis.get("prefer_early_pages"):
            print(f"  📄 Boosting early pages (1-25)")
            docs = boost_early_pages(docs, query)
        
        if analysis.get("prefer_balance_sheet"):
            print(f"  📊 Boosting balance sheet pages (30-40)")
            docs = boost_balance_sheet_pages(docs, query)

        # Table preference
        if analysis.get("prefer_tables"):
            tables = [d for d in docs if d["metadata"].get("is_table")]
            non_tables = [d for d in docs if not d["metadata"].get("is_table")]
            if tables:
                print(f"  📊 Prioritizing {len(tables)} table chunks")
                docs = tables + non_tables

        # Remove TOC
        docs = remove_toc_chunks(docs)
        
        # Deduplicate
        seen = set()
        unique_docs = []
        for d in docs:
            text_key = d["text"][:200]  # Use first 200 chars as key
            if text_key not in seen:
                unique_docs.append(d)
                seen.add(text_key)
        
        # Limit before reranking to save time
        docs_to_rerank = unique_docs[:100]  # Only rerank top 100
        
        # Rerank
        pairs = [(query, d["text"]) for d in docs_to_rerank]
        scores = self.reranker.predict(pairs, batch_size=32)
        
        # Combine with original position score for better ranking
        ranked = []
        for i, (doc, score) in enumerate(zip(docs_to_rerank, scores)):
            # Boost score if early in list (vector search already ranked these)
            position_boost = (100 - i) / 100 * 0.1  # Small boost for top results
            combined_score = score + position_boost
            ranked.append((doc, combined_score))
        
        # Sort by combined score
        ranked.sort(key=lambda x: x[1], reverse=True)
        ranked_docs = [doc for doc, _ in ranked]
        
        # Take top_k
        final_docs = ranked_docs[:top_k]
        
        top_pages = [d["metadata"]["page"] for d in final_docs]
        print(f"  📄 Top pages: {top_pages[:5]}")
        
        # DEBUG: Show top chunks
        print()
        print("🔎 TOP RETRIEVED CHUNKS:")
        
        for i, d in enumerate(final_docs[:3]):
            print()
            print(f"--- Chunk {i+1} (Page {d['metadata']['page']}) ---")
            is_table = d['metadata'].get('is_table', False)
            section = d['metadata'].get('section', 'unknown')
            print(f"Type: {'TABLE' if is_table else 'TEXT'} | Section: {section}")
            print(d["text"][:400])
            
        return final_docs, analysis
