
import torch
from typing import List, Dict, Tuple
from sentence_transformers import SentenceTransformer, CrossEncoder
from chromadb import PersistentClient

EMBED_MODEL_NAME = "BAAI/bge-base-en"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"
COLLECTION_NAME = "sec_10k"


def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"


# --------------------------------------------------
# REMOVE TABLE OF CONTENTS NOISE
# --------------------------------------------------
def remove_toc_chunks(chunks: List[Dict]) -> List[Dict]:
    filtered = []

    for c in chunks:
        text = c["text"].lower()

        if "table of contents" in text:
            continue

        if text.strip().startswith("table of contents"):
            continue

        filtered.append(c)

    return filtered


# --------------------------------------------------
# REASONING BOOST
# --------------------------------------------------
def rerank_reasoning(chunks: List[Dict]) -> List[Dict]:
    reasoning_terms = [
        "strategy",
        "innovation",
        "leadership",
        "disrupt",
        "risk",
        "dependent"
    ]

    def score(chunk):
        t = chunk["text"].lower()
        return sum(1 for r in reasoning_terms if r in t)

    return sorted(chunks, key=score, reverse=True)


# --------------------------------------------------
# QUERY ROUTER
# --------------------------------------------------
class QueryRouter:

    def analyze(self, query: str):

        q = query.lower()

        analysis = {
            "company": None,
            "numerical": False,
            "query_type": None,
            "is_shares_question": False,
            "is_debt_question": False,
            "keywords": []
        }

        # --------------------------
        # COMPANY
        # --------------------------
        if "apple" in q:
            analysis["company"] = "apple"
        elif "tesla" in q:
            analysis["company"] = "tesla"

        # --------------------------
        # NUMERICAL
        # --------------------------
        if any(k in q for k in ["revenue", "debt", "shares", "income", "assets", "percentage"]):
            analysis["numerical"] = True

        # --------------------------
        # SHARES (Q2)
        # --------------------------
        if "shares" in q and "outstanding" in q:
            analysis["is_shares_question"] = True
            analysis["query_type"] = "shares"
            analysis["keywords"].extend(["shares", "outstanding", "common stock"])

        # --------------------------
        # TERM DEBT (Q3)
        # --------------------------
        if "term debt" in q:
            analysis["is_debt_question"] = True
            analysis["query_type"] = "financial"
            analysis["keywords"].extend(["term debt", "current", "non-current"])

        # --------------------------
        # CALCULATION (Q7)
        # --------------------------
        if "percentage" in q and "automotive" in q:
            analysis["query_type"] = "calculation"
            analysis["keywords"].extend(["automotive sales", "total revenues"])

        # --------------------------
        # REASONING (Q8, Q10)
        # --------------------------
        if "elon musk" in q or "dependent" in q or "pass-through" in q:
            analysis["query_type"] = "reasoning"
            analysis["keywords"].extend(["elon musk", "dependent", "risk", "pass-through"])

        # --------------------------
        # FINANCIAL (revenue etc.)
        # --------------------------
        if "revenue" in q and "total" in q:
            analysis["query_type"] = "financial"
            analysis["keywords"].extend(["total net sales", "revenue"])

        # --------------------------
        # VEHICLES (Q9)
        # --------------------------
        if "vehicles" in q or "produce" in q:
            analysis["query_type"] = "factual"
            analysis["keywords"].extend(
                ["model s", "model 3", "model x", "model y", "cybertruck"]
            )

        return analysis


# --------------------------------------------------
# RETRIEVER
# --------------------------------------------------
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

    def retrieve(self, query: str, top_k=10) -> Tuple[List[Dict], Dict]:

        analysis = self.router.analyze(query)

        emb = self.embed.encode([query]).tolist()

        # --------------------------
        # COMPANY FILTER
        # --------------------------
        where = None
        if analysis.get("company"):
            doc_map = {
                "apple": "10-Q4-2024-As-Filed.pdf",
                "tesla": "tsla-20231231-gen.pdf"
            }
            where = {"document": doc_map[analysis["company"]]}

        # --------------------------
        # WIDE RETRIEVAL
        # --------------------------
        results = self.collection.query(
            query_embeddings=emb,
            n_results=150,
            where=where,
            include=["documents", "metadatas"]
        )

        docs = [
            {"text": results["documents"][0][i],
             "metadata": results["metadatas"][0][i]}
            for i in range(len(results["documents"][0]))
        ]

        query_type = analysis.get("query_type")

        # ==================================================
        # QUERY-AWARE RETRIEVAL (THIS FIXES ALL BREAKS)
        # ==================================================

        # --------------------------
        # SHARES → no filtering
        # --------------------------
        if analysis.get("is_shares_question"):
            print("  🧠 Shares question → semantic search")

        # --------------------------
        # CALCULATION → wide search
        # --------------------------
        elif query_type == "calculation":
            print("  🧠 Calculation → wide context")

        # --------------------------
        # NUMERICAL FINANCIAL
        # --------------------------
        elif analysis.get("numerical"):
            print("  🧠 Numerical → financial filtering")

            financial_terms = [
                "revenue", "sales", "income",
                "term debt", "assets", "liabilities"
            ]

            filtered = [
                d for d in docs
                if any(term in d["text"].lower() for term in financial_terms)
            ]

            if filtered:
                docs = filtered

        # --------------------------
        # REASONING
        # --------------------------
        elif query_type == "reasoning":
            print("  🧠 Reasoning → remove TOC")
            docs = remove_toc_chunks(docs)

        # --------------------------
        # FACTUAL
        # --------------------------
        else:
            keywords = analysis.get("keywords", [])

            if keywords:
                print(f"  🔍 Filtering for keywords: {keywords}")

                filtered = [
                    d for d in docs
                    if any(k.lower() in d["text"].lower() for k in keywords)
                ]

                if filtered:
                    docs = filtered

        # --------------------------
        # DEDUP
        # --------------------------
        seen = set()
        unique_docs = []

        for d in docs:
            if d["text"] not in seen:
                unique_docs.append(d)
                seen.add(d["text"])

        # --------------------------
        # CROSS-ENCODER RERANK
        # --------------------------
        pairs = [(query, d["text"]) for d in unique_docs]
        scores = self.reranker.predict(pairs, batch_size=16)

        boosted = []
        for doc, score in zip(unique_docs, scores):
            boost = 0.0

            # boost tables for numerical
            if analysis.get("numerical") and doc["metadata"].get("is_table"):
                boost += 0.2

            # reasoning boost
            if query_type == "reasoning":
                if "risk" in doc["text"].lower():
                    boost += 0.4

            boosted.append(score + boost)

        ranked = sorted(
            zip(unique_docs, boosted),
            key=lambda x: x[1],
            reverse=True
        )

        ranked_docs = [doc for doc, _ in ranked]

        # reasoning rerank final
        if query_type == "reasoning":
            ranked_docs = rerank_reasoning(ranked_docs)

        top_pages = [d["metadata"]["page"] for d in ranked_docs[:top_k]]
        print(f"  📄 Top pages: {top_pages[:5]}")

        return ranked_docs[:top_k], analysis

