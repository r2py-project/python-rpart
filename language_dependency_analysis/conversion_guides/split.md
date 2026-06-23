# Conversion Guide: `split` (R to Python)

---

## 1. Overview of `split` in R

`split(x, f, drop = FALSE, ...)` is a base R function that **partitions the elements of `x` into a named list of subsets**, where the grouping is determined by the factor (or coercible object) `f`.

- **`x`**: A vector (or data frame) whose elements are to be divided.
- **`f`**: A factor, or an object that can be coerced to a factor via `as.factor(f)`. Each unique level of `f` defines one group. When `f` is a plain integer or numeric vector, R internally converts it to a factor, so each distinct integer value becomes a group label.
- **`drop`**: Logical; if `TRUE`, factor levels with no members are omitted from the output list.
- **Return value**: A named list. Each name is a level of `f` (character-coerced), and the corresponding value is the integer-index vector of all positions in `x` that belong to that level. The list entries appear in the sorted order of the factor levels.

The key property exploited in the rpart code is that `split` performs a **group-by on arbitrary, non-contiguous positions**: all indices whose label equals a given level end up together in one list entry, regardless of where they appear in `x`. This is fundamentally different from splitting an array by position or by consecutive runs.

---

## 2. Contextual Usage Analysis

Both usages occur in `rpartco.R` inside the single function `rpartco`, which computes x-y plot coordinates for an rpart decision tree.

### Common setup (lines 11-14)

```r
frame  <- tree$frame                     # data.frame, one row per tree node
node   <- as.numeric(row.names(frame))   # integer vector: node IDs (e.g. 1, 2, 3, 4, 5, …)
depth  <- tree.depth(node)               # integer vector, same length as node: depth of each node
is.leaf <- (frame$var == "<leaf>")       # logical vector, same length as node
```

`seq(node)` produces `1, 2, 3, ..., length(node)` — a plain 1-based positional index into the `node`/`depth`/`is.leaf` vectors. `depth` is the grouping key.

### Usage 1 — line 29

```r
temp <- split(seq(node), depth)
```

Groups **all** node positions by their depth level. `temp` is a named list such as `list("0" = c(1), "1" = c(2, 3), "2" = c(4, 5, 6, 7), ...)`. It is then iterated depth-level by depth-level (skipping depth 0 with `temp[-1L]`) so that parent nodes are always processed before children.

Both `seq(node)` and `depth` are integer vectors of the same length (`length(node)`). The return value is a list of integer vectors (1-based positional indices).

### Usage 2 — line 60

```r
temp <- split(seq(node)[!is.leaf], depth[!is.leaf])
```

Identical in structure, but first **filters out leaf nodes**. `!is.leaf` is a logical mask, so both `x` and `f` are shortened to cover only interior (non-leaf) nodes before grouping. The result is used in `rev(temp)` — iterating from the deepest depth upward — to propagate x-coordinates from children to parents.

Both vectors passed to `split` are again integers; the return value is a list of integer vectors (1-based positional indices).

### Recurring patterns

| Pattern | Description |
|---|---|
| `x = seq(node)` or `seq(node)[mask]` | Integer positional indices (1-based in R) |
| `f = depth` or `depth[mask]` | Integer depth values used as group labels |
| Result used as `temp[-1L]` | Drop depth-0 group; iterate remaining groups in depth order |
| Result used as `rev(temp)` | Iterate groups in reverse depth order (deepest first) |
| Inner loop body uses `i` as a vector | Each `i` is an array of indices, not a scalar |

---

## 3. Python Conversion Strategy

### Chosen library: `itertools.groupby` + `sorted`, or plain dict-based grouping

Because the grouping key (`depth`) is a plain 1-D integer array and `x` is also a 1-D integer array, the most idiomatic and readable Python equivalent is a **dictionary comprehension that maps each unique depth value to a list of 0-based indices**. This matches R's `split` semantics exactly:

- Non-contiguous positions with the same depth are collected into one group.
- Groups are keyed by the depth value.
- The result can be iterated in sorted key order (ascending depth) or reverse sorted order.

