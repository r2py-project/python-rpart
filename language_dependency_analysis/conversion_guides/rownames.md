# Conversion Guide: `rownames` (R to Python)

---

## 1. Overview of `rownames` in R

`rownames()` retrieves or sets the row names of a matrix or data frame. When called with a single argument it is a getter, returning a character vector of length equal to the number of rows in the object. When called as `rownames(x) <- value` it is a setter.

Typical signature:

```r
rownames(x)
```

- **Input:** `x` — a matrix or data frame (or any 2-D object that supports the `dimnames` attribute).
- **Output:** A character vector of length `nrow(x)`, or `NULL` if no row names have been set.

Row names in R serve as a labelling mechanism; they are stored as the first element of the `dimnames` list attached to a matrix, and as the `rownames` attribute of a data frame.

---

## 2. Contextual Usage Analysis

All six occurrences in the CSV are read-only (getter) calls. They fall into two structurally distinct patterns:

### Pattern A — Row names of the predictor matrix `x` / `X`

Found in `pred.rpart.R` (lines 7 and 29) and `xpred.rpart.R` (lines 138 and 142). In every case the object is a numeric matrix whose rows represent observations. The returned character vector is used either:

- as the `names` attribute of a length-`n` prediction vector (line 7 and 29 of `pred.rpart.R`), or
- as `dimnames` labels when constructing an array or matrix of cross-validated predictions (lines 138 and 142 of `xpred.rpart.R`).

### Pattern B — Row names of the splits matrix `fit$splits` / `x$splits`

Found in `pred.rpart.R` (line 13) and `summary.rpart.R` (line 43). `fit$splits` / `x$splits` is a numeric matrix where each row represents one split in the decision tree and the row name is the variable name associated with that split. The returned character vector is used for:

- index lookup via `match()` to map variable names to column positions (line 13 of `pred.rpart.R`),
- label lookup when printing node summaries (line 43 of `summary.rpart.R`).

In both patterns the return value is always a plain character vector (or `None`/`None`-equivalent if no row names exist); no arithmetic is performed on it.

---

## 3. Python Conversion Strategy

The natural Python equivalent depends on the container type holding the data:

| R object type | Likely Python equivalent | How row names are stored |
|---|---|---|
| numeric matrix (observations x features) | `numpy.ndarray` with a `pandas.DataFrame` wrapper | `pandas.DataFrame.index` |
| named matrix with meaningful row labels | `pandas.DataFrame` | `pandas.DataFrame.index` |

Because rpart's predictor matrices carry meaningful observation identifiers as row names (used as output labels), and the splits matrix carries variable names as row names (used for look-up), the cleanest Python translation is to represent both objects as `pandas.DataFrame`. This makes row-name retrieval a direct `.index` property access (returning a `pandas.Index`, which behaves like an array of labels).

When the downstream code only needs the labels as a plain list or numpy array, `.index.tolist()` or `.index.to_numpy()` can be used.

**Primary library:** `pandas` (backed by `numpy` where array output is required).

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Row names of the predictor matrix used as output labels

**Locations:**
- `pred.rpart.R`, function `pred.rpart`, lines 7 and 29
- `xpred.rpart.R`, function `xpred.rpart`, lines 138 and 142

**Original R Context:**

`x` / `X` is a numeric matrix of shape `(n_obs, n_features)`. Row names are a character vector of length `n_obs` used to name the output vector or to supply `dimnames` to an output array/matrix.

