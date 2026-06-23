# Conversion Guide: `floor` in R

## 1. Overview of `floor` in R

`floor(x)` returns the largest integer less than or equal to each element of `x` (i.e., rounds toward negative infinity). It is the standard mathematical floor function.

- **Input:** A numeric scalar or numeric vector (integer, double, or complex).
- **Output:** A numeric vector of the same length as the input, where each value is the floor of the corresponding input element. The return type mirrors the input type; for double inputs the result is still a double, not an integer, though its value is always a whole number.
- **Vectorized:** Yes. R applies `floor` element-wise over any vector without an explicit loop.

R documentation reference: `base::floor` (part of base R, no package import required).

---

## 2. Contextual Usage Analysis

Three call sites are present across two source files.

### `rpart/R/rpart.R`, function `rpart`, line 197

```r
ccut <- floor(splits[indx, 4L])
```

`splits` is a numeric matrix constructed earlier in the same function from `rpfit$dsplit` (double-precision values). The column indexed by `4L` holds a cut-point value for ordered-factor splits. `indx` is a logical vector that selects a subset of rows, so `splits[indx, 4L]` is a numeric vector of length equal to the number of ordered-factor splits. `floor` converts each floating-point cut-point to an integer-valued double. The result `ccut` is subsequently used as an integer index (`1L:ccut[i]`) inside a loop, making the truncation semantically significant.

### `rpart/R/zzz.R`, function `tree.depth`, line 7

```r
depth <- floor(log(nodes, base = 2) + 1e-7)
```

`nodes` is a numeric vector of node identifiers (positive integers, typically powers of two or their neighbours in binary tree numbering). `log(nodes, base = 2)` produces a double vector of the same length. The small additive constant `1e-7` guards against floating-point errors that could cause values that are mathematically exact integers (e.g., `log2(4) = 2`) to appear slightly below the integer and floor incorrectly. `floor` then converts each value to the largest integer not exceeding it. The result is a double vector used in arithmetic (`depth - min(depth)`).

### `rpart/R/zzz.R`, function `descendants`, line 43

```r
lev <- floor(log(nodes, base = 2))
```

The setup is identical to `tree.depth`: `nodes` is a vector of integer node identifiers and `log(nodes, base = 2)` computes the binary logarithm element-wise. Here no floating-point guard constant is added. The result `lev` is a double vector used as an integer level index for looping (`for (i in max(lev):2L)`) and for logical comparisons (`lev == i`).

### Recurring patterns

- All three call sites pass a **numeric vector** (not a scalar) to `floor`, confirming that vectorized behaviour is required.
- Two of the three sites compute `floor(log(..., base = 2))` to derive binary-tree depth levels from node identifiers, a common rpart internal pattern.
- The results are always used as integer-like indices or cut-points, so the floor operation is semantically critical and not merely cosmetic rounding.

---

## 3. Python Conversion Strategy

The chosen library is **NumPy** (`numpy.floor`).

Rationale:
- R's `floor` is inherently vectorized over arrays. NumPy's `numpy.floor` mirrors this behaviour exactly, operating element-wise on scalars, lists, or `numpy.ndarray` objects and returning an `ndarray` of the same shape and dtype.
- The rpart code uses the results as array indices and in array arithmetic, contexts that are native to NumPy arrays.
- `math.floor` from the Python standard library operates only on scalars and would require an explicit loop or list comprehension to replicate R's vector semantics; it is therefore not the idiomatic choice here.
- `numpy.log2` provides the binary logarithm, directly replacing R's `log(x, base = 2)` without additional argument mapping.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Floor of matrix column subset (cut-point extraction)

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`, function `rpart`

**Original R Context**

- `splits` is a 2-D numeric matrix (double) with named columns; the fifth column (1-indexed `4L`) stores floating-point cut-point values.
- `indx` is a logical vector used to subset rows.
- `floor(splits[indx, 4L])` returns a double vector of integer-valued cut-points.

```r
# splits: numeric matrix, shape (n_splits, 5)
# indx:   logical vector of length n_splits
ccut <- floor(splits[indx, 4L])
# ccut is a numeric vector; used later as 1:ccut[i] in a loop
```

**Python Equivalent**

```python
import numpy as np

