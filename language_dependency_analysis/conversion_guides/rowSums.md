# Conversion Guide: `rowSums` (R → Python)

---

## 1. Overview of `rowSums` in R

`rowSums(x, na.rm = FALSE, dims = 1)` computes the sum of each row of a numeric array or matrix. It is a vectorized convenience function equivalent to `apply(x, 1, sum)` but substantially faster because it is implemented in C.

- **Input:** A numeric matrix or 2-D array (or data frame whose columns are all numeric). The optional `na.rm` argument controls whether `NA` values are silently ignored (`FALSE` by default).
- **Output:** A named numeric vector of length equal to the number of rows in `x`. Each element is the sum of the corresponding row.
- **Key property:** Because R is column-major and inherently vectorized, `rowSums` operates on every row in a single pass with no explicit loop. The result is typically used immediately for element-wise normalization (row-wise division).

---

## 2. Contextual Usage Analysis

Both call sites in the rpart package use `rowSums` for the same purpose: **row-wise normalization of a numeric matrix** — dividing each element of a matrix by the sum of its row so that every row sums to 1.

### Call site 1 — `rpart.R`, function `rpart`, line 255

```r
temp <- rpfit$dnode[, 4L + (1L:numclass)] %*% diag(init$parms$prior/temp)
yprob <- temp / rowSums(temp)
```

`temp` is a numeric matrix with shape `(num_nodes, numclass)` produced by a matrix multiplication (`%*%`). `rowSums(temp)` returns a numeric vector of length `num_nodes`; the division normalizes every row of `temp` into a proper probability distribution. The comment "necessary with altered priors" confirms the purpose: user-supplied class priors can make the raw weighted counts no longer sum to 1, so explicit row normalization is required.

### Call site 2 — `rpart.class.R`, function `rpart.class`, line 42

```r
if (any(rowSums(temp2) == 0))
    stop("Loss matrix has a row of zeros")
```

`temp2` is a square numeric matrix of shape `(numclass, numclass)` representing the user-supplied loss matrix. `rowSums(temp2)` returns a vector of length `numclass`; the check flags a degenerate loss matrix where at least one entire row is zero (which would make the penalty for misclassification undefined).

**Recurring pattern summary:**

| Call site | Matrix shape | Purpose |
|-----------|-------------|---------|
| `rpart.R:255` | `(num_nodes, numclass)` floating-point | Row normalization (probabilities) |
| `rpart.class.R:42` | `(numclass, numclass)` floating-point | Row-sum validation (guard clause) |

Both usages operate on 2-D numeric matrices and rely on `rowSums` returning a 1-D vector aligned with the row axis.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

`numpy.ndarray.sum(axis=1)` — or equivalently `numpy.sum(arr, axis=1)` — is the direct, idiomatic counterpart to R's `rowSums` for all matrix (2-D array) inputs. It:

- Operates on the row axis (`axis=1`) in a single vectorized C pass, matching R's performance characteristic.
- Returns a 1-D `numpy` array aligned with rows, exactly as `rowSums` returns a named vector aligned with rows.
- Supports `nan` handling via `numpy.nansum(arr, axis=1)` when `na.rm = TRUE` behavior is needed (not required here, since both call sites use non-`NA` matrices).
- Enables broadcasting for the row-normalization pattern: dividing a 2-D array by the resulting 1-D array requires `keepdims=True` (or explicit reshaping) to broadcast correctly — this is the one indexing nuance to handle explicitly.

`pandas.DataFrame.sum(axis=1)` is an alternative but adds unnecessary overhead for pure numeric matrix operations that do not require labelled axes.

---

## 4. Step-by-Step Conversion Examples

### Example 1 — Row normalization of a probability matrix

**Locations:** `rpart.R`, function `rpart` (line 255)

**Original R Context:**

- `temp` is a `(num_nodes, numclass)` numeric matrix produced by a matrix–diagonal-matrix multiplication.
- `rowSums(temp)` returns a `(num_nodes,)` numeric vector.
- The division `temp / rowSums(temp)` is broadcast column-wise by R (R broadcasts a vector along columns by default for matrix/vector division), normalizing each row.
- `yprob` is therefore a `(num_nodes, numclass)` numeric matrix whose rows sum to 1.

