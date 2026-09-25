"""Dataset generation for the evaluation suites.

**Why generate instead of scrape.** Market JD text has no ground truth: nobody publishes "the
correct skill set" for a scraped posting. A controlled corpus does, so precision and recall can be
measured rather than asserted. The trade-off is stated wherever these numbers are reported: this is
a **controlled benchmark**, not a sample of the live job market.

**What is generated and what is authored.** Two of the four datasets are generated here (JD
extraction, RAG retrieval): both are parametric corpora where the ground truth follows from
construction, and being seeded means a metric can only move because the code moved. The other two
are **authored by hand** and merely serialised here:

* ``evidence_validation`` — from ``evals/corpus_evidence.py``. Generated claim cases were retired
  in PHASE 12 after they turned out to hold 22 distinct claim/kind pairs across 120 rows, with
  labels that tracked the rule layer's own logic.
* ``interview_relevance`` — from ``evals/corpus_interview.py``. Which questions are reasonable for
  a role is a judgement, and a judgement has to be written down by a person.

Everything is seeded, so the same command produces byte-identical datasets and a metric change can
only come from a code change. ``--check`` verifies the committed files still match, which is what
makes that claim enforceable in CI.

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

from corpus_builders import build_jd_dataset, build_retrieval_dataset
from corpus_data import SEED
from corpus_evidence import build_evidence_cases
from corpus_evidence_shared import FIXTURE_VERSION as EVIDENCE_VERSION
from corpus_interview import FIXTURE_VERSION as INTERVIEW_VERSION, build_interview_rows

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "evals" / "datasets"

#: Fixture version per dataset. Bumped when the cases change in a way that makes an old number
#: incomparable with a new one — a golden dataset that changes silently turns a regression
#: comparison into a statement about the dataset.
_JD_VERSION = "jd1.0"
_RAG_VERSION = "rag1.0"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    payload = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")


def generate_all() -> dict[str, Any]:
    jd_rows = build_jd_dataset()
    rag_rows = build_retrieval_dataset()
    evidence_rows = build_evidence_cases()
    interview_rows = build_interview_rows()

    paths = {
        "jd_extraction": DATASET_DIR / "jd_extraction.jsonl",
        "rag_retrieval": DATASET_DIR / "rag_retrieval.jsonl",
        "evidence_validation": DATASET_DIR / "evidence_validation.jsonl",
        "interview_relevance": DATASET_DIR / "interview_relevance.jsonl",
    }
    _write_jsonl(paths["jd_extraction"], jd_rows)
    _write_jsonl(paths["rag_retrieval"], rag_rows)
    _write_jsonl(paths["evidence_validation"], evidence_rows)
    _write_jsonl(paths["interview_relevance"], interview_rows)

    evidence_labels: dict[str, int] = {}
    for row in evidence_rows:
        label = row["expected_label"]
        evidence_labels[label] = evidence_labels.get(label, 0) + 1

    manifest = {
        "seed": SEED,
        "generator": "evals/generate_datasets.py",
        "note": (
            "Controlled benchmark with exact ground truth. The JD and retrieval corpora are "
            "generated (real postings carry no labels); the evidence and interview cases are "
            "hand-authored. Treat these numbers as indicators of behaviour on this corpus, not "
            "as market-representative accuracy."
        ),
        "datasets": {
            "jd_extraction": {
                "path": "evals/datasets/jd_extraction.jsonl",
                "fixture_version": _JD_VERSION,
                "origin": "generated",
                "samples": len(jd_rows),
                "sha256": _sha256(paths["jd_extraction"]),
                "families": sorted({row["family"] for row in jd_rows}),
                "languages": sorted({row["language"] for row in jd_rows}),
                "with_distractor": sum(1 for row in jd_rows if row["has_distractor"]),
            },
            "rag_retrieval": {
                "path": "evals/datasets/rag_retrieval.jsonl",
                "fixture_version": _RAG_VERSION,
                "origin": "generated",
                "samples": sum(len(row["queries"]) for row in rag_rows),
                "sha256": _sha256(paths["rag_retrieval"]),
                "documents": sum(len(row["documents"]) for row in rag_rows),
                "note": "samples counts queries; documents counts indexed evidence fragments",
            },
            "evidence_validation": {
                "path": "evals/datasets/evidence_validation.jsonl",
                "fixture_version": EVIDENCE_VERSION,
                "origin": "hand-authored",
                "samples": len(evidence_rows),
                "sha256": _sha256(paths["evidence_validation"]),
                "labels": dict(sorted(evidence_labels.items())),
                "rubric": (
                    "supported = every substantive element carried by >=2 independent evidence "
                    "kinds; partially_supported = core action evidenced but one element weaker; "
                    "unsupported = a substantive element has no support anywhere"
                ),
                "note": (
                    "Replaced the generated claim corpus, which held 22 distinct claim/kind pairs "
                    "across 120 rows and therefore measured a template rather than the gate."
                ),
            },
            "interview_relevance": {
                "path": "evals/datasets/interview_relevance.jsonl",
                "fixture_version": INTERVIEW_VERSION,
                "origin": "hand-authored",
                "samples": len(interview_rows),
                "sha256": _sha256(paths["interview_relevance"]),
                "roles": [row["scenario"]["role"] for row in interview_rows],
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
        missing = [name for name in manifest["datasets"] if name not in before["datasets"]]
        drift = [
            name
            for name in manifest["datasets"]
            if name in before["datasets"]
            and before["datasets"][name]["sha256"] != manifest["datasets"][name]["sha256"]
        ]
        version_drift = [
            name
            for name in manifest["datasets"]
            if name in before["datasets"]
            and before["datasets"][name].get("fixture_version")
            != manifest["datasets"][name].get("fixture_version")
        ]
        if missing:
            print(f"datasets missing from the manifest: {', '.join(missing)}", file=sys.stderr)
            return 1
        if drift:
            print(f"dataset drift detected in: {', '.join(drift)}", file=sys.stderr)
            return 1
        if version_drift:
            # A changed fixture version with an unchanged hash is a documentation bug: the version
            # is what makes an old report comparable, so it has to move when the content moves.
            print(
                f"fixture_version changed without content drift: {', '.join(version_drift)}",
                file=sys.stderr,
            )
            return 1
        print("datasets match the generator")
        return 0

    for name, info in manifest["datasets"].items():
        print(
            f"{name}: {info['samples']} samples, {info['origin']}, "
            f"v{info['fixture_version']}, sha256 {info['sha256'][:16]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
