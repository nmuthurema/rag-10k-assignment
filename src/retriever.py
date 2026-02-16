
import re
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
    return [
        c for c in chunks
        if "table of contents" not in c["text"].lower()
    ]


# STRICT only for vehicle queries
def strict_keyword_filter(chunks: List[Dict], query: str) -> List[Dict]:
    q = query.lower()

    if "vehicles" in q or "produce" in q or "deliver" in q:
        filtered = []
        for c in chunks:
            t = c["text"].lower()
            if any(m in t for m in [
                "model s", "model 3", "model x",
                "model y", "cybertruck"
            ]):
                filtered.append(c)

        if filtered:
            print(f"  ✅ STRICT vehicle filter: {len(chunks)} → {len(filtered)}")
            return filtered

    return chunks


class QueryRouter:
    def analyze(self, query: str) -> Dict:
        q = query.lower()

        analysis = {
            "company": None,
            "prefer_tables": False,
        }

        if "apple" in q:
            analysis["company"] = "apple"
        elif "tesla" in q:
            analysis["company"] = "tesla"

        if "term debt" in q:
            analysis["prefer_tables"] = True

        return analysis


class ImprovedRetriever:

    def __init__(self, persist_dir="chroma_db"):
        print("Connecting to vector database...")
        self.client = PersistentClient(path=persist_dir)
        self.collection = self.client.get_collection(COLLECTION_NAME)

        print("Loading embedding + reranker...")
        self.embed = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())
        self.reranker = CrossEncoder(RERANK_MODEL_NAME, device=get_device())
        self.router = QueryRouter()

        print("✅ Retriever ready")


    def retrieve(self, query: str, top_k: int = 20):

        analysis = self.router.analyze(query)
        query_lower = query.lower()

        query_emb = self.embed.encode([query]).tolist()

        # Company filter
        where = None
        if analysis.get("company"):
            doc_map = {
                "apple": "10-Q4-2024-As-Filed.pdf",
                "tesla": "tsla-20231231-gen.pdf",
            }
            where = {"document": doc_map[analysis["company"]]}

        results = self.collection.query(
            query_embeddings=query_emb,
            n_results=300,
            where=where,
            include=["documents", "metadatas"],
        )

        docs = [
            {"text": results["documents"][0][i], "metadata": results["metadatas"][0][i]}
            for i in range(len(results["documents"][0]))
        ]

        # STEP 1: STRICT for vehicle queries only
        docs = strict_keyword_filter(docs, query)

        # STEP 2: BOOSTING
        boosted, others = [], []

        for doc in docs:
            boost_score = 0

            page = doc["metadata"].get("page", 0)
            section = doc["metadata"].get("section", "")
            is_table = doc["metadata"].get("is_table", False)

            # Revenue → income statement + tables
            if "revenue" in query_lower:
                if section == "income_statement":
                    boost_score += 300
                if is_table:
                    boost_score += 200

            # Shares → early pages + tables
            if "shares" in query_lower:
                if page <= 3:
                    boost_score += 400
                if is_table:
                    boost_score += 200

            # Debt → balance sheet + tables
            if "debt" in query_lower:
                if section == "balance_sheet":
                    boost_score += 400
                if is_table:
                    boost_score += 200

            if boost_score > 0:
                boosted.append((doc, boost_score))
            else:
                others.append((doc, 0))

        boosted.sort(key=lambda x: x[1], reverse=True)
        docs = [d for d, _ in boosted] + [d for d, _ in others]

        print(f"  📊 Boosted {len(boosted)} chunks")

        # STEP 3: Remove TOC
        docs = remove_toc_chunks(docs)

        # STEP 4: Deduplicate
        seen, unique_docs = set(), []
        for d in docs:
            key = d["text"][:200]
            if key not in seen:
                unique_docs.append(d)
                seen.add(key)

        # Candidate trimming
        if "vehicles" in query_lower:
            unique_docs = unique_docs[:60]
        else:
            unique_docs = unique_docs[:120]

        # Financial → tables first
        if any(x in query_lower for x in ["revenue", "shares", "debt"]):
            tables = [d for d in unique_docs if d["metadata"].get("is_table")]
            non_tables = [d for d in unique_docs if not d["metadata"].get("is_table")]
            if tables:
                unique_docs = tables + non_tables

        # STEP 5: Rerank
        docs_to_rerank = unique_docs[:80]
        pairs = [(query, d["text"]) for d in docs_to_rerank]
        scores = self.reranker.predict(pairs, batch_size=32)

        ranked = sorted(zip(docs_to_rerank, scores), key=lambda x: x[1], reverse=True)
        final_docs = [doc for doc, _ in ranked[:top_k]]

        pages = [d["metadata"]["page"] for d in final_docs]
        print(f"  📄 Top pages: {pages[:5]}")

        return final_docs, analysis
