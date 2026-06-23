# Conversion Guide: `rev` in R

---

### 1. Overview of `rev` in R

`rev` is a base R function that returns the elements of its input in reversed order. Its signature is:

```r
rev(x)
```

- **Input:** A vector (numeric, integer, character, logical), a list, or any other object with a defined order. Named vectors retain their names after reversal.
- **Output:** An object of the same type and length as `x`, with elements in the opposite order.

`rev` is strictly an ordering operation. It does not alter values — only their sequence. For atomic vectors it returns a vector; for lists it returns a list with elements in reverse order.

---

### 2. Contextual Usage Analysis

Across the six call sites in the CSV, `rev` is used in three functionally distinct patterns:

**Pattern A — Suffix (right-to-left) cumulative sum (`rpart.exp.R`, lines 82 and 87).**
The compound expression `rev(cumsum(rev(x)))` appears twice inside the `drate2` helper. Here `x` is a named integer vector produced by `table()`. The idiom:
1. Reverses the vector so the last element comes first.
2. Applies `cumsum`, which now accumulates from what was originally the right end.
3. Reverses again to restore original element order.

The net result is a vector of the same length where each element holds the sum of all elements from that position to the rightmost end (a suffix sum). The inner `rev(tab1)` and `rev(tab2)` sub-expressions in lines 82 and 87 are the first step of this compound pattern.

**Pattern B — List reversal for depth-order traversal (`rpartco.R`, line 61).**
`temp` is a list produced by `split(seq(node)[!is.leaf], depth[!is.leaf])`, where each element is a numeric vector of node indices at one depth level. `rev(temp)` reverses the list so the loop processes the deepest tree level first and works upward toward the root — a bottom-up traversal needed when computing x-coordinates from leaves to root.

**Pattern C — Length-2 vector element swap (`text.rpart.R`, line 20).**
`cxy <- par("cxy")` returns a two-element numeric vector `c(width, height)` representing character dimensions. When the text rotation parameter `srt == 90`, `rev(cxy)` swaps the two elements so that the width and height roles are exchanged, effectively transposing the character extent for rotated text layout.

---

### 3. Python Conversion Strategy

The primary Python equivalent is `numpy.flip()` (or its slice alias `[::-1]`). NumPy is the correct choice because:

- R vectors are inherently array-like; `numpy.ndarray` is the natural Python analogue.
- `numpy.flip()` operates element-wise on arrays of any shape, matching R's vectorized semantics.
- For the suffix-sum pattern, `numpy.cumsum` combined with `numpy.flip` replicates the compound `rev(cumsum(rev(x)))` exactly.

For Pattern B (list reversal), a plain Python `list` is the appropriate container and Python's built-in `reversed()` or `list[::-1]` slice is sufficient — no NumPy is needed.

For Pattern C (length-2 vector swap), either `numpy.flip` on a length-2 array or a simple Python tuple/list reversal works.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Pattern A — Suffix cumulative sum: `rev(cumsum(rev(x)))`

**Locations:** `rpart/R/rpart.exp.R`, function `drate2`, lines 82 and 87.

**Original R Context:**

```r
# tab1 is a named integer vector produced by table(index)
# Values are counts of observations per time interval (integer, length = ngrp)
tab1 <- table(index)                        # e.g., c(3L, 5L, 2L, 4L)

# Inner rev reverses the vector; cumsum accumulates from the original right end;
# outer rev restores original left-to-right order.
# Result: each position holds the total count from that interval onward.
temp <- rev(cumsum(rev(tab1)))              # suffix (right-to-left) cumulative sum

# temp is then used to compute person-years in each interval
pyears <- ilength * c(temp[-1L], 0) + tapply(itime, index, sum)
```

```r
# Identical structure for tab2 (line 87)
tab2 <- table(index2, levels = 1:ngrp)
temp <- rev(cumsum(rev(tab2)))
py2  <- ilength * c(0, temp[-ngrp]) + tapply(itime2, index2, sum)
```

**Python Equivalent:**

```python
import numpy as np

# tab1 is a 1-D integer numpy array of counts per time interval
# (equivalent to R's named integer vector from table())
tab1 = np.array([3, 5, 2, 4], dtype=np.int64)   # example values

# Suffix cumulative sum: sum from each position to the right end
temp = np.flip(np.cumsum(np.flip(tab1)))
# temp == np.array([14, 11, 6, 4])

# Equivalent for tab2
tab2 = np.array([1, 3, 4, 2], dtype=np.int64)
temp2 = np.flip(np.cumsum(np.flip(tab2)))
```

**Explanation:**

