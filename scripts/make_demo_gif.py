"""Assemble the README GIF from a sequence of real browser frames.

The frames come from Playwright (`apps/web/e2e/demo-capture.spec.ts`), which walks the Evidence
Graph interaction on the live app and writes numbered PNGs. This script only encodes them — it never
draws, composites or "cleans up" a screenshot, because a demo GIF that shows something the product
does not do is the same lie as a fabricated metric.

Encoding needs Pillow (there is no ffmpeg on this machine):

    .venv\\Scripts\\python.exe -m pip install pillow

Usage::

    python scripts/make_demo_gif.py --frames .tmp/graph-frames --out docs/assets/evidence-graph-demo.gif
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_pillow() -> object:
    try:
        # Optional tooling dependency, imported on demand: the repo must lint and test on a machine
        # that has never installed Pillow. (The `noqa` for PLC0415 this used to carry became an
        # unused directive once that rule stopped being selected — `ruff check .` flagged it.)
        from PIL import Image

        return Image
    except ImportError:  # pragma: no cover - depends on the machine
        print(
            "Pillow is required to encode the GIF:\n"
            r"  .venv\Scripts\python.exe -m pip install pillow",
            file=sys.stderr,
        )
        raise SystemExit(2) from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True, help="directory of numbered PNGs")
    parser.add_argument(
        "--out", type=Path, default=REPO_ROOT / "docs/assets/evidence-graph-demo.gif"
    )
    parser.add_argument("--width", type=int, default=1200, help="output width in pixels")
    parser.add_argument("--fps", type=float, default=2.0, help="frames per second")
    parser.add_argument(
        "--hold-last",
        type=float,
        default=2.0,
        help="seconds to hold the final frame, so the drawer is legible",
    )
    parser.add_argument(
        "--max-mb", type=float, default=2.5, help="fail rather than ship a heavy GIF"
    )
    args = parser.parse_args()
    # Resolve before use: `args.out.relative_to(REPO_ROOT)` raised on a relative path, so the
    # GIF was written and the command still exited 1 — a success reported as a failure.
    args.frames = args.frames.resolve()
    args.out = args.out.resolve()

    Image = _load_pillow()

    frames = sorted(args.frames.glob("*.png"))
    if len(frames) < 3:
        print(f"expected at least 3 frames in {args.frames}, found {len(frames)}", file=sys.stderr)
        return 1

    duration_ms = int(1000 / args.fps)
    images = []
    for path in frames:
        image = Image.open(path).convert("RGB")  # type: ignore[attr-defined]
        ratio = args.width / image.width
        images.append(image.resize((args.width, int(image.height * ratio)), Image.LANCZOS))  # type: ignore[attr-defined]

    # One palette for the whole sequence: a per-frame palette makes the GIF flicker, which reads as a
    # rendering bug rather than an animation.
    palette_source = images[-1].quantize(colors=128, method=Image.MEDIANCUT)  # type: ignore[attr-defined]
    quantised = [
        image.quantize(palette=palette_source, dither=Image.FLOYDSTEINBERG) for image in images
    ]  # type: ignore[attr-defined]
    durations = [duration_ms] * (len(quantised) - 1) + [int(args.hold_last * 1000)]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    quantised[0].save(
        args.out,
        save_all=True,
        append_images=quantised[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )

    size_mb = args.out.stat().st_size / (1024 * 1024)
    print(f"wrote {args.out.relative_to(REPO_ROOT)} — {len(quantised)} frames, {size_mb:.2f} MB")
    if size_mb > args.max_mb:
        print(
            f"the GIF is {size_mb:.2f} MB, above the {args.max_mb} MB budget: lower --width or drop "
            "frames rather than committing a file that makes the README slow to load",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
