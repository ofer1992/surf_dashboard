"""Score the zero-shot YOLO detector against hand-labelled ground truth.

Matching is greedy nearest-centre within a radius, not IoU: at 10-20 px the
box extents are dominated by whether the model happened to include the board,
so IoU is far noisier than "did it find this surfer".

Blobs marked `ambiguous` in the ground truth are excluded from both counts. A
detection landing on one is neither a hit nor a false positive -- at this
resolution some objects genuinely cannot be resolved, and forcing a call on
them would flatter or punish the detector arbitrarily.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from .yolo_detect import detect


def match(dets: np.ndarray, truth: list, ambiguous: list, radius: float = 22.0):
    """Greedy nearest-centre matching. Returns (tp, fp, fn, matched_flags)."""
    centres = (np.stack([(dets[:, 0] + dets[:, 2]) / 2,
                         (dets[:, 1] + dets[:, 3]) / 2], axis=1)
               if len(dets) else np.zeros((0, 2)))
    truth = np.array(truth, float).reshape(-1, 2)
    amb = np.array(ambiguous, float).reshape(-1, 2)

    hit = np.zeros(len(truth), bool)
    used = np.zeros(len(centres), bool)
    # Highest-confidence detections claim their target first.
    for di in np.argsort(-dets[:, 4]) if len(dets) else []:
        if not len(truth):
            break
        d = np.linalg.norm(truth - centres[di], axis=1)
        d[hit] = np.inf
        best = int(np.argmin(d))
        if d[best] <= radius:
            hit[best] = True
            used[di] = True

    # Unmatched detections sitting on an ambiguous blob are set aside.
    excused = np.zeros(len(centres), bool)
    for di in range(len(centres)):
        if used[di] or not len(amb):
            continue
        if np.linalg.norm(amb - centres[di], axis=1).min() <= radius:
            excused[di] = True

    tp = int(hit.sum())
    fp = int((~used & ~excused).sum())
    fn = int((~hit).sum())
    return tp, fp, fn, used, excused


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames", type=Path, help="directory holding the labelled frames")
    ap.add_argument("--gt", type=Path, default=Path(__file__).parent / "groundtruth.json")
    ap.add_argument("--weights", default="yolo11m.pt")
    ap.add_argument("--tile", type=int, default=192)
    ap.add_argument("--imgsz", type=int, default=768)
    ap.add_argument("--conf", type=float, nargs="+",
                    default=[0.05, 0.10, 0.15, 0.25, 0.40])
    args = ap.parse_args()

    gt = json.loads(args.gt.read_text())["frames"]
    model = YOLO(args.weights)

    # Detect once at the lowest threshold, then re-score by filtering.
    base = min(args.conf)
    cache = {}
    for name in gt:
        img = cv2.imread(str(args.frames / name))
        if img is None:
            raise SystemExit(f"missing frame {args.frames / name}")
        cache[name] = detect(model, img, tile=args.tile, overlap=args.tile // 4,
                             imgsz=args.imgsz, conf=base)

    print(f"{'conf':>5} {'GT':>4} {'det':>4} {'TP':>4} {'FP':>4} {'FN':>4} "
          f"{'prec':>6} {'recall':>7} {'F1':>6}")
    for conf in sorted(args.conf):
        T = F = N = G = D = 0
        for name, entry in gt.items():
            d = cache[name]
            d = d[d[:, 4] >= conf] if len(d) else d
            tp, fp, fn, _, _ = match(d, entry["surfers"], entry["ambiguous"])
            T += tp; F += fp; N += fn
            G += len(entry["surfers"]); D += len(d)
        prec = T / (T + F) if T + F else 0.0
        rec = T / (T + N) if T + N else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        print(f"{conf:5.2f} {G:4d} {D:4d} {T:4d} {F:4d} {N:4d} "
              f"{prec:6.2f} {rec:7.2f} {f1:6.2f}")


if __name__ == "__main__":
    main()
