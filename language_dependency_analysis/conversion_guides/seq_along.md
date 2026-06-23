# Conversion Guide: `seq_along` (R to Python)

---

## 1. Overview of `seq_along` in R

`seq_along(x)` generates an integer sequence `1, 2, ..., length(x)` — that is, one index for every element of the vector, list, or other object `x`. It is the safe, idiomatic alternative to writing `1:length(x)`, because it returns `integer(0)` (an empty sequence) when `x` is empty, whereas `1:length(x)` incorrectly returns `c(1L, 0L)` for an empty input.

**Typical inputs:** any R vector, list, matrix row/column, or character vector.  
**Return value:** an integer vector of the same length as `x`, starting at 1 and incrementing by 1.

Key characteristics:
- Always 1-based.
- Always the same length as its argument.
- Safe for empty inputs.
- Commonly used to drive `for` loops and to create positional index vectors for subsetting.

---

## 2. Contextual Usage Analysis

Across the ten call sites in the rpart source, `seq_along` is used in two distinct patterns:

**Pattern A — Full index sequence as a standalone object or loop driver (6 occurrences):**  
The complete index sequence is used directly as an iteration counter in a `for` loop, or assigned to a variable that serves as axis tick positions or a subsetting range.

- `importance.R` line 13: `spri[seq_along(fpri)]` — subscripts the result of `cumsum` back down to the length of `fpri` (an integer vector from `which()`).
- `importance.R` line 28: `for (i in seq_along(fpri))` — iterates over primary-split positions.
- `labels.rpart.R` line 74: `for (i in seq_along(jrow))` — iterates over factor-variable row indices.
- `plotcp.R` line 15: `ns <- seq_along(nsplit)` — creates a 1-based tick-position vector for a plot axis; `nsplit` is a numeric column from a matrix.
- `summary.rpart.R` line 46: `for (i in seq_along(cuts))` — iterates over a character vector of split-cut strings.
- `summary.rpart.R` line 68: `for (ii in seq_along(rows))` — iterates over an integer index vector of selected frame rows.

**Pattern B — Filtered index sequence (4 occurrences):**  
The full index sequence is immediately filtered by a boolean condition to select positions satisfying a predicate. This combines index generation with logical subsetting in one expression.

- `labels.rpart.R` line 59: `seq_along(ncat)[ncat > 1L]` — positions within a numeric vector where values exceed 1; `ncat` holds split-type codes.
- `labels.rpart.R` line 68: `seq_along(z)` inside `lapply` — generates indices for a character vector `z` of factor levels, passed to `pmin` to cap at 52.
- `plotcp.R` line 35: `seq_along(xerror)[xerror == min(xerror)]` — positions of the minimum cross-validation error; `xerror` is a numeric vector.
- `summary.rpart.R` line 37: `seq_along(id)[parent.cp > cp]` — positions within an integer vector `id` where the parent's complexity exceeds a threshold.

All arguments to `seq_along` in these files are flat 1-D vectors (integer, numeric, or character). There are no matrix or list inputs.

---

## 3. Python Conversion Strategy

The primary Python equivalent is **`numpy`**, specifically `numpy.arange`. NumPy arrays are the natural counterpart to R's atomic vectors, and `numpy.arange` produces an integer range array efficiently and without copying data.

The mapping is:

| R idiom | Python equivalent |
|---|---|
| `seq_along(x)` (full sequence, 1-based) | `np.arange(len(x))` (0-based) or `np.arange(1, len(x) + 1)` (1-based) |
| `for (i in seq_along(x))` | `for i in range(len(x)):` |
| `seq_along(x)[cond_on_x]` | `np.where(cond_on_x)[0]` or `np.arange(len(x))[cond_on_x]` |

**Index base:** R is 1-based; Python is 0-based. The correct choice depends on whether the resulting indices are used for further R-style 1-based subscripting (which must be converted site-by-site) or only as loop counters (where 0-based is idiomatic Python). For plain `for` loops, `range(len(x))` is the most idiomatic Python form and eliminates the index entirely when only the element is needed. When the indices are stored or used as positional values (e.g., axis tick positions in `plotcp`), the 1-based form `np.arange(1, len(x) + 1)` is the faithful translation.

