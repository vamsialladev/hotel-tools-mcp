# Copied from stage 1 (hotel-ops-assistant 1.6.0, commit 392e1b5), src/ingest.py.
# Do not edit here: change it in Project 1, then run `python scripts/sync_policy.py --ref <commit>`.
# Only the import lines are rewritten (src.config / src.ingest -> hotel_tools.policy.config / .ingest).
"""Load messy hotel documents, split them into chunks, and build the search index.

Run:  python -m src.ingest
"""

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from hotel_tools.policy.config import EMBED_MODEL, INDEX_DIR, RAW_DIR, USE_EMBEDDINGS

SUPPORTED = {".md", ".txt", ".pdf"}
FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
MAX_CHARS = 1200


@dataclass
class Chunk:
    id: str
    text: str
    property: str  # folder name, e.g. "beach-resort" or "shared"
    source: str  # file path relative to data/raw
    section: str  # heading path, e.g. "Policies > Pets"
    page: int | None  # PDF page number, if any
    effective: str | None
    title: str = ""  # human-readable document name, shown on source chips


def contextual_text(chunk: dict) -> str:
    """Text used for search: adds property + section so a chunk that just says
    '$75 per stay' can still be found by a question about Miami pets."""
    return f"Property: {chunk['property']}\nSection: {chunk['section']}\n{chunk['text']}"


def display_title(rel: str, meta: dict) -> str:
    """Short document title: 'Spa Menu - Beach Resort' -> 'Spa Menu', 'Beach Resort - Property Policies' ->
    'Beach Resort policies', and a readable file name when there's no title ('front_desk_notes.txt' ->
    'Front desk notes')."""
    title = meta.get("title")
    if title:
        name, _, kind = title.partition(" - ")
        if kind.lower().startswith("property policies"):  # keep any suffix, e.g. "(2024)"
            return f"{name} policies{kind[len('property policies') :]}"
        return name if kind else title
    stem = Path(rel).stem.replace("_", " ").strip()
    return stem[:1].upper() + stem[1:]


def property_label(prop: str) -> str:
    return prop.replace("-", " ").title()


def document_name(rel: str, meta: dict) -> str:
    """The one readable name used everywhere in the UI: 'Mountain Lodge front desk notes',
    'Beach Resort restaurant menu', 'Hotel Group Brand Standards'. Never a file path."""
    prop = rel.split("/", 1)[0]
    title = display_title(rel, meta)
    if prop == "shared" or title.lower().startswith(property_label(prop).lower()):
        return title
    words = [w if w.isupper() and len(w) > 1 else w.lower() for w in title.split()]
    return f"{property_label(prop)} {' '.join(words)}"


def pdf_meta(path: Path) -> dict:
    """PDF title metadata, when the PDF has a real one."""
    from pypdf import PdfReader

    title = (PdfReader(str(path)).metadata or {}).get("/Title", "")
    return {"title": title} if title and title.lower() != "untitled" else {}


def document_meta(path: Path) -> dict:
    if path.suffix.lower() == ".pdf":
        return pdf_meta(path)
    return parse_front_matter(path.read_text(encoding="utf-8"))[0]


def parse_front_matter(text: str):
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()
    return meta, text[match.end() :]


def split_by_headings(body: str):
    """Section-aware chunking: one chunk per heading, keeping the heading path.
    Long sections are split on blank lines, which never cuts a table in half."""
    sections, path, buf = [], [], []

    def flush():
        text = "\n".join(buf).strip()
        if text:
            sections.append((" > ".join(path) or "Intro", text))
        buf.clear()

    for line in body.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading:
            flush()
            level = len(heading.group(1))
            path[:] = path[: level - 1] + [heading.group(2).strip()]
        else:
            buf.append(line)
    flush()

    out = []
    for section, text in sections:
        if len(text) <= MAX_CHARS:
            out.append((section, text))
            continue
        current = ""
        for block in re.split(r"\n\s*\n", text):
            if current and len(current) + len(block) > MAX_CHARS:
                out.append((section, current))
                current = block
            else:
                current = f"{current}\n\n{block}" if current else block
        if current:
            out.append((section, current))
    return out


