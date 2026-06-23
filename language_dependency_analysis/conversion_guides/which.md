# Conversion Guide: `which` (R to Python)

---

## 1. Overview of `which` in R

`which()` is a base R function that returns the **integer indices** of all `TRUE` elements in a logical vector or array. It is the standard way to locate elements satisfying a condition when the downstream code needs positional indices rather than a filtered subset.

**Signature:**

```r
which(x, arr.ind = FALSE, useNames = TRUE)
```

| Argument   | Type              | Default | Description                                                                                  |
|------------|-------------------|---------|----------------------------------------------------------------------------------------------|
| `x`        | logical vector/array | —    | The logical condition to evaluate. `NA` values are treated as `FALSE` and are excluded.      |
| `arr.ind`  | logical           | `FALSE` | When `TRUE` and `x` is an array, returns a matrix of multi-dimensional indices.              |
| `useNames` | logical           | `TRUE`  | Whether to preserve names from the input in the output.                                      |

**Return value:** An integer vector whose values are the 1-based positions where `x` is `TRUE`. If no element is `TRUE`, an integer vector of length 0 is returned. `NA` values in `x` are silently omitted (treated as `FALSE`).

---

## 2. Contextual Usage Analysis

There is one distinct usage in the CSV dataset, found in `importance.R` inside the `importance` function (line 11):

```r
fpri <- which(ff$var != "<leaf>")
```

**Context:** `ff` is `fit$frame`, a data frame representing the nodes of the fitted rpart decision tree. The column `ff$var` is a factor (or character vector) holding the name of the split variable used at each node, with the special sentinel value `"<leaf>"` marking terminal nodes. The call produces `fpri`, an integer vector of 1-based row indices pointing to all non-leaf (internal split) nodes. This index vector is then used throughout the rest of `importance()` to subset rows of `ff` and rows of the `fit$splits` matrix.

**Data types involved:**
- **Input to `which`:** A logical vector produced by the inequality `ff$var != "<leaf>"`. Because `ff$var` may be a factor, R compares each level against the string `"<leaf>"` and returns a logical vector of the same length as `nrow(ff)`.
- **Output of `which`:** A named integer vector of 1-based indices (names come from row names of `ff`).

**Recurring pattern:** The result `fpri` is used with R's 1-based indexing (e.g., `ff$ncompete[fpri]`, `ff$dev[fpri]`, `ff$var[fpri]`), so the Python equivalent must yield 0-based indices to index into pandas/numpy structures.

---

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

Because `ff` (R's `fit$frame`) will be represented as a `pandas.DataFrame` in Python, the logical condition `ff["var"] != "<leaf>"` naturally produces a `pandas.Series` of booleans. NumPy's `np.where()` (or equivalently `numpy.nonzero()`) then extracts the 0-based integer indices of `True` positions, matching the vectorized nature of R's `which()`.

The key adjustment is the index base: R returns **1-based** indices; Python/NumPy returns **0-based** indices. No explicit offset is needed when the downstream code also uses Python's 0-based indexing consistently.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Filtering non-leaf nodes in `importance`

**Locations:** `importance.R` — function `importance`, line 11.

**Original R Context:**

- `ff` is a `data.frame`; `ff$var` is a factor/character column with values like `"age"`, `"income"`, `"<leaf>"`.
- `which(ff$var != "<leaf>")` returns a 1-based integer vector of positions where the node is not a leaf.

```r
# Generalized R snippet
ff <- fit$frame                          # data.frame, one row per tree node
fpri <- which(ff$var != "<leaf>")       # integer vector of 1-based non-leaf indices

# Downstream use (1-based subsetting)
ff$ncompete[fpri]
ff$dev[fpri]
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# ff is a pandas DataFrame equivalent of fit$frame
# ff["var"] is a Series of strings/categorical values
mask = ff["var"] != "<leaf>"            # boolean Series, same length as ff
fpri = np.where(mask)[0]               # 0-based integer ndarray of non-leaf indices

# Downstream use (0-based indexing)
ff["ncompete"].iloc[fpri]
ff["dev"].iloc[fpri]
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `ff$var != "<leaf>"` | `ff["var"] != "<leaf>"` | Both produce a boolean vector/Series of the same length as the data. |
| `which(logical_vec)` | `np.where(boolean_series)[0]` | `np.where` with a single argument returns a tuple; `[0]` extracts the first (and only) element, which is the array of 0-based indices. |
| 1-based index usage `ff$col[fpri]` | 0-based `.iloc[fpri]` | R indices are 1-based; Python indices are 0-based. Use `.iloc` for positional indexing on a pandas Series/DataFrame. |
| `NA` in logical vector treated as `FALSE` | `NaN`/`pd.NA` in boolean Series is `False` in `np.where` | Behavior matches automatically: `np.where` treats `NaN`/`NA` as falsy when the boolean mask is constructed via standard comparisons. |

**Alternative using pandas directly** (when only a boolean mask is needed for subsetting, not the indices themselves):

```python
# If only filtered rows are needed, skip index extraction entirely
ff_non_leaf = ff[ff["var"] != "<leaf>"]   # equivalent to ff[fpri, ] in R
```

Use `np.where` when the integer position array `fpri` is needed for cross-referencing another structure (e.g., a separate NumPy matrix like `fit$splits`), as is the case in the original `importance()` function.