**Why not `math` or plain `range`?** The source arrays are all NumPy arrays in the translated rpart codebase, so keeping results as NumPy integer arrays allows direct use in boolean-mask indexing and vectorized arithmetic without additional conversion.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Full Index as Array Subscript

**Locations:** `importance.R`, function `importance`, line 13.

**Original R Context:**
```r
# fpri: integer vector (indices of non-leaf rows in ff$frame)
# spri: integer vector produced by cumsum, potentially longer than fpri
spri <- 1 + cumsum(c(0, 1 + ff$ncompete[fpri] + ff$nsurrogate[fpri]))
spri <- spri[seq_along(fpri)]  # trim spri to exactly length(fpri) elements
```
`seq_along(fpri)` produces `c(1L, 2L, ..., length(fpri))`, which is used as a 1-based positional subscript to drop the extra trailing element that `cumsum` appended.

**Python Equivalent:**
```python
import numpy as np

# fpri: np.ndarray of int (indices of non-leaf rows)
# ncompete, nsurrogate: np.ndarrays of int
spri = 1 + np.cumsum(np.concatenate([[0], 1 + ff_ncompete[fpri] + ff_nsurrogate[fpri]]))
spri = spri[:len(fpri)]   # trim to length of fpri (0-based slice)
```

**Explanation:** In Python, trimming an array to the length of another is most directly expressed as a slice `[:len(fpri)]`. The `seq_along`-as-subscript pattern disappears entirely because Python slicing is already 0-based and exclusive of the upper bound. No NumPy call is needed here; the slice achieves the same result.

---

### 4.2 Loop Iterator Over a Vector

**Locations:** `importance.R` line 28, `labels.rpart.R` line 74, `summary.rpart.R` lines 46 and 68.

**Original R Context:**
```r
# fpri: integer vector; loop accesses fpri[i] and related arrays by position
for (i in seq_along(fpri)) {
    if (nsurr[i] > 0L) {
        indx <- spri[i] + ff$ncompete[fpri[i]] + seq_len(nsurr[i])
        sname[[i]] <- sdim[indx]
        sval[[i]]  <- scaled.imp[i] * fit$splits[indx, "adj"]
    }
}

# cuts: character vector; loop fills cuts[i] by position
for (i in seq_along(cuts)) {
    cuts[i] <- if (temp[i] == -1L) paste("<", ...) else ...
}

# rows: integer vector; loop prints per-node summary
for (ii in seq_along(rows)) {
    i <- rows[ii]
    ...
}
```

**Python Equivalent:**
```python
# Pattern 1: index only needed to address parallel arrays
for i in range(len(fpri)):
    if nsurr[i] > 0:
        indx = spri[i] + ff_ncompete[fpri[i]] + np.arange(1, nsurr[i] + 1)
        sname[i] = sdim[indx - 1]        # convert 1-based indx to 0-based
        sval[i]  = scaled_imp[i] * splits_matrix[indx - 1, adj_col]

# Pattern 2: filling a list/array by position
cuts = [''] * len(temp)
for i in range(len(cuts)):
    if temp[i] == -1:
        cuts[i] = '< ' + str(...)
    else:
        cuts[i] = ...

# Pattern 3: enumerate when both position and a derived index are needed
for ii, i in enumerate(rows):
    nn = ff_n[i]
    ...
```

**Explanation:** `for (i in seq_along(x))` in R is the direct equivalent of `for i in range(len(x)):` in Python. Both provide a 0-based (Python) or 1-based (R) counter; when translating, subtract 1 whenever `i` is used to index into a NumPy array. When the loop uses both an enumeration counter (`ii`) and an element from the iterated vector (`rows[ii]`), Python's `enumerate` is cleaner than maintaining two variables.

---

### 4.3 Full Index Sequence Stored as Positional Array

**Locations:** `plotcp.R`, function `plotcp`, line 15.

**Original R Context:**
```r
# nsplit: numeric vector — second column of cptable (number of splits per row)
# ns is used as x-axis tick positions (1, 2, 3, ...) in plot() and axis() calls
ns <- seq_along(nsplit)   # integer vector: 1, 2, ..., length(nsplit)
do.call(plot, c(list(ns, xerror, ...), dots))
axis(1L, at = ns, labels = as.character(signif(cp, 2L)), ...)
```
Here `ns` carries semantic meaning as 1-based row numbers (displayed on a plot axis).

