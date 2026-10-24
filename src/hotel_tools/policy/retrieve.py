# Copied from stage 1 (hotel-ops-assistant 1.6.0, commit 392e1b5), src/retrieve.py.
# Do not edit here: change it in Project 1, then run `python scripts/sync_policy.py --ref <commit>`.
# Only the import lines are rewritten (src.config / src.ingest -> hotel_tools.policy.config / .ingest).
"""Hybrid search: keyword (BM25) + meaning (embeddings), merged with Reciprocal Rank Fusion.
Results are always filtered to the selected property + brand-wide (shared) documents."""

import json
import re
import unicodedata

import numpy as np
from rank_bm25 import BM25Okapi

from hotel_tools.policy.config import EMBED_MODEL, INDEX_DIR, SHARED, TOP_K
from hotel_tools.policy.ingest import contextual_text

STOPWORDS = set(
    "a an the is are am be can do does did i we our you your to of for in on at and or "
    "what how much many when where which who with it this that my me if".split()
)
# Domain stopwords: words that appear in almost every hotel document and add no signal.
# Found via eval: "guest" in "Can a guest bring their dog?" pulled loyalty docs to the top.
STOPWORDS |= {"guest", "guests", "hotel", "hotels"}


def stem(word: str) -> str:
    """Light stemmer so word forms match: cats->cat, RVs->rv, smoking/smoke->smok, cribs->crib."""
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "y"
    elif word.endswith("ing") and len(word) > 5:
        word = word[:-3]
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 2:
        word = word[:-1]
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


# One spelling for compound words, in documents and questions alike: "check-out", "check out" and "checkout"
# all become "checkout". Found via the visitor eval: "What time is checkout?" matched nothing.
COMPOUNDS = [(re.compile(r"\bcheck[\s-]+(in|out)\b"), r"check\1"), (re.compile(r"\bwi[\s-]?fi\b"), "wifi")]

# Words visitors type that the documents say differently. Added to the query only (never the documents),
# for keyword search and the scope check. Found via the visitor eval: "gym" never matched "fitness center"
# and "I left something" never matched "Lost and Found".
SYNONYMS = {
    "internet": "wifi",
    "gym": "fitness",
    "workout": "fitness",
    "exercise": "fitness",
    "left": "lost found",
    "forgot": "lost found",
    "forgotten": "lost found",
    "lost": "found",
    "bags": "luggage",
    "baggage": "luggage",
    "suitcase": "luggage",
    "wheelchair": "accessible accessibility",
    "disabled": "accessible accessibility",
    "disability": "accessible accessibility",
    "hike": "hiking trail",
    "hiking": "trail",
    "shuttle": "airport transfer",
    "cancel": "cancellation",
    "noise": "quiet",
    "loud": "quiet noise",
    "washing": "laundry",
    "eat": "dining restaurant breakfast",
    "food": "dining restaurant",
}


# Spanish hotel vocabulary -> the English words the documents use (keys without accents). The documents stay
# English; the answer is written in the guest's language. Built from the documents' section titles before the
# Project 4 held-out Spanish cases were run, so it covers topics, not test questions (decision 51). Spanish words
# only: none of these keys is an English word a staff member would type.
SPANISH = {
    "estacionamiento": "parking",
    "aparcamiento": "parking",
    "parqueo": "parking",
    "coche": "parking",
    "carro": "parking",
    "cargador": "ev charging",
    "electrico": "ev charging",
    "mascota": "pet pets",
    "mascotas": "pet pets",
    "perro": "dog pet",
    "perros": "dogs pet",
    "gato": "cat pet",
    "gatos": "cats pet",
    "animales": "pets",
    "lazarillo": "service animal",
    "piscina": "pool",
    "alberca": "pool",
    "playa": "beach",
    "toalla": "towel",
    "toallas": "towels",
    "desayuno": "breakfast",
    "almuerzo": "dining restaurant",
    "cena": "dining restaurant",
    "comida": "dining restaurant",
    "restaurante": "restaurant",
    "servicio": "service",
    "salida": "checkout",
    "entrada": "checkin",
    "llegada": "checkin arrival",
    "temprano": "early checkin",
    "tarde": "late checkout",
    "cancelar": "cancellation",
    "cancelacion": "cancellation",
    "reembolso": "refund",
    "devolucion": "refund",
    "reserva": "booking reservation",
    "tarifa": "rate fee",
    "cuota": "fee",
    "precio": "fee price",
    "cuesta": "fee cost",
    "incluye": "includes",
    "traslado": "airport transfer shuttle",
    "aeropuerto": "airport transfer",
    "transporte": "shuttle transfer",
    "contrasena": "wifi password",
    "gimnasio": "fitness",
    "masaje": "spa treatment",
    "tratamiento": "spa treatment",
    "ruido": "quiet noise",
    "silencio": "quiet hours",
    "fumar": "smoking",
    "fuma": "smoking",
    "lavanderia": "laundry",
    "ropa": "laundry",
    "equipaje": "luggage",
    "maleta": "luggage",
    "maletas": "luggage",
    "perdido": "lost found",
    "perdidos": "lost found",
    "olvide": "lost found",
    "olvido": "lost found",
    "cuna": "crib",
    "cama": "rollaway bed",
    "almohada": "pillow",
    "almohadas": "pillows",
    "limpieza": "housekeeping daily service",
    "habitacion": "room",
    "despertador": "wake-up call",
    "accesible": "accessible accessibility",
    "silla": "wheelchair accessible",
    "ruedas": "wheelchair",
    "puntos": "points loyalty",
    "lealtad": "loyalty",
    "miembro": "member loyalty",
    "socio": "member loyalty",
    "senderismo": "hiking trail",
    "caminata": "hiking trail",
    "boda": "wedding event",
    "evento": "event",
    "descuento": "discount",
    "propina": "gratuity",
    "deposito": "deposit",
}


