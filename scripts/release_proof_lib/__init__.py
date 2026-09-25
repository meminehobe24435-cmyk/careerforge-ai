"""Support code for ``scripts/release_proof.py``.

The entry point, the process/network harness, the step bodies and the report writers live in
separate modules so that every file stays well under the repository's 500-line limit
(``scripts/check_file_length.py``). ``scripts/release_proof.py`` is the only entry point.
"""

from __future__ import annotations

from release_proof_lib import harness, reporting, steps

__all__ = ["harness", "reporting", "steps"]
