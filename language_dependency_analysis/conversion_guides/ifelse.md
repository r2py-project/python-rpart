# Conversion Guide: `ifelse` in R (rpart package)

---

## 1. Overview of `ifelse` in R

`ifelse` is R's vectorized conditional function. Its signature is:

```r
ifelse(test, yes, no)
```

- **`test`**: A logical vector (or any object coercible to one). Each element is evaluated independently.
- **`yes`**: Values to return where `test` is `TRUE`. Recycled to the length of `test`.
- **`no`**: Values to return where `test` is `FALSE`. Recycled to the length of `test`.
- **Return value**: A vector of the same length as `test`, where each position is filled from `yes` if `test[i]` is `TRUE`, or from `no` if `test[i]` is `FALSE`. The result type is determined by the types of `yes` and `no`.

Critical properties:
- It is **fully vectorized**: it evaluates the condition element-by-element across an entire array in a single call.
- It **always evaluates both** `yes` and `no` in full before selecting, meaning side effects in either branch will always execute (unlike scalar `if/else`).
- When `test` contains `NA`, the corresponding result element is also `NA`.
- Unlike scalar `if/else`, it cannot be used as a control-flow statement; it only selects values.

---

## 2. Contextual Usage Analysis

Across the 13 CSV rows drawn from five source files, `ifelse` is used exclusively as a **value-selection function on arrays/vectors** — never as a scalar branch. The data types and patterns observed are:

**Pattern A — Integer vector mapping (rpart.R, summary.rpart.R, rpartco.R):**
`test` is an integer vector; `yes` and `no` are integer scalars or integer array lookups. The result is an integer vector used downstream for indexing or arithmetic.

**Pattern B — String label selection (labels.rpart.R):**
`test` is a logical vector derived from an integer column (`ncat`); `yes` and `no` are string literals. Results are character vectors used to build split-label strings via `paste0`. Two of these calls are nested inside a subscript `[ncat < 2L]` to further subset the result.

**Pattern C — Numeric fallback / guard value (residuals.rpart.R):**
`test` is a logical vector from a floating-point comparison (`expect == 0`); the result replaces zeroes with a small epsilon (`0.0001`) to guard against `log(0)`. The vector has the same length as the observation array.

**Pattern D — Scalar-like single-element selection (rpartco.R, summary.rpart.R loop body):**
Inside a `for` loop iterating over individual indices, `ifelse` operates on a single logical value at a time, making it effectively scalar. In `rpartco.R` line 47, `temp2` and `fudge` are scalar doubles inside the loop. In `summary.rpart.R` line 35, `id` is an integer vector but the pattern is a clean vectorized operation.

**Pattern E — Nested `ifelse` for three-way string selection (summary.rpart.R lines 59–60):**
Two `ifelse` calls are nested to implement a three-way string choice (`temp >= 2L` → `","`, `temp == 1L` → `" to the right,"`, else → `" to the left, "`). Both `test` vectors are integer comparison results over the same array.

---

## 3. Python Conversion Strategy

**Primary equivalent: `numpy.where(condition, x, y)`**

`numpy.where` is the direct structural counterpart to R's `ifelse`:
- It accepts arrays for all three arguments.
- It is element-wise and fully vectorized.
- It returns an `ndarray` of the same shape as `condition`.
- It handles mixed scalar/array broadcasting identically to R's recycling.

**When to use `numpy.where`:** Any context where the `test`, `yes`, or `no` operands are NumPy arrays (or Pandas Series), or where the result feeds into further array operations. This covers the overwhelming majority of cases in this codebase.

**When to use a Python ternary (`x if cond else y`):** Only when all three operands are confirmed scalars (Python `int`, `float`, or `str`) and the result is used as a scalar. In this rpart codebase, the `rpartco.R` line 47 usage inside the loop body qualifies — `temp2`, `fudge`, and `haskids` are all scalar quantities within each loop iteration.

**Nested `ifelse`:** Use `numpy.where` nested directly, mirroring R's nesting: `np.where(cond1, val1, np.where(cond2, val2, val3))`.

**Pandas context:** When operating on a `pandas.Series`, `numpy.where` still applies cleanly since Series is array-backed. Alternatively, `pandas.Series.where` or `pandas.Series.mask` can be used, but `numpy.where` is simpler and more idiomatically parallel to R.

---

## 4. Step-by-Step Conversion Examples

### 4.1 String label selection for split direction (Pattern B)

**Locations:** `labels.rpart.R`, function `labels.rpart`, lines 46–47

**Original R Context:**