def fold_accents(text: str) -> str:
    """Lowercase without accents ('Habitación' -> 'habitacion'), so Spanish words match the table above."""
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


def expand_query(text: str) -> str:
    """The question plus the document-side words for any synonyms (or Spanish words) it uses."""
    words = re.findall(r"[a-z]+", fold_accents(text))
    extra = [SYNONYMS[w] for w in words if w in SYNONYMS] + [SPANISH[w] for w in words if w in SPANISH]
    return f"{text} {' '.join(extra)}" if extra else text


def tokenize(text: str):
    # Single letters ("s" from "guest's", "a") carry no meaning but matched almost every passage.
    text = text.lower()
    for pattern, replacement in COMPOUNDS:
        text = pattern.sub(replacement, text)
    return [
        stem(t) for t in re.findall(r"[a-z0-9$:]+", text) if t not in STOPWORDS and not (len(t) == 1 and t.isalpha())
    ]


class Retriever:
    def __init__(self, use_embeddings: bool = True):
        index_file = INDEX_DIR / "chunks.json"
        if not index_file.exists():
            raise FileNotFoundError("No index found. Run: python -m src.ingest")
        self.chunks = json.loads(index_file.read_text(encoding="utf-8"))
        self.bm25 = BM25Okapi([tokenize(contextual_text(c)) for c in self.chunks])

        self.model, self.vectors = None, None
        if use_embeddings and (INDEX_DIR / "vectors.npy").exists():
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:  # light install: fall back to keyword search
                return
            self.vectors = np.load(INDEX_DIR / "vectors.npy")
            self.model = SentenceTransformer(EMBED_MODEL)

    def properties(self):
        return sorted({c["property"] for c in self.chunks} - {SHARED})

    @property
    def mode(self) -> str:
        return "hybrid" if self.model is not None else "keyword"

    def signals(self, query: str, prop: str) -> dict:
        """How well the question matches this property's documents, used by the scope check:
        number of passages sharing a keyword, and (hybrid only) the best meaning similarity."""
        allowed = [i for i, c in enumerate(self.chunks) if c["property"] in (prop, SHARED)]
        scores = self.bm25.get_scores(tokenize(expand_query(query)))
        best = None
        if self.model is not None:
            q = self.model.encode([query], normalize_embeddings=True)[0]
            best = float(max(self.vectors[i] @ q for i in allowed))
        return {"keyword_matches": sum(1 for i in allowed if scores[i] > 0), "best_similarity": best}

    def search(self, query: str, prop: str, k: int = TOP_K):
        allowed = [i for i, c in enumerate(self.chunks) if c["property"] in (prop, SHARED)]

        bm25_scores = self.bm25.get_scores(tokenize(expand_query(query)))
        # Only passages that match at least one keyword; a zero score is not a match.
        matched = [i for i in allowed if bm25_scores[i] > 0]
        rankings = [sorted(matched, key=lambda i: -bm25_scores[i])]

        if self.model is not None:
            q = self.model.encode([query], normalize_embeddings=True)[0]
            sims = self.vectors @ q
            rankings.append(sorted(allowed, key=lambda i: -sims[i]))

        fused = {}
        for ranking in rankings:
            for rank, i in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1.0 / (60 + rank + 1)

        top = sorted(fused, key=lambda i: -fused[i])[:k]
        return [{**self.chunks[i], "score": round(fused[i], 4)} for i in top]
