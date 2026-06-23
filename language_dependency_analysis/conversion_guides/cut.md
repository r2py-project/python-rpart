# Conversion Guide: `cut` (R to Python)

---

## 1. Overview of `cut` in R

`cut` is a base R function that converts a continuous numeric vector into a categorical factor by dividing its range into intervals defined by a set of breakpoints.

**Signature:**
```r
cut(x, breaks, labels = NULL, include.lowest = FALSE, right = TRUE,
    dig.lab = 3L, ordered_result = FALSE, ...)
```

**Key parameters:**
- `x`: A numeric vector of values to be binned.
- `breaks`: A numeric vector of two or more unique cut points (bin edges) in increasing order, or a single integer specifying the number of equal-width intervals to create.
- `labels`: Optional character vector of labels for the resulting factor levels. When `NULL` (default), labels are generated automatically as interval notation strings such as `"(a,b]"`. When `FALSE`, integer codes are returned directly instead of a factor.
- `include.lowest`: Logical. When `TRUE`, the leftmost interval is closed on both sides, i.e., `[a,b]` rather than `(a,b]` for the first bin. This ensures the minimum value of `x` (if equal to the first break) is assigned to the first bin rather than becoming `NA`. Default is `FALSE`.
- `right`: Logical. When `TRUE` (default), intervals are closed on the right and open on the left: `(a, b]`. When `FALSE`, they are closed on the left and open on the right: `[a, b)`.

**Return value:** By default, a `factor` whose levels correspond to the intervals. Values that fall outside the range of `breaks` are assigned `NA`. When `labels = FALSE`, an integer vector of bin indices (1-based) is returned instead.

---

## 2. Contextual Usage Analysis

Both usages appear inside the nested function `drate2` within `rpart.exp` in `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.exp.R`.

The purpose of `drate2` is to compute a piecewise-constant empirical hazard rate over a set of user-defined time intervals (`itable`). The function processes survival data where each observation has an event/censoring time (`time`) and optionally a start time (`stime` when `ny == 3L` for interval-censored data).

**Pattern:** In both usages, `cut` is immediately wrapped in `unclass()`:
```r
unclass(cut(time, itable, include.lowest = TRUE))
```
`unclass()` strips the factor class from the result and returns a plain 1-based integer vector of bin indices. This integer index is then used directly for numeric subscripting into `itable`:
```r
itime <- time - itable[index]
```

**Arguments used:**
- `x` is always a numeric vector (`time` or `stime`) — never a scalar.
- `breaks` is `itable`, a numeric vector of interval boundaries constructed as `c(0, dtimes[-length(dtimes)], max(time))`.
- `include.lowest = TRUE` is always set, because `itable[1]` is `0` and observation times can equal the first break exactly (e.g., `time == 0` edge cases are excluded upstream, but `stime` can equal `0`).
- `right` is not specified, so the default `TRUE` applies: intervals are left-open, right-closed `(a, b]`, except the first which becomes `[a, b]` due to `include.lowest = TRUE`.
- `labels` is not specified (defaults to `NULL`), but the factor label strings are never used — only the integer codes from `unclass()` matter.

**Recurring pattern summary:** The entire idiom `unclass(cut(x, breaks, include.lowest = TRUE))` is used to assign each element of a numeric vector to a 1-based interval index, where intervals are right-closed and the first interval includes its left boundary.

---

## 3. Python Conversion Strategy

The chosen Python equivalent is **`numpy.digitize`** from the `numpy` library.

**Rationale:**
- `numpy.digitize(x, bins, right)` operates natively on NumPy arrays, matching R's vectorized semantics exactly.
- It returns a 1-based integer array of bin indices directly, which mirrors the output of `unclass(cut(...))` without any extra step to extract integer codes.
- The `right=True` parameter makes intervals right-closed `(a, b]`, matching R's `cut` default of `right = TRUE`.
- Handling of `include.lowest = TRUE` (i.e., including the minimum break in the first bin) can be reproduced with a single post-processing clamp, as detailed below.
- `pandas.cut` is a closer semantic match to R's `cut` (returning a `Categorical` with interval labels), but it adds unnecessary overhead when only integer bin indices are needed. Since the R code always calls `unclass()` to discard the factor and work only with integer codes, `numpy.digitize` is more direct and efficient.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Binning end-times (`time`) — line 64

