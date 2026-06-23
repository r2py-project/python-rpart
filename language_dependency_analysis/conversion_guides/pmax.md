# Conversion Guide: `pmax` (R to Python)

## 1. Overview of `pmax` in R

`pmax` (parallel maximum) is a base R function that computes the **element-wise maximum** across two or more vectors or scalars. Unlike `max()`, which collapses all inputs into a single scalar, `pmax` operates position by position and returns a vector of the same length as the longest input argument. Shorter arguments are recycled to match the longest one, following R's standard recycling rules.

**Signature:**
```r
pmax(..., na.rm = FALSE)
```

- `...`: Two or more numeric (or coercible) vectors or scalars.
- `na.rm`: Logical. If `TRUE`, `NA` values are ignored; otherwise a position that has an `NA` in any argument yields `NA` in the output.
- **Return value:** A vector (numeric or integer) of length equal to the longest argument, where each element is the maximum across all corresponding input elements.

The function is closely mirrored by `pmin`, which performs the element-wise minimum.

---

## 2. Contextual Usage Analysis

The CSV identifies four call sites of `pmax` across three source files. Two distinct usage patterns appear:

### Pattern A — Clamping a vector to a scalar floor

Three of the four call sites clamp each element of a vector to be at least as large as a fixed scalar lower bound:

- `prune.rpart.R` line 9: clamps a column of the CP table to be at least `cp`.
- `rpart.R` line 241: clamps a column of integer node counts (`rpfit$inode[, 3L] - 1L`) to be at least `0L`.
- `rpart.R` line 253: clamps the integer class-frequency vector `init$counts` to be at least `1L` (to prevent division by zero).

In every case the first argument is a numeric/integer **vector** and the second argument is a scalar. The result is a vector of the same length used immediately in a subsequent arithmetic or indexing expression.

### Pattern B — Element-wise maximum of two numeric vectors

- `rpartco.R` line 125: merges left/right tree boundary arrays by taking the element-wise maximum of two same-length slices (`tempr[1L:mind]` vs. `right$right - slide`), both of which are floating-point coordinate vectors.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

Because all four call sites operate on vectors (R numeric/integer arrays), `numpy.maximum` is the natural and idiomatic equivalent. It:

