# Conversion Guide: `min` in R

## 1. Overview of `min` in R

`min(..., na.rm = FALSE)` returns the minimum value among all supplied arguments. It is a generic function that handles:

- **Scalars:** returns the single value itself.
- **Vectors / arrays:** traverses every element and returns the overall minimum.
- **Multiple arguments:** `min(a, b, c)` flattens all arguments and returns the smallest element across all of them.
- **NA handling:** by default any `NA` in the input propagates to `NA` in the output; setting `na.rm = TRUE` strips `NA`s before comparison.

Return value is always a length-1 scalar of the same atomic type as the input (numeric, integer, or double).

---

## 2. Contextual Usage Analysis

Across the seven call sites in the CSV the function is used in three structurally distinct ways:

| Pattern | CSV rows | Description |
|---|---|---|
| **Element-wise arithmetic result** | `plotcp.R:19`, `rsq.rpart.R:24` | `min(xerror - xstd)` — minimum of a vector produced by element-wise subtraction of two numeric vectors. |
| **Nested / compound minimum** | `plotcp.R:35` (two entries) | `min(seq_along(xerror)[xerror == min(xerror)])` — inner `min(xerror)` finds the minimum value of a numeric vector; outer `min(...)` finds the smallest index position where that minimum is attained. |
| **Two-argument minimum** | `rpartco.R:109` | `min(left$depth, right$depth)` — minimum of two integer scalars (or short integer vectors). |
| **Minimum of a slice difference** | `rpartco.R:114` | `min(right$left[1L:mind] - left$right[1L:mind])` — minimum of an element-wise subtraction of two numeric sub-vectors extracted via an integer-range index. |
| **Offset vector minimum** | `zzz.R:8` | `min(depth)` — minimum of a numeric vector, used to normalise the vector by subtraction. |

In every context the inputs are numeric (double or integer) vectors, never lists or data frames. No `na.rm` argument is passed anywhere, so the default (`na.rm = FALSE`) is relied upon throughout.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

Because every call site operates on R numeric vectors (not scalars), the natural Python counterpart is `numpy.ndarray`. `numpy.min()` (equivalently `ndarray.min()`) replicates R's behaviour exactly:

- It operates element-wise when applied to the result of a vectorised arithmetic expression (e.g. `xerror - xstd` translates directly to a NumPy array subtraction).
- When called on a single array it returns a scalar, matching R's scalar return value.
- When called with multiple array arguments the R idiom `min(a, b)` must be written as `np.minimum(a, b)` (element-wise) **or** `min(a.min(), b.min())` / `np.array([a, b]).min()` depending on whether the intent is to compare two scalars or two vectors element-by-element.

`math.min` does not exist in Python's standard library (`math.inf` is unrelated), and Python's built-in `min()` is scalar-friendly but does not broadcast over arrays in a vectorised way. `numpy.min()` is therefore the most direct and idiomatic replacement for all patterns found here.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Minimum of an Element-Wise Arithmetic Result

**Locations:** `plotcp.R` / `plotcp` (line 19), `rsq.rpart.R` / `rsq.rpart` (line 24)

**Original R Context:**

```r
# xerror and xstd are numeric vectors of the same length
# (columns from a cptable matrix)
ylim_lower <- min(xerror - xstd) - 0.1
```

Input types: `xerror` — `numeric` vector, `xstd` — `numeric` vector of equal length.
Return value: a length-1 `numeric` scalar (the global minimum of the difference vector).

**Python Equivalent:**

```python
import numpy as np

# xerror and xstd are 1-D numpy arrays of the same shape
ylim_lower = np.min(xerror - xstd) - 0.1
```

**Explanation:**

`xerror - xstd` in both R and NumPy performs element-wise subtraction, producing a vector/array of the same length. `np.min()` then returns the single smallest value from that array, equivalent to R's `min()`. No argument mapping differences exist here.

---

### 4.2 Nested Minimum — Finding the Leftmost Index of the Global Minimum

**Locations:** `plotcp.R` / `plotcp` (line 35) — two `min` calls on the same line

**Original R Context:**

```r
# xerror is a numeric vector
# Inner call: find the minimum value of the vector
# Outer call: find the first (smallest) index where that minimum is attained
# seq_along produces 1-based integer indices
minpos <- min(seq_along(xerror)[xerror == min(xerror)])
```

Input types:
- Inner `min(xerror)`: `xerror` is a `numeric` vector; returns a length-1 scalar.
- `xerror == min(xerror)`: logical vector used as a boolean mask.
- `seq_along(xerror)[...]`: integer index vector filtered by the mask.
- Outer `min(...)`: integer vector; returns the smallest 1-based integer index.

Return value: a length-1 integer scalar (1-based position of the first occurrence of the minimum).

**Python Equivalent:**

