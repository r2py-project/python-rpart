### 1. Overview of `seq` in R

`seq` is a core R function that generates regular sequences of numbers or integer indices. It is one of the most heavily overloaded functions in base R, with behavior that shifts depending on the number and type of arguments supplied:

- **`seq(x)`** — when given a single vector or logical argument, it behaves like `seq_along(x)`, returning an integer sequence `1, 2, ..., length(x)`. This is the "along" form.
- **`seq(from, to, by)`** — generates a numeric sequence from `from` to `to` with step `by`.
- **`seq(from, to, length.out = n)`** — generates `n` evenly spaced values between `from` and `to`.
- **`seq(from, length.out = n)`** — starting at `from`, generates a sequence of length `n` with default step 1 (i.e., `from, from+1, ..., from+n-1`).

All forms return a numeric or integer vector. Indexing in R is 1-based, and `seq` indices always start at 1.

---

### 2. Contextual Usage Analysis

Across the nine call sites in the rpart R source, `seq` is used in three functionally distinct modes:

**Mode A — `seq(x)` as `seq_along(x)` (index generation over a vector).**
This appears in `na.rpart.R` (line 18), `residuals.rpart.R` (line 23), `rpartco.R` (lines 29, 60), and `print.rpart.R` (line 14). In each case `x` is a vector (logical, numeric, or character), and `seq(x)` produces the integer vector `1:length(x)`. The result is used immediately for boolean subsetting, row indexing into a matrix, or as the argument to `split()`.

**Mode B — `seq(x)` applied to a count scalar (integer sequence from 1 to n).**
This appears in `rpartco.R` line 55: `seq(sum(is.leaf))`. Here the argument is a single non-negative integer, and `seq` returns `1:n`. The result assigns consecutive integer x-coordinates to leaf nodes.

**Mode C — `seq(from, length.out = n)` (offset integer range).**
This appears twice in `summary.rpart.R` (lines 87 and 97). The `from` argument is an integer offset into the `splits` matrix (`index[i]` or `1L + index[i] + ff$ncompete[i]`), and `length.out` controls how many consecutive indices to generate. The result is used as a row-index vector to slice rows from `x$splits` and related vectors.

**Mode D — `seq(from, to, by)` (floating-point arithmetic sequence).**
This appears once in `text.rpart.R` line 63: `seq(0, 2 * pi, pi/30)`. The result is a numeric vector of angles used to draw an oval/ellipse with `cos`/`sin`.

---

### 3. Python Conversion Strategy

The chosen library is **NumPy**. R's `seq` is inherently vectorized and always returns an array-like object. NumPy's `np.arange` and `np.linspace` are the direct structural equivalents:

- `seq(x)` (along form) → `np.arange(1, len(x) + 1)` or, when 0-based indexing suffices, `np.arange(len(x))`.
- `seq(n)` (count form, scalar integer) → `np.arange(1, n + 1)`.
- `seq(from, length.out = n)` (offset range) → `np.arange(from_, from_ + n)` (adjusting for 0-based indexing).
- `seq(from, to, by)` (step form) → `np.arange(from_, to_ + epsilon, step)` or `np.linspace(from_, to_, n)` when the count is known.

The critical indexing shift: R indices start at 1; Python/NumPy indices start at 0. Every Mode A/B/C conversion requires subtracting 1 when the resulting index vector is used to subscript a Python array or list.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Mode A — Generating 1-based index sequence over a vector (`seq(vec)`)

**Locations:**
- `na.rpart.R`, function `na.rpart`, line 18
- `residuals.rpart.R`, function `residuals.rpart`, line 23
- `rpartco.R`, function `rpartco`, lines 29 and 60
- `print.rpart.R`, function `print.rpart`, line 14

**Original R Context:**

`keep` is a logical vector (one entry per data row). `seq(keep)` produces `c(1L, 2L, ..., length(keep))`, and `seq(keep)[!keep]` selects the positions of `FALSE` entries — i.e., the 1-based row indices of omitted observations.

```r
# na.rpart.R line 18
keep  <- ...  # logical vector, length = nrow(x)
temp  <- seq(keep)[!keep]          # 1-based positions of omitted rows
names(temp) <- row.names(x)[!keep]

# residuals.rpart.R line 23 — y is a factor vector
yhat <- yprob[cbind(seq(y), unclass(y))]  # row 1-based index paired with class code

# rpartco.R line 29 — node is a numeric vector of node IDs
temp <- split(seq(node), depth)    # split 1-based indices by depth level

# rpartco.R line 60
temp <- split(seq(node)[!is.leaf], depth[!is.leaf])

# print.rpart.R line 14 — depth is an integer vector
substring(indent, 1L, spaces * seq(depth))
```

