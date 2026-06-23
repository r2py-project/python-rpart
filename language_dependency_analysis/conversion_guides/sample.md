# Conversion Guide: `sample` (R to Python)

---

## 1. Overview of `sample` in R

`sample(x, size, replace = FALSE, prob = NULL)` draws a random sample of `size` elements from a population `x`. It is a base R function defined in the `base` package and requires no imports.

Key characteristics:

- **Input `x`:** Either a positive integer scalar (in which case sampling is performed from `1:x`) or a vector of one or more elements to sample from.
- **Input `size`:** A non-negative integer giving the number of elements to draw. Defaults to `length(x)` when `replace = FALSE`.
- **Input `replace`:** Logical. When `FALSE` (the default), sampling is without replacement and `size` must not exceed `length(x)`. When `TRUE`, each draw is independent (with replacement).
- **Input `prob`:** An optional numeric vector of probability weights for each element of `x`. When `NULL` (the default), all elements are equally likely.
- **Output:** An integer or numeric vector of length `size` containing the sampled elements (or indices, when `x` is a scalar).
- **Vectorization:** The function returns a vector; the draw itself is inherently a single vectorized operation producing `size` results at once.

---

## 2. Contextual Usage Analysis

Both CSV rows contain the identical call:

```r
sample(rep(1L:xval, length.out = nobs), nobs, replace = FALSE)
```

**What the arguments are:**

- `xval` — a positive integer scalar (e.g., `10L` by default from `rpart.control`), representing the number of cross-validation groups/folds.
- `nobs` — a positive integer scalar: `nrow(X)`, the number of observations in the training dataset.
- `rep(1L:xval, length.out = nobs)` — an integer vector of length `nobs` produced by repeating the sequence `1, 2, ..., xval` cyclically until it reaches exactly `nobs` elements. This ensures every fold label from `1` to `xval` appears as evenly as possible.
- `replace = FALSE` — sampling is without replacement, so the output is a random permutation of the input vector.

**What the call produces:**

Because `size == length(x)` and `replace = FALSE`, `sample` here is equivalent to a random shuffle (permutation) of the balanced fold-label vector. The result `xgroups` is an integer vector of length `nobs` where each element is a fold index in `[1, xval]`, and the assignment of observations to folds is random but balanced (each fold gets approximately `nobs / xval` observations).

**Recurring pattern:**

The identical expression appears in:
- `rpart/R/rpart.R`, function `rpart`, line 119 — building `xgroups` for cross-validation during model fitting.
- `rpart/R/xpred.rpart.R`, function `xpred.rpart`, line 70 — rebuilding `xgroups` identically for cross-validated predictions on an existing fit.

There is exactly one functional pattern across all CSV rows.

---

## 3. Python Conversion Strategy

The chosen library is **NumPy** (`numpy`), specifically `numpy.tile` / `numpy.resize` for replicating the fold-label sequence and `numpy.random.Generator.permutation` (via `numpy.random.default_rng`) for the shuffle.

Rationale:

- R's `rep(1L:xval, length.out = nobs)` produces a balanced integer vector. `numpy.resize(numpy.arange(1, xval + 1), nobs)` replicates R's `rep(..., length.out = nobs)` exactly: it tiles the source array and truncates to length `nobs`, giving the same cyclic repetition.
- R's `sample(..., replace = FALSE)` over a vector of the same length as `size` is a random permutation. `numpy.random.Generator.permutation` (or `numpy.random.default_rng().permutation`) is the idiomatic NumPy equivalent and operates in a single vectorized call.
- Using `numpy.random.default_rng()` is the modern, recommended NumPy random API (introduced in NumPy 1.17) and avoids the legacy global state of `numpy.random.shuffle` / `numpy.random.permutation`.
- The standard library `random.sample` is not appropriate here because the inputs and outputs are NumPy integer arrays embedded in larger array-based computations.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Randomly shuffling a balanced fold-label vector for cross-validation

**Locations:**
- File: `rpart/R/rpart.R`, Function: `rpart`, Line 119
- File: `rpart/R/xpred.rpart.R`, Function: `xpred.rpart`, Line 70

**Original R Context:**

```r
# xval:  positive integer scalar — number of CV folds (e.g., 10L)
# nobs:  positive integer scalar — number of observations (nrow(X))

# Step 1: build a balanced fold-label vector of length nobs
#   rep(1L:xval, length.out = nobs) repeats 1,2,...,xval cyclically
#   until the vector reaches exactly nobs elements.
# Step 2: randomly permute it (sample without replacement, size == length)
xgroups <- sample(rep(1L:xval, length.out = nobs), nobs, replace = FALSE)

# xgroups: integer vector of length nobs
#   each element is in [1, xval]
#   folds are balanced: every fold index appears floor(nobs/xval) or
#   ceil(nobs/xval) times
#   the assignment of observations to folds is uniformly random
```

`xgroups` is subsequently passed to C-level rpart routines as a grouping vector that determines which observations belong to each cross-validation fold.

**Python Equivalent:**

```python
import numpy as np

# xval: int — number of CV folds (e.g., 10)
# nobs: int — number of observations

rng = np.random.default_rng()   # or pass a seed: default_rng(seed=42)

# Step 1: replicate [1, 2, ..., xval] cyclically to length nobs
#   np.arange(1, xval + 1) -> array([1, 2, ..., xval])
#   np.resize(..., nobs)   -> cyclic repetition truncated to nobs elements
fold_labels = np.resize(np.arange(1, xval + 1), nobs)

# Step 2: random permutation (shuffle without replacement)
xgroups = rng.permutation(fold_labels)

# xgroups: np.ndarray of shape (nobs,), dtype int64
#   each element is in [1, xval]
```

**Explanation:**

- `np.arange(1, xval + 1)` produces the integer sequence `[1, 2, ..., xval]`, equivalent to R's `1L:xval`. The upper bound is exclusive in NumPy, so `xval + 1` is required.
- `np.resize(array, nobs)` tiles the source array cyclically and returns a new array of exactly `nobs` elements, which is the NumPy equivalent of R's `rep(1L:xval, length.out = nobs)`. Note that `np.resize` (not `numpy.ndarray.resize`) returns a new array and does not modify in place.
- `rng.permutation(fold_labels)` returns a new array that is a uniformly random permutation of `fold_labels`, which is exactly what R's `sample(x, length(x), replace = FALSE)` does. It does not modify `fold_labels` in place.
- `np.random.default_rng()` creates a modern `Generator` object. Passing an integer seed (e.g., `default_rng(seed=42)`) makes results reproducible, equivalent to calling `set.seed(42)` before `sample` in R.
- The result `xgroups` is a 1-D NumPy integer array of shape `(nobs,)`. Fold indices remain 1-based (`1` through `xval`) to match the R convention, which is important if downstream C-level code or Python logic that was ported from R uses 1-based fold labels. If the rest of the Python port adopts 0-based fold indices, subtract 1: `xgroups = rng.permutation(fold_labels) - 1`.
