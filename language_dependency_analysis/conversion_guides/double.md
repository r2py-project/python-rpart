# Conversion Guide: `double` (R to Python)

### 1. Overview of `double` in R

`double(n)` is a base R function that allocates a numeric vector of length `n`, with all elements initialized to `0`. It is the typed equivalent of `vector("double", n)` or `numeric(n)`. The function signature is:

```r
double(length = 0)
```

- **Input:** A single non-negative integer specifying the desired length of the vector.
- **Output:** A numeric vector of the given length, with every element set to `0.0` (double-precision floating-point values).

`double` is distinct from `integer` or `logical` in that it explicitly signals the intent to store floating-point values. It is commonly used to pre-allocate a buffer that will be filled in element-by-element or by index-based assignment in a subsequent loop.

---

### 2. Contextual Usage Analysis

**File:** `rpart/R/rpartco.R`
**Function:** `rpartco`
**Line 54:**

```r
x <- double(length(node))         # allocate, then fill it in below
```

**Context (lines 52-62):**

```r
# Now compute the x coordinates, by spacing out the leaves and then
#   filling in
x <- double(length(node))         # allocate, then fill it in below
x[is.leaf] <- seq(sum(is.leaf))      # leaves at 1, 2, 3, ....
left.child <- match(node * 2L, node)
right.child <- match(node * 2L + 1L, node)

## temp is a list of non-is.leaf, by depth
temp <- split(seq(node)[!is.leaf], depth[!is.leaf])
for (i in rev(temp))
    x[i] <- 0.5 * (x[left.child[i]] + x[right.child[i]])
```

**Analysis:**

- `node` is a numeric vector derived from `as.numeric(row.names(frame))` at line 12, where `frame` is `tree$frame` — a data frame whose row count equals the number of nodes in the decision tree.
- `length(node)` therefore evaluates to an integer scalar equal to the total number of nodes.
- `double(length(node))` pre-allocates a zero-initialized float array of that length — a standard R idiom for creating a result buffer before populating it with indexed writes.
- Immediately after allocation, leaf positions are written by index (`x[is.leaf] <- seq(sum(is.leaf))`), and internal node positions are computed in a subsequent loop as the average of their two children's x-coordinates.
- The pattern is purely a pre-allocation idiom; no arithmetic is performed on the zeros themselves. The important properties are: (a) the length matches `node`, and (b) the dtype is floating-point so that the subsequent averaging (`0.5 * ...`) stores correctly without integer truncation.

**Recurring pattern:** A single usage. The pattern is "allocate a zero-filled float buffer sized to an existing vector, then fill by positional index."

---

### 3. Python Conversion Strategy

`numpy.zeros(n, dtype=np.float64)` is the direct and idiomatic Python equivalent. Reasons:

1. **Vectorized nature:** NumPy arrays, like R vectors, support element-wise operations and boolean/integer index-based assignment (`x[mask] = values`), which are used immediately after the allocation on lines 55 and 62.
2. **Type fidelity:** R's `double` creates IEEE 754 double-precision values. `numpy.float64` (the default dtype for `numpy.zeros`) matches this exactly.
3. **Zero initialization:** Both `double(n)` and `numpy.zeros(n)` guarantee all elements start at `0.0`.
4. `numpy.zeros` is preferable to `numpy.empty` here because the surrounding code only writes to a subset of indices (the non-leaf nodes are filled by a loop; remaining slots may be zero-dependent for correctness).

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Pre-allocating a zero-filled float buffer sized to a node vector

**Locations:**
- File: `rpart/R/rpartco.R`
- Function: `rpartco`

**Original R Context:**

- `node` is a 1-D numeric vector of length equal to the number of tree nodes (integer count, positive).
- `double(length(node))` returns a numeric vector of the same length, all zeros, ready for index-based assignment.
- Return type: `double` (numeric) vector.

```r
# R
node <- as.numeric(row.names(frame))   # e.g., c(1, 2, 3, 4, 5)

x <- double(length(node))              # -> c(0, 0, 0, 0, 0)  (float64)
x[is.leaf] <- seq(sum(is.leaf))        # assign leaf x-positions
for (i in rev(temp))
    x[i] <- 0.5 * (x[left.child[i]] + x[right.child[i]])
```

**Python Equivalent:**

```python
import numpy as np

# node is a 1-D numpy array of node identifiers, e.g.:
# node = np.array(row_names_of_frame, dtype=np.float64)

x = np.zeros(len(node), dtype=np.float64)   # equivalent to double(length(node))

# Assign leaf x-positions (is_leaf is a boolean numpy array)
x[is_leaf] = np.arange(1, int(np.sum(is_leaf)) + 1)   # R's seq() is 1-based

# Fill internal node x-positions (loop over levels in reverse depth order)
for i in reversed(temp):                     # temp is a list of index arrays
    x[i] = 0.5 * (x[left_child[i]] + x[right_child[i]])
```

**Explanation:**

| R | Python | Notes |
|---|--------|-------|
| `double(length(node))` | `np.zeros(len(node), dtype=np.float64)` | Both allocate a zero-initialized float buffer of the same length as the node vector. |
| `length(node)` | `len(node)` | `len()` on a NumPy array returns the size of its first axis, matching R's `length()` on a vector. |
| `x[is.leaf] <- seq(sum(is.leaf))` | `x[is_leaf] = np.arange(1, int(np.sum(is_leaf)) + 1)` | R's `seq(n)` produces `1:n` (1-based); Python's `np.arange(1, n+1)` replicates this. Boolean indexing works identically in both. |
| `0.5 * (x[left.child[i]] + x[right.child[i]])` | `0.5 * (x[left_child[i]] + x[right_child[i]])` | NumPy supports integer-array fancy indexing the same way R supports integer vector indexing; the arithmetic is element-wise in both cases. |

The critical nuance is the 1-based vs. 0-based indexing in the sequential leaf assignment (`seq(sum(is.leaf))` in R starts at 1). The downstream code uses these x-coordinates only for relative spacing in a tree plot, so the offset is consistent throughout and does not need adjustment — as long as Python replicates the same 1-based starting value with `np.arange(1, n+1)`.
