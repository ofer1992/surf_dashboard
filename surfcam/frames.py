"""Decode a captured MPEG-TS file into JPEG frames at a fixed time interval.

PyAV is used rather than an ffmpeg subprocess because the static ffmpeg builds
available via pip segfault in this environment, and PyAV ships its own libav.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import av
import cv2


def extract(src: Path, outdir: Path, every: float, prefix: str = "frame") -> list[Path]:
    """Write one JPEG every `every` seconds of stream time. Returns the paths."""
    outdir.mkdir(parents=True, exist_ok=True)
    container = av.open(str(src))
    stream = container.streams.video[0]
    ctx = stream.codec_context
    print(f"{src.name}: {ctx.name} {ctx.width}x{ctx.height} @ {float(stream.average_rate or 0):.2f}fps")

    written: list[Path] = []
    next_t = 0.0
    for frame in container.decode(video=0):
        if frame.pts is None:
            continue
        t = float(frame.pts * stream.time_base)
        if t + 1e-6 < next_t:
            continue
        path = outdir / f"{prefix}_{len(written) + 1:04d}.jpg"
        cv2.imwrite(str(path), frame.to_ndarray(format="bgr24"),
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        written.append(path)
        next_t = t + every

    print(f"wrote {len(written)} frames to {outdir}")
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=Path)
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--every", type=float, default=1.0, help="seconds between frames")
    args = ap.parse_args()
    extract(args.src, args.outdir, args.every)


if __name__ == "__main__":
    main()
