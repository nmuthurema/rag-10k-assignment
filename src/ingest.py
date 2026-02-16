
import os
import re
import torch
from typing import List, Dict
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from chromadb import PersistentClient

EMBED_MODEL_NAME = "BAAI/bge-base-en"
COLLECTION_NAME = "sec_10k"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 150


def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"


# ============================================================
# TABLE DETECTOR (IMPROVED)
# ============================================================

class TableDetector:

    @staticmethod
    def has_dollar_amounts(line: str) -> bool:
        return bool(re.search(r'\$\s*[\d,]+', line))

    @staticmethod
    def has_multiple_numbers(line: str) -> bool:
        numbers = re.findall(r'\d{1,3}(?:,\d{3})*', line)
        return len(numbers) >= 2

    @staticmethod
    def has_wide_spacing(line: str) -> bool:
        return bool(re.search(r'\s{2,}', line))

    @staticmethod
    def is_financial_keyword(line: str) -> bool:
        keywords = [
            'assets', 'liabilities', 'equity', 'revenue', 'sales',
            'income', 'cash', 'debt', 'total', 'net', 'balance',
            'current', 'non-current', 'shares', 'common stock',
            'term debt', 'accounts payable', 'inventory'
        ]
        line_lower = line.lower()
        return any(kw in line_lower for kw in keywords)

    @staticmethod
    def is_table_row(line: str) -> bool:

        if len(line.strip()) < 5:
            return False

        has_dollars = TableDetector.has_dollar_amounts(line)
        has_numbers = TableDetector.has_multiple_numbers(line)
        has_spacing = TableDetector.has_wide_spacing(line)
        has_keyword = TableDetector.is_financial_keyword(line)

        if has_dollars and has_spacing:
            return True

        if has_numbers and has_spacing:
            return True

        if has_keyword and (has_numbers or has_spacing or has_dollars):
            return True

        return False


    # ⭐ FIX: make table detection robust to Apple format
    @staticmethod
    def extract_table_blocks(text: str) -> List[Dict]:

        lines = text.split('\n')
        tables = []
        current_table = []
        in_table = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            if not stripped:
                if in_table and len(current_table) >= 2:   # ⭐ relaxed
                    tables.append({
                        'text': '\n'.join(current_table),
                        'start_line': i - len(current_table),
                        'end_line': i
                    })
                current_table = []
                in_table = False
                continue

            if TableDetector.is_table_row(line):
                in_table = True
                current_table.append(stripped)
            else:
                if in_table and len(current_table) >= 2:
                    tables.append({
                        'text': '\n'.join(current_table),
                        'start_line': i - len(current_table),
                        'end_line': i
                    })
                current_table = []
                in_table = False

        if len(current_table) >= 2:
            tables.append({
                'text': '\n'.join(current_table),
                'start_line': len(lines) - len(current_table),
                'end_line': len(lines)
            })

        return tables


# ============================================================
# SECTION DETECTOR
# ============================================================

def detect_section(text: str) -> str:
    t = text.lower()

    if "balance sheet" in t:
        return "balance_sheet"

    if "statement of operations" in t or "income statement" in t:
        return "income_statement"

    if "cash flow" in t:
        return "cash_flow"

    if "item 8" in t:
        return "item_8"

    if "item 7" in t:
        return "item_7"

    if "item 1a" in t:
        return "item_1a"

    return "general"


# ============================================================
# LOAD PDF
# ============================================================

def load_pdf(path: str) -> List[Dict]:

    reader = PdfReader(path)
    pages = []

    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except:
            text = ""

        pages.append({"page": i + 1, "text": text})

    return pages


# ============================================================
# SMART CHUNKING (CRITICAL FIXES)
# ============================================================

def smart_chunk(pages: List[Dict]) -> List[Dict]:

    chunks = []

    for p in pages:

        page = p["page"]
        text = p["text"]

        tables = TableDetector.extract_table_blocks(text)

        table_line_ranges = set()
        for t in tables:
            for line_num in range(t["start_line"], t["end_line"]):
                table_line_ranges.add(line_num)

        # ⭐ TABLE chunks (DO NOT SPLIT — critical for Q3)
        for t in tables:
            if len(t["text"]) > 40:
                chunks.append({
                    "text": t["text"],
                    "page": page,
                    "section": detect_section(t["text"]),
                    "is_table": True
                })

        # ⭐ NON-TABLE chunks
        lines = text.split('\n')
        non_table_lines = [
            line for i, line in enumerate(lines)
            if i not in table_line_ranges and line.strip()
        ]

        non_table_text = '\n'.join(non_table_lines)
        words = non_table_text.split()

        start = 0
        while start < len(words):

            end = min(start + CHUNK_SIZE, len(words))
            chunk_text = " ".join(words[start:end])

            if len(chunk_text.strip()) > 20:
                chunks.append({
                    "text": chunk_text,
                    "page": page,
                    "section": detect_section(chunk_text),
                    "is_table": False
                })

            if end == len(words):
                break

            start = end - CHUNK_OVERLAP

    return chunks


# ============================================================
# BUILD DOCUMENTS
# ============================================================

def build_documents(data_folder="data") -> List[Dict]:

    docs = []
    print("📄 Processing PDFs...")

    for file in os.listdir(data_folder):

        if not file.endswith(".pdf"):
            continue

        path = os.path.join(data_folder, file)
        print(f"  Processing: {file}")

        pages = load_pdf(path)
        chunks = smart_chunk(pages)

        for i, c in enumerate(chunks):

            docs.append({
                "id": f"{file}_p{c['page']}_{i}",
                "text": c["text"],
                "metadata": {
                    "document": file,
                    "page": int(c["page"]),
                    "is_table": bool(c.get("is_table", False)),
                    "section": str(c.get("section", "general"))
                }
            })

    print(f"\n📊 Total chunks: {len(docs)}")
    return docs


# ============================================================
# INDEX
# ============================================================

def index_documents(persist_dir="/kaggle/working/chroma_db"):

    import shutil, time, gc

    if os.path.exists(persist_dir):
        shutil.rmtree(persist_dir, ignore_errors=True)
        time.sleep(2)

    gc.collect()

    os.makedirs(persist_dir, exist_ok=True)

    model = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())
    client = PersistentClient(path=persist_dir)

    try:
        client.delete_collection(COLLECTION_NAME)
    except:
        pass

    collection = client.get_or_create_collection(COLLECTION_NAME)

    docs = build_documents()
    texts = [d["text"] for d in docs]

    print("\n🔢 Generating embeddings...")
    embeddings = model.encode(texts, batch_size=32, convert_to_numpy=True)

    print("💿 Storing vectors...")

    for i in range(0, len(docs), 50):

        collection.add(
            ids=[d["id"] for d in docs[i:i+50]],
            documents=texts[i:i+50],
            metadatas=[d["metadata"] for d in docs[i:i+50]],
            embeddings=embeddings[i:i+50].tolist()
        )

    print(f"✅ Indexed {len(docs)} chunks")
