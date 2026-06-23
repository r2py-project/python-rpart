# Conversion Guide: `colnames` (R to Python)

---

## 1. Overview of `colnames` in R

`colnames` is a base R function that gets or sets the column names of a matrix-like object (matrix, data frame, or any 2-dimensional object that supports dimnames).

**Signatures:**
```r
colnames(x)                 # getter: returns a character vector of column names
colnames(x) <- value        # setter: assigns a character vector of column names
```

**Inputs:**
- `x`: A matrix or 2-dimensional array. In R, `colnames` reads the second element of `dimnames(x)`.

**Outputs:**
- Getter form: a character vector of column names (length equal to `ncol(x)`), or `NULL` if no names are set.
- Setter form: modifies `x` in-place (via R's copy-on-modify semantics) by updating its column names.

`colnames` is strictly for 2-dimensional structures. For data frames, `names()` and `colnames()` are interchangeable, but `colnames` is the canonical choice for matrices.

---

## 2. Contextual Usage Analysis

Across the CSV rows, `colnames` appears in four R source files and is used in two distinct roles:

**Role 1 — Getter (reading column names):**
- `pred.rpart.R` line 13: `colnames(x)` retrieves the column names of the predictor matrix `x` so that `match()` can look up split-variable positions.
- `rpart.R` line 87: `colnames(X)` retrieves the column names of the predictor matrix `X` to match them against factor level names stored in `xlevels`.
- `rpart.R` line 184: `colnames(X)` retrieves the column names of `X` to build the `tname` character vector used as row labels for the `splits` matrix.
- `xpred.rpart.R` lines 55–56: `colnames(X)` is used twice within the same expression — first in `%in% colnames(X)` to filter `xlevels` keys, then in `match(names(xlevels), colnames(X))` to find the positional indices of factor variables.

**Role 2 — Setter (assigning column names):**
- `rpart.matrix.R` line 29: `colnames(X) <- sub("^`(.*)`", "\\1", colnames(X))` strips backtick quoting from column names that `model.matrix` introduces around variable names with special characters. The getter is nested inside the setter call here.

**Data types involved:**
- `x` / `X` in all cases is a numeric matrix (class `"matrix"` or `"rpart.matrix"`), produced either by `rpart.matrix()` or from `fit$x` stored on the fitted model.
- The return value of the getter is a character vector (`character`).
- The input `value` for the setter is a character vector derived from `sub()`.

**Recurring patterns:**
- The getter is always called on a 2-D numeric matrix, never on a data frame or higher-dimensional array.
- The setter pattern `colnames(X) <- f(colnames(X))` (apply a transformation to the existing names) appears exactly once.

---

## 3. Python Conversion Strategy

The natural Python equivalent is **`numpy`** (`numpy.ndarray`) for the matrix and the **`.columns`** attribute of a **`pandas.DataFrame`** for named column access, but the dominant pattern throughout rpart uses raw NumPy arrays together with a **separate Python list (or `numpy` array) of column names**.

Rationale:
- R matrices carry column names as metadata via `dimnames`. NumPy arrays do not natively carry named dimensions; column names must be tracked explicitly as a parallel list or stored on a `pandas.DataFrame`.
- All rpart usages treat `X` as a plain numeric 2-D array for computation (passed to C routines) and access `colnames(X)` only to look up positional indices. This maps cleanly to a Python list of strings kept alongside the NumPy array, or to `pandas.DataFrame.columns`.
- Where pandas DataFrames are used for `X`, `df.columns.tolist()` is the exact getter equivalent and `df.columns = new_names` is the exact setter equivalent — no import beyond pandas is needed.
- Where NumPy arrays are used and column names are stored as a separate Python list `col_names`, `col_names` is the getter and `col_names = new_names` is the setter.

**Chosen primary strategy:** maintain `X` as a `numpy.ndarray` together with a `list[str]` named `col_names` (mirroring R's dimnames), and use `pandas` I/O or construction to populate `col_names` when the matrix originates from a DataFrame or `model_matrix`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Getter — Match column names to a reference list

**Locations:**
- `pred.rpart.R`, function `pred.rpart`, line 13
- `rpart.R`, function `rpart`, line 87
- `rpart.R`, function `rpart`, line 184
- `xpred.rpart.R`, function `xpred.rpart`, lines 55–56

**Original R Context:**

`X` is a numeric matrix with column names set by `rpart.matrix`. The getter returns a `character` vector.

```r
# pred.rpart.R line 13
# x: numeric matrix, rows = observations, cols = predictor variables
# fit$splits row names are variable names; colnames(x) lists them in column order
vnum <- match(rownames(fit$splits), colnames(x))

# rpart.R line 87
# xlevels: named list of factor levels; colnames(X) used to find column positions
indx <- match(names(xlevels), colnames(X), nomatch = 0)

# rpart.R line 184
# Build a name lookup vector: "<leaf>" at position 1, then variable names
tname <- c("<leaf>", colnames(X))

# xpred.rpart.R lines 55-56
# Filter xlevels to only names present in X, then find their column positions
xlevels <- xlevels[names(xlevels) %in% colnames(X)]
cats[match(names(xlevels), colnames(X))] <- unlist(lapply(xlevels, length))
```

**Python Equivalent:**

```python
import numpy as np

# Assume X is a np.ndarray and col_names is a list[str] of column names
# with len(col_names) == X.shape[1]

# --- pred.rpart equivalent (line 13) ---
# split_names: list[str] of variable names from fit.splits index
vnum = [col_names.index(name) if name in col_names else None
        for name in split_names]
# Or using np.where for vectorized lookup:
vnum = np.array([col_names.index(name) for name in split_names])

# --- rpart equivalent (line 87) ---
# xlevels: dict mapping factor-variable names to their list of levels
indx = np.array([col_names.index(name) if name in col_names else -1
                 for name in xlevels.keys()])

# --- rpart equivalent (line 184) ---
# Build tname with "<leaf>" sentinel at position 0
tname = ["<leaf>"] + col_names

# --- xpred.rpart equivalent (lines 55-56) ---
# Filter xlevels to only keys present in col_names
xlevels = {k: v for k, v in xlevels.items() if k in col_names}
# Then find column positions and assign category counts
for name, levels in xlevels.items():
    cats[col_names.index(name)] = len(levels)
```

**Explanation:**
- R's `colnames(x)` returns a `character` vector; the Python analogue is a `list[str]` (or `np.ndarray` of dtype `object`) that travels alongside the matrix.
- R's `match(a, b)` returns 1-based indices; Python's `list.index()` returns 0-based indices — adjust downstream index arithmetic accordingly.
- R's `%in%` operator maps to a Python `in` membership test or `np.isin()` for vectorized checks.
- When `X` is a `pandas.DataFrame`, replace `col_names` with `X.columns.tolist()` for identical semantics without maintaining a separate list.

---

### 4.2 Setter with in-place name transformation

**Location:** `rpart.matrix.R`, function `rpart.matrix`, line 29

**Original R Context:**

`X` is the numeric matrix returned by `model.matrix(...)[, -1L, drop = FALSE]`. `model.matrix` in R wraps variable names that contain special characters in backtick pairs (e.g., `` `var name` ``). The assignment strips these backtick wrappers.

```r
# X: numeric matrix whose colnames may contain backtick-quoted names
# sub("^`(.*)`", "\\1", colnames(X)) removes leading/trailing backticks
colnames(X) <- sub("^`(.*)`", "\\1", colnames(X))
```

**Python Equivalent:**

```python
import re
import numpy as np

# Option A: col_names is a standalone list[str]
col_names = [re.sub(r'^`(.*)`$', r'\1', name) for name in col_names]

# Option B: X is a pandas DataFrame
import pandas as pd
X.columns = X.columns.str.replace(r'^`(.*)`$', r'\1', regex=True)
```

**Explanation:**
- R's `sub("^`(.*)`", "\\1", ...)` applies a regex substitution that strips backtick delimiters. The pattern `^`(.*)`$` matches a string that starts and ends with a backtick, capturing the content in group 1; `"\\1"` replaces the whole match with just the captured group.
- In Python, `re.sub(r'^`(.*)`$', r'\1', name)` is the exact equivalent. The `$` anchor is added explicitly (R's `sub` matches at the end of the string automatically when the pattern ends with a literal backtick there).
- The list comprehension form applies the substitution element-wise, mirroring R's automatic vectorization of `sub` over a character vector.
- For pandas DataFrames, `Series.str.replace(..., regex=True)` is the idiomatic vectorized equivalent, producing a new `Index` assigned back to `df.columns`.
- Note that `model.matrix` in R is typically replaced by `patsy.dmatrices` or `sklearn`-style feature engineering in Python. In the rpart Python port, the column name cleaning step should be applied immediately after constructing the design matrix, before passing it to any downstream C extension.
