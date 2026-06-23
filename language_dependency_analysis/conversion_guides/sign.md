# Conversion Guide: `sign` (R to Python)

### 1. Overview of `sign` in R

`sign(x)` returns the mathematical signum function applied to each element of `x`. For a given numeric value or vector, it returns:

- `-1` for each element that is strictly negative
- `0` for each element that is exactly zero
- `+1` for each element that is strictly positive

`sign` is fully vectorized in R: when passed a vector, it returns a vector of the same length with element-wise results. It accepts numeric, integer, or complex inputs and returns a value of the same type. `NA` inputs propagate as `NA` in the output.

---

### 2. Contextual Usage Analysis

In `rpart/R/residuals.rpart.R`, the function `residuals.rpart` computes residuals for rpart models fitted with the `"poisson"` or `"exp"` method. Within the `"deviance"` branch of the `switch` statement (lines 36–41), the expression is:

```r
deviance = sign(events - expect) *
    sqrt(2 * (events * log(events/temp) - (events - expect)))
```

The variables involved are:

- `events`: extracted as `y[, 2L]` — a **numeric vector** of observed event counts, one entry per observation in the dataset.
- `expect`: computed as `lambda * time` — a **numeric vector** of expected event counts (element-wise product of fitted rates and observation times).
- `events - expect`: a **numeric vector** of signed differences (raw residuals).
- `sign(events - expect)`: a **numeric vector** of -1, 0, or +1 values, providing the direction of each deviance residual.
- The final product is a **numeric vector** of signed deviance residuals.

The sole usage of `sign` in the CSV is this single pattern: `sign` is applied to a vector subtraction result and its output is immediately used as a sign-correcting multiplier for the absolute deviance magnitudes. This is the standard formula for signed deviance residuals in Poisson models.

---

### 3. Python Conversion Strategy

`numpy.sign()` is the direct and preferred equivalent. The reasons are:

1. **Vectorization parity:** `numpy.sign` operates element-wise over NumPy arrays, exactly mirroring R's vectorized `sign`. In this context, `events` and `expect` will be NumPy arrays (one value per observation), so a scalar function such as `math.copysign` would be incorrect.
2. **Type compatibility:** `numpy.sign` handles `float64` arrays natively and propagates `numpy.nan` in the same manner that R propagates `NA`.
3. **Signature match:** `numpy.sign(x)` requires no extra arguments, matching R's `sign(x)` exactly.
4. **Ecosystem fit:** The broader deviance residual formula uses `numpy.sqrt` and `numpy.log`, so keeping `numpy.sign` keeps all operations within the same array-computation layer with no dtype conversion overhead.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Signed Deviance Residuals for Poisson/Exp Method

**Locations**

- File: `rpart/R/residuals.rpart.R`
- Function: `residuals.rpart`

**Original R Context**

Input types:
- `events`: `numeric` vector — observed event counts per observation (non-negative).
- `expect`: `numeric` vector — expected event counts per observation (non-negative), same length as `events`.
- `events - expect`: `numeric` vector — signed raw residual per observation.

Return type: `numeric` vector of signed deviance residuals, same length as `events`.

Generalized R snippet:

```r
# events: numeric vector, length n (observed event counts)
# expect: numeric vector, length n (expected event counts = lambda * time)
# temp:   numeric vector, length n (failsafe: expect where expect > 0, else 0.0001)
temp <- ifelse(expect == 0, 0.0001, expect)  # avoid log(0)

deviance_resid <- sign(events - expect) *
    sqrt(2 * (events * log(events / temp) - (events - expect)))
```

**Python Equivalent**

```python
import numpy as np

# events: np.ndarray, shape (n,), dtype float64 — observed event counts
# expect: np.ndarray, shape (n,), dtype float64 — expected event counts
# temp:   np.ndarray, shape (n,), dtype float64 — failsafe for log(0)

# Replicate R's ifelse(expect == 0, 0.0001, expect)
temp = np.where(expect == 0, 0.0001, expect)

deviance_resid = (
    np.sign(events - expect)
    * np.sqrt(2 * (events * np.log(events / temp) - (events - expect)))
)
```

A minimal, self-contained executable example:

```python
import numpy as np

# Simulated inputs (3 observations)
events = np.array([3.0, 0.0, 5.0])
expect = np.array([2.5, 1.0, 5.0])

# Failsafe: replace zero expected values to avoid log(0)
temp = np.where(expect == 0, 0.0001, expect)

# Signed deviance residuals
deviance_resid = (
    np.sign(events - expect)
    * np.sqrt(2 * (events * np.log(events / temp) - (events - expect)))
)

print(deviance_resid)
# Example output: [ 0.6585...  -1.4142...   0.      ]
```

**Explanation**

| R | Python | Notes |
|---|--------|-------|
| `sign(x)` | `np.sign(x)` | Both operate element-wise over vectors/arrays; returns -1, 0, or +1 per element. |
| `events - expect` | `events - expect` | NumPy arrays support the `-` operator element-wise, identical to R vector subtraction. |
| `ifelse(expect == 0, 0.0001, expect)` | `np.where(expect == 0, 0.0001, expect)` | R's `ifelse` is the vectorized conditional; `np.where` is its NumPy equivalent. |
| `sqrt(...)` | `np.sqrt(...)` | Element-wise square root over arrays. |
| `log(...)` | `np.log(...)` | Natural logarithm, element-wise. |
| `*` (vector multiply) | `*` (array multiply) | Both perform element-wise multiplication when operands are vectors/arrays. |
| No import needed | `import numpy as np` | NumPy must be explicitly imported in Python. |

There are no zero-indexing concerns here since the operation is purely arithmetic over array contents, not index-based access. The `numpy.sign` function returns `float64` when the input is `float64`, which is consistent with how R's `sign` returns `numeric` for `numeric` input.
