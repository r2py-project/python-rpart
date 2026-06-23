# Conversion Guide: `outer` (R to Python)

---

## 1. Overview of `outer` in R

`outer` computes a **generalized outer product** of two arrays by applying a function to every pairwise combination of their elements.

**Signature:**

```r
outer(X, Y, FUN = "*", ...)
```

- `X`: First array or vector (length M).
- `Y`: Second array or vector (length N).
- `FUN`: A vectorized binary function applied to all (X[i], Y[j]) pairs. Defaults to multiplication (`"*"`).
- `...`: Additional arguments forwarded to `FUN`.

**Return value:** An array with dimensions `c(length(X), length(Y))` (i.e., shape M x N), where element `[i, j]` equals `FUN(X[i], Y[j])`.

The key property is that `FUN` receives two vectors of equal length (the flattened Cartesian expansion of X and Y) and must return a vector of the same length. This means `FUN` must itself be vectorized. When `FUN` is the comparison `>=`, the result is a boolean matrix of shape `(M, N)`.

---

## 2. Contextual Usage Analysis

The single usage in the CSV occurs in `/groups/jli9/Yufei/python-rpart/rpart/R/roc.rpart.R`, inside the function `roc.rpart` at line 13:

```r
pred.np <- outer(cutoffs, object$frame$yprob[endnodes, 2L], ss.compare)
```

**Data types involved:**

- `cutoffs` is a numeric vector of sorted unique threshold values derived from `object$frame$yprob[endnodes, 2L]`, augmented with 0 and 1. Its length M is dynamic (depends on the number of unique predicted probabilities at leaf nodes).
- `object$frame$yprob[endnodes, 2L]` is a numeric vector of length N, holding the predicted class-2 probability for each terminal (leaf) node in the rpart classification tree.
- `ss.compare` is a locally defined binary comparison function `function(a, b) a >= b`. It is vectorized because R's `>=` operator is itself vectorized.

**What the result represents:**

`pred.np` is a boolean matrix of shape `(M, N)`. Row i corresponds to threshold `cutoffs[i]`; column j corresponds to leaf node j. Entry `[i, j]` is `TRUE` when `cutoffs[i] >= yprob[j]`, meaning that at threshold `cutoffs[i]`, leaf node j is predicted as the negative class (below the cutoff). This matrix is the core structure driving the ROC curve computation in the function.

**Pattern summary:** There is exactly one distinct functional usage: `outer` with a custom boolean comparison function (`>=`), operating on two 1-D numeric vectors and producing a 2-D boolean matrix.

---

## 3. Python Conversion Strategy

**Chosen approach: NumPy broadcasting with `>=`**

R's `outer` with a custom `FUN` has two natural Python equivalents:

1. `numpy.ufunc.outer` — e.g., `np.greater_equal.outer(cutoffs, yprob)`: directly mirrors R's semantics for any numpy ufunc. Produces the same `(M, N)` boolean array.
2. **NumPy broadcasting** — `cutoffs[:, np.newaxis] >= yprob[np.newaxis, :]`: a general idiom that works for any binary operator, including `>=`. It is idiomatic, requires no additional imports, and is equally efficient.

The broadcasting approach is preferred here because:
- `>=` is a native Python/NumPy operator, making the intent immediately readable.
- No ufunc name lookup is required.
- It generalizes cleanly if the comparison function changes.

`numpy.outer` (the plain function) is **not** a valid substitute here because it only computes element-wise multiplication and has no `FUN` parameter.

---

## 4. Step-by-Step Conversion Examples

### 4.1 `outer` with a custom `>=` comparison function

**Locations:**
- File: `rpart/R/roc.rpart.R`
- Function: `roc.rpart`

**Original R Context:**

```r
# ss.compare is defined locally as a vectorized >= comparison:
ss.compare <- function(a, b) a >= b

# cutoffs: numeric vector of M sorted threshold values (e.g., [0, 0.3, 0.7, 1.0])
# yprob:   numeric vector of N leaf-node predicted probabilities
cutoffs <- sort(unique(c(0, 1, object$frame$yprob[endnodes, 2L])))
yprob   <- object$frame$yprob[endnodes, 2L]

# Returns a boolean matrix of shape (M, N):
# pred.np[i, j] is TRUE when cutoffs[i] >= yprob[j]
pred.np <- outer(cutoffs, yprob, ss.compare)
```

Input types: both `cutoffs` and `yprob` are numeric vectors (R `double`).
Return type: logical matrix of shape `(M, N)`.

**Python Equivalent:**

```python
import numpy as np

# cutoffs: 1-D numpy array of M sorted threshold values, dtype float64
# yprob:   1-D numpy array of N leaf-node predicted probabilities, dtype float64
#
# Broadcasting produces a boolean array of shape (M, N).
# pred_np[i, j] is True when cutoffs[i] >= yprob[j].
pred_np = cutoffs[:, np.newaxis] >= yprob[np.newaxis, :]
```

Alternatively, using `numpy.ufunc.outer`:

```python
pred_np = np.greater_equal.outer(cutoffs, yprob)
```

Both produce an `ndarray` of shape `(M, N)` with `dtype=bool`.

**Explanation:**

| R concept | Python equivalent | Notes |
|---|---|---|
| `outer(X, Y, FUN)` with vectorized `FUN` | `X[:, np.newaxis] op Y[np.newaxis, :]` | Broadcasting expands X to (M,1) and Y to (1,N), then applies the operator element-wise to produce (M,N). |
| `ss.compare <- function(a, b) a >= b` | Python's `>=` operator | No separate function needed; the operator is applied directly via broadcasting. |
| R logical matrix (1-indexed) | NumPy `bool` ndarray (0-indexed) | Row/column access shifts from `pred.np[i, ]` in R to `pred_np[i, :]` in Python. |
| `dim(pred.np)[1L]` / `dim(pred.np)[2L]` | `pred_np.shape[0]` / `pred_np.shape[1]` | Zero-based dimension indexing in Python. |
| `pred.np[i, ]` (row i, all columns) | `pred_np[i, :]` | R uses 1-based row indexing; Python uses 0-based. |
| `!pred.np[i, ]` (logical negation) | `~pred_np[i, :]` | NumPy uses `~` for element-wise boolean NOT on arrays. |
| `rbind(matrix(FALSE, ...), pred.np)` | `np.vstack([np.zeros((1, N), dtype=bool), pred_np])` | Prepending a row of `False` values. |
| `rbind(pred.np, matrix(TRUE, ...))` | `np.vstack([pred_np, np.ones((1, N), dtype=bool)])` | Appending a row of `True` values. |

**General rule for converting `outer(X, Y, FUN)` to Python:**

- If `FUN` is a standard comparison or arithmetic operator: use NumPy broadcasting directly — `X[:, np.newaxis] op Y[np.newaxis, :]`.
- If `FUN` corresponds to a NumPy ufunc (e.g., `np.add`, `np.multiply`, `np.greater_equal`): use `np.<ufunc>.outer(X, Y)`.
- If `FUN` is an arbitrary Python function that is not a ufunc: use `np.vectorize(FUN).outer(X, Y)` or construct the result with a list comprehension and `np.array([[FUN(x, y) for y in Y] for x in X])`.
