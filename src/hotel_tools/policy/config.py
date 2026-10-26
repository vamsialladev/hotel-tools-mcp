"""Settings for the copied stage 1 modules (retrieve.py and ingest.py import these names).

The tool server always searches keyword-only (BM25): no PyTorch, starts in about a second. The documents are stage 1's
synthetic hotel documents, copied by scripts/sync_policy.py; the index is built on first use.
"""

import os
from pathlib import Path

from hotel_tools.config import DATA_DIR  # the source checkout's data/, or the copy installed with the package

ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = DATA_DIR / "policy" / "raw"
INDEX_DIR = Path(os.getenv("POLICY_INDEX_DIR", DATA_DIR / "policy_index"))
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # unused: embeddings are off here
USE_EMBEDDINGS = False
TOP_K = int(os.getenv("POLICY_TOP_K", "5"))  # stage 1's tested setting
SHARED = "shared"
