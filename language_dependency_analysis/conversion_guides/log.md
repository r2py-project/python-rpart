# Conversion Guide: `log` (R to Python)

---

## 1. Overview of `log` in R

`log(x, base = exp(1))` computes logarithms of its argument `x`.

- **Default behaviour:** when `base` is omitted, it computes the **natural logarithm** (base *e*), equivalent to `ln(x)`.
- **Custom base:** when `base` is supplied explicitly (e.g. `base = 2`), it computes the logarithm in that base, implemented internally as `log(x) / log(base)`.
- **Vectorized:** `x` may be a scalar or any length vector/array; the result has the same shape as `x`.
- **Return type:** a numeric scalar or numeric vector of the same length/dimensions as `x`.
- **Domain:** `x` must be positive; `log(0)` returns `-Inf` with a warning; negative values return `NaN`.

---

## 2. Contextual Usage Analysis

Four call sites appear across two source files, falling into two functionally distinct patterns.

**Pattern A — natural logarithm (default base), operating on numeric vectors**

Both occurrences are inside the `poisson`/`exp` residual branch of `residuals.rpart`, where `y` and `frame` hold per-observation data, making every operand a numeric vector of length equal to the number of observations.

- `log(yhat)` (line 28): `yhat` is a per-observation probability vector extracted from `frame$yval2`; the call appears inside a `deviance` residual formula `-2 * log(yhat)`.
- `log(events/temp)` (line 40): both `events` (count vector from `y[, 2L]`) and `temp` (a failsafe replacement of zero expected counts) are observation-length numeric vectors; the result feeds into the deviance computation `events * log(events/temp) - (events - expect)`.

**Pattern B — base-2 logarithm, operating on integer node-index vectors**

Both calls use `base = 2` to convert binary-tree node indices into tree depths. In rpart, node indices are integers stored in a specific doubling scheme (root = 1, children of node *k* are *2k* and *2k+1*), so `floor(log(nodes, base = 2))` gives the zero-based depth level of each node.

- `tree.depth` (line 7): `nodes` is the integer vector `object$frame$nodes` (one entry per frame row); the result, after subtracting its minimum, becomes the relative depth of each node.
- `descendants` (line 43): same node-index integer vector; `lev` is used to iterate over levels from the deepest back to the root.

**Recurring pattern:** in both R files, `log` is always called on a vector (never a bare scalar), so a vectorized Python replacement is mandatory.

---

## 3. Python Conversion Strategy

`numpy.log` and `numpy.log2` are the correct replacements.

- `numpy.log` computes the **natural logarithm** element-wise over any array-like input, matching R's default `log(x)` behaviour exactly.
- `numpy.log2` computes the **base-2 logarithm** element-wise, matching R's `log(x, base = 2)` exactly and more efficiently than the general `numpy.log(x) / numpy.log(2)` formulation.
- Both functions accept NumPy arrays, Python lists, and scalars, preserving vectorization.
- `math.log` is **not** suitable here because it operates on Python scalars only and would require an explicit loop over vectors.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Natural logarithm on a probability vector — `log(yhat)`

**Locations:** `residuals.rpart.R`, function `residuals.rpart`, line 28.

**Original R context**

```r
# yhat  : numeric vector, per-observation predicted class probability (0 < yhat <= 1)
# result: numeric vector of the same length, used in the deviance residual formula

deviance = -2 * log(yhat)
```

`yhat` is sliced from a matrix of class probabilities; it is always a numeric vector whose length equals the number of observations. `log` returns a vector of the same length.

**Python equivalent**

```python
import numpy as np

# yhat: np.ndarray of shape (n_obs,), dtype float64, values in (0, 1]
deviance = -2.0 * np.log(yhat)
# result: np.ndarray of shape (n_obs,), dtype float64
```

**Explanation**

- `np.log` is the element-wise natural logarithm, directly equivalent to R's default `log`.
- The scalar multiplier `-2` broadcasts over the array identically to R's vectorized arithmetic.
- No argument mapping is needed: both R's `log(x)` and `np.log(x)` use base *e* by default.

---

### 4.2 Natural logarithm on a ratio of count vectors — `log(events/temp)`

**Locations:** `residuals.rpart.R`, function `residuals.rpart`, line 40.

**Original R context**

```r
# events : numeric vector, observed event counts per observation
# temp   : numeric vector, expected event counts (zeros replaced by 0.0001 as failsafe)
# result : numeric vector, used inside the deviance formula

deviance = sign(events - expect) *
    sqrt(2 * (events * log(events / temp) - (events - expect)))
```

`events / temp` is element-wise division of two equal-length numeric vectors, and `log` is applied to the resulting ratio vector.

**Python equivalent**

```python
import numpy as np

# events : np.ndarray, shape (n_obs,), dtype float64, observed counts
# expect : np.ndarray, shape (n_obs,), dtype float64, expected counts (lambda * time)
# failsafe: replace zeros in expect to avoid log(0)
temp = np.where(expect == 0, 0.0001, expect)

deviance = np.sign(events - expect) * np.sqrt(
    2.0 * (events * np.log(events / temp) - (events - expect))
)
# result: np.ndarray, shape (n_obs,), dtype float64
```

**Explanation**

- `np.log` operates element-wise on the ratio array `events / temp`, matching R exactly.
- R's `ifelse(expect == 0, 0.0001, 0)` should be read carefully: in R that line sets `temp` to `0.0001` where `expect == 0` and to `0` elsewhere, then later `events/temp` uses `temp` as the denominator; in Python `np.where(expect == 0, 0.0001, expect)` replicates the intent of providing a safe non-zero divisor.
- `np.sign` and `np.sqrt` are the vectorized equivalents of R's `sign` and `sqrt`.

---

### 4.3 Base-2 logarithm on an integer node-index vector — `log(nodes, base = 2)`

**Locations:**
- `zzz.R`, function `tree.depth`, line 7.
- `zzz.R`, function `descendants`, line 43.

**Original R context**

```r
# nodes: integer vector of rpart node indices (root = 1, children of k are 2k and 2k+1)
# result: numeric vector of tree depth levels (0-based after subtracting minimum)

# tree.depth
depth <- floor(log(nodes, base = 2) + 1e-7)
depth - min(depth)

# descendants
lev <- floor(log(nodes, base = 2))
```

`nodes` is always an integer vector. `log(nodes, base = 2)` produces a floating-point vector of the same length. `floor` then converts each value to its integer depth level. The small additive constant `1e-7` in `tree.depth` guards against floating-point rounding causing exact powers of 2 to land just below an integer.

**Python equivalent**

```python
import numpy as np

# nodes: np.ndarray, shape (n_nodes,), dtype int or float

# tree.depth equivalent
depth = np.floor(np.log2(nodes) + 1e-7).astype(int)
depth = depth - depth.min()

# descendants equivalent
lev = np.floor(np.log2(nodes)).astype(int)
```

**Explanation**

- `np.log2(x)` is the dedicated base-2 logarithm function; it is equivalent to R's `log(x, base = 2)` and is preferred over `np.log(x) / np.log(2)` for clarity and minor numerical precision benefits.
- R's `floor` maps directly to `np.floor`; the result is kept as a float in NumPy, so `.astype(int)` converts it to an integer array matching the downstream integer arithmetic (array indexing, comparisons with `2L`).
- The `1e-7` guard translates unchanged into Python; its purpose is identical in both languages.
- R's `min(depth)` maps to `depth.min()` on a NumPy array, or equivalently `np.min(depth)`.