```r
# R (generalized)
# temp: matrix of shape (num_nodes, numclass), numeric
# prior: numeric vector of length numclass (class priors, sum to 1)
# class_counts: integer vector of length numclass (observed class frequencies)

temp <- node_counts_matrix %*% diag(prior / pmax(1L, class_counts))
yprob <- temp / rowSums(temp)   # each row is now a valid probability vector
```

**Python Equivalent:**

```python
import numpy as np

# Inputs (numpy equivalents):
#   node_counts_matrix : np.ndarray, shape (num_nodes, numclass), float64
#   prior              : np.ndarray, shape (numclass,), float64  -- class priors, sum to 1
#   class_counts       : np.ndarray, shape (numclass,), int/float -- observed class frequencies

# Step 1: replicate  rpfit$dnode[, 4L + (1L:numclass)] %*% diag(prior / pmax(1L, class_counts))
safe_counts = np.maximum(1, class_counts)          # pmax(1L, class_counts)
scale = prior / safe_counts                         # element-wise, shape (numclass,)
temp = node_counts_matrix * scale[np.newaxis, :]   # broadcast: scale each column
# Equivalently: temp = node_counts_matrix @ np.diag(scale)

# Step 2: row-normalize  temp / rowSums(temp)
row_sums = temp.sum(axis=1, keepdims=True)          # shape (num_nodes, 1)
yprob = temp / row_sums                             # broadcasts correctly, shape (num_nodes, numclass)
```

**Explanation:**

- `np.maximum(1, class_counts)` replicates R's `pmax(1L, init$counts)`.
- `temp.sum(axis=1, keepdims=True)` is the direct translation of `rowSums(temp)`. The `keepdims=True` argument keeps the result as shape `(num_nodes, 1)` so that numpy's broadcasting divides each row element by its own row-sum. Without `keepdims=True` the result would be shape `(num_nodes,)` and a plain `/` would attempt to broadcast along the wrong axis, producing incorrect results.
- In R the broadcast is implicit (vector recycled column-by-column); in numpy it must be made explicit with `keepdims=True` or `[:, np.newaxis]`.
- No `nan` handling is needed because the `pmax(1L, ...)` guard ensures the denominator is never zero.

---

### Example 2 — Validation guard on a loss matrix

**Locations:** `rpart.class.R`, function `rpart.class` (line 42)

**Original R Context:**

- `temp2` is a `(numclass, numclass)` numeric matrix supplied by the user as a loss (misclassification cost) matrix.
- `rowSums(temp2)` returns a numeric vector of length `numclass`.
- The check `any(rowSums(temp2) == 0)` detects whether any entire row of the loss matrix is zero, which would signal a degenerate penalty structure and cause a hard stop.

```r
# R (generalized)
# temp2: matrix of shape (numclass, numclass), numeric, diagonal must be 0
if (any(rowSums(temp2) == 0))
    stop("Loss matrix has a row of zeros")
```

**Python Equivalent:**

```python
import numpy as np

# Input:
#   temp2 : np.ndarray, shape (numclass, numclass), float64
#           loss matrix; diagonal entries are 0, off-diagonal entries >= 0

if np.any(temp2.sum(axis=1) == 0):
    raise ValueError("Loss matrix has a row of zeros")
```

**Explanation:**

- `temp2.sum(axis=1)` computes the sum of each row, returning a 1-D array of length `numclass` — exactly what R's `rowSums(temp2)` returns.
- `np.any(...)` replicates R's `any(...)` — it returns `True` if at least one element of the array is `True`.
- The equality comparison `== 0` works identically in both R and numpy for floating-point arrays in this context (the diagonal entries are explicitly set to integer 0, so exact equality is safe here).
- R's `stop(...)` maps to Python's `raise ValueError(...)`.
- `keepdims` is not needed here because the result of `sum(axis=1)` is used only for a scalar boolean test, not for further matrix arithmetic.
