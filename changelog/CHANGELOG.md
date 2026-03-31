# Changelog

## v0.9.0 — 2026-03-08
SOS two-stage pipeline — SOS-Detection + SOS-Classification (47 brands) replacing DA_YOLO11X

## v0.8.8 — 2026-03-08
Fix QPDS cls OOM — chunked inference with cache clearing between chunks to handle fragmented GPU memory

## v0.8.7 — 2026-03-05
Simplify store compliance — CSD==100 auto-passes; otherwise raw total compliance >= 80 threshold

## v0.8.6 — 2026-03-05
Add MAR26 POSM entries for Dove conditioner sachet hanger and Sunsilk triple sachet poster

## v0.8.5 — 2026-03-02
Fix planogram order for multiple shelf types (Lux, Prestige, Ponds, Haircare)

## v0.8.4 — 2026-03-02
Set `shelftalker_affects_success: false` for all shelf types in QPDS standards

## v0.8.3 — 2026-03-02
Fix inconsistent return values in `_detect_shelftalker_roi` causing unpack error

## v0.8.2 — 2026-03-01
Remove unused scikit-image and scipy from requirements

## v0.8.1 — 2026-03-01
Add scikit-learn, scikit-image, scipy to requirements

## v0.8.0 — 2026-03-01
Add vertical adjacency detection — haircare above/below skincare gets 4 legs, skincare gets 3 and shelftalker waived

## v0.7.5 — 2026-03-01
Fix POSM aggregation crash when planned item maps to multiple AI classes

## v0.7.4 — 2026-03-01
Refactor POSM standards to standard-name-keyed structure; add March QPDS rules; add POSM cap_visible_to_planned toggle

## v0.7.3 — 2026-02-27
Fix shelftalker_affects_success flag in QPDS standards

## v0.7.2 — 2026-02-25
Fix POSM duplicate YAML keys; add aliases support; add pyproject.toml + __version__

## v0.7.1 — 2026-02-25
Promote analyzer debug logs to info; add changelog infrastructure

## v0.7.0 — 2026-02-25
Initial version tracking. Project already in active development — see git log for pre-0.7.0 history.