```r
# line 7 – names a 1-element prediction vector for a root-only tree
return(structure(rep(1, nrow(x)), names = rownames(x)))

# line 29 – names the final prediction vector
names(temp) <- rownames(x)

# line 138 – supplies row-dimension labels to a 3-D array
temp <- array(pred, dim = c(numresp, length(cp), nrow(X)),
              dimnames = list(NULL, format(cp), rownames(X)))

# line 142 – supplies row labels to a 2-D matrix
matrix(pred, nrow = nrow(X), byrow = TRUE,
       dimnames = list(rownames(X), format(cp)))
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# ---------------------------------------------------------------
# Assume X is a pandas DataFrame: rows = observations (with
# meaningful index labels), columns = feature names.
# ---------------------------------------------------------------

# Equivalent of rownames(X)
row_labels = X.index                   # pandas Index (array-like)
row_labels_list = X.index.tolist()     # plain Python list of strings

# --- line 7 equivalent: root-only tree, return a Series of ones ---
n_obs = len(X)
temp = pd.Series(np.ones(n_obs), index=X.index)

# --- line 29 equivalent: name an ndarray result ---
# If temp is a plain numpy array:
result = pd.Series(temp_array, index=X.index)

# --- line 138 equivalent: 3-D array with labelled last axis ---
# pred is a flat numpy array; numresp, n_cp = scalar ints
temp_3d = pred_array.reshape((numresp, n_cp, n_obs))
# Axis labels are best captured by converting to xarray or by
# storing the label list separately; pure numpy does not hold labels:
row_labels_np = X.index.to_numpy()    # numpy array of row name strings

# --- line 142 equivalent: 2-D DataFrame ---
result_df = pd.DataFrame(
    pred_array.reshape(n_obs, n_cp),   # byrow=TRUE -> reshape row-major
    index=X.index,
    columns=cp_labels,                 # equivalent of format(cp)
)
```

**Explanation:**

- `X.index` is the direct counterpart of `rownames(X)`. It is a `pandas.Index` object that can be iterated, sliced, or converted to a list/numpy array as needed.
- `pd.Series(..., index=X.index)` replicates R's `names(temp) <- rownames(x)` in one step.
- R's `matrix(..., dimnames = list(rownames(X), ...))` maps to `pd.DataFrame(..., index=X.index, columns=...)`.
- R's 3-D `array` with `dimnames` has no direct pandas equivalent; the row-name vector can be stored as a plain list (`X.index.tolist()`) and later used to label a `pd.DataFrame` after collapsing one dimension.
- `np.ones(n_obs)` instead of `math.prod` is used to keep operations vectorised, consistent with R's `rep(1, nrow(x))`.

---

### 4.2 Pattern B — Row names of the splits matrix used as variable-name labels

**Locations:**
- `pred.rpart.R`, function `pred.rpart`, line 13
- `summary.rpart.R`, function `summary.rpart`, line 43

**Original R Context:**

`fit$splits` / `x$splits` is a numeric matrix where each row corresponds to one split in the tree. The row name of each row is the name of the predictor variable involved in that split. The returned character vector is used for:

- index look-up (`match`) to find a variable's column position in the predictor matrix (line 13),
- label look-up to print split descriptions (line 43).

```r
# line 13 – find column positions of split variables in x
vnum <- match(rownames(fit$splits), colnames(x))

# line 43 – store split variable names for later printing
sname <- rownames(x$splits)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# ---------------------------------------------------------------
# Assume splits is a pandas DataFrame whose index holds the
# variable names (one row per split).
# Assume x (predictor matrix) is also a pandas DataFrame.
# ---------------------------------------------------------------

# --- line 13 equivalent: find column positions of split variables ---
split_var_names = fit_splits.index.tolist()        # list of variable name strings
col_names       = x.columns.tolist()

# Option 1: returns a list of integer positions (-1 when not found,
#           matching R's NA behaviour for missing variables)
vnum = [col_names.index(v) if v in col_names else -1
        for v in split_var_names]

# Option 2: pandas-idiomatic index alignment
vnum_series = pd.Index(col_names).get_indexer(split_var_names)
# vnum_series[i] == -1 when the variable is not present (analogous to NA)

if any(v == -1 for v in vnum_series):
    raise ValueError("Tree has variables not found in new data")

# --- line 43 equivalent: retrieve split variable names as a list ---
sname = x_splits.index.tolist()   # list of strings, used for printing
```

**Explanation:**

- `fit$splits` in R is a named matrix; in Python it is naturally a `pandas.DataFrame` with the split variable name stored in `df.index`.
- `rownames(fit$splits)` becomes `fit_splits.index.tolist()` to obtain a plain list of strings, or simply `fit_splits.index` when a `pandas.Index` is sufficient.
- R's `match(rownames(fit$splits), colnames(x))` maps to `pd.Index(col_names).get_indexer(split_var_names)`. This returns `-1` for unmatched values, which directly replaces R's `NA` in the subsequent `is.na(vnum)` check.
- `sname` (line 43) is used purely as a label vector; `x_splits.index.tolist()` is the cleanest equivalent for downstream string formatting.
