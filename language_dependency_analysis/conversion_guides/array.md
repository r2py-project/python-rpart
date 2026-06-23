### 1. Overview of `array` in R

`array()` creates a multi-dimensional array by filling a contiguous block of memory with values from a data vector and labeling the shape with a `dim` integer vector and optional `dimnames` list.

**Signature:**
```r
array(data = NA, dim = length(data), dimnames = NULL)
```

**Parameters:**
- `data` - A vector supplying the values. If shorter than the total number of elements implied by `dim`, the values are recycled; if longer, they are truncated.
- `dim` - An integer vector whose elements are the extents of each dimension, listed from the leftmost (fastest-varying) dimension to the rightmost (slowest-varying). A scalar `dim = n` produces a 1-D array of length n.
- `dimnames` - An optional list with one element per dimension. Each element is either `NULL` or a character vector of labels for that dimension's indices.

**Return value:** An R array object (a vector with a `dim` attribute and optionally a `dimnames` attribute). A 2-D array is equivalent to a matrix. R stores elements in column-major (Fortran) order: the first index varies fastest.

---

### 2. Contextual Usage Analysis

Two distinct usages appear across the rpart source files:

**Usage A — zero-initialized 3-D array (`roc.rpart.R`, line 38):**
```r
ss.table <- array(0, c(cutoff.n, 2L, 2L))
```
A scalar `0` is supplied as data and recycled to fill every cell of a `cutoff.n × 2 × 2` integer/numeric array. No dimension names are provided. The array acts as a pre-allocated accumulator; however, it is immediately overwritten inside the loop that follows (the loop reassigns `ss.table` to a plain 2-D matrix on each iteration, so the 3-D allocation serves only as a zero-filled placeholder before the loop begins).

**Usage B — reshaping a flat numeric vector into a named 3-D array (`xpred.rpart.R`, lines 137-139):**
```r
temp <- array(pred, dim = c(numresp, length(cp), nrow(X)),
              dimnames = list(NULL, format(cp), rownames(X)))
aperm(temp)   # flip/transpose the dimensions
```
`pred` is a flat `double` vector returned by the C routine `C_xpred`. It is reshaped into a `numresp × length(cp) × nrow(X)` array. `dimnames` assigns no labels to the first dimension, `format(cp)` labels (complexity-parameter values) to the second, and `rownames(X)` (observation identifiers) to the third. The result is immediately passed to `aperm()` to reverse the dimension order.

**Patterns observed:**
- Both usages produce 3-D arrays.
- One usage exploits scalar recycling to zero-fill; the other reshapes an existing flat vector.
- Named dimensions are used in the second case to preserve row/column metadata through the subsequent transpose.
- R's column-major storage order is the critical subtlety when converting: filling a 3-D array from a flat vector in R is equivalent to NumPy's Fortran (column-major, `order='F'`) reshape.

---

### 3. Python Conversion Strategy

`numpy` is the natural equivalent for both usages:

- `numpy.zeros(shape)` replaces `array(0, dim)` for zero-initialized arrays.
- `numpy.reshape(a, newshape, order='F')` (or `ndarray.reshape(..., order='F')`) replaces `array(data_vector, dim)` when reshaping a flat vector, because R fills arrays in column-major order (first index varies fastest), which matches NumPy's `order='F'`.
- `numpy.transpose` / `numpy.moveaxis` replaces R's `aperm()`.
- Dimension names have no direct NumPy equivalent; where metadata must be preserved, a `pandas` object (e.g., `xarray.DataArray` or a `pandas.DataFrame`) can carry labels, but in a pure numerical pipeline they are usually dropped or managed separately.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Zero-initialized 3-D array

**Locations:** `roc.rpart.R`, function `roc.rpart`, line 38.

**Original R context:**

`cutoff.n` is a positive integer (the number of cutoff thresholds). The call allocates a 3-D numeric array of shape `(cutoff.n, 2, 2)` filled with zeros. The return value is a numeric array of type `double` in R.

```r
# cutoff.n: integer scalar
cutoff.n <- length(cutoffs)   # e.g. 5

ss.table <- array(0, c(cutoff.n, 2L, 2L))
# Result: numeric array of shape (cutoff.n, 2, 2), all zeros
```

**Python equivalent:**

