"""Capture a live HLS webcam stream to a local MPEG-TS file.

Why not just point ffmpeg at the .m3u8: in sandboxed/proxied environments
ffmpeg's TLS stack often cannot negotiate an HTTP CONNECT proxy, while
`requests` picks up HTTPS_PROXY automatically. Pulling the segments ourselves
also makes the capture restartable and easy to rate-limit.

The playlist is a sliding window of ~2s segments, so we poll it and append
each newly published segment. Concatenated MPEG-TS is directly decodable.

Usage:
    python -m surfcam.capture yafo out.ts --duration 300
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

STREAM_URLS = Path(__file__).resolve().parent.parent / "stream_url.json"


def resolve(cam: str) -> str:
    """Look a camera up in the repo's stream_url.json (refreshed by CI)."""
    urls = json.loads(STREAM_URLS.read_text())
    if cam in urls:
        return urls[cam]
    if cam.startswith("http"):
        return cam
    raise SystemExit(f"unknown cam {cam!r}; known: {', '.join(sorted(urls))}")


def capture(m3u8: str, out: Path, duration: float, poll: float = 2.0) -> int:
    base = m3u8.rsplit("/", 1)[0]
    session = requests.Session()
    seen: set[str] = set()
    total = 0
    deadline = time.time() + duration

    with out.open("wb") as fh:
        while time.time() < deadline:
            try:
                playlist = session.get(m3u8, timeout=15).text
            except requests.RequestException as exc:
                print(f"playlist fetch failed: {exc}")
                time.sleep(poll)
                continue

            # Segment names are relative; the playlist uses CRLF endings, so
            # strip before joining or the URL comes out malformed.
            for name in (l.strip() for l in playlist.splitlines()):
                if not name or name.startswith("#") or name in seen:
                    continue
                seen.add(name)
                try:
                    resp = session.get(f"{base}/{name}", timeout=20)
                    resp.raise_for_status()
                except requests.RequestException as exc:
                    print(f"segment {name} failed: {exc}")
                    continue
                fh.write(resp.content)
                fh.flush()
                total += len(resp.content)
            time.sleep(poll)

    print(f"{out}: {total} bytes in {len(seen)} segments")
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cam", help="camera key from stream_url.json, or a full m3u8 URL")
    ap.add_argument("out", type=Path)
    ap.add_argument("--duration", type=float, default=120.0, help="seconds to record")
    args = ap.parse_args()
    capture(resolve(args.cam), args.out, args.duration)


if __name__ == "__main__":
    main()