```python
import numpy as np

# xerror is a 1-D numpy array
# np.argmin returns 0-based index of the first minimum occurrence
minpos = int(np.argmin(xerror))          # 0-based; use directly as array index
# If a 1-based index is needed (matching R's convention):
minpos_1based = int(np.argmin(xerror)) + 1
```

Alternatively, to preserve the exact logical structure of the R code:

```python
import numpy as np

min_val = np.min(xerror)
indices = np.where(xerror == min_val)[0]   # 0-based indices
minpos = int(indices[0])                   # first (smallest) matching index (0-based)
```

**Explanation:**

R's `seq_along(xerror)` produces `1, 2, ..., n` (1-based). The compound expression selects those indices where `xerror` equals its minimum value and returns the smallest one. In NumPy the direct equivalent is `np.argmin()`, which already returns the index of the first occurrence of the minimum in a single call (0-based). Choose between `np.argmin()` and the explicit `np.where()` form depending on whether downstream code uses Python 0-based or R 1-based indexing conventions.

---

### 4.3 Minimum of Two Scalar (or Short-Vector) Arguments

**Locations:** `rpartco.R` / `compress` (line 109)

**Original R Context:**

```r
# left$depth and right$depth are single integer values
# (depths of the left and right subtrees)
mind <- min(left$depth, right$depth) - depth
```

Input types: two integer scalars passed as separate arguments to `min`.
Return value: a length-1 integer scalar.

**Python Equivalent:**

```python
# left_depth and right_depth are Python ints (or 0-d numpy integers)
mind = min(left_depth, right_depth) - depth
```

Or, if using numpy arrays throughout:

```python
import numpy as np

mind = int(np.minimum(left_depth, right_depth)) - depth
```

**Explanation:**

When both arguments to R's `min()` are scalar integers, Python's built-in `min()` is perfectly appropriate and avoids an unnecessary NumPy dependency. If the surrounding code already uses NumPy arrays, `np.minimum(a, b)` computes the element-wise minimum (returning a scalar when both inputs are scalars), which is equivalent. Note that `np.minimum` is the element-wise function, whereas `np.min` reduces a single array — for two separate scalar arguments use Python's `min()` or `np.minimum()`.

---

### 4.4 Minimum of a Slice-Subtraction Result

**Locations:** `rpartco.R` / `compress` (line 114)

**Original R Context:**

```r
# right$left and left$right are numeric vectors of tree boundary extents per depth
# mind is an integer scalar computed as in Example 4.3
# 1L:mind is an integer range index (1-based, inclusive both ends)
slide <- min(right$left[1L:mind] - left$right[1L:mind]) - 1L
```

Input types:
- `right$left` and `left$right` — `numeric` vectors of equal length.
- `1L:mind` — integer range, 1-based, selects a sub-sequence.
- Element-wise subtraction produces a `numeric` vector of length `mind`.

Return value: a length-1 `numeric` scalar (minimum gap between tree boundaries).

**Python Equivalent:**

```python
import numpy as np

# right_left and left_right are 1-D numpy arrays (0-indexed)
# mind is a Python int (0-based slice length equivalent)
# R's 1L:mind maps to Python slice [0:mind]
slide = np.min(right_left[0:mind] - left_right[0:mind]) - 1
```

**Explanation:**

R's `1L:mind` is a 1-based inclusive integer range equivalent to `range(1, mind + 1)` in concept, which maps to the Python/NumPy 0-based slice `[0:mind]` (exclusive upper bound). The element-wise subtraction `right_left[0:mind] - left_right[0:mind]` is identical in NumPy to R's vector subtraction. `np.min()` then reduces the resulting array to a scalar. The trailing `- 1` is a plain integer subtraction in both languages.

---

### 4.5 Minimum of a Vector for Normalisation

**Locations:** `zzz.R` / `tree.depth` (line 8)

**Original R Context:**

```r
# nodes is an integer vector of node numbers in a binary tree
depth <- floor(log(nodes, base = 2) + 1e-7)
depth <- depth - min(depth)   # shift so that the root depth is 0
```

Input types: `depth` — `numeric` vector produced by `floor(log(...))`.
Return value: a length-1 `numeric` scalar subtracted from every element of `depth`.

**Python Equivalent:**

```python
import numpy as np

# nodes is a 1-D numpy array of integers
depth = np.floor(np.log2(nodes) + 1e-7)
depth = depth - np.min(depth)   # or equivalently: depth - depth.min()
```

**Explanation:**

R's `log(x, base = 2)` maps to `np.log2(x)`. `np.floor()` and `np.min()` are direct equivalents of R's `floor()` and `min()`. The subtraction `depth - np.min(depth)` broadcasts the scalar minimum across the entire array, producing a normalised vector where the minimum value is 0 — exactly replicating R's vectorised subtraction. The method form `depth.min()` is idiomatic NumPy and equally correct.
