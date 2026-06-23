# Conversion Guide: `range` (R to Python)

---

## 1. Overview of `range` in R

`range()` is a base R function that returns a numeric vector of length 2 containing the **minimum** and **maximum** values of its input, in that order.

**Signature:**
```r
range(..., na.rm = FALSE)
```

**Typical behaviour:**
- Accepts one or more numeric vectors (or objects coercible to numeric).
- Returns `c(min(x), max(x))` as a named numeric vector of length 2.
- When `na.rm = TRUE`, `NA` values are stripped before computing the extremes; otherwise a single `NA` in the input propagates to both elements of the result.
- Because R vectorises arithmetic, the returned two-element vector participates naturally in subsequent operations such as `diff(range(x))` (total span) or `range(x) + scalar * c(-1, 1)` (symmetric expansion).

---

## 2. Contextual Usage Analysis

All five CSV rows reduce to two functionally distinct call patterns, both found within tree-plotting utilities of the rpart package.

### Pattern A — margin expansion (lines 19 and 20 of `plot.rpart.R`)

```r
temp1 <- range(xx) + diff(range(xx)) * c(-margin, margin)
temp2 <- range(yy) + diff(range(yy)) * c(-margin, margin)
```

`xx` and `yy` are numeric vectors of node x- and y-coordinates produced by `rpartco()`. The expression:
1. Computes `[min, max]` of the coordinate vector.
2. Computes the total span with `diff(range(...))` — equivalent to `max - min`.
3. Subtracts `margin * span` from the minimum and adds `margin * span` to the maximum, symmetrically widening the plot axis limits.

The result is a two-element numeric vector used directly as axis limits in the subsequent `plot()` call.

### Pattern B — fudge factor scaling (line 43 of `rpartco.R`)

```r
fudge <- minbranch * diff(range(y)) / max(depth)
```

`y` is a numeric vector of deviance-derived y-coordinates for every node in the tree. `range(y)` is used purely as an intermediate inside `diff()` to obtain the total vertical span of the coordinate system. The scalar result scales a minimum branch-length threshold (`minbranch`) by that span and the maximum tree depth.

**Recurring types:** In every occurrence `range()` receives a plain numeric vector and produces a length-2 numeric vector. No `na.rm` argument is passed, so the default (`FALSE`) applies throughout.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

R's `range()` inherently operates element-wise over an entire vector and returns an array-like pair. `numpy` is the direct equivalent for this style of computation:

- `np.min(x)` and `np.max(x)` operate on `ndarray` inputs of any size, matching R's vectorised semantics exactly.
- Combining them as `np.array([np.min(x), np.max(x)])` reproduces the length-2 result that participates in subsequent vectorised arithmetic.
- `np.ptp(x)` (peak-to-peak) is the one-call equivalent of `diff(range(x))` — it returns `max - min` as a scalar, matching `diff()` applied to a two-element vector.
- Using `math.min` / `math.max` would require scalar inputs and cannot operate on arrays, so `numpy` is the only appropriate choice here.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Symmetric margin expansion of axis limits

**Locations:**
- `plot.rpart.R`, function `plot.rpart`, lines 19 and 20

**Original R Context:**

`xx` and `yy` are numeric vectors (`double`) holding node coordinates. `margin` is a scalar `double` (default `0`). The result is a length-2 numeric vector used as axis limits.

```r
# R
temp1 <- range(xx) + diff(range(xx)) * c(-margin, margin)
temp2 <- range(yy) + diff(range(yy)) * c(-margin, margin)
```

**Python Equivalent:**

```python
import numpy as np

# xx and yy are numpy arrays of node coordinates; margin is a float scalar

temp1 = np.array([np.min(xx), np.max(xx)]) + np.ptp(xx) * np.array([-margin, margin])
temp2 = np.array([np.min(yy), np.max(yy)]) + np.ptp(yy) * np.array([-margin, margin])
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `range(xx)` | `np.array([np.min(xx), np.max(xx)])` | Returns a 1-D array of length 2, matching R's two-element vector. |
| `diff(range(xx))` | `np.ptp(xx)` | `np.ptp` (peak-to-peak) computes `max - min` in one call, identical to R's `diff()` on a length-2 range vector. |
| `c(-margin, margin)` | `np.array([-margin, margin])` | R's `c()` becomes a numpy array for element-wise arithmetic. |
| Vectorised `+` and `*` | Numpy broadcasting | Both sides are arrays of the same length; numpy broadcasts the scalar `np.ptp(xx)` automatically. |

When `margin = 0` (the default), both expressions reduce to `np.array([np.min(x), np.max(x)])`, identical to the plain `range(x)` result.

---

### 4.2 Pattern B — Scalar span for fudge factor

**Locations:**
- `rpartco.R`, function `rpartco`, line 43

**Original R Context:**

`y` is a numeric vector (`double`) of deviance-based y-coordinates for every tree node. `minbranch` is a scalar `double` (default `0.3`). `depth` is an integer vector of node depths. The result `fudge` is a scalar `double`.

```r
# R
fudge <- minbranch * diff(range(y)) / max(depth)
```

**Python Equivalent:**

```python
import numpy as np

# y is a numpy array of node y-coordinates
# minbranch is a float scalar; depth is a numpy array of integer depths

fudge = minbranch * np.ptp(y) / np.max(depth)
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `range(y)` | (implicit inside `np.ptp`) | Not materialised separately; `np.ptp(y)` directly yields `max(y) - min(y)`. |
| `diff(range(y))` | `np.ptp(y)` | Computes the total span of `y` as a single scalar. |
| `max(depth)` | `np.max(depth)` | `depth` is a numpy integer array; `np.max` returns a scalar. |
| Scalar arithmetic | Standard Python `*` and `/` | All operands are scalars at this point, so no special broadcasting is needed. |

`np.ptp` is preferred over the two-step `np.max(y) - np.min(y)` because it is a direct semantic match for `diff(range(y))` and keeps the expression concise. Note that `np.ptp` was deprecated in NumPy 2.0; for codebases targeting NumPy 2+, replace it with the explicit `np.max(y) - np.min(y)`.
