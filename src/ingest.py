
import os
import torch
from typing import List, Dict
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from chromadb import PersistentClient

EMBED_MODEL_NAME = "BAAI/bge-base-en"
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
COLLECTION_NAME = "sec_10k"

def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"

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

def chunk_text(pages: List[Dict]) -> List[Dict]:
    chunks = []
    for p in pages:
        words = p["text"].split()
        start = 0
        while start < len(words):
            end = min(start + CHUNK_SIZE, len(words))
            chunk = " ".join(words[start:end])
            chunks.append({"text": chunk, "page": p["page"]})
            if end == len(words):
                break
            start = end - CHUNK_OVERLAP
    return chunks

def build_documents(data_folder="data") -> List[Dict]:
    docs = []
    print("Loading PDFs...")
    for file in os.listdir(data_folder):
        if not file.endswith(".pdf"):
            continue
        path = os.path.join(data_folder, file)
        print(f"Processing: {file}")
        pages = load_pdf(path)
        chunks = chunk_text(pages)
        for i, c in enumerate(chunks):
            docs.append({
                "id": f"{file}_p{c['page']}_{i}",
                "text": c["text"],
                "metadata": {"document": file, "page": c["page"]}
            })
    if len(docs) == 0:
        raise ValueError("No text extracted")
    print(f"Total chunks: {len(docs)}")
    return docs

def index_documents(persist_dir="chroma_db"):
    print("Device:", get_device())
    model = SentenceTransformer(EMBED_MODEL_NAME, device=get_device())
    client = PersistentClient(path=persist_dir)
    try:
        client.delete_collection(COLLECTION_NAME)
    except:
        pass
    collection = client.get_or_create_collection(COLLECTION_NAME)
    docs = build_documents()
    texts = [d["text"] for d in docs]
    print("Generating embeddings...")
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=True, convert_to_numpy=True)
    print("Storing vectors...")
    collection.add(
        ids=[d["id"] for d in docs],
        documents=texts,
        metadatas=[d["metadata"] for d in docs],
        embeddings=embeddings.tolist()
    )
    print(f"✅ Indexed {len(docs)} chunks")
