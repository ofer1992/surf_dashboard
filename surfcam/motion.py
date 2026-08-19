"""Track the camera's pan and segment its preset tour.

The Jaffa cam is not static: it runs a repeating tour, panning for several
seconds and then dwelling. Everything downstream depends on knowing which of
those two states a frame is in:

  * DWELL frames are stable to well under a pixel, so background subtraction
    and frame differencing work on them directly, with no stabilisation.
  * MOVE frames are useless for detection and must be dropped.

Registration uses ORB + RANSAC homography. Because the camera rotates about
(near enough) its optical centre, one homography explains the whole frame
regardless of scene depth -- see docs/surfer_detection.md. Features are taken
from the whole frame here; for production registration restrict them to land
(see `land_mask`), since water features are non-rigid and drag the estimate.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

CENTRE = np.float32([[[960.0, 540.0]]])


def features(gray: np.ndarray, orb: cv2.ORB, mask: np.ndarray | None = None):
    return orb.detectAndCompute(gray, mask)


def homography(prev, curr, matcher) -> tuple[np.ndarray | None, float]:
    """Homography mapping `prev` onto `curr`, plus the RANSAC inlier ratio."""
    (pk, pd), (ck, cd) = prev, curr
    if pd is None or cd is None:
        return None, 0.0
    matches = sorted(matcher.match(pd, cd), key=lambda m: m.distance)[:2000]
    if len(matches) < 12:
        return None, 0.0
    src = np.float32([pk[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([ck[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
    if H is None:
        return None, 0.0
    return H, float(mask.sum()) / len(matches)


@dataclass
class Step:
    index: int
    dx: float
    dy: float
    inliers: float
    moving: bool


def analyse(paths: list[Path], still_px: float = 2.0) -> list[Step]:
    """Per-frame pan/tilt of the image centre, and a moving/still verdict."""
    orb = cv2.ORB_create(nfeatures=4000)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    steps: list[Step] = []
    prev = None
    for i, path in enumerate(paths):
        gray = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2GRAY)
        curr = features(gray, orb)
        if prev is not None:
            H, ratio = homography(prev, curr, matcher)
            if H is None:
                steps.append(Step(i, float("nan"), float("nan"), ratio, True))
            else:
                cx, cy = cv2.perspectiveTransform(CENTRE, H)[0][0]
                dx, dy = float(cx - 960), float(cy - 540)
                # A low inlier ratio during a large apparent jump means the
                # matcher lost the scene mid-pan; treat as moving, not as a
                # measurement.
                bad = ratio < 0.4 and abs(dx) > 100
                moving = bad or abs(dx) > still_px or abs(dy) > still_px
                steps.append(Step(i, dx, dy, ratio, moving))
        prev = curr
    return steps


def segments(steps: list[Step]) -> list[tuple[str, int, int]]:
    """Collapse per-frame verdicts into MOVE / DWELL runs."""
    runs: list[tuple[str, int, int]] = []
    state = None
    start = 0
    for s in steps:
        label = "MOVE" if s.moving else "DWELL"
        if label != state:
            if state is not None:
                runs.append((state, start, s.index - 1))
            state, start = label, s.index
    if state is not None:
        runs.append((state, start, steps[-1].index))
    return runs


def land_mask(shape: tuple[int, int], horizon_y: int, shore_y: int) -> np.ndarray:
    """Keep only rigid scenery: above the horizon and below the shoreline.

    The water band between them is non-rigid and must be excluded when
    estimating camera motion.
    """
    mask = np.full(shape[:2], 255, np.uint8)
    mask[horizon_y:shore_y] = 0
    return mask


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames", type=Path, help="directory of extracted frames")
    ap.add_argument("--glob", default="*.jpg")
    args = ap.parse_args()

    paths = sorted(args.frames.glob(args.glob))
    if len(paths) < 2:
        raise SystemExit(f"need >=2 frames, found {len(paths)}")

    steps = analyse(paths)
    cum = 0.0
    print(f"{'i':>4} {'dx':>9} {'dy':>8} {'inl':>5}  {'cum_pan':>9}  state")
    for s in steps:
        cum += 0.0 if np.isnan(s.dx) else s.dx
        dx = "   nan" if np.isnan(s.dx) else f"{s.dx:9.1f}"
        dy = "  nan" if np.isnan(s.dy) else f"{s.dy:8.1f}"
        print(f"{s.index:4d} {dx} {dy} {s.inliers:5.2f}  {cum:9.0f}  "
              f"{'MOVE' if s.moving else 'dwell'}")

    print(f"\n{'state':6} {'start':>6} {'end':>6} {'frames':>7}")
    for state, a, b in segments(steps):
        print(f"{state:6} {a:6d} {b:6d} {b - a + 1:7d}")


if __name__ == "__main__":
    main()
