"""Dataset generation for the evaluation suites.

Why generate instead of scrape
------------------------------
Market JD text has no ground truth: nobody publishes "the correct skill set" for
a scraped posting. A controlled corpus does, so precision and recall can be
measured rather than asserted. The trade-off is stated plainly wherever these
numbers are reported: this is a **controlled benchmark**, not a sample of the
live job market.

Everything is seeded, so the same command produces byte-identical datasets and a
metric change can only come from a code change. ``--check`` verifies that the
committed files still match, which is what makes that claim enforceable.

Usage::

    python evals/generate_datasets.py            # regenerate in place
    python evals/generate_datasets.py --check     # verify committed files match
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus_builders import (
    build_claim_dataset,
    build_jd_dataset,
    build_retrieval_dataset,
)
from corpus_data import (
    SEED,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "evals" / "datasets"


# ── Writing ──────────────────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")


def generate_all() -> dict[str, Any]:
    jd_rows = build_jd_dataset()
    claim_rows = build_claim_dataset()
    retrieval_rows = build_retrieval_dataset()

    jd_path = DATASET_DIR / "jd_extraction.jsonl"
    claim_path = DATASET_DIR / "claim_validation.jsonl"
    retrieval_path = DATASET_DIR / "retrieval.jsonl"
    _write_jsonl(jd_path, jd_rows)
    _write_jsonl(claim_path, claim_rows)
    _write_jsonl(retrieval_path, retrieval_rows)

    manifest = {
        "seed": SEED,
        "generator": "evals/generate_datasets.py",
        "note": (
            "Controlled benchmark with exact ground truth. Generated, not scraped: "
            "real postings carry no labels. Treat these numbers as upper-bound "
            "indicators of extraction quality, not as market-representative accuracy."
        ),
        "datasets": {
            "jd_extraction": {
                "path": "evals/datasets/jd_extraction.jsonl",
                "samples": len(jd_rows),
                "sha256": _sha256(jd_path),
                "families": sorted({row["family"] for row in jd_rows}),
                "languages": sorted({row["language"] for row in jd_rows}),
                "with_distractor": sum(1 for row in jd_rows if row["has_distractor"]),
            },
            "claim_validation": {
                "path": "evals/datasets/claim_validation.jsonl",
                "samples": len(claim_rows),
                "sha256": _sha256(claim_path),
                "kinds": sorted({row["gold"]["kind"] for row in claim_rows}),
            },
            "retrieval": {
                "path": "evals/datasets/retrieval.jsonl",
                "samples": sum(len(row["queries"]) for row in retrieval_rows),
                "sha256": _sha256(retrieval_path),
                "documents": sum(len(row["documents"]) for row in retrieval_rows),
                "note": "samples counts queries; documents counts indexed evidence fragments",
            },
        },
    }
    (DATASET_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed datasets match what the generator produces",
    )
    args = parser.parse_args()

    manifest_path = DATASET_DIR / "manifest.json"
    before = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    )
    manifest = generate_all()

    if args.check:
        if before is None:
            print("dataset manifest was missing", file=sys.stderr)
            return 1
        drift = [
            name
            for name in manifest["datasets"]
            if before["datasets"][name]["sha256"] != manifest["datasets"][name]["sha256"]
        ]
        if drift:
            print(f"dataset drift detected in: {', '.join(drift)}", file=sys.stderr)
            return 1
        print("datasets match the generator")
        return 0

    for name, info in manifest["datasets"].items():
        print(f"{name}: {info['samples']} samples, sha256 {info['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