**Python Equivalent:**

```python
import numpy as np

# --- na.rpart equivalent ---
keep = np.array([True, False, True, False, True])  # boolean mask
# R: seq(keep)[!keep]  ->  1-based indices where keep is False
# Python: convert to 0-based indices directly
omitted_indices_0based = np.where(~keep)[0]           # 0-based
omitted_indices_1based = np.where(~keep)[0] + 1       # 1-based, to match R output

# --- residuals.rpart equivalent ---
# y is a 1D array of integer class labels (already 0-based in Python)
# R: yprob[cbind(seq(y), unclass(y))]  ->  fancy row/col indexing
# In Python (0-based), row indices are simply np.arange(len(y))
row_idx = np.arange(len(y))          # 0-based row indices
col_idx = y_class_codes              # 0-based class codes (subtract 1 from R's unclass)
yhat = yprob[row_idx, col_idx]

# --- rpartco equivalent (split indices by depth) ---
node  = np.array([1, 2, 3, 4, 5])   # node ID vector
depth = np.array([0, 1, 1, 2, 2])   # depth of each node
is_leaf = np.array([False, False, True, True, True])

# R: temp <- split(seq(node), depth)
# Python equivalent using a dict grouped by depth
indices_0based = np.arange(len(node))
from collections import defaultdict
temp = defaultdict(list)
for idx, d in zip(indices_0based, depth):
    temp[d].append(idx)

# R: split(seq(node)[!is.leaf], depth[!is.leaf])
non_leaf_indices = indices_0based[~is_leaf]
non_leaf_depth   = depth[~is_leaf]
temp_non_leaf = defaultdict(list)
for idx, d in zip(non_leaf_indices, non_leaf_depth):
    temp_non_leaf[d].append(idx)

# --- print.rpart equivalent ---
spaces = 2
depth_vec = np.array([0, 1, 1, 2, 2])
# R: spaces * seq(depth)  ->  c(spaces*1, spaces*2, ...)
# Python: spaces * (depth_vec_index + 1)  when used as substring lengths
widths = spaces * (np.arange(len(depth_vec)) + 1)
```

**Explanation:**

- `seq(vec)` in R produces 1-based positions. In Python, `np.arange(len(vec))` gives the same positions but 0-based. When the indices are used to subscript another array (as in `yprob[cbind(...)]`), subtract 1 from any R-sourced class code to align with 0-based NumPy fancy indexing.
- `np.where(~keep)[0]` replaces the two-step `seq(keep)[!keep]` pattern and directly returns the 0-based positions of `False` entries.
- `split(seq(node), depth)` groups index positions by a key; the Python idiom uses `collections.defaultdict(list)` or `{d: indices_0based[depth == d].tolist() for d in np.unique(depth)}`.

---

#### 4.2 Mode B — Integer sequence from 1 to a scalar count (`seq(n)`)

**Locations:**
- `rpartco.R`, function `rpartco`, line 55

**Original R Context:**

`is.leaf` is a logical vector. `sum(is.leaf)` gives the count of leaf nodes (an integer scalar). `seq(sum(is.leaf))` returns `c(1L, 2L, ..., count)`, which is then assigned as the x-coordinates of leaves.

```r
is.leaf <- (frame$var == "<leaf>")
x[is.leaf] <- seq(sum(is.leaf))   # assign 1, 2, 3, ... to leaf positions
```

**Python Equivalent:**

```python
import numpy as np

is_leaf = frame_var == "<leaf>"            # boolean NumPy array
n_leaves = int(is_leaf.sum())

# R: seq(sum(is.leaf))  ->  1, 2, ..., n_leaves
# Python (1-based to match R's plotting convention):
leaf_coords_1based = np.arange(1, n_leaves + 1)

x = np.zeros(len(is_leaf))
x[is_leaf] = leaf_coords_1based
```

**Explanation:**

`seq(n)` where `n` is a scalar integer is equivalent to `np.arange(1, n + 1)`. The 1-based convention is preserved here because the result feeds into a coordinate system where the first leaf is at x=1, matching the R plotting logic. If downstream Python code uses 0-based arrays exclusively, use `np.arange(n_leaves)` instead and adjust any comparisons accordingly.

---

#### 4.3 Mode C — Offset integer range with `length.out` (`seq(from, length.out = n)`)

**Locations:**
- `summary.rpart.R`, function `summary.rpart`, lines 87 and 97

**Original R Context:**

`index[i]` is a 1-based integer offset into the `splits` matrix. `ff$ncompete[i]` and `ff$nsurrogate[i]` are non-negative integer counts. The two calls slice consecutive row ranges out of `x$splits`:

