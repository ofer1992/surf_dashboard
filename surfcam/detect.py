"""Baseline surfer detector -- a candidate miner, not a finished detector.

Measured on a 23 s dwell of the Jaffa cam (see docs/surfer_detection.md):

    plain median-background differencing   ~750 blobs/frame
    top-hat + temporal persistence         ~550 blobs/frame

Neither is usable on its own. Two properties of this scene defeat them:
surfers are only 10-20 px wide with modest contrast, and the wave field
contains structures of exactly that scale which stay put for tens of seconds,
so "small, dark and persistent" describes a wave crest as well as a surfer.

What this module is genuinely good for is cutting the cost of labelling. It
concentrates the candidates into a few hundred boxes per frame out of ~2M
pixel locations, which is a large enough reduction to make hand-labelling a
training set for a learned detector practical. Treat its output as proposals
to be reviewed, never as detections.

The two ideas worth keeping for the learned pipeline:
  * `MORPH_BLACKHAT` at surfer scale suppresses broad wave shading while
    keeping compact dark objects, and is a cheap, useful input channel.
  * Persistence across a dwell is real signal -- a surfer stays put and drifts
    smoothly, whereas texture decorrelates -- it is just not, by itself,
    discriminative enough.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def blackhat(gray: np.ndarray, size: int = 15) -> np.ndarray:
    """Response to compact dark objects up to `size` px across."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    return cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, k)


def persistence(frames: list[np.ndarray], water: tuple[int, int],
                thresh: float = 10.0) -> np.ndarray:
    """Fraction of the dwell in which each pixel reads as a compact dark object.

    `frames` must all come from one dwell, so the camera is effectively static.
    """
    y0, y1 = water
    acc = np.zeros(frames[0].shape[:2], np.float32)
    for img in frames:
        resp = blackhat(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)).astype(np.float32)
        resp[:y0] = 0
        resp[y1:] = 0
        acc += resp > thresh
    return acc / len(frames)


def propose(votes: np.ndarray, min_votes: float = 0.55,
            area: tuple[int, int] = (6, 600),
            max_wh: tuple[int, int] = (60, 40)) -> list[tuple[float, float, int]]:
    """Connected components of the persistence map, filtered to surfer scale."""
    mask = (votes >= min_votes).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, cent = cv2.connectedComponentsWithStats(mask, 8)

    out = []
    for i in range(1, n):
        _, _, w, h, a = stats[i]
        if area[0] <= a <= area[1] and w <= max_wh[0] and h <= max_wh[1]:
            out.append((float(cent[i][0]), float(cent[i][1]), int(a)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames", type=Path, help="frames from a single dwell")
    ap.add_argument("--water", type=int, nargs=2, default=(200, 830),
                    metavar=("Y0", "Y1"), help="water band for this preset")
    ap.add_argument("--out", type=Path, help="write an annotated preview here")
    ap.add_argument("--glob", default="*.jpg")
    args = ap.parse_args()

    paths = sorted(args.frames.glob(args.glob))
    imgs = [cv2.imread(str(p)) for p in paths]
    if not imgs:
        raise SystemExit(f"no frames matched {args.glob} in {args.frames}")

    votes = persistence(imgs, tuple(args.water))
    props = propose(votes)
    print(f"{len(imgs)} frames -> {len(props)} proposals "
          f"(expect many false positives; review before use)")

    if args.out:
        vis = imgs[len(imgs) // 2].copy()
        for cx, cy, _ in props:
            cv2.rectangle(vis, (int(cx) - 16, int(cy) - 12),
                          (int(cx) + 16, int(cy) + 12), (0, 0, 255), 2)
        cv2.imwrite(str(args.out), vis)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
