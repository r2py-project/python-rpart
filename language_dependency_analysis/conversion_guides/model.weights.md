# Conversion Guide: `model.weights` (R to Python)

---

### 1. Overview of `model.weights` in R

`model.weights` is a convenience extractor function from R's `stats` package. It retrieves the `"(weights)"` column from a **model frame** — the structured data object produced by `stats::model.frame()` after a formula has been evaluated against the supplied data.

**Signature:**
```r
model.weights(x)
```

- **Input:** `x` — a model frame (a `data.frame` subclass with a `"terms"` attribute and possibly a `"(weights)"` column).
- **Return value:** A numeric vector of per-observation case weights if a `weights` argument was supplied when building the model frame, or `NULL` if no weights were provided.

The function is essentially a thin wrapper equivalent to:
```r
attr(x, "weights")  # or equivalently:
x[["(weights)"]]
```

Its sole purpose is to give a named, readable way to pull the optional weights column out of a model frame, keeping the calling code independent of the internal column-naming convention `"(weights)"`.

**Key behaviors:**
- Returns `NULL` when no `weights` argument was passed to `model.frame()`.
- When weights are present they form a numeric vector of the same length as the number of rows in the model frame.
- Weights must be non-negative; rpart enforces this with an explicit guard immediately after calling `model.weights`.

---

### 2. Contextual Usage Analysis

**File:** `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`, function `rpart`, line 27.

The call appears inside the `rpart()` function immediately after the model frame `m` has been built:

```r
Y   <- model.response(m)    # line 26 – extract response variable
wt  <- model.weights(m)     # line 27 – extract optional case weights
if (any(wt < 0)) stop("negative weights not allowed")   # line 28
if (!length(wt)) wt <- rep(1, nrow(m))                  # line 29
offset <- model.offset(m)                               # line 30
```

**Pattern summary:**

| Aspect | Detail |
|---|---|
| Input type | A model frame (`data.frame`-like object, result of `stats::model.frame`) |
| Return type when weights supplied | Numeric vector, length = number of observations |
| Return type when weights absent | `NULL` |
| Post-extraction guard | `if (any(wt < 0)) stop(...)` |
| Fallback when `NULL` | `wt <- rep(1, nrow(m))` — every observation gets weight 1 |

There is exactly one distinct functional usage in the CSV: extracting the optional per-observation weights from a model frame and defaulting to a unit-weight vector when none were provided.

---

### 3. Python Conversion Strategy

**Chosen library: `numpy`**

In the Python translation of rpart, the model frame abstraction is replaced by a plain `numpy` array or `pandas` DataFrame for the feature matrix, with weights passed directly as a separate argument (a `numpy` array or `None`). Because rpart works on arrays of observations, weights are always array-valued (vectorized), making `numpy` the natural fit.

There is no Python object that directly mirrors R's model frame, so `model.weights(m)` does not translate to a single library call. Instead, the weights are accepted as an explicit parameter to the Python function and the same `NULL → ones` defaulting logic is reproduced with `numpy`.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Extracting Case Weights from a Model Frame (`rpart`, line 27)

**Locations:**
- File: `rpart/R/rpart.R`
- Function: `rpart`

**Original R Context:**

```r
# m       : model frame (data.frame-like), produced by stats::model.frame()
# weights : optional numeric vector passed by the caller; may be missing

wt <- model.weights(m)
# wt is either:
#   - a numeric vector of length nrow(m)  (when caller supplied weights)
#   - NULL                                (when caller did not supply weights)

if (any(wt < 0)) stop("negative weights not allowed")
if (!length(wt)) wt <- rep(1, nrow(m))
# After the fallback: wt is always a numeric vector of length nrow(m)
```

**Python Equivalent:**

```python
import numpy as np

def _resolve_weights(weights, n_samples: int) -> np.ndarray:
    """
    Mirror the R idiom:
        wt <- model.weights(m)
        if (any(wt < 0)) stop("negative weights not allowed")
        if (!length(wt)) wt <- rep(1, nrow(m))

    Parameters
    ----------
    weights : array-like or None
        Per-observation case weights supplied by the caller, or None when
        no weights were provided (equivalent to R's missing / NULL).
    n_samples : int
        Number of observations (rows in the model frame).

    Returns
    -------
    np.ndarray of shape (n_samples,) with dtype float64
    """
    if weights is None:
        # R: if (!length(wt)) wt <- rep(1, nrow(m))
        return np.ones(n_samples, dtype=np.float64)

    wt = np.asarray(weights, dtype=np.float64)

    # R: if (any(wt < 0)) stop("negative weights not allowed")
    if np.any(wt < 0):
        raise ValueError("negative weights not allowed")

    return wt
```

Usage inside the translated `rpart` function:

```python
def rpart(formula_data, weights=None, ...):
    # ... build X (feature matrix) and y (response) from formula_data ...
    n_samples = X.shape[0]

    # Replaces:  wt <- model.weights(m)  +  fallback + guard
    wt = _resolve_weights(weights, n_samples)

    # wt is now always a float64 ndarray of length n_samples
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `model.weights(m)` | `weights` parameter (passed explicitly) | Python has no model-frame object; weights are supplied as a direct argument |
| Return value `NULL` | `None` | Pythonic sentinel for "not provided" |
| `!length(wt)` (checks NULL or zero-length) | `weights is None` | In Python the `None` check is sufficient because callers either pass an array or nothing |
| `rep(1, nrow(m))` | `np.ones(n_samples, dtype=np.float64)` | Creates a unit-weight array with one entry per observation |
| `any(wt < 0)` | `np.any(wt < 0)` | Element-wise vectorized comparison; `numpy` mirrors R's vectorized semantics |
| `stop(...)` | `raise ValueError(...)` | Standard Python exception for invalid input |

**Key nuances:**
- R's `model.weights` encapsulates the column look-up inside the model frame; in Python this indirection is eliminated by making weights an explicit function parameter, which is consistent with how scikit-learn and similar libraries handle sample weights (`sample_weight=`).
- `numpy.ones` produces a C-contiguous `float64` array, which matches the numeric precision R uses for weights internally.
- The `np.asarray(..., dtype=np.float64)` call safely handles the case where the caller passes a Python list, a `pandas` Series, or an existing `numpy` array of a different dtype — all of which are valid inputs in Python but have no exact R analogue since R always stores weights as a plain numeric vector.