# splits: np.ndarray of shape (n_splits, 5), dtype float64
# indx:   boolean np.ndarray of length n_splits
ccut = np.floor(splits[indx, 3])   # column index 3 (0-based) == R's 4L (1-based)
# ccut is a float64 ndarray with integer values
# When used as a range upper bound, cast to int:
# np.arange(1, int(ccut[i]) + 1)  analogous to R's 1L:ccut[i]
```

**Explanation**

- R uses 1-based indexing for matrix columns; column `4L` in R becomes column index `3` in Python (0-based).
- `np.floor` returns a `float64` array, matching R's behaviour of returning a double rather than an integer type.
- When `ccut[i]` is later used as the upper bound of an integer range (R `1L:ccut[i]`), it must be explicitly cast to `int` in Python: `range(1, int(ccut[i]) + 1)` or `np.arange(1, int(ccut[i]) + 1)`.

---

### 4.2 Binary-tree depth with floating-point guard

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/zzz.R`, function `tree.depth`

**Original R Context**

- `nodes` is a numeric vector of positive integer node identifiers following binary-tree numbering (root = 1, children of node `k` are `2k` and `2k+1`).
- `log(nodes, base = 2)` computes the base-2 logarithm element-wise.
- The additive constant `1e-7` prevents floating-point underflow from causing correct integer results to be floored one step too low.
- The result `depth` is a double vector representing the depth level of each node (0-indexed, root at depth 0 after subtracting `min(depth)`).

```r
# nodes: integer or numeric vector, e.g. c(1, 2, 3, 4, 5, 6, 7)
depth <- floor(log(nodes, base = 2) + 1e-7)
depth <- depth - min(depth)
# depth is a numeric vector of 0-based tree depths
```

**Python Equivalent**

```python
import numpy as np

# nodes: np.ndarray of positive integers, e.g. np.array([1, 2, 3, 4, 5, 6, 7])
depth = np.floor(np.log2(nodes) + 1e-7)
depth = depth - depth.min()
# depth is a float64 ndarray of 0-based tree depths
```

**Explanation**

- R's `log(x, base = 2)` maps directly to `np.log2(x)`.
- The floating-point guard constant `1e-7` is carried over unchanged; its purpose and magnitude are the same in Python because both environments use IEEE 754 double precision.
- `np.floor` returns a `float64` array. If integer dtype is needed downstream, apply `.astype(int)`.
- `depth.min()` replaces R's `min(depth)`; both return a scalar minimum over the vector.

---

### 4.3 Binary-tree level index without floating-point guard

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/zzz.R`, function `descendants`

**Original R Context**

- `nodes` is a numeric vector of binary-tree node identifiers (same convention as above).
- `floor(log(nodes, base = 2))` computes the integer level (depth) of each node without a guard constant.
- The result `lev` is used as an integer-valued level index in a loop and in equality comparisons (`lev == i`).

```r
# nodes: numeric vector of node IDs
lev <- floor(log(nodes, base = 2))
for (i in max(lev):2L) {
    # uses lev == i to identify nodes at level i
}
```

**Python Equivalent**

```python
import numpy as np

# nodes: np.ndarray of positive integer node IDs
lev = np.floor(np.log2(nodes))
for i in range(int(lev.max()), 1, -1):   # analogous to R's max(lev):2L (descending)
    mask = (lev == i)
    # use mask to index into arrays at level i
```

**Explanation**

- The translation follows the same pattern as Section 4.2 but omits the `1e-7` guard, matching the original R source.
- R's descending sequence `max(lev):2L` (inclusive on both ends) becomes `range(int(lev.max()), 1, -1)` in Python; `range` excludes its stop value, so `1` (not `2`) is used as the stop to include level 2 in the iteration.
- Comparing `lev == i` works identically in NumPy: broadcasting produces a boolean array usable as a mask.
- If strict integer dtype is required for `lev` (e.g., to use it as an index array), apply `lev = np.floor(np.log2(nodes)).astype(int)`.