No external library (numpy, pandas) is required for the grouping itself; the operation is purely structural. However, the **index arithmetic inside the loop bodies** that follow does use numpy arrays in the converted code, so indices are stored as `np.ndarray` of dtype `int64` (0-based) to remain compatible with that downstream code.

`numpy.split` is **not** appropriate here: it splits by array position/slice boundaries, not by a categorical label vector, and has no equivalent to the `f` argument.

`itertools.groupby` requires pre-sorting and only groups consecutive elements, adding unnecessary complexity. A dictionary comprehension is cleaner and more direct.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Usage 1 — Group all nodes by depth

**Locations:** `rpart/R/rpartco.R`, function `rpartco`, line 29.

**Original R Context:**

- `seq(node)`: integer vector, values `1` to `n` (1-based positions), length `n`.
- `depth`: integer vector, same length `n`, values `0, 1, 1, 2, 2, 2, 2, ...`.
- Return type: named list of integer vectors; names are depth levels as character strings; values are 1-based positional index vectors.

```r
# R
node  <- as.numeric(row.names(frame))   # length-n integer vector
depth <- tree.depth(node)               # length-n integer vector

temp <- split(seq(node), depth)
# temp is a list: {"0": [1], "1": [2, 3], "2": [4, 5, 6, 7], ...}

for (i in temp[-1L]) {
    # i is a vector of 1-based indices at one depth level
    temp2 <- dev[parent[i]] - (dev[i] + dev[sibling[i]])
    y[i] <- y[parent[i]] - temp2
}
```

**Python Equivalent:**

```python
import numpy as np
from collections import defaultdict

# Assume these are already numpy arrays (0-based indices throughout):
#   node    : np.ndarray of int, shape (n,)
#   depth   : np.ndarray of int, shape (n,)
#   dev, y, parent, sibling : np.ndarray of float/int, shape (n,)

n = len(node)
indices = np.arange(n)  # 0-based equivalent of R's seq(node)

# R: split(seq(node), depth)
# Build a dict mapping each depth level -> array of 0-based positions
temp = defaultdict(list)
for idx, d in zip(indices, depth):
    temp[d].append(idx)
# Convert lists to numpy arrays and sort by depth key
temp = {d: np.array(v) for d, v in sorted(temp.items())}

# R: for (i in temp[-1L]) — skip depth 0 group
depth_levels = sorted(temp.keys())
for d in depth_levels[1:]:           # skip the first (shallowest) level
    i = temp[d]                       # numpy array of 0-based indices
    temp2 = dev[parent[i]] - (dev[i] + dev[sibling[i]])
    y[i] = y[parent[i]] - temp2
```

**Explanation:**

| R | Python |
|---|---|
| `seq(node)` (1-based, length `n`) | `np.arange(n)` (0-based, length `n`) |
| `split(x, f)` | `defaultdict(list)` loop, then convert to sorted `dict` of `np.ndarray` |
| Named list keys are character depth labels | Dict keys are integer depth values |
| `temp[-1L]` drops the first list element | `depth_levels[1:]` skips the lowest depth key |
| `i` inside loop is a 1-based index vector | `i` inside loop is a 0-based `np.ndarray` |
| `dev[parent[i]]` — R 1-based vector indexing | `dev[parent[i]]` — numpy 0-based fancy indexing (same syntax, different base) |

The critical translation detail is the **index base shift**: R's `seq(node)` starts at 1, so all downstream array accesses like `dev[i]` use 1-based indices. In Python, `np.arange(n)` starts at 0, and numpy fancy indexing is 0-based. This means `parent` and `sibling` arrays also need to store 0-based indices in the Python translation.

---

### 4.2 Usage 2 — Group only non-leaf nodes by depth

**Locations:** `rpart/R/rpartco.R`, function `rpartco`, line 60.

**Original R Context:**

- `seq(node)[!is.leaf]`: integer vector; subset of 1-based positions for non-leaf nodes only.
- `depth[!is.leaf]`: integer vector; depth values for those same non-leaf nodes.
- Both inputs are the same length (number of non-leaf nodes); the grouping logic is otherwise identical to Usage 1.
- Return type: named list of integer vectors (1-based positions into the full `node` array).
- Used with `rev(temp)` — iteration from deepest depth to shallowest.

