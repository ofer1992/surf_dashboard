"""Off-the-shelf YOLO surfer detection, per frame, no training.

Stock COCO weights already carry `person` (0) and `surfboard` (37), so this is
zero-shot -- no labelling, no fine-tune. The only real problem is scale.

Surfers on this cam are 10-20 px in a 1920x1080 frame. Fed a whole frame at
imgsz=640 the model downscales them to ~5 px and finds almost nothing. The fix
is to slice the frame into small tiles and let each tile be *upscaled* to the
model's input size, so a 15 px surfer arrives as ~60 px. Upscale factor is by
far the most important knob here -- see docs/detector_eval.md for the sweep.

Detections from neighbouring tiles are merged twice: once by IoU NMS, and then
again by centre distance. The second pass matters because two boxes on the same
surfer are often small and barely overlapping (a torso box and a torso+board
box), so IoU NMS leaves both and the count comes out nearly double.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
import torch
from torchvision.ops import nms
from ultralytics import YOLO

PERSON, SURFBOARD = 0, 37


def tile_origins(w: int, h: int, size: int, overlap: int) -> list[tuple[int, int]]:
    """Top-left corners of overlapping tiles covering the frame."""
    step = size - overlap
    xs = list(range(0, max(w - size, 0) + 1, step))
    ys = list(range(0, max(h - size, 0) + 1, step))
    if xs[-1] != w - size:
        xs.append(w - size)
    if ys[-1] != h - size:
        ys.append(h - size)
    return [(x, y) for y in ys for x in xs]


def merge_by_distance(boxes: np.ndarray, radius: float = 18.0) -> np.ndarray:
    """Collapse boxes whose centres are within `radius` into one.

    IoU NMS alone does not do this: a torso box and a torso+board box on the
    same surfer can overlap too little to suppress, which double-counts.
    """
    if not len(boxes):
        return boxes
    centres = np.stack([(boxes[:, 0] + boxes[:, 2]) / 2,
                        (boxes[:, 1] + boxes[:, 3]) / 2], axis=1)
    order = np.argsort(-boxes[:, 4])
    used = np.zeros(len(boxes), bool)
    out = []
    for i in order:
        if used[i]:
            continue
        group = [i]
        used[i] = True
        for j in order:
            if not used[j] and np.linalg.norm(centres[i] - centres[j]) < radius:
                group.append(j)
                used[j] = True
        g = boxes[group]
        out.append([g[:, 0].min(), g[:, 1].min(), g[:, 2].max(), g[:, 3].max(),
                    g[:, 4].max()])
    return np.array(out, np.float32)


def detect(model: YOLO, img: np.ndarray, tile: int = 192, overlap: int = 48,
           imgsz: int = 768, conf: float = 0.05,
           water: tuple[int, int] | None = (180, 860),
           merge_radius: float = 18.0) -> np.ndarray:
    """Return merged (x1, y1, x2, y2, conf) detections for one frame."""
    h, w = img.shape[:2]
    rows = []
    for x, y in tile_origins(w, h, tile, overlap):
        res = model.predict(img[y:y + tile, x:x + tile], imgsz=imgsz, conf=conf,
                            classes=[PERSON, SURFBOARD], verbose=False)[0]
        for box, score in zip(res.boxes.xyxy.cpu().numpy(),
                              res.boxes.conf.cpu().numpy()):
            rows.append([box[0] + x, box[1] + y, box[2] + x, box[3] + y, float(score)])

    if not rows:
        return np.zeros((0, 5), np.float32)
    arr = np.array(rows, np.float32)

    if water is not None:
        cy = (arr[:, 1] + arr[:, 3]) / 2
        arr = arr[(cy > water[0]) & (cy < water[1])]
        if not len(arr):
            return arr

    keep = nms(torch.from_numpy(arr[:, :4]), torch.from_numpy(arr[:, 4]), 0.5)
    return merge_by_distance(arr[keep.numpy()], merge_radius)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("frames", type=Path)
    ap.add_argument("--weights", default="yolo11m.pt")
    ap.add_argument("--tile", type=int, default=192)
    ap.add_argument("--imgsz", type=int, default=768)
    ap.add_argument("--conf", type=float, default=0.05)
    ap.add_argument("--out", type=Path, help="directory for annotated previews")
    ap.add_argument("--glob", default="*.jpg")
    args = ap.parse_args()

    model = YOLO(args.weights)
    paths = sorted(args.frames.glob(args.glob)) if args.frames.is_dir() else [args.frames]
    for path in paths:
        img = cv2.imread(str(path))
        dets = detect(model, img, tile=args.tile, overlap=args.tile // 4,
                      imgsz=args.imgsz, conf=args.conf)
        print(f"{path.name}: {len(dets)} surfers")
        if args.out:
            args.out.mkdir(parents=True, exist_ok=True)
            vis = img.copy()
            for x1, y1, x2, y2, s in dets:
                cv2.rectangle(vis, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
                cv2.putText(vis, f"{s:.2f}", (int(x1), int(y1) - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
            cv2.imwrite(str(args.out / path.name), vis)


if __name__ == "__main__":
    main()