`ncat` is an integer vector extracted from `object$splits[irow, 2L]`, where each element encodes the number of categories for a split variable. Negative values indicate a "less-than" direction for continuous splits. `temp1` and `temp2` are character vectors used to form left-split and right-split labels.

```r
# ncat: integer vector, length = number of non-leaf splits
# Selects directional label strings element-wise
temp1 <- (ifelse(ncat < 0, "< ", ">="))[ncat < 2L]
temp2 <- (ifelse(ncat < 0, ">=", "< "))[ncat < 2L]
lsplit[ncat < 2L] <- paste0(temp1, cutpoint)
rsplit[ncat < 2L] <- paste0(temp2, cutpoint)
```

**Python Equivalent:**

```python
import numpy as np

# ncat: np.ndarray of dtype int, shape (n_splits,)
# cutpoint: np.ndarray of str, shape (n_continuous_splits,)

continuous_mask = ncat < 2
temp1_full = np.where(ncat < 0, "< ", ">=")
temp2_full = np.where(ncat < 0, ">=", "< ")
temp1 = temp1_full[continuous_mask]
temp2 = temp2_full[continuous_mask]
lsplit[continuous_mask] = np.char.add(temp1, cutpoint)
rsplit[continuous_mask] = np.char.add(temp2, cutpoint)
```

**Explanation:** `np.where(ncat < 0, "< ", ">=")` maps directly to `ifelse(ncat < 0, "< ", ">=")`. The outer subscript `[ncat < 2L]` in R becomes a boolean-mask index applied after the `np.where` call. String concatenation with `paste0` maps to `np.char.add` for element-wise string addition on NumPy string arrays.

---

### 4.2 Prefix string for categorical vs. continuous splits (Pattern B, variant)

**Locations:** `labels.rpart.R`, function `labels.rpart`, lines 93–94

**Original R Context:**

`ncat` is the same integer vector as above. Here the `ifelse` prepends `"="` for categorical splits (`ncat >= 2`) and an empty string for continuous ones, then concatenates with the already-built `lsplit`/`rsplit`.

```r
# ncat: integer vector
# lsplit, rsplit: character vectors of split labels
lsplit <- paste0(ifelse(ncat < 2L, "", "="), lsplit)
rsplit <- paste0(ifelse(ncat < 2L, "", "="), rsplit)
```

**Python Equivalent:**

```python
import numpy as np

# ncat: np.ndarray, dtype int
# lsplit, rsplit: np.ndarray, dtype str (or list of str)

prefix = np.where(ncat < 2, "", "=")
lsplit = np.char.add(prefix, lsplit)
rsplit = np.char.add(prefix, rsplit)
```

**Explanation:** This is a straightforward scalar-string broadcast via `np.where`. Both `yes` and `no` are string literals, so NumPy broadcasts them across the length of `ncat`. The `paste0` concatenation becomes `np.char.add`.

---

### 4.3 Numeric guard value to prevent log(0) (Pattern C)

**Locations:** `residuals.rpart.R`, function `residuals.rpart`, line 34

**Original R Context:**

`expect` is a numeric vector of expected event counts (`lambda * time`). When any element is zero, `log(0)` would produce `-Inf`, so `ifelse` substitutes `0.0001` for those positions. `temp` is then used as the denominator in Pearson residuals and the argument to `log` in deviance residuals.

```r
# expect: numeric vector (lambda * time), length = n_observations
# temp replaces zeroes with 0.0001 to guard log(0)
temp <- ifelse(expect == 0, 0.0001, 0)
# ...used as:
pearson  = (events - expect) / sqrt(temp)
deviance = sign(events - expect) * sqrt(2 * (events * log(events / temp) - (events - expect)))
```

Note: `temp` is `0.0001` where `expect == 0`, and `0` otherwise. The subsequent `log(events/temp)` and `sqrt(temp)` are only meaningful in the Poisson/survival deviance/Pearson paths where `expect == 0` would be the guard case.

**Python Equivalent:**

```python
import numpy as np

# expect: np.ndarray, dtype float64, shape (n_observations,)
# events: np.ndarray, dtype float64, shape (n_observations,)

temp = np.where(expect == 0, 0.0001, 0.0)

pearson_resid  = (events - expect) / np.sqrt(temp)
deviance_resid = (np.sign(events - expect) *
                  np.sqrt(2.0 * (events * np.log(events / temp) - (events - expect))))
```

