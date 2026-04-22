from __future__ import annotations
import os
import json
import hashlib
import numpy as np
import openai
from pathlib import Path
from typing import List, Dict

DOCS_DIR = Path(__file__).parent / "documents"
INDEX_PATH = Path(__file__).parent / "vector_index.json"


def _chunk_document(text: str, chunk_size: int = 500, overlap: int = 100) -> list[dict]:
    chunks = []
    lines = text.strip().split("\n")

    title = ""
    current_section = ""
    current_text = []

    for line in lines:
        if line.startswith("TITLE:"):
            title = line.replace("TITLE:", "").strip()
        elif line.startswith("SECTION:"):
            if current_text:
                full_text = " ".join(current_text).strip()
                if full_text:
                    words = full_text.split()
                    for i in range(0, len(words), chunk_size - overlap):
                        chunk_words = words[i:i + chunk_size]
                        if len(chunk_words) > 50:
                            chunks.append({
                                "text": " ".join(chunk_words),
                                "source": title,
                                "section": current_section,
                            })
            current_section = line.replace("SECTION:", "").strip()
            current_text = []
        else:
            if line.strip():
                current_text.append(line.strip())

    if current_text:
        full_text = " ".join(current_text).strip()
        if full_text:
            words = full_text.split()
            for i in range(0, len(words), chunk_size - overlap):
                chunk_words = words[i:i + chunk_size]
                if len(chunk_words) > 50:
                    chunks.append({
                        "text": " ".join(chunk_words),
                        "source": title,
                        "section": current_section,
                    })

    return chunks


def _get_embeddings(texts: list[str], api_key: str) -> list[list[float]]:
    client = openai.OpenAI(api_key=api_key)
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr = np.array(a)
    b_arr = np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr) + 1e-10))


class RAGEngine:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.chunks: list[dict] = []
        self.embeddings: list[list[float]] = []
        self._loaded = False

    def build_index(self, force_rebuild: bool = False):
        if self._loaded and not force_rebuild:
            return

        if INDEX_PATH.exists() and not force_rebuild:
            with open(INDEX_PATH, "r") as f:
                data = json.load(f)
            self.chunks = data["chunks"]
            self.embeddings = data["embeddings"]
            self._loaded = True
            return

        all_chunks = []
        for doc_path in sorted(DOCS_DIR.glob("*.txt")):
            text = doc_path.read_text()
            chunks = _chunk_document(text)
            all_chunks.extend(chunks)

        if not all_chunks:
            self._loaded = True
            return

        texts = [c["text"] for c in all_chunks]
        embeddings = _get_embeddings(texts, self.api_key)

        self.chunks = all_chunks
        self.embeddings = embeddings
        self._loaded = True

        with open(INDEX_PATH, "w") as f:
            json.dump({"chunks": self.chunks, "embeddings": self.embeddings}, f)

    def query(self, question: str, n_results: int = 5) -> list[dict]:
        if not self._loaded:
            self.build_index()

        if not self.chunks:
            return []

        q_embedding = _get_embeddings([question], self.api_key)[0]

        scored = []
        for i, emb in enumerate(self.embeddings):
            sim = _cosine_similarity(q_embedding, emb)
            scored.append((sim, i))

        scored.sort(reverse=True)
        results = []
        for sim, idx in scored[:n_results]:
            chunk = self.chunks[idx].copy()
            chunk["similarity"] = round(sim, 4)
            results.append(chunk)

        return results

    def get_context_for_chat(self, question: str, n_results: int = 4) -> str:
        results = self.query(question, n_results)
        if not results:
            return ""

        context_parts = []
        for r in results:
            context_parts.append(
                f"[Source: {r['source']} — {r['section']}]\n{r['text']}"
            )

        return "\n\n---\n\n".join(context_parts)

    @property
    def stats(self) -> dict:
        return {
            "total_chunks": len(self.chunks),
            "total_documents": len(set(c["source"] for c in self.chunks)) if self.chunks else 0,
            "index_built": self._loaded and len(self.chunks) > 0,
        }
