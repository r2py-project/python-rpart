# Conversion Guide: `sqrt` (R to Python)

---

## 1. Overview of `sqrt` in R

`sqrt(x)` computes the non-negative square root of each element in `x`.

- **Input:** A numeric scalar or numeric vector (and by extension any object that can be coerced to numeric).
- **Output:** A numeric scalar or numeric vector of the same length as `x`, where each element is the square root of the corresponding input element. If an element is negative, the result is `NaN` (with a warning).
- **Vectorization:** `sqrt` is fully vectorized in R: passing a vector returns a vector of the same shape without any explicit loop.
- **Special values:** `sqrt(Inf)` returns `Inf`; `sqrt(0)` returns `0`; `sqrt(NaN)` returns `NaN`.

---

## 2. Contextual Usage Analysis

Across the five call sites in the rpart source the function is used in two distinct roles:

### Role A — Vector-valued geometric-mean scaling of CP sequences (3 occurrences)

Both `plotcp` and `xpred.rpart` compute a geometric-mean sequence from the complexity-parameter (CP) table:

```r
# plotcp.R line 17
cp <- sqrt(cp0 * c(Inf, cp0[-length(cp0)]))

# xpred.rpart.R line 63
cp <- sqrt(cp * c(10, cp[-length(cp)]))
```

In both cases the argument to `sqrt` is an element-wise product of two numeric vectors of the same length. The return value is a numeric vector of equal length used subsequently as axis tick labels or passed to downstream C routines. `Inf` (or the scalar `10`) is prepended to create a "sentinel" for the first element of the geometric-mean sequence.

### Role B — Vector-valued residual computation (2 occurrences)

Inside `residuals.rpart`, `sqrt` appears in the denominators and radicands of Pearson and deviance residual formulas for Poisson/survival data:

```r
# residuals.rpart.R line 38  (Pearson residual)
pearson = (events - expect) / sqrt(temp)

# residuals.rpart.R line 40  (deviance residual)
deviance = sign(events - expect) *
    sqrt(2 * (events * log(events/temp) - (events - expect)))
```

`temp` and `events` are both numeric vectors (one row per observation). The `sqrt` call therefore operates element-wise over all observations at once.

### Role C — Scalar geometric constant (1 occurrence)

In `text.rpart`, `sqrt(2)` is used to compute the semi-axes of the smallest oval that circumscribes a given bounding rectangle:

```r
# text.rpart.R line 89
oval(xy$x[i], xy$y[i], sqrt(2) * a.length / 2, sqrt(2) * b.length / 2)
```

The argument `2` is a plain numeric scalar. The result is also a scalar.

---

## 3. Python Conversion Strategy

**Primary equivalent: `numpy.sqrt`**

Because the dominant usage pattern in this codebase is element-wise application over numeric vectors (NumPy arrays), `numpy.sqrt` is the correct and idiomatic replacement in all cases:

- It is fully vectorized, matching R's implicit vectorization.
- It handles `numpy.inf` and `numpy.nan` in exactly the same way as R handles `Inf` and `NaN`.
- For the single scalar call `sqrt(2)` in `text.rpart`, `numpy.sqrt(2)` returns a NumPy scalar that behaves identically to Python's `math.sqrt(2)` in arithmetic expressions, so no special treatment is needed.

`math.sqrt` from the standard library is intentionally avoided because it does not accept arrays and would require an explicit loop when operating on vectors.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Geometric-mean scaling of a CP vector (Role A)

**Locations:**
- `plotcp.R`, function `plotcp`, line 17
- `xpred.rpart.R`, function `xpred.rpart`, line 63

**Original R Context:**

`cp0` / `cp` is a 1-D numeric vector extracted from an `rpart` CP table column. The call constructs a shifted copy of the vector (with a sentinel prepended) and takes element-wise square roots to produce a geometric-mean sequence.

```r
# plotcp.R — geometric mean with Inf sentinel
cp0 <- p.rpart[, 1L]                        # numeric vector, length n
cp  <- sqrt(cp0 * c(Inf, cp0[-length(cp0)]))  # numeric vector, length n

# xpred.rpart.R — geometric mean with scalar 10 sentinel
cp <- fit$cptable[, 1L]                     # numeric vector, length n
cp <- sqrt(cp * c(10, cp[-length(cp)]))     # numeric vector, length n
cp[1L] <- (1 + fit$cptable[1L, 1L]) / 2    # override first element
```

**Python Equivalent:**

