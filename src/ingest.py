
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

# FIXED: Column-based table detection
class TableDetector:
    @staticmethod
    def has_columns(line: str) -> bool:
        """Check if line has multiple columns (3+ spaces = separator)"""
        return len(re.findall(r'\s{3,}', line)) >= 1
    
    @staticmethod
    def is_table_row(line: str) -> bool:
        """Check if line is part of a table"""
        if len(line.strip()) < 10:
            return False
        
        has_numbers = bool(re.search(r'\d', line))
        has_columns = TableDetector.has_columns(line)
        has_dollar = '$' in line
        
        keywords = ['revenue', 'sales', 'income', 'assets', 'liabilities', 
                   'debt', 'cash', 'total', 'net', 'equity']
        has_keyword = any(k in line.lower() for k in keywords)
        
        # Table row: has numbers AND (columns OR dollar) OR (keyword AND columns)
        return (has_numbers and (has_columns or has_dollar)) or (has_keyword and has_columns)
    
    @staticmethod
    def extract_table_blocks(text: str) -> List[Dict]:
        """Extract tables based on column structure"""
        lines = text.split('\n')
        tables = []
        current = []
        
        for i, line in enumerate(lines):
            if TableDetector.is_table_row(line):
                current.append(line.strip())
            else:
                if len(current) >= 3:  # At least 3 rows
                    tables.append({
                        'text': '\n'.join(current),
                        'lines': current.copy(),
                        'start_line': i - len(current)
                    })
                current = []
        
        if len(current) >= 3:
            tables.append({
                'text': '\n'.join(current),
                'lines': current.copy(),
                'start_line': len(lines) - len(current)
            })
        
        return tables

def detect_section(text: str) -> str:
    """Detect document section"""
    t = text.lower()
    if "balance sheet" in t: return "balance_sheet"
    if "income" in t and "statement" in t: return "income_statement"
    if "cash flow" in t: return "cash_flow"
    if "item 8" in t: return "item_8"
    if "item 7" in t: return "item_7"
    return "general"

def load_pdf(path: str) -> List[Dict]:
    """Load PDF pages"""
    reader = PdfReader(path)
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except:
            text = ""
        pages.append({"page": i + 1, "text": text})
    return pages

def smart_chunk(pages: List[Dict]) -> List[Dict]:
    """Chunk with table preservation"""
    chunks = []
    
    for p in pages:
        page = p["page"]
        text = p["text"]
        
        # Extract tables
        tables = TableDetector.extract_table_blocks(text)
        table_lines = set()
        
        # Create table chunks
        for t in tables:
            chunks.append({
                "text": t["text"],
                "page": page,
                "section": detect_section(t["text"]),
                "is_table": True
            })
            for i in range(t["start_line"], t["start_line"] + len(t["lines"])):
                table_lines.add(i)
        
        # Create non-table chunks
        lines = text.split('\n')
        non_table = [line for i, line in enumerate(lines) if i not in table_lines]
        non_table_text = '\n'.join(non_table)
        words = non_table_text.split()
        
        start = 0
        while start < len(words):
            end = min(start + CHUNK_SIZE, len(words))
            chunk = " ".join(words[start:end])
            chunks.append({
                "text": chunk,
                "page": page,
                "section": detect_section(chunk),
                "is_table": False
            })
            if end == len(words):
                break
            start = end - CHUNK_OVERLAP
    
    return chunks

def build_documents(data_folder="data") -> List[Dict]:
    """Build document collection"""
    docs = []
    print("📄 Processing PDFs...")
    
    for file in os.listdir(data_folder):
        if not file.endswith(".pdf"):
            continue
        
        path = os.path.join(data_folder, file)
        print(f"  Processing: {file}")
        
        pages = load_pdf(path)
        company = "apple" if "10-q" in file.lower() else "tesla"
        chunks = smart_chunk(pages)
        
        for i, c in enumerate(chunks):
            docs.append({
                "id": f"{file}_p{c['page']}_{i}",
                "text": c["text"],
                "metadata": {
                    "document": file,
                    "page": int(c["page"]),
                    "is_table": bool(c.get("is_table", False)),
                    "company": company,
                    "section": str(c.get("section", "general"))
                }
            })
    
    print(f"\n📊 Total chunks: {len(docs)}")
    table_count = sum(1 for d in docs if d["metadata"]["is_table"])
    print(f"  • Tables: {table_count}")
    print(f"  • Balance sheets: {sum(1 for d in docs if d['metadata']['section'] == 'balance_sheet')}")
    print(f"  • Income statements: {sum(1 for d in docs if d['metadata']['section'] == 'income_statement')}")
    
    return docs

def index_documents(persist_dir="/kaggle/working/chroma_db"):
    import shutil
    import time
    import gc
    
    # CRITICAL: Force cleanup
    if os.path.exists(persist_dir):
        try:
            shutil.rmtree(persist_dir, ignore_errors=True)
        except:
            pass
        time.sleep(3)  # Wait for file handles to release
    
    # Force garbage collection
    gc.collect()
    
    # Create fresh directory
    os.makedirs(persist_dir, exist_ok=True)
    
    # Set permissions
    os.chmod(persist_dir, 0o777)
    
    print("DB path:", persist_dir)
    
    model = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())
    
    # Create new client
    client = PersistentClient(path=persist_dir)
    
    # Delete collection if exists
    try:
        client.delete_collection(COLLECTION_NAME)
        time.sleep(1)
    except:
        pass
    
    # Create fresh collection
    collection = client.get_or_create_collection(COLLECTION_NAME)
    
    docs = build_documents()
    texts = [d["text"] for d in docs]
    
    print("\n🔢 Generating embeddings...")
    embeddings = model.encode(texts, batch_size=32, convert_to_numpy=True, show_progress_bar=True)
    
    print("💿 Storing vectors...")
    
    # Add in batches with error handling
    batch_size = 50
    for i in range(0, len(docs), batch_size):
        try:
            collection.add(
                ids=[d["id"] for d in docs[i:i+batch_size]],
                documents=texts[i:i+batch_size],
                metadatas=[d["metadata"] for d in docs[i:i+batch_size]],
                embeddings=embeddings[i:i+batch_size].tolist()
            )
        except Exception as e:
            print(f"Warning: Batch {i} failed: {e}")
            # Try one by one
            for j in range(i, min(i+batch_size, len(docs))):
                try:
                    collection.add(
                        ids=[docs[j]["id"]],
                        documents=[texts[j]],
                        metadatas=[docs[j]["metadata"]],
                        embeddings=[embeddings[j].tolist()]
                    )
                except Exception as e2:
                    print(f"  Skipped doc {j}: {e2}")
    
    print(f"✅ Indexed {len(docs)} chunks")
