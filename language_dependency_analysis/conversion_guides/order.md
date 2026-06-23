# Conversion Guide: `order` in R

---

## 1. Overview of `order` in R

`order(...)` is a base R function that returns a permutation of indices — an integer vector — which, when used to subscript the input vector, places its elements in ascending (or descending) sorted order.

Key characteristics:

- **Input:** One or more atomic vectors (numeric, integer, character, logical, etc.). Multiple vectors are used for tie-breaking, exactly like SQL `ORDER BY col1, col2`.
- **Output:** An integer vector of the same length as the input, containing 1-based positional indices.
- **Default behaviour:** Ascending order (`decreasing = FALSE`).
- **Ties:** Stable — tied elements retain their original relative order.
- **NA handling:** `NA` values are placed last by default (`na.last = TRUE`).

`order` is fundamentally different from `sort`: `sort` returns the sorted values themselves, while `order` returns the indices needed to produce those sorted values. To retrieve sorted values you write `x[order(x)]`; to reorder a second vector by the sorted positions of a first you write `y[order(x)]`.

---

## 2. Contextual Usage Analysis

**Source file:** `/groups/jli9/Yufei/python-rpart/rpart/R/summary.rpart.R`
**Function:** `summary.rpart`
**Line 38:**

```r
rows <- if (length(rows)) rows[order(id[rows])] else 1L
```

**Surrounding context (lines 32–40):**

```r
ff <- x$frame                                           # data frame: the rpart node frame
id <- as.integer(row.names(ff))                         # integer vector of node IDs (e.g. 1, 2, 3, 4, ...)
parent.id <- ifelse(id == 1L, 1L, id %/% 2L)           # integer vector: parent node ID for each node
parent.cp <- ff$complexity[match(parent.id, id)]        # numeric vector: complexity param of each parent
rows <- seq_along(id)[parent.cp > cp]                   # integer vector: 1-based indices where parent cp > threshold
rows <- if (length(rows)) rows[order(id[rows])] else 1L # reorder `rows` so that nodes are visited in node-ID order
is.leaf <- ff$var == "<leaf>"
```

**Data types involved:**

| Variable | R type | Description |
|---|---|---|
| `id` | `integer` vector | Node IDs extracted from row names of the frame data frame |
| `rows` | `integer` vector | 1-based index positions into `id` (and `ff`) for qualifying nodes |
| `id[rows]` | `integer` vector | The subset of node IDs for qualifying nodes |
| `order(id[rows])` | `integer` vector | Permutation of positions within `id[rows]` that sorts it ascending |
| `rows[order(id[rows])]` | `integer` vector | `rows` reordered so the corresponding node IDs are in ascending order |

**Pattern:** The call `rows[order(id[rows])]` is a classic R idiom for indirect sorting. Rather than sorting `rows` by its own values, it sorts `rows` by the values of a secondary vector (`id[rows]`). The net effect is that the qualifying row indices are reordered so that, when used to index into `ff`, the nodes are visited in ascending node-ID order (breadth-first tree traversal order).

The `else 1L` branch handles the degenerate case where no node passes the `cp` filter — falling back to node index 1 (the root).

---

## 3. Python Conversion Strategy

**Chosen library:** `numpy`

**Rationale:**

- `id` and `rows` are integer arrays derived from iterating over all nodes in the rpart frame — they are inherently vector-valued, not scalars.
- `numpy.argsort()` is the direct, idiomatic NumPy equivalent of R's `order()`: both return an array of indices that, when applied to the input array, produce an ascending-sorted result.
- `numpy` operates on zero-based integer arrays, which maps cleanly to Python's indexing model once the R 1-based index convention is adjusted.
- `scipy` and `pandas` offer no closer match for this purely integer-index permutation operation; `numpy.argsort` is the most concise and efficient choice.

**Key translation mapping:**

| R idiom | Python / NumPy equivalent |
|---|---|
| `order(v)` | `np.argsort(v)` |
| `v[order(v)]` | `v[np.argsort(v)]` (i.e. `np.sort(v)`) |
| `rows[order(id[rows])]` | `rows[np.argsort(id[rows])]` |
| 1-based integer index `rows` | 0-based integer index `rows` |
| `length(rows)` truthiness check | `len(rows) > 0` or just `if rows.size` |
| `else 1L` (root node, 1-based) | `else np.array([0])` (root node, 0-based) |

---

## 4. Step-by-Step Conversion Examples

### 4.1 Reordering Row Indices by a Secondary Integer Vector

**Locations:** `summary.rpart.R` — function `summary.rpart`

**Original R Context**

Types involved:
- `id`: `integer` vector, length = number of nodes in the tree
- `rows`: `integer` vector of 1-based positions into `id`
- `order(id[rows])`: `integer` permutation vector, same length as `rows`
- Result: `integer` vector — `rows` reordered so that `id[rows]` is ascending

```r
# id: integer vector of node IDs (1-based row indices)
# rows: integer vector of qualifying 1-based positions into id / ff

rows <- if (length(rows)) rows[order(id[rows])] else 1L
```

**Python Equivalent**

```python
import numpy as np

# id: np.ndarray of dtype int, shape (n_nodes,)  — node IDs
# rows: np.ndarray of dtype int, shape (k,)      — 0-based qualifying positions into id / ff

if rows.size > 0:
    rows = rows[np.argsort(id[rows])]
else:
    rows = np.array([0], dtype=int)
```

**Explanation**

1. **`order` -> `np.argsort`:** R's `order(v)` returns 1-based indices that sort `v` ascending. NumPy's `np.argsort(v)` does exactly the same thing but returns 0-based indices. The result is a permutation array that can be used immediately to subscript another array.

2. **Indirect sort pattern:** The expression `rows[order(id[rows])]` in R — and `rows[np.argsort(id[rows])]` in Python — is a two-level indirect sort. First `id[rows]` extracts the node-ID subset; then `argsort` produces the permutation of *positions within that subset* needed to sort those IDs; finally that permutation is applied to `rows` itself, yielding the original qualifying positions reordered by ascending node ID.

3. **Index base shift (1-based -> 0-based):** In R, `rows` holds 1-based integer positions (from `seq_along(id)`). In Python, the equivalent must be 0-based. When translating the broader function, `seq_along(id)` becomes `np.arange(len(id))`, producing 0-based positions from the start, so no explicit subtraction is needed at the `argsort` call site.

4. **`length(rows)` truthiness -> `.size`:** R's `if (length(rows))` is truthy when the vector is non-empty. The Python equivalent `if rows.size > 0` (or equivalently `if len(rows) > 0` if `rows` is a plain list) is the idiomatic check.

5. **Fallback scalar `1L` -> `np.array([0])`:** R's `else 1L` returns a length-1 integer scalar used as a 1-based index to the root node. In Python this becomes `np.array([0], dtype=int)` — a length-1 0-based index to the root, kept as an array so that all downstream code that iterates over or indexes with `rows` continues to work uniformly.

6. **Import:** Only `import numpy as np` is required; no additional dependencies are needed for this operation.
