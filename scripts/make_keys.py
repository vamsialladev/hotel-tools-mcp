"""Create demo API keys, one per role, for the simulated hotel group (and one for the second tenant).

    python scripts/make_keys.py              # writes .hotel-mcp/keys.json (hashes only) and prints each key ONCE
    python scripts/make_keys.py --env        # also writes .env.keys with HOTEL_MCP_KEY_<ROLE>=... (git-ignored)

Keys are random; only their SHA-256 hashes are stored. Re-running replaces all keys.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hotel_tools.auth import add_key  # noqa: E402
from hotel_tools.config import KEYS_FILE  # noqa: E402

DEMO = [
    ("guest", "hg-demo", "elena.ruiz@mail.test"),
    ("front_desk", "hg-demo", "staff-fd-01"),
    ("manager", "hg-demo", "staff-mgr-01"),
    ("auditor", "hg-demo", "staff-aud-01"),
    ("front_desk", "hg-other", "staff-other-fd"),
]


def make(keys_file: Path = KEYS_FILE) -> dict[str, str]:
    keys, shown = {}, {}
    for role, tenant, subject in DEMO:
        label = role if tenant == "hg-demo" else f"{role}_{tenant}"
        shown[label.upper().replace("-", "_")] = add_key(keys, role, tenant, subject)
    keys_file.parent.mkdir(parents=True, exist_ok=True)
    keys_file.write_text(json.dumps(keys, indent=2) + "\n", encoding="utf-8")
    return shown


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env", action="store_true", help="also write .env.keys (git-ignored)")
    args = parser.parse_args(argv)
    shown = make()
    lines = [f"HOTEL_MCP_KEY_{label}={key}" for label, key in shown.items()]
    if args.env:
        (ROOT / ".env.keys").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {KEYS_FILE} (hashes) and .env.keys (keys). Keep .env.keys private.")
    else:
        print(f"Wrote {KEYS_FILE} (hashes only). Copy these keys now; they are not shown again:")
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
