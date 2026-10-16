"""Build a panorama across the camera's preset tour.

The panorama is the fixed reference frame for the whole project. Because the
camera only rotates, every frame maps into it by a homography no matter how
far away the scene is, so the mosaic can carry a single geo-calibration that
all frames inherit (see `project.py`).

This chains pairwise homographies between consecutive frames, which is fine
for a one-off reference build but accumulates drift across a full sweep. For a
mosaic you intend to keep, bundle-adjust the poses afterwards and warp to a
cylinder rather than a plane -- a planar canvas stretches badly once the total
pan approaches the field of view.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from .motion import features, homography


def build(paths: list[Path], targets: list[int], ref: int,
          canvas: tuple[int, int] = (5200, 1700),
          offset: tuple[int, int] = (1500, 300)) -> np.ndarray:
    """Warp `targets` into one canvas, all referenced to frame `ref`."""
    orb = cv2.ORB_create(nfeatures=6000)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    cache: dict[int, tuple] = {}

    def feat(i):
        if i not in cache:
            img = cv2.imread(str(paths[i]))
            cache[i] = (img, features(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), orb))
        return cache[i]

    def to_ref(target: int) -> np.ndarray:
        """Chain single-step homographies from `target` back to `ref`."""
        H = np.eye(3)
        step = 1 if target < ref else -1
        for i in range(target, ref, step):
            _, a = feat(i)
            _, b = feat(i + step)
            h, ratio = homography(a, b, matcher)
            if h is None:
                raise RuntimeError(f"lost registration between frames {i} and {i + step}")
            H = h @ H
        return H

    w, h = canvas
    T = np.array([[1, 0, offset[0]], [0, 1, offset[1]], [0, 0, 1]], float)
    pano = np.zeros((h, w, 3), np.uint8)
    for t in targets:
        H = T @ to_ref(t)
        img, _ = feat(t)
        warped = cv2.warpPerspective(img, H, (w, h))
        # First writer wins, so earlier (less drifted) presets are not
        # overpainted by later ones.
        fill = (warped.sum(axis=2) > 0) & (pano.sum(axis=2) == 0)
        pano[fill] = warped[fill]
        cx, cy = cv2.perspectiveTransform(np.float32([[[960.0, 540.0]]]), H)[0][0]
        print(f"frame {t:4d} -> canvas centre ({cx:7.0f}, {cy:6.0f})")
    return pano


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--targets", type=int, nargs="+", required=True,
                    help="frame indices, one per preset dwell")
    ap.add_argument("--ref", type=int, required=True, help="reference frame index")
    ap.add_argument("--glob", default="*.jpg")
    args = ap.parse_args()

    paths = sorted(args.frames.glob(args.glob))
    pano = build(paths, args.targets, args.ref)
    cv2.imwrite(str(args.out), pano, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"wrote {args.out} {pano.shape}")


if __name__ == "__main__":
    main()