**Python Equivalent:**
```python
import numpy as np
import matplotlib.pyplot as plt

# nsplit: np.ndarray of numeric values
ns = np.arange(1, len(nsplit) + 1)   # array([1, 2, ..., len(nsplit)]), dtype int

plt.plot(ns, xerror, 'o-')
plt.xticks(ns, [f'{v:.2g}' for v in cp])
```

**Explanation:** `np.arange(1, len(nsplit) + 1)` faithfully replicates R's 1-based `seq_along`. The upper bound is exclusive in `np.arange`, so `len(nsplit) + 1` is required. Using 1-based values here is deliberate: the array is displayed on a plot axis where position 1 corresponds to the first tree, and the tick labels are separate.

---

### 4.4 Filtered Index Sequence (Boolean Mask on Index Array)

**Locations:** `labels.rpart.R` line 59, `plotcp.R` line 35, `summary.rpart.R` line 37.

**Original R Context:**
```r
# ncat: numeric vector of split-type codes from a matrix column
# Returns positional indices (1-based) where ncat > 1
jrow <- seq_along(ncat)[ncat > 1L]

# xerror: numeric vector of cross-validation errors
# Returns the smallest 1-based position where xerror equals its minimum
minpos <- min(seq_along(xerror)[xerror == min(xerror)])

# id: integer vector of node ids; parent.cp: numeric vector
# Returns 1-based positions of rows whose parent complexity exceeds cp
rows <- seq_along(id)[parent.cp > cp]
```

**Python Equivalent:**
```python
import numpy as np

# ncat: np.ndarray of numeric values
# np.where returns a tuple; [0] extracts the array of matching indices
jrow = np.where(ncat > 1)[0]           # 0-based integer positions

# xerror: np.ndarray of floats
minpos = int(np.where(xerror == xerror.min())[0].min())  # 0-based index of first minimum

# id: np.ndarray of int; parent_cp: np.ndarray of float
rows = np.where(parent_cp > cp)[0]     # 0-based integer positions
```

**Explanation:** In R, `seq_along(x)[condition]` is a two-step idiom: generate all indices, then subset by a boolean vector. NumPy's `np.where(condition)` performs both steps in one call and returns 0-based indices directly. When only indices are needed (not values), `np.where` is preferred over `np.arange(len(x))[condition]`, though both are correct. The resulting indices are 0-based and can be used directly in NumPy array subscripting without adjustment. When a scalar is required (as for `minpos`), wrap with `int(...)` and call `.min()` on the result array before converting.

---

### 4.5 Index Sequence Inside `lapply` / List Comprehension

**Locations:** `labels.rpart.R`, function `labels.rpart`, line 68.

**Original R Context:**
```r
# xlevels: named list of character vectors (one per factor variable)
# For each character vector z (factor levels), generate indices 1..length(z),
# cap at 52, and use them to select from c(letters, LETTERS)
xlevels <- lapply(xlevels, function(z)
    c(letters, LETTERS)[pmin(seq_along(z), 52L)])
```
`seq_along(z)` generates `1:length(z)` for the current level-vector `z`; `pmin` caps each index at 52; the result indexes into the 52-character alphabet vector.

**Python Equivalent:**
```python
import numpy as np

LETTERS_52 = list('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')

# xlevels: dict mapping variable name -> list/array of level strings
xlevels = {
    name: [LETTERS_52[min(i, 51)] for i in range(len(levels))]
    for name, levels in xlevels.items()
}
```

Or equivalently using NumPy for the inner computation:

```python
import numpy as np

LETTERS_52 = np.array(list('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'))

xlevels = {
    name: LETTERS_52[np.minimum(np.arange(len(levels)), 51)].tolist()
    for name, levels in xlevels.items()
}
```

**Explanation:** `seq_along(z)` inside `lapply` becomes `np.arange(len(levels))` (0-based). R's `pmin(..., 52L)` caps at 52 (1-based), which translates to `np.minimum(..., 51)` (0-based cap) because R's index 1 maps to Python index 0 and R's index 52 maps to Python index 51. The dict comprehension replaces `lapply`. The NumPy version is more efficient for large factor-level lists; the list-comprehension version is simpler for small inputs.