| R | Python |
|---|--------|
| `rev(x)` | `np.flip(x)` |
| `cumsum(x)` | `np.cumsum(x)` |
| `rev(cumsum(rev(tab1)))` | `np.flip(np.cumsum(np.flip(tab1)))` |

`np.flip` returns a view with the element order reversed, matching R's `rev` exactly. `np.cumsum` computes a left-to-right prefix sum on whatever array it receives, so flipping before and after produces a suffix sum just as in R. Note that R's `table` output carries names; in Python the equivalent integer array carries no index labels unless a `pandas.Series` is used. In the downstream arithmetic (`ilength * c(temp[-1L], 0)`), the names are not used, so a plain `ndarray` is sufficient.

---

#### 4.2 Pattern B — Reversing a list for bottom-up tree traversal: `rev(temp)`

**Locations:** `rpart/R/rpartco.R`, function `rpartco`, line 61.

**Original R Context:**

```r
# temp is a list of numeric vectors, one element per depth level.
# Each element contains the positional indices of non-leaf nodes at that depth.
# e.g., temp = list(`0` = c(1), `1` = c(2, 3), `2` = c(4, 5, 6, 7))
temp <- split(seq(node)[!is.leaf], depth[!is.leaf])

# rev(temp) reverses the list so the deepest level comes first,
# enabling a bottom-up pass to set x-coordinates from leaves toward the root.
for (i in rev(temp))
    x[i] <- 0.5 * (x[left.child[i]] + x[right.child[i]])
```

**Python Equivalent:**

```python
# temp is a dict (or list of arrays) keyed/ordered by depth level,
# analogous to R's named list from split().
# Using a list of arrays where index 0 = depth 0, etc.

temp = [
    np.array([0]),          # depth 0: root index
    np.array([1, 2]),       # depth 1
    np.array([3, 4, 5, 6]), # depth 2
]

# Reverse the list to iterate from deepest to shallowest
for indices in reversed(temp):
    x[indices] = 0.5 * (x[left_child[indices]] + x[right_child[indices]])
```

**Explanation:**

| R | Python |
|---|--------|
| `rev(temp)` on a list | `reversed(temp)` iterator, or `temp[::-1]` |
| `for (i in rev(temp))` | `for indices in reversed(temp):` |

`reversed()` is the idiomatic Python way to iterate a sequence in reverse without copying it. If in-place indexed access to the reversed list is needed, use `temp[::-1]` to get a new list. The loop body is a vectorized average of left and right child x-coordinates; `x`, `left_child`, and `right_child` should be `numpy` arrays so that array indexing with `indices` works directly.

---

#### 4.3 Pattern C — Swapping elements of a length-2 vector: `rev(cxy)`

**Locations:** `rpart/R/text.rpart.R`, function `text.rpart`, line 20.

**Original R Context:**

```r
# cxy is a length-2 numeric vector: c(character_width, character_height)
# returned by par("cxy") in R's graphics system.
cxy <- par("cxy")                   # e.g., c(0.02, 0.04)

# When text is rotated 90 degrees, width and height swap roles.
if (!is.null(srt <- list(...)$srt) && srt == 90)
    cxy <- rev(cxy)                 # cxy becomes c(0.04, 0.02)

# cxy[2L] is then used as a vertical offset for text placement
FUN(xy$x, xy$y + 0.5 * cxy[2L], rows[left.child], ...)
```

**Python Equivalent:**

```python
import numpy as np

# cxy is a length-2 numpy array: [char_width, char_height]
cxy = np.array([0.02, 0.04])

srt = kwargs.get("srt", None)
if srt is not None and srt == 90:
    cxy = np.flip(cxy)              # cxy becomes np.array([0.04, 0.02])
    # Equivalently: cxy = cxy[::-1]

# cxy[1] (0-based) is used as the vertical offset (was cxy[2L] in R, 1-based)
ax.text(xy_x, xy_y + 0.5 * cxy[1], label, ...)
```

**Explanation:**

| R | Python |
|---|--------|
| `rev(cxy)` | `np.flip(cxy)` or `cxy[::-1]` |
| `cxy[2L]` (1-based index) | `cxy[1]` (0-based index) |

Because this is a length-2 array, `np.flip(cxy)` and `cxy[::-1]` are equivalent. The key indexing difference is that R uses 1-based indexing (`cxy[2L]` is the second element) whereas Python uses 0-based indexing (`cxy[1]`). The `par("cxy")` call has no direct Python/matplotlib equivalent; the character size must be obtained from the matplotlib axes object (e.g., via `ax.get_window_extent()` and font metrics), but the `rev` translation itself is straightforward regardless of how `cxy` is populated.