**Locations:** `rpart/R/rpart.exp.R`, function `drate2`

**Original R context:**

```r
# itable: numeric vector of interval boundaries, e.g. c(0, t1, t2, ..., tmax)
# time:   numeric vector (one entry per observation) of event/censoring times
#         All values satisfy: itable[1] <= time[i] <= itable[length(itable)]

index <- unclass(cut(time, itable, include.lowest = TRUE))
# index: integer vector, 1-based, same length as time.
# index[i] == k  means  itable[k] < time[i] <= itable[k+1]
# For time[i] == itable[1] (the minimum break), include.lowest=TRUE
# forces index[i] == 1 rather than NA.

itime <- time - itable[index]
# itime[i]: time elapsed within interval k since its left boundary itable[k]
```

Input types:
- `time`: `numeric` vector of length `n` (number of observations).
- `itable`: `numeric` vector of interval breakpoints of length `ngrp + 1`.

Return type of `unclass(cut(...))`:
- `integer` vector of length `n`, values in `1..ngrp`.

**Python equivalent:**

```python
import numpy as np

# itable: 1-D numpy array of interval boundaries, shape (ngrp + 1,)
# time:   1-D numpy array of observation end-times, shape (n,)

# numpy.digitize with right=True gives right-closed intervals (a, b],
# matching R's cut default.  It returns 1-based indices: index[i] == k means
# itable[k-1] < time[i] <= itable[k].
index = np.digitize(time, itable, right=True)

# Reproduce include.lowest=TRUE: clamp index to 1 so that time[i] == itable[0]
# (which digitize assigns to bin 0, meaning "below all breaks") maps to bin 1.
index = np.clip(index, 1, len(itable) - 1)

# Use 0-based subscripting: itable[index - 1] is the left boundary of bin index.
# This corresponds to R's itable[index] (1-based).
itime = time - itable[index - 1]
```

**Explanation:**

| R | Python | Notes |
|---|--------|-------|
| `cut(time, itable, ...)` | `np.digitize(time, itable, right=True)` | Both bin a numeric array against explicit breakpoints. `right=True` matches R's default right-closed intervals. |
| `unclass(...)` | (no extra step needed) | `np.digitize` returns integer indices directly; no factor to unwrap. |
| `include.lowest = TRUE` | `np.clip(index, 1, len(itable) - 1)` | R's `include.lowest` forces the leftmost break into bin 1. `np.digitize` returns `0` for values equal to `itable[0]` (below the first right-closed boundary), so clamping to `1` reproduces this. |
| `itable[index]` (1-based) | `itable[index - 1]` (0-based) | NumPy arrays are 0-indexed; subtract 1 to convert the 1-based bin number to a 0-based array index. |

---

### 4.2 Binning start-times (`stime`) — line 71

**Locations:** `rpart/R/rpart.exp.R`, function `drate2`

**Original R context:**

```r
# Only executed when ny == 3L (interval-censored survival data with start times)
stime <- y[, 1L]   # start time for each observation
index2 <- unclass(cut(stime, itable, include.lowest = TRUE))
itime2 <- stime - itable[index2]
```

This usage is structurally identical to 4.1. The only difference is the input vector: `stime` (start times) instead of `time` (end times). The same `itable` breakpoints are used and the same `include.lowest = TRUE` flag applies.

Input types:
- `stime`: `numeric` vector of length `n`.
- `itable`: same breakpoint array as in 4.1.

**Python equivalent:**

```python
import numpy as np

# stime: 1-D numpy array of observation start-times, shape (n,)
# itable: same 1-D numpy array of interval boundaries as in section 4.1

index2 = np.digitize(stime, itable, right=True)
index2 = np.clip(index2, 1, len(itable) - 1)

itime2 = stime - itable[index2 - 1]
```

**Explanation:**

The translation is identical to section 4.1. The conversion pattern `np.digitize(..., right=True)` followed by `np.clip(..., 1, len(itable) - 1)` is a reusable idiom for the full R expression `unclass(cut(x, itable, include.lowest = TRUE))` whenever:
- `itable` is a sorted numeric vector of explicit breakpoints.
- `include.lowest = TRUE` is set (left boundary of first interval is included).
- `right = TRUE` (default) is in effect (intervals are right-closed).
- Only the integer bin indices are needed (the factor labels are not used).
