
from typing import Dict, List
from .retriever import ImprovedRetriever
from .llm import SmartLLM


def build_context(chunks: List[Dict], max_chars: int = 15000) -> str:
    """Build context from chunks with smart ordering"""
    parts = []
    total_chars = 0

    for i, c in enumerate(chunks, 1):
        doc = c["metadata"]["document"]
        page = c["metadata"]["page"]
        text = c["text"]

        snippet = f"[{i}] {doc}, p. {page}\n{text}\n\n"

        if total_chars + len(snippet) > max_chars:
            break

        parts.append(snippet)
        total_chars += len(snippet)

    return "".join(parts)


class ImprovedRAGPipeline:

    def __init__(self, persist_dir="chroma_db"):
        print("\n" + "=" * 60)
        print("🚀 INITIALIZING QUERY-TYPE-DRIVEN RAG")
        print("=" * 60)

        print("\n📡 Loading retriever...")
        self.retriever = ImprovedRetriever(persist_dir)

        print("\n🧠 Loading Smart LLM...")
        self.llm = SmartLLM()

        print("\n" + "=" * 60)
        print("✅ RAG READY")
        print("=" * 60)

    def answer_question(self, query: str, verbose: bool = False) -> Dict:

        if verbose:
            print(f"\n🔍 Query: {query[:80]}...")

        # -------------------------------------------------
        # STEP 1: RETRIEVAL
        # -------------------------------------------------
        chunks, analysis = self.retriever.retrieve(query, top_k=20)

        if not chunks:
            return {
                "answer": "This question cannot be answered based on the provided documents.",
                "sources": [],
            }

        if verbose:
            table_count = sum(1 for c in chunks if c["metadata"].get("is_table"))
            print(f"  ✅ Retrieved {len(chunks)} chunks (tables: {table_count})")

        # -------------------------------------------------
        # STEP 2: DEDUP
        # -------------------------------------------------
        seen = set()
        unique_chunks = []

        for c in chunks:
            key = c["text"][:300]
            if key not in seen:
                unique_chunks.append(c)
                seen.add(key)

        # -------------------------------------------------
        # STEP 3: SMART CONTEXT ORDERING
        # -------------------------------------------------
        query_lower = query.lower()

        # ⭐ Financial → tables first
        if any(x in query_lower for x in ["revenue", "shares", "debt"]):
            tables = [c for c in unique_chunks if c["metadata"].get("is_table")]
            non_tables = [c for c in unique_chunks if not c["metadata"].get("is_table")]
            ordered_chunks = tables + non_tables
        else:
            ordered_chunks = unique_chunks

        # -------------------------------------------------
        # STEP 4: VEHICLE BOOST
        # -------------------------------------------------
        if "vehicles" in query_lower:
            vehicle_chunks = []
            others = []

            for c in ordered_chunks:
                text = c["text"].lower()
                if any(m in text for m in [
                    "model s", "model 3", "model x",
                    "model y", "cybertruck"
                ]):
                    vehicle_chunks.append(c)
                else:
                    others.append(c)

            if vehicle_chunks:
                ordered_chunks = vehicle_chunks + others

        # -------------------------------------------------
        # STEP 5: BUILD CONTEXT
        # -------------------------------------------------
        context = build_context(ordered_chunks, max_chars=15000)

        # -------------------------------------------------
        # STEP 6: GENERATE ANSWER
        # -------------------------------------------------
        try:
            result = self.llm.answer(query, context)
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return {"answer": "Not specified in the document.", "sources": []}

        answer = result.get("answer", "").strip()

        # -------------------------------------------------
        # STEP 7: SOURCES
        # -------------------------------------------------
        sources = []
        for c in ordered_chunks[:5]:
            sources.append([
                c["metadata"]["document"],
                c["metadata"]["page"]
            ])

        return {"answer": answer, "sources": sources}
