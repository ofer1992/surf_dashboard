# surfcam

Exploratory computer-vision tooling for detecting surfers on the Jaffa (`yafo`)
beach cam and mapping them to real-world positions.

**Status: brainstorming / feasibility.** Nothing here runs in CI, and it is kept
deliberately separate from the dashboard: the GitHub Pages workflow installs
only `requests` and `beautifulsoup4`, and must not be made to pull heavy CV
wheels every 15 minutes. Install `surfcam/requirements.txt` separately.

Start with **[docs/detector_eval.md](docs/detector_eval.md)** — the zero-shot
YOLO detector and its measured precision/recall. Background on the camera
itself is in **[docs/surfer_detection.md](docs/surfer_detection.md)**.

The short version:

- The camera runs a **preset tour**: pans a few seconds, then dwells 5–27 s.
  During a dwell it is still to under 0.5 px, so no stabilisation is needed.
- The motion is a **pure rotation**, so frames register into a panorama by
  homography with no depth model. Confirmed by stitching the presets.
- Projection to the world splits into a per-frame pose homography and a
  **single hand-calibrated sea-plane homography**.
- **Detection works zero-shot with tiled YOLO.** Stock COCO weights, no
  training: **0.86 precision / 0.77 recall**, and **zero false positives** at
  conf ≥ 0.15. Upscale factor is the key knob — surfers are 10–20 px, so the
  frame is sliced into 192 px tiles fed at 768. Misses are dominated by prone
  paddlers. A bigger model (`yolo11x`) is *worse* on both axes.
- Classical background subtraction produced ~550–750 false blobs per frame and
  does not work; that code is retained only as a labelling aid.

| module | purpose |
|---|---|
| `capture.py` | pull a live HLS stream to a local `.ts` file |
| `frames.py` | decode `.ts` to JPEG frames at a fixed interval |
| `motion.py` | track pan, segment the tour into MOVE / DWELL |
| `mosaic.py` | stitch presets into the reference panorama |
| `project.py` | panorama pixels → world metres, with error analysis |
| `detect.py` | classical candidate proposals for labelling (**not** a detector) |
| `yolo_detect.py` | tiled zero-shot YOLO detection |
| `eval_detector.py` | scores detections against `groundtruth.json` |