```python
import numpy as np

cutoff_n = len(cutoffs)  # e.g. 5

ss_table = np.zeros((cutoff_n, 2, 2), dtype=float)
# Result: numpy array of shape (cutoff_n, 2, 2), all zeros
```

**Explanation:**

- `array(0, c(cutoff.n, 2L, 2L))` recycles the scalar `0` to fill every element of the specified shape. `numpy.zeros(shape)` is the direct idiomatic equivalent and avoids the recycling mechanism altogether.
- R dimensions `c(cutoff.n, 2L, 2L)` map directly to the NumPy `shape` tuple `(cutoff_n, 2, 2)`. Index order is preserved (first axis = cutoff index, second = 2, third = 2).
- Note: in the R source the 3-D `ss.table` is immediately overwritten by a 2-D matrix inside the loop, so in a Python translation the loop body would similarly reassign `ss_table` to a 2-D array (`np.zeros((2, 2))`). The initial 3-D allocation is a placeholder that may be omitted if the loop is the first use.

---

#### 4.2 Reshaping a flat vector into a named 3-D array

**Locations:** `xpred.rpart.R`, function `xpred.rpart`, lines 137-139.

**Original R context:**

`pred` is a flat `double` vector of length `numresp * length(cp) * nrow(X)` returned by the C routine `C_xpred`. `numresp` is an integer scalar (number of response columns), `cp` is a numeric vector of complexity-parameter values, and `X` is the numeric design matrix with `nrow(X)` observations. The result is a 3-D array with named second and third dimensions, which is then transposed by `aperm()`.

```r
# pred:    numeric vector, length = numresp * length(cp) * nrow(X)
# numresp: integer scalar
# cp:      numeric vector of length ncp
# X:       numeric matrix with nrow(X) rows

temp <- array(pred, dim = c(numresp, length(cp), nrow(X)),
              dimnames = list(NULL, format(cp), rownames(X)))
# Result: numeric array of shape (numresp, length(cp), nrow(X))
#         with dimension names: [none, cp labels, row names of X]

aperm(temp)   # reverses dimension order -> shape (nrow(X), length(cp), numresp)
```

**Python equivalent:**

```python
import numpy as np

# pred:    1-D numpy array, length = numresp * len(cp) * n_obs
# numresp: int
# cp:      1-D numpy array of complexity-parameter values
# X:       2-D numpy array of shape (n_obs, n_vars)

n_obs = X.shape[0]
n_cp  = len(cp)

# R fills arrays column-major (first index fastest), so use order='F'
temp = pred.reshape((numresp, n_cp, n_obs), order='F')
# temp.shape == (numresp, n_cp, n_obs)

# aperm(temp) with default perm reverses all dimensions
result = np.transpose(temp)   # shape becomes (n_obs, n_cp, numresp)

# Optional: attach labels via a dictionary or pandas structures
cp_labels  = [f"{v:.6g}" for v in cp]   # equivalent to format(cp)
row_labels = list(row_names_X)           # equivalent to rownames(X)
# NumPy arrays do not store axis labels natively; use xarray.DataArray
# or pandas if label propagation is required downstream.
```

**Explanation:**

- `array(pred, dim = c(numresp, length(cp), nrow(X)))` in R fills the new array by iterating the first index fastest (column-major / Fortran order). NumPy's default `reshape` uses C order (last index fastest). Therefore `order='F'` is mandatory to reproduce R's filling behaviour.
- `dim = c(numresp, length(cp), nrow(X))` maps to the NumPy shape tuple `(numresp, n_cp, n_obs)` in the same left-to-right order.
- `aperm(temp)` without an explicit `perm` argument reverses all dimension indices, which is identical to `numpy.transpose()` applied to a 3-D array (this reverses the axis order from `(0,1,2)` to `(2,1,0)`).
- `dimnames = list(NULL, format(cp), rownames(X))` has no NumPy equivalent. If axis labels must be preserved (e.g., for subsequent named indexing), use `xarray.DataArray` with `coords` and `dims`, or convert the final 2-D slice to a `pandas.DataFrame` with appropriate index/column labels after the transpose.
- `format(cp)` in R produces a character vector of consistently formatted floating-point strings. In Python, a list comprehension such as `[f"{v:.6g}" for v in cp]` or `np.array(cp).astype(str)` achieves a similar result, though exact formatting may differ.