**Explanation:** `np.where(expect == 0, 0.0001, 0.0)` is a direct element-wise substitution. The comparison `expect == 0` produces a boolean array; NumPy broadcasts the scalar alternatives `0.0001` and `0.0` across it. Downstream `np.sqrt` and `np.log` are the NumPy equivalents of R's vectorized `sqrt` and `log`.

---

### 4.4 Safe index remapping for tree node splits (Pattern A)

**Locations:** `rpart.R`, function `rpart`, lines 231–232

**Original R Context:**

`index` is an integer vector extracted from `rpfit$inode[, 2L]`, pointing to the first split row for each tree node. Leaf nodes have `index == 0L` (no split). To avoid out-of-bounds access into `rpfit$isplit`, zero entries are temporarily mapped to `1L` for the array lookup, and then `svar` is forced to `0L` for those positions (the `"<leaf>"` entry in `tname` is at index 0).

```r
# index: integer vector, length = n_nodes; 0 for leaf nodes
# rpfit$isplit: integer matrix; column 1 holds variable indices
temp <- ifelse(index == 0L, 1L, index)           # safe fallback index
svar <- ifelse(index == 0L, 0L, rpfit$isplit[temp, 1L])  # 0 = leaf sentinel
```

**Python Equivalent:**

```python
import numpy as np

# index: np.ndarray, dtype int, shape (n_nodes,)
# isplit: np.ndarray, dtype int, shape (n_splits, ...) — column 0 = variable index (0-based)

leaf_mask = (index == 0)
safe_index = np.where(leaf_mask, 0, index - 1)      # convert to 0-based, leaves use row 0 safely
svar = np.where(leaf_mask, 0, isplit[safe_index, 0])
```

**Explanation:** In R, `rpfit$isplit[temp, 1L]` uses 1-based indexing; in Python the column index becomes `0`. The two-step pattern — first build a safe index vector, then use it for the array lookup — is reproduced identically with two `np.where` calls. The `leaf_mask` boolean array gates both operations. Because `np.where` evaluates both branches eagerly, using `safe_index` (which replaces zeros with a valid row index `0`) prevents any out-of-bounds access before the mask is applied.

---

### 4.5 NA-to-zero fill for class weight counts (Pattern C, variant)

**Locations:** `rpart.class.R`, function `rpart.class`, line 9

**Original R Context:**

`counts` is the result of `tapply(wt, factor(y, levels=1:numclass), sum)` — a named numeric vector of per-class weight sums. If a class has no observations, `tapply` returns `NA` for that class. The `ifelse` replaces those `NA` values with `0`.

```r
# counts: numeric vector, length = numclass; may contain NA for empty classes
counts <- ifelse(is.na(counts), 0, counts)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# Option 1: using numpy (counts is a np.ndarray or can contain np.nan)
counts = np.where(np.isnan(counts), 0.0, counts)

# Option 2: using pandas (counts is a pd.Series from groupby/reindex)
counts = counts.fillna(0.0)
```

**Explanation:** R's `NA` maps to `np.nan` in floating-point NumPy arrays. `np.isnan` is the equivalent of `is.na` for floats. `np.where(np.isnan(counts), 0.0, counts)` is the direct structural translation. When `counts` is already a Pandas Series (common when using `groupby().sum()` with `reindex` to ensure all classes appear), `fillna(0.0)` is more idiomatic and concise. Both are correct; choose based on whether the upstream computation yields an `ndarray` or a `Series`.

---

### 4.6 Sibling node index computation (Pattern A, scalar-within-loop)

**Locations:** `rpartco.R`, function `rpartco`, line 31

**Original R Context:**

`node` is a numeric vector of tree node indices (using binary-heap numbering: left child = `2*parent`, right child = `2*parent+1`). Even-numbered nodes are right children; odd-numbered nodes are left children. The `ifelse` computes the sibling of each node: if odd, subtract 1 to get the even (right) sibling; if even, add 1 to get the odd (left) sibling.

```r
# node: numeric vector of node indices (binary-heap numbering)
sibling <- match(ifelse(node %% 2L, node - 1L, node + 1L), node)
```

**Python Equivalent:**

```python
import numpy as np

# node: np.ndarray, dtype int, shape (n_nodes,)

sibling_node = np.where(node % 2 == 1, node - 1, node + 1)
# R's match(x, table) → equivalent: build a lookup
node_to_idx = {v: i for i, v in enumerate(node)}
sibling = np.array([node_to_idx[s] for s in sibling_node])
```