def split_notes(text: str):
    """Informal notes files: each blank-line-separated note becomes its own chunk."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    return [("Staff notes", b) for b in blocks]


def load_pdf_pages(path: Path):
    """Yield (page_number, text) with repeated headers/footers removed."""
    from pypdf import PdfReader

    pages = [(p.extract_text() or "") for p in PdfReader(str(path)).pages]
    repeated = set()
    if len(pages) > 2:
        # Digits are masked so "Page 1 of 3" and "Page 2 of 3" count as the same footer.
        counts = Counter(normalize_line(line) for page in pages for line in set(page.splitlines()) if line.strip())
        repeated = {line for line, n in counts.items() if n >= max(2, int(len(pages) * 0.6))}
    for number, page in enumerate(pages, 1):
        lines = [line for line in page.splitlines() if normalize_line(line) not in repeated]
        yield number, "\n".join(lines)


def normalize_line(line: str) -> str:
    return re.sub(r"\d+", "#", line.strip())


def load_chunks():
    chunks = []
    for path in sorted(RAW_DIR.rglob("*")):
        if path.suffix.lower() not in SUPPORTED:
            continue
        rel = path.relative_to(RAW_DIR).as_posix()
        prop = path.relative_to(RAW_DIR).parts[0]

        if path.suffix.lower() == ".pdf":
            title = document_name(rel, pdf_meta(path))
            for page, text in load_pdf_pages(path):
                if len(text.strip()) < 30:
                    print(f"  ! {rel} page {page}: almost no text (scanned page? needs OCR)")
                    continue
                for j, (_, piece) in enumerate(split_by_headings(text)):
                    chunks.append(Chunk(f"{rel}#p{page}-{j}", piece, prop, rel, f"Page {page}", page, None, title))
            continue

        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        if meta.get("status", "").lower() == "superseded":
            print(f"  - skipping superseded document: {rel}")
            continue
        pieces = split_by_headings(body) if path.suffix.lower() == ".md" else split_notes(body)
        for j, (section, piece) in enumerate(pieces):
            title = document_name(rel, meta)
            chunks.append(Chunk(f"{rel}#{j}", piece, prop, rel, section, None, meta.get("effective"), title))
    return [asdict(c) for c in chunks]


def docs_fingerprint(use_embeddings: bool, raw_dir: Path = RAW_DIR) -> str:
    """Changes whenever a document is added, removed or edited, or the search mode changes. Stored with the
    index, so a running app (Streamlit Cloud keeps its files between pushes) knows to rebuild."""
    digest = hashlib.sha256(f"embeddings={use_embeddings}".encode())
    for path in sorted(p for p in Path(raw_dir).rglob("*") if p.is_file()):
        digest.update(path.relative_to(raw_dir).as_posix().encode() + b"|" + path.read_bytes())
    return digest.hexdigest()


def index_is_current(use_embeddings: bool, index_dir: Path = INDEX_DIR, raw_dir: Path = RAW_DIR) -> bool:
    stamp = Path(index_dir) / "fingerprint.txt"
    return (
        (Path(index_dir) / "chunks.json").exists()
        and stamp.exists()
        and stamp.read_text(encoding="utf-8").strip() == docs_fingerprint(use_embeddings, raw_dir)
    )


def build_index(use_embeddings: bool = True):
    print(f"Reading documents from {RAW_DIR}")
    requested = use_embeddings
    chunks = load_chunks()
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    (INDEX_DIR / "chunks.json").write_text(json.dumps(chunks, indent=2), encoding="utf-8")

    if use_embeddings:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            print("  ! sentence-transformers not installed: keyword search only")
            print("    (for hybrid search: pip install -r requirements-hybrid.txt)")
            use_embeddings = False
    if use_embeddings:
        model = SentenceTransformer(EMBED_MODEL)
        vectors = model.encode([contextual_text(c) for c in chunks], normalize_embeddings=True, show_progress_bar=True)
        np.save(INDEX_DIR / "vectors.npy", vectors)
    else:  # vectors from an older build no longer match these chunks
        (INDEX_DIR / "vectors.npy").unlink(missing_ok=True)
    (INDEX_DIR / "fingerprint.txt").write_text(docs_fingerprint(requested), encoding="utf-8")

    by_prop = Counter(c["property"] for c in chunks)
    print(f"Indexed {len(chunks)} chunks: {dict(by_prop)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--bm25-only", action="store_true", help="skip embeddings (no model download)")
    args = parser.parse_args()
    build_index(use_embeddings=USE_EMBEDDINGS and not args.bm25_only)
