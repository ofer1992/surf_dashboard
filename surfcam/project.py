"""Map panorama pixels to real-world sea-surface coordinates.

The projection is deliberately split in two, because the two halves have very
different lifetimes:

    live frame  --H_pose-->  panorama  --H_sea-->  world (metres, sea level)

`H_pose` changes every time the camera moves. It is re-estimated automatically
per frame from rigid land features (see motion.py). It is exact rather than
approximate because the camera rotates about its optical centre: for a pure
rotation the image-to-image map is a homography for *all* scene points,
however far away, so there is no depth or parallax term to model.

`H_sea` is fixed and is calibrated once by hand. The sea surface is a plane,
and the map from a plane to its image is a homography, so four correspondences
between panorama pixels and known real-world points at sea level determine it.

Splitting this way means the expensive, manual part (geo-referencing) is done
once against a static mosaic, and every frame inherits it for free.

Calibration landmarks visible from this camera, in rough order of usefulness:
    * the breakwater's outer corner and its beacon
    * the root of the breakwater where it meets the shore
    * groyne tips along the beach
    * fixed shoreline structures (the lifeguard tower base)
Read their coordinates off satellite imagery (OSM/Google), convert to a local
metric frame (UTM 36N for Israel), and pair them with their panorama pixels.
Prefer points spread widely in both range and bearing; four near-collinear
points along the shoreline will give a badly conditioned fit.

Two things to get right when using the result:

    * Use a surfer's *waterline* (the bottom of the detection box), not its
      centroid. The homography is only valid for points at z=0. A surfer
      standing 1.5 m above the water back-projects as if they were many metres
      further out.
    * Report the local ground resolution with every position. Near the
      horizon the view is grazing, so one pixel spans a large ground distance
      and positions there are close to meaningless. `ground_resolution`
      quantifies this, and `usable_mask` thresholds it.
"""
from __future__ import annotations

import numpy as np

Array = np.ndarray


def fit_sea_homography(image_pts: Array, world_pts: Array) -> Array:
    """Least-squares homography from panorama pixels to world metres (z=0).

    `image_pts` and `world_pts` are (N,2) arrays of corresponding points, N>=4.
    """
    image_pts = np.asarray(image_pts, float)
    world_pts = np.asarray(world_pts, float)
    if image_pts.shape != world_pts.shape or image_pts.shape[0] < 4:
        raise ValueError("need matching (N,2) arrays with N >= 4")

    # Direct linear transform. Normalising both point sets first is what keeps
    # the system well conditioned when pixel and metre scales differ wildly.
    Ti, ni = _normalise(image_pts)
    Tw, nw = _normalise(world_pts)

    rows = []
    for (x, y), (X, Y) in zip(ni, nw):
        rows.append([-x, -y, -1, 0, 0, 0, X * x, X * y, X])
        rows.append([0, 0, 0, -x, -y, -1, Y * x, Y * y, Y])
    _, _, Vt = np.linalg.svd(np.asarray(rows))
    H = Vt[-1].reshape(3, 3)

    H = np.linalg.inv(Tw) @ H @ Ti
    return H / H[2, 2]


def _normalise(pts: Array) -> tuple[Array, Array]:
    """Translate to centroid and scale to mean distance sqrt(2) (Hartley)."""
    c = pts.mean(axis=0)
    d = np.linalg.norm(pts - c, axis=1).mean()
    s = np.sqrt(2) / d if d > 0 else 1.0
    T = np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])
    return T, (pts - c) * s


def apply(H: Array, pts: Array) -> Array:
    """Apply a homography to (N,2) points."""
    pts = np.asarray(pts, float).reshape(-1, 2)
    h = np.hstack([pts, np.ones((len(pts), 1))]) @ H.T
    return h[:, :2] / h[:, 2:3]


def image_to_world(H_sea: Array, H_pose: Array, pts: Array) -> Array:
    """Frame pixels -> world metres, via the panorama.

    `H_pose` maps this frame into the panorama; `H_sea` maps the panorama to
    the world. Pass the detection *waterline*, not its centroid.
    """
    return apply(H_sea @ H_pose, pts)


def reprojection_error(H: Array, image_pts: Array, world_pts: Array) -> Array:
    """Per-landmark residual in world units. The honest check on a calibration."""
    return np.linalg.norm(apply(H, image_pts) - np.asarray(world_pts, float), axis=1)


def ground_resolution(H_sea: Array, pts: Array) -> Array:
    """Metres of ground covered per pixel, at each point.

    This is the local Jacobian's larger singular value, so it reports the worst
    direction. It grows without bound towards the horizon, which is why
    positions far offshore carry huge uncertainty even with a perfect fit.
    """
    pts = np.asarray(pts, float).reshape(-1, 2)
    out = np.empty(len(pts))
    for i, (x, y) in enumerate(pts):
        base = apply(H_sea, [[x, y]])[0]
        dx = apply(H_sea, [[x + 1, y]])[0] - base
        dy = apply(H_sea, [[x, y + 1]])[0] - base
        out[i] = np.linalg.svd(np.column_stack([dx, dy]), compute_uv=False)[0]
    return out


def usable_mask(H_sea: Array, pts: Array, max_m_per_px: float = 2.0) -> Array:
    """Boolean mask of points whose ground resolution is good enough to trust."""
    return ground_resolution(H_sea, pts) <= max_m_per_px


def _self_test() -> None:
    """Round-trip the maths on a synthetic camera, so the algebra is checked
    even before real landmark coordinates exist."""
    rng = np.random.default_rng(0)
    world = np.array([[0.0, 0.0], [300.0, 0.0], [300.0, 200.0],
                      [0.0, 200.0], [150.0, 90.0], [40.0, 170.0]])
    true_H = np.array([[2.4, 0.7, 900.0],
                       [0.1, 1.9, 400.0],
                       [0.0003, 0.0016, 1.0]])
    img = apply(np.linalg.inv(true_H), world)  # world -> pixels

    H = fit_sea_homography(img, world)
    err = reprojection_error(H, img, world)
    assert err.max() < 1e-6, err
    print(f"exact fit: max reprojection error {err.max():.2e} m")

    noisy = img + rng.normal(0, 0.5, img.shape)
    Hn = fit_sea_homography(noisy, world)
    print(f"with 0.5px landmark noise: max error {reprojection_error(Hn, noisy, world).max():.2f} m")

    res = ground_resolution(H, img)
    for (x, y), r in zip(img, res):
        print(f"  pixel ({x:7.1f},{y:7.1f}) -> {r:6.2f} m/px")
    print("self-test ok")


if __name__ == "__main__":
    _self_test()