```python
import numpy as np

# --- plotcp equivalent ---
cp0 = p_rpart[:, 0]                               # 1-D numpy array, length n
cp  = np.sqrt(cp0 * np.concatenate([[np.inf], cp0[:-1]]))

# --- xpred.rpart equivalent ---
cp = fit_cptable[:, 0]                            # 1-D numpy array, length n
cp = np.sqrt(cp * np.concatenate([[10.0], cp[:-1]]))
cp[0] = (1 + fit_cptable[0, 0]) / 2              # override first element
```

**Explanation:**
- R's `c(Inf, cp0[-length(cp0)])` prepends `Inf` and drops the last element. The NumPy equivalent is `np.concatenate([[np.inf], cp0[:-1]])`. Note the zero-based slice `[:-1]` replaces R's `[-length(cp0)]`.
- R's `c(10, cp[-length(cp)])` is analogous; replace `np.inf` with `10.0`.
- `np.sqrt` operates element-wise on the resulting array, matching R's vectorized `sqrt`.
- Column indexing uses `[:, 0]` in Python (zero-based) versus `[, 1L]` in R (one-based).

---

### 4.2 Pearson residual denominator (Role B — line 38)

**Location:**
- `residuals.rpart.R`, function `residuals.rpart`, line 38

**Original R Context:**

`temp` is a numeric vector produced by `ifelse(expect == 0, 0.0001, 0)` (a failsafe to avoid `log(0)`), and `events` / `expect` are numeric vectors of the same length (one entry per observation).

```r
temp   <- ifelse(expect == 0, 0.0001, 0)   # numeric vector, length n
pearson <- (events - expect) / sqrt(temp)  # numeric vector, length n
```

**Python Equivalent:**

```python
import numpy as np

temp    = np.where(expect == 0, 0.0001, 0.0)      # 1-D numpy array, length n
pearson = (events - expect) / np.sqrt(temp)        # 1-D numpy array, length n
```

**Explanation:**
- R's `ifelse` is replaced by `np.where`, which has the same three-argument structure: `(condition, value_if_true, value_if_false)`.
- `np.sqrt(temp)` computes the element-wise square root over the array, matching R's vectorized behavior.
- Division by `np.sqrt(temp)` is also element-wise because both operands are arrays of the same shape.

---

### 4.3 Deviance residual radicand (Role B — line 40)

**Location:**
- `residuals.rpart.R`, function `residuals.rpart`, line 40

**Original R Context:**

All variables (`events`, `expect`, `temp`) are numeric vectors. The expression computes the signed deviance residual for Poisson/survival data.

```r
deviance <- sign(events - expect) *
    sqrt(2 * (events * log(events / temp) - (events - expect)))
```

**Python Equivalent:**

```python
import numpy as np

deviance = np.sign(events - expect) * \
    np.sqrt(2 * (events * np.log(events / temp) - (events - expect)))
```

**Explanation:**
- R's `sign()` maps directly to `np.sign()`, which is likewise element-wise over arrays.
- R's `log()` maps to `np.log()`.
- `np.sqrt` takes the entire scalar-multiplied vector expression as its argument, producing a vector result. All arithmetic operators (`*`, `-`, `/`) are also element-wise on NumPy arrays, so no structural changes are needed beyond swapping the function names.

---

### 4.4 Scalar geometric constant (Role C)

**Location:**
- `text.rpart.R`, function `text.rpart`, line 89

**Original R Context:**

`sqrt(2)` is a compile-time numeric constant used to scale the semi-axes of an oval so that it exactly circumscribes the bounding rectangle of a label. `a.length` and `b.length` are Python scalars (floats).

```r
oval(xy$x[i], xy$y[i], sqrt(2) * a.length / 2, sqrt(2) * b.length / 2)
```

**Python Equivalent:**

```python
import numpy as np

# Option 1: numpy (preferred for consistency with the rest of the codebase)
SQRT2 = np.sqrt(2)
oval(xy_x[i], xy_y[i], SQRT2 * a_length / 2, SQRT2 * b_length / 2)

# Option 2: math (acceptable for a pure scalar context)
import math
SQRT2 = math.sqrt(2)
oval(xy_x[i], xy_y[i], SQRT2 * a_length / 2, SQRT2 * b_length / 2)
```

**Explanation:**
- Both `np.sqrt(2)` and `math.sqrt(2)` return the same floating-point constant (`1.4142135623730951`).
- `numpy.sqrt` is preferred in this codebase for uniformity; the NumPy scalar participates normally in all subsequent float arithmetic.
- Because this is a scalar expression and no vectorization is needed, either option is functionally correct.