```r
# R
temp <- split(seq(node)[!is.leaf], depth[!is.leaf])
for (i in rev(temp))
    x[i] <- 0.5 * (x[left.child[i]] + x[right.child[i]])
```

**Python Equivalent:**

```python
import numpy as np
from collections import defaultdict

# Assume:
#   is_leaf      : np.ndarray of bool, shape (n,)
#   depth        : np.ndarray of int,  shape (n,)
#   x, left_child, right_child : np.ndarray, shape (n,)

n = len(node)
indices = np.arange(n)  # 0-based

# R: seq(node)[!is.leaf]  and  depth[!is.leaf]
non_leaf_indices = indices[~is_leaf]    # 0-based positions of non-leaf nodes
non_leaf_depths  = depth[~is_leaf]

# R: split(seq(node)[!is.leaf], depth[!is.leaf])
temp = defaultdict(list)
for idx, d in zip(non_leaf_indices, non_leaf_depths):
    temp[d].append(idx)
temp = {d: np.array(v) for d, v in sorted(temp.items())}

# R: for (i in rev(temp)) — iterate from deepest to shallowest
for d in sorted(temp.keys(), reverse=True):
    i = temp[d]   # numpy array of 0-based indices
    x[i] = 0.5 * (x[left_child[i]] + x[right_child[i]])
```

**Explanation:**

| R | Python |
|---|---|
| `!is.leaf` (logical negation) | `~is_leaf` (bitwise NOT on boolean numpy array) |
| `seq(node)[!is.leaf]` | `indices[~is_leaf]` — numpy boolean fancy indexing |
| `depth[!is.leaf]` | `depth[~is_leaf]` — same boolean mask applied to depth |
| `rev(temp)` iterates the list in reverse | `sorted(temp.keys(), reverse=True)` iterates depth keys from largest to smallest |
| `x[left.child[i]]` — R named vector, 1-based | `x[left_child[i]]` — numpy array, 0-based; R's `.` in names becomes `_` in Python |

The mask filtering (`!is.leaf` / `~is_leaf`) translates directly with numpy boolean indexing. The reversal of iteration order (`rev(temp)` / `reverse=True`) ensures parent x-coordinates are assigned only after both children have been placed, which is the same bottom-up traversal in both languages.

---

### 4.3 Reusable Helper Function

Because the same pattern appears twice in `rpartco`, it is idiomatic to extract it as a helper in the Python translation:

```python
import numpy as np
from collections import defaultdict
from typing import Dict

def split_indices_by_group(indices: np.ndarray, groups: np.ndarray) -> Dict[int, np.ndarray]:
    """
    Python equivalent of R's split(x, f) when x is a positional index vector
    and f is an integer grouping vector of the same length.

    Returns an ordered dict (sorted by group key ascending) mapping each
    unique group value to a numpy array of the corresponding indices.

    Parameters
    ----------
    indices : np.ndarray of int
        0-based positional indices to be partitioned.
    groups : np.ndarray of int
        Group label for each index; same length as `indices`.

    Returns
    -------
    dict[int, np.ndarray]
        Keys are unique group values in ascending order.
        Values are numpy arrays of 0-based indices belonging to that group.
    """
    bucket: dict = defaultdict(list)
    for idx, g in zip(indices, groups):
        bucket[g].append(idx)
    return {g: np.array(v) for g, v in sorted(bucket.items())}


# Usage 1 (line 29 equivalent):
n = len(node)
temp = split_indices_by_group(np.arange(n), depth)
depth_levels = sorted(temp.keys())
for d in depth_levels[1:]:
    i = temp[d]
    # ... process i ...

# Usage 2 (line 60 equivalent):
non_leaf_mask = ~is_leaf
temp = split_indices_by_group(np.arange(n)[non_leaf_mask], depth[non_leaf_mask])
for d in sorted(temp.keys(), reverse=True):
    i = temp[d]
    # ... process i ...
```
