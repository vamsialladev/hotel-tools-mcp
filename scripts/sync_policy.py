"""Copy stage 1's keyword policy search, PII redaction and synthetic documents into the package, at a pinned commit.

    python scripts/sync_policy.py                      # re-copy at the pinned commit (policy/SOURCE.json)
    python scripts/sync_policy.py --ref <commit>       # move the pin to another stage 1 commit
    python scripts/sync_policy.py --check              # exit 1 if the copied files changed since the last sync

Reads from Project 1's git history (`git show <commit>:<path>`), never its working tree, so the copy is exactly what
that commit contains. Project 1 is never modified. Only import lines are rewritten; everything else is byte-for-byte.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "src" / "hotel_tools" / "policy"
DOCS_DEST = ROOT / "data" / "policy"
SOURCE_FILE = DEST / "SOURCE.json"
DEFAULT_REPO = ROOT.parent / "hotel-ops-assistant"
CODE = {"src/retrieve.py": "retrieve.py", "src/ingest.py": "ingest.py", "src/pii.py": "pii.py"}
IMPORTS = [
    ("from src.config import", "from hotel_tools.policy.config import"),
    ("from src.ingest import", "from hotel_tools.policy.ingest import"),
]


def header(ref: str, version: str, path: str) -> str:
    return (
        f"# Copied from stage 1 (hotel-ops-assistant {version}, commit {ref[:7]}), {path}.\n"
        "# Do not edit here: change it in Project 1, then run `python scripts/sync_policy.py --ref <commit>`.\n"
        "# Only the import lines are rewritten (src.config / src.ingest -> hotel_tools.policy.config / .ingest).\n"
    )


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def rewrite(text: str) -> str:
    for old, new in IMPORTS:
        text = text.replace(old, new)
    return text


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def copied_files() -> dict[str, Path]:
    files = {name: DEST / name for name in CODE.values()}
    files |= {p.relative_to(ROOT).as_posix(): p for p in sorted(DOCS_DEST.rglob("*")) if p.is_file()}
    return files


def check() -> int:
    if not SOURCE_FILE.exists():
        print("No src/hotel_tools/policy/SOURCE.json: run scripts/sync_policy.py first.")
        return 1
    recorded = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))["files"]
    current = {name: sha(path.read_bytes()) for name, path in copied_files().items()}
    if current != recorded:
        changed = sorted(set(current.items()) ^ set(recorded.items()))
        print("Copied policy files changed since the last sync:", ", ".join(sorted({n for n, _ in changed})))
        return 1
    print(f"Policy copy matches Project 1 commit {json.loads(SOURCE_FILE.read_text())['commit'][:7]}.")
    return 0


def sync(repo: Path, ref: str) -> None:
    ref = git(repo, "rev-parse", ref).decode().strip()
    pyproject = git(repo, "show", f"{ref}:pyproject.toml").decode()
    version = next(line.split('"')[1] for line in pyproject.splitlines() if line.startswith("version"))
    DEST.mkdir(parents=True, exist_ok=True)
    for src, name in CODE.items():
        text = rewrite(git(repo, "show", f"{ref}:{src}").decode("utf-8"))
        (DEST / name).write_bytes((header(ref, version, src) + text).encode("utf-8"))
    listing = git(repo, "ls-tree", "-r", "--name-only", ref, "data/raw").decode().splitlines()
    for old in sorted(DOCS_DEST.rglob("*"), reverse=True):  # documents removed upstream disappear here too
        old.unlink() if old.is_file() else old.rmdir()
    for path in listing:
        target = DOCS_DEST / "raw" / Path(path).relative_to("data/raw")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git(repo, "show", f"{ref}:{path}"))
    files = {name: sha(path.read_bytes()) for name, path in copied_files().items()}
    record = {"project": "hotel-ops-assistant", "version": version, "commit": ref, "files": files}
    SOURCE_FILE.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Copied {len(CODE)} modules and {len(listing)} documents from Project 1 {version} ({ref[:7]}).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO, help="path to the hotel-ops-assistant checkout")
    parser.add_argument("--ref", help="Project 1 commit to copy (default: the pinned one)")
    parser.add_argument("--check", action="store_true", help="verify the copy instead of syncing")
    args = parser.parse_args()
    if args.check:
        return check()
    ref = args.ref or (json.loads(SOURCE_FILE.read_text())["commit"] if SOURCE_FILE.exists() else None)
    if not ref:
        print("First sync: pass --ref <Project 1 commit>.")
        return 1
    sync(args.repo, ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