**Explanation:** `node %% 2L` in R tests parity (non-zero = odd = `TRUE`). In Python, `node % 2 == 1` produces the equivalent boolean array. `np.where` then selects `node - 1` (sibling is even) or `node + 1` (sibling is odd). R's `match(x, table)` returns 1-based positions; the Python equivalent builds an index lookup dictionary and constructs the result array (0-based). If `node` is a Pandas Series, `pd.Index(node).get_indexer(sibling_node)` achieves the same result more efficiently.

---

### 4.7 Fudge-factor guard for near-zero deviance splits (Pattern D — scalar-within-loop)

**Locations:** `rpartco.R`, function `rpartco`, line 47

**Original R Context:**

Inside a `for` loop over depth levels, `temp2` and `fudge` are scalar doubles. `haskids` is a scalar logical. The `ifelse` guards against splits with near-zero deviance gain by replacing `temp2` with a minimum `fudge` amount to keep the tree plot readable.

```r
# Inside for loop: i is a vector of indices at one depth level
# temp2: scalar double — deviance gain for this split
# fudge: scalar double — minimum branch length
# haskids: scalar logical — whether this node has children
y[i] <- y[parent[i]] - ifelse(temp2 <= fudge & haskids, fudge, temp2)
```

**Python Equivalent:**

```python
# Inside a for loop where i is an array of indices at one depth level
# temp2: float scalar
# fudge: float scalar
# haskids: bool scalar

branch_length = fudge if (temp2 <= fudge and haskids) else temp2
y[i] = y[parent[i]] - branch_length
```

**Explanation:** This is one of the two cases in the codebase where a Python ternary is more appropriate than `np.where`. Both `temp2` and `fudge` are scalar values computed earlier in the loop body, and `haskids` is a single boolean. A ternary `fudge if (temp2 <= fudge and haskids) else temp2` is cleaner, avoids unnecessary NumPy overhead, and reads more naturally. Note the use of Python's `and` instead of R's `&` for scalar boolean logic.

---

### 4.8 Parent node ID lookup (Pattern A)

**Locations:** `summary.rpart.R`, function `summary.rpart`, line 35

**Original R Context:**

`id` is an integer vector of tree node IDs from `row.names(ff)`. In binary-heap numbering, the parent of node `n` is `n %/% 2`, except for the root node (`id == 1L`) which has no parent and maps to itself.

```r
# id: integer vector of node IDs (binary-heap numbering)
parent.id <- ifelse(id == 1L, 1L, id %/% 2L)
parent.cp <- ff$complexity[match(parent.id, id)]
```

**Python Equivalent:**

```python
import numpy as np

# id: np.ndarray, dtype int, shape (n_nodes,)
# ff_complexity: np.ndarray of complexity values aligned to id

parent_id = np.where(id == 1, 1, id // 2)
# match(parent.id, id): find position of each parent_id in id array
node_to_idx = {v: i for i, v in enumerate(id)}
parent_cp = ff_complexity[np.array([node_to_idx[p] for p in parent_id])]
```

**Explanation:** `id %/% 2L` is integer division, which maps directly to Python's `//` operator on integer arrays. `np.where(id == 1, 1, id // 2)` handles the root-node special case identically to the R code. The subsequent `match` call uses the same dictionary-lookup pattern described in Example 4.6.

---

### 4.9 Nested `ifelse` for three-way string suffix selection (Pattern E)

**Locations:** `summary.rpart.R`, function `summary.rpart`, lines 59–60

**Original R Context:**

`temp` is an integer vector holding the `ncat` column of `x$splits`. Three distinct string suffixes are appended to `cuts` based on three ranges of `temp`: `>= 2` (categorical), `== 1` (right split), or neither (left split). Lines 59 and 60 together implement a three-way selection:

```r
# temp: integer vector (ncat column of splits matrix)
# cuts: character vector being built up
cuts <- paste0(cuts, ifelse(temp >= 2L, ",",
                            ifelse(temp == 1L, " to the right,", " to the left, ")))
```

**Python Equivalent:**

```python
import numpy as np

# temp: np.ndarray, dtype int (ncat column)
# cuts: np.ndarray or list of str

suffix = np.where(temp >= 2, ",",
                  np.where(temp == 1, " to the right,", " to the left, "))
cuts = np.char.add(cuts, suffix)
```

**Explanation:** Nested `np.where` calls directly mirror R's nested `ifelse`. The outer condition `temp >= 2` maps to categorical splits (comma suffix); the inner `temp == 1` maps to right-direction continuous splits; the fallback `" to the left, "` handles `temp <= 0` (left-direction splits). NumPy evaluates all three string arrays upfront and then selects element-wise, matching R's eager-evaluation semantics. String concatenation uses `np.char.add` in place of `paste0`.