```r
# Primary splits: rows from index[i] to index[i] + ncompete[i]  (inclusive)
j <- seq(index[i], length.out = 1L + ff$ncompete[i])
temp <- cuts[j]
cat(paste(..., x$splits[j, 3L], ...))

# Surrogate splits: rows starting one past the primary block
j <- seq(1L + index[i] + ff$ncompete[i], length.out = ff$nsurrogate[i])
agree <- x$splits[j, 3L]
```

Both produce a contiguous 1-based integer vector: `seq(from, length.out=n)` gives `c(from, from+1, ..., from+n-1)`.

**Python Equivalent:**

```python
import numpy as np

# Assume splits is a 2D NumPy array (0-based row/col indexing)
# index_i  is the R 1-based start index -> convert to 0-based: index_i - 1
# ncompete and nsurrogate are plain integer counts

# R: j <- seq(index[i], length.out = 1L + ff$ncompete[i])
# Python (0-based slice):
start_primary = index_i - 1                          # convert R 1-based to 0-based
count_primary = 1 + ncompete_i
j_primary = np.arange(start_primary, start_primary + count_primary)

primary_improve = splits[j_primary, 2]               # column 3 in R -> index 2 in Python
primary_cuts    = cuts[j_primary]
primary_sname   = sname[j_primary]

# R: j <- seq(1L + index[i] + ff$ncompete[i], length.out = ff$nsurrogate[i])
# Python:
start_surrogate = index_i + ncompete_i               # already 0-based after the +1 cancels
count_surrogate = nsurrogate_i
j_surrogate = np.arange(start_surrogate, start_surrogate + count_surrogate)

surrogate_agree = splits[j_surrogate, 2]
surrogate_adj   = splits[j_surrogate, 4]             # column 5 in R -> index 4 in Python
```

**Explanation:**

`seq(from, length.out = n)` maps directly to `np.arange(from_0based, from_0based + n)` after adjusting for 0-based indexing. The R expression `1L + index[i] + ff$ncompete[i]` as the start of the surrogate block becomes `index_i + ncompete_i` in 0-based Python because the `+1` in R compensates for R's 1-based offset, which cancels against the `-1` needed for Python conversion: `(1 + index_i + ncompete_i) - 1 = index_i + ncompete_i`. Column indices in `splits` also shift by -1 (R column 3 -> Python index 2; R column 5 -> Python index 4).

---

#### 4.4 Mode D — Arithmetic floating-point sequence with explicit step (`seq(from, to, by)`)

**Locations:**
- `text.rpart.R`, inner function `oval`, line 63

**Original R Context:**

`oval` draws an ellipse by computing angles at equally spaced increments of `pi/30` radians from 0 to `2*pi`, then evaluating `cos` and `sin` at each angle.

```r
oval <- function(middlex, middley, a, b) {
    theta <- seq(0, 2 * pi, pi/30)     # 61 angle values: 0, pi/30, 2*pi/30, ..., 2*pi
    newx  <- middlex + a * cos(theta)
    newy  <- middley + b * sin(theta)
    polygon(newx, newy, border = TRUE, col = bg)
}
```

**Python Equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

def oval(middlex, middley, a, b, ax, bg="white"):
    # R: seq(0, 2 * pi, pi/30)
    # np.arange includes 'start', steps by 'step', stops before exceeding 'stop'
    # To ensure 2*pi is included, use np.linspace or add a small epsilon:
    theta = np.arange(0, 2 * np.pi + 1e-10, np.pi / 30)   # 61 points: 0 .. 2*pi
    # Alternatively, with linspace for exact endpoint inclusion:
    # theta = np.linspace(0, 2 * np.pi, 61)

    newx = middlex + a * np.cos(theta)
    newy = middley + b * np.sin(theta)

    polygon = Polygon(np.column_stack([newx, newy]), closed=True,
                      edgecolor="black", facecolor=bg)
    ax.add_patch(polygon)
```

**Explanation:**

`seq(0, 2 * pi, pi/30)` uses the `by` form and generates 61 values (0, pi/30, 2*pi/30, ..., 2*pi). The direct Python equivalent is `np.arange(0, 2*np.pi + epsilon, np.pi/30)` where a small epsilon (e.g., `1e-10`) ensures the endpoint `2*pi` is not dropped due to floating-point rounding — the same boundary-inclusion guarantee that R's `seq` provides. Alternatively, `np.linspace(0, 2*np.pi, 61)` is more numerically stable for fixed-count sequences and avoids the epsilon workaround entirely. Both `np.cos` and `np.sin` are vectorized over the angle array, matching R's element-wise behavior exactly. The R `polygon` call maps to `matplotlib.patches.Polygon`.