- operates element-wise on arrays of any shape,
- broadcasts a scalar against an array automatically (matching R's recycling),
- handles integer and floating-point arrays uniformly, and
- mirrors R's `pmax` semantics exactly for two arguments.

`math.fmax` or plain Python `max()` are inappropriate here because they do not vectorize over arrays.

For completeness: if more than two arguments need to be compared (R's `pmax` accepts `...`), `numpy.maximum.reduce([a, b, c, ...])` handles the general case.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Clamping a matrix column to a scalar — CP table (`prune.rpart.R`)

**Locations:** `prune.rpart.R`, function `prune.rpart`, line 9.

**Original R Context:**

```r
# tree$cptable[, 1L] : numeric vector (length = number of CP rows)
# cp                 : scalar numeric, the pruning complexity parameter
temp <- pmax(tree$cptable[, 1L], cp)
keep <- match(unique(temp), temp)
newx$cptable <- tree$cptable[keep, , drop = FALSE]
newx$cptable[length(keep), 1L] <- cp
```

Input: a 1-D numeric vector and a scalar.
Output: a 1-D numeric vector of the same length; used to identify which CP table rows to keep after pruning.

**Python Equivalent:**

```python
import numpy as np

# cptable : 2-D np.ndarray, shape (n_cp_rows, n_cols), dtype float64
# cp      : float scalar
temp = np.maximum(cptable[:, 0], cp)          # column 0 = R's column 1 (0-based index)
_, unique_indices = np.unique(temp, return_index=True)
keep = np.sort(unique_indices)                 # preserve original order
newx_cptable = cptable[keep, :]
newx_cptable[len(keep) - 1, 0] = cp
```

**Explanation:**

- `np.maximum(vector, scalar)` broadcasts the scalar across every element, exactly replicating `pmax(vector, scalar)`.
- Column indexing shifts from R's 1-based `[, 1L]` to Python's 0-based `[:, 0]`.
- `np.unique` with `return_index=True` and a subsequent sort replicates R's `match(unique(temp), temp)` idiom (which finds the first occurrence of each unique value in original order).

---

### 4.2 Clamping node counts to a non-negative floor (`rpart.R`, line 241)

**Locations:** `rpart.R`, function `rpart`, line 241.

**Original R Context:**

```r
# rpfit$inode[, 3L] : integer vector (number of competitor splits per node)
# result assigned to the 'ncompete' column of a data.frame
ncompete = pmax(0L, rpfit$inode[, 3L] - 1L)
```

Input: an integer vector produced by subtracting 1 from each element; scalar lower bound `0`.
Output: an integer vector of the same length stored as the `ncompete` column.

**Python Equivalent:**

```python
import numpy as np

# inode : 2-D np.ndarray, shape (n_nodes, n_cols), dtype int32/int64
ncompete = np.maximum(0, inode[:, 2] - 1)    # column 2 = R's column 3 (0-based)
```

**Explanation:**

- `np.maximum(0, array)` is the standard numpy idiom for clamping an integer array to zero from below.
- The subtraction `inode[:, 2] - 1` is applied before `np.maximum`, matching R's operator precedence inside the `pmax` call.
- The result dtype stays integer as long as `inode` is an integer array, preserving the original semantics.

---

### 4.3 Clamping class frequency counts to prevent division by zero (`rpart.R`, line 253)

**Locations:** `rpart.R`, function `rpart`, line 253.

**Original R Context:**

```r
## The "pmax" ... is for the case of a factor y which has
##   no one at all in one of its classes.  Both the prior and the
##   count will be zero, which led to a 0/0.
# init$counts : integer vector, length = numclass (overall class frequencies)
temp <- pmax(1L, init$counts)
temp <- rpfit$dnode[, 4L + (1L:numclass)] %*% diag(init$parms$prior / temp)
```

Input: integer vector of per-class observation counts; scalar lower bound `1`.
Output: integer vector of the same length, used as a divisor in a matrix-diagonal scaling expression.

**Python Equivalent:**

```python
import numpy as np

# counts    : 1-D np.ndarray, shape (numclass,), dtype int32/int64
# dnode     : 2-D np.ndarray, shape (n_nodes, n_cols), dtype float64
# prior     : 1-D np.ndarray, shape (numclass,), dtype float64
temp = np.maximum(1, counts)                          # clamp to avoid 0/0
scale = prior / temp                                  # element-wise division
temp_matrix = dnode[:, 4:4 + numclass] * scale       # broadcast scaling (replaces diag multiply)
yprob = temp_matrix / temp_matrix.sum(axis=1, keepdims=True)
```

**Explanation:**

- `np.maximum(1, counts)` clamps every zero-count class to 1, exactly matching R's intent (preventing division by zero in the subsequent prior rescaling).
- R's `%*% diag(v)` (right-multiplying by a diagonal matrix) is replaced by the more efficient `* scale` broadcast, which scales each column of `dnode[:, 4:4+numclass]` by the corresponding element of `scale`. This avoids constructing an explicit diagonal matrix.
- Column indices shift from R's 1-based `4 + (1:numclass)` to Python's 0-based `4:4+numclass`.

---

### 4.4 Element-wise maximum of two coordinate vectors (`rpartco.R`, line 125)

**Locations:** `rpartco.R`, function `compress`, line 125.

**Original R Context:**

```r
# tempr        : numeric vector of right-boundary x-coordinates, length >= mind
# right$right  : numeric vector of same structure from the right subtree
# slide        : scalar numeric offset applied to the right subtree
# mind         : integer scalar, minimum depth shared by left and right subtrees
tempr[1L:mind] <- pmax(tempr[1L:mind], right$right - slide)
```

Input: two numeric vectors of equal length `mind` (tree layout x-coordinates).
Output: a numeric vector of length `mind` containing the element-wise maximum; assigned back into the first `mind` positions of `tempr`.

**Python Equivalent:**

```python
import numpy as np

# tempr       : 1-D np.ndarray, dtype float64
# right_right : 1-D np.ndarray, dtype float64 (right subtree boundary coords)
# slide       : float scalar
# mind        : int
tempr[:mind] = np.maximum(tempr[:mind], right_right - slide)
```

**Explanation:**

- Both arguments are same-length slices of floating-point arrays, so no recycling is involved — `np.maximum` directly maps to `pmax` here.
- The in-place slice assignment `tempr[:mind] = ...` replicates R's `tempr[1L:mind] <- ...`. Python's slice `[:mind]` covers indices `0` through `mind-1`, which is the same `mind` elements as R's `1L:mind`.
- `right_right - slide` is a straightforward NumPy broadcast of a scalar subtraction, identical to R's vector minus scalar arithmetic.
