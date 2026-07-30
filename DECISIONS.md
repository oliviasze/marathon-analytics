## Modeling approach: two iterations

### Attempt 1: Per-run Riegel-implied regression (model.py)
Extrapolated each training run's own pace to marathon distance via Riegel,
used engineered features (HR efficiency, mileage trend, elevation) to
predict this per-run target via ridge regression.

Issues found along the way:
- Data leakage: an early feature was built from the same run it was
  predicting, artificially inflating apparent accuracy (78% "improvement"
  over baseline was not real).
- Target contamination: including easy/recovery runs as regression
  targets systematically biased predictions slow, since Riegel assumes
  race effort and easy pace isn't race effort.
- Extrapolation ratio: short fast efforts (e.g. a 3-mile tempo run)
  extrapolated to marathon distance via Riegel are far less reliable
  than long runs closer to race distance.

Fixed by restricting targets to "quality effort" runs only (long runs, or
relatively fast efforts meeting a distance floor) — improved from a
misleading 78% to a more defensible ~55% MAE improvement over baseline,
but predictions still ran slower than my own subjective fitness read.

### Attempt 2: Half-marathon-anchored trend (trend_analysis.py)
Pivoted to anchor on an actual known result (half marathon, Feb 1, 1:34:49)
rather than synthesizing targets from training runs. Computed a rolling
pace-per-heartbeat efficiency metric (SQL window function), compared a
14-day window around the half to a current 14-day window, scaled the
actual half time by the efficiency change, then applied Riegel purely
for the distance conversion.

This produced a more defensible and more believable projection
(~3:15, vs. a plain unadjusted Riegel extrapolation of ~3:18 from the
same half — a small, credible gap rather than a large, suspicious one).