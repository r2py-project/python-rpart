# Conversion Guide: `is.na` (R to Python)

---

## 1. Overview of `is.na` in R

`is.na(x)` tests each element of `x` for being `NA` (Not Available — R's missing-value sentinel). It returns a logical vector, matrix, or array of the same shape as `x`, with `TRUE` wherever an element is missing and `FALSE` elsewhere.

Key characteristics:

- Works element-wise on any R object: atomic vectors, matrices, data frames, lists.
- On a **data frame**, it returns a logical matrix of the same dimensions.
- On a **matrix**, it returns a logical matrix of identical dimensions.
- On a **scalar** or **length-1 vector**, it returns a single `TRUE`/`FALSE`.
- `NA` values can arise from arithmetic (e.g., `0/0`), coercion failures (e.g., `as.integer("abc")`), or explicit assignment.
- `pmatch()` returns `NA` when no unambiguous match is found, so `is.na(pmatch(...))` is the canonical way to detect a failed partial-match lookup.

---

## 2. Contextual Usage Analysis

Across the eleven call sites in the CSV, three semantically distinct patterns appear:

### Pattern A — Missing-value detection on a data frame (matrix result)

`is.na` is applied to an entire data frame or a column-subset of a data frame. The result is a boolean matrix that is then reduced row-wise (via matrix-multiplication with a ones vector) to decide which rows contain enough valid values to keep.

Locations: `na.rpart.R` lines 6, 9, 10.

### Pattern B — Element-wise NA test on a vector or matrix (boolean array)

`is.na` is applied to a plain numeric or integer vector/matrix. The resulting boolean vector is used directly in logical conditions or passed as an integer array to a C routine.

Locations: `pred.rpart.R` lines 14 and 28, `rpart.class.R` lines 7 and 9.

### Pattern C — Detecting a failed lookup (scalar boolean)

`pmatch()` returns `NA` when there is no unambiguous match. `is.na(pmatch(...))` collapses to a single `TRUE`/`FALSE` used in an `if` guard or `any(...)` check.

Locations: `residuals.rpart.R` line 11, `rpart.R` line 59, `rpart.exp.R` line 122, `snip.rpart.R` line 48.

---

## 3. Python Conversion Strategy

**Primary library: `numpy`** (`numpy.isnan` / boolean masks on `pandas` DataFrames).

Rationale:

- R's `NA` for floating-point data maps directly to IEEE 754 `NaN`, which `numpy.isnan` detects element-wise across arrays and matrices.
- R's `NA` for integer/character data is usually represented in Python as `None` inside object arrays, `pd.NA`, or `numpy.nan` cast to float; `pandas.isna` handles all of these uniformly.
- `pandas.isna` is the most direct drop-in when working with `pandas.DataFrame` objects (Pattern A), because it mirrors the shape-preserving, element-wise behaviour of R's `is.na` on data frames.
- For the failed-lookup pattern (Pattern C), Python's `None` is used in place of `NA`; a simple `value is None` check replaces `is.na`.

Import assumptions for all examples below:

```python
import numpy as np
import pandas as pd
```

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Missing-value detection on a data frame

**Locations:** `na.rpart.R` — `na.rpart`, lines 6, 9, 10.

**Original R context.**

`x` is a `data.frame`. `is.na(x)` produces a logical matrix; row sums are compared against the column count to decide which rows are complete enough to keep. When a response variable column index `yvar` is known, the predictors and the response are checked separately.

```r
# x is a data.frame; yvar is an integer column index (1-based)

# Case 1: no response variable — keep rows that have at least one non-NA predictor
xmiss <- is.na(x)                      # logical matrix, same shape as x
keep  <- (xmiss %*% rep(1, ncol(xmiss))) < ncol(xmiss)

# Case 2: separate predictor and response checks
xmiss <- is.na(x[-yvar])               # logical matrix, predictor columns only
ymiss <- is.na(x[[yvar]])              # logical vector (or matrix for multi-col response)
keep  <- ((xmiss %*% rep(1, ncol(xmiss))) < ncol(xmiss)) & !ymiss
```

**Python equivalent.**

`x` is a `pd.DataFrame`. `pd.isna(x)` returns a boolean DataFrame of identical shape. Row-wise summation replaces the `%*% rep(1, ncol(...))` trick.

```python
# x is a pd.DataFrame; yvar is a column name or 0-based integer index

# Case 1: no response variable
xmiss = pd.isna(x)                          # boolean DataFrame, same shape as x
keep  = xmiss.sum(axis=1) < x.shape[1]      # True where row has at least one non-NA

# Case 2: separate predictor and response checks
# yvar_col is the column name of the response; all others are predictors
predictor_cols = [c for c in x.columns if c != yvar_col]
xmiss = pd.isna(x[predictor_cols])
ymiss = pd.isna(x[yvar_col])               # boolean Series (scalar response)
keep  = (xmiss.sum(axis=1) < len(predictor_cols)) & ~ymiss
```

**Explanation.**

| R | Python |
|---|--------|
| `is.na(x)` on a data frame | `pd.isna(x)` — returns a boolean DataFrame |
| `%*% rep(1, ncol(xmiss))` | `.sum(axis=1)` — row-wise sum of booleans |
| `x[-yvar]` (drop column by 1-based index) | `x[predictor_cols]` or `x.drop(columns=[yvar_col])` |
| `x[[yvar]]` (select single column by 1-based index) | `x[yvar_col]` |
| `!ymiss` | `~ymiss` |

`pd.isna` is preferred over `np.isnan` here because a DataFrame may contain non-float columns (strings, categoricals) where `np.isnan` would raise a TypeError.

---

### 4.2 Pattern B — Element-wise NA test on a vector or matrix

**Locations:** `pred.rpart.R` — `pred.rpart`, lines 14 and 28; `rpart.class.R` — `rpart.class`, lines 7 and 9.

**Original R context.**

In `pred.rpart`, `vnum` is an integer vector produced by `match()`; `match` returns `NA` for unmatched elements. `is.na(vnum)` checks for unmatched split variables before passing the model to C. `is.na(x)` on the numeric predictor matrix `x` produces a logical matrix that is cast to integer and forwarded to a C routine.

```r
# vnum is an integer vector from match(); NA means variable not found
if (any(is.na(vnum)))
    stop("Tree has variables not found in new data")

# x is a numeric matrix; is.na produces an integer 0/1 matrix for C
as.integer(is.na(x))
```

In `rpart.class`, `y` is an integer vector of class labels; `counts` is a numeric vector produced by `tapply()` and may contain `NA` for empty classes.

```r
numclass <- max(y[!is.na(y)])           # ignore NA labels when finding max class
counts   <- ifelse(is.na(counts), 0, counts)  # replace NA counts with 0
```

**Python equivalent.**

`numpy.isnan` covers float arrays; use `pandas.isna` for mixed-type or integer arrays (where `numpy.isnan` would fail on non-float dtypes).

```python
# vnum is a numpy integer array; np.nan is used where match fails (represented as -1
# in the Python port, but shown here assuming NaN-carrying float array for fidelity)

# Guard: any unmatched variable?
if np.any(np.isnan(vnum)):
    raise ValueError("Tree has variables not found in new data")

# x is a 2-D numpy float array; produce integer 0/1 mask for downstream C call
x_missing = np.isnan(x).astype(np.int32)  # shape matches x

# For a 1-D float array that may contain NaN
y_valid = y[~np.isnan(y)]
numclass = int(np.max(y_valid))

# Replace NaN counts with 0 (counts is a numpy float array from np.bincount / groupby)
counts = np.where(np.isnan(counts), 0.0, counts)
```

**Explanation.**

| R | Python |
|---|--------|
| `is.na(vnum)` on integer vector | `np.isnan(vnum)` if float; `pd.isna(vnum)` for integer arrays with `pd.NA` |
| `any(is.na(...))` | `np.any(np.isnan(...))` |
| `as.integer(is.na(x))` | `np.isnan(x).astype(np.int32)` |
| `y[!is.na(y)]` | `y[~np.isnan(y)]` |
| `ifelse(is.na(counts), 0, counts)` | `np.where(np.isnan(counts), 0.0, counts)` |

Note on integer arrays: Python/NumPy integer dtypes (`int32`, `int64`) cannot store `NaN` natively. In the Python port of rpart, unmatched `match()` results are typically represented as `-1` (sentinel) rather than `NaN`, so the guard becomes `if np.any(vnum == -1)`. Use `pd.isna()` when working with nullable integer arrays (`pd.array(..., dtype="Int64")`).

---

### 4.3 Pattern C — Detecting a failed partial-match lookup

**Locations:** `residuals.rpart.R` — `residuals.rpart`, line 11; `rpart.R` — `rpart`, line 59; `rpart.exp.R` — `rpart.exp`, line 122; `snip.rpart.R` — `snip.rpart`, line 48.

**Original R context.**

R's `pmatch()` (partial string matching) and `match()` (exact lookup) return `NA` when no match is found. `is.na` on their result detects the failure.

```r
# residuals.rpart.R — type validation via match + is.na
if (is.na(match(type, c("usual", "pearson", "deviance"))))
    stop("Invalid type of residual")

# rpart.R — method validation via pmatch + is.na
method.int <- pmatch(method, c("anova", "poisson", "class", "exp"))
if (is.na(method.int)) stop("Invalid method")

# rpart.exp.R — parms$method validation
method <- pmatch(parms$method, c("deviance", "sqrt"))
if (is.na(method)) stop("Invalid error method for Poisson")

# snip.rpart.R — membership test: which row ids are NOT in 'toss'
keepit <- (1:ff.n)[is.na(match(id, toss))]
```

**Python equivalent.**

Python has no `NA` sentinel for lookup failures. The idiomatic replacements are:

- `str not in list` for membership/validation.
- `numpy.isin` for vectorised set membership, negated to find non-members.
- Index `-1` or `None` as a sentinel if `match`-style position lookup is needed.

```python
# residuals.rpart — type validation
valid_types = ("usual", "pearson", "deviance")
if type_ not in valid_types:
    raise ValueError("Invalid type of residual")

# rpart — method validation via partial match (simulate pmatch)
valid_methods = ["anova", "poisson", "class", "exp"]
matches = [m for m in valid_methods if m.startswith(method)]
if len(matches) != 1:
    raise ValueError("Invalid method")
method_int = valid_methods.index(matches[0]) + 1  # 1-based to match R

# rpart.exp — parms method validation
valid_methods_exp = ["deviance", "sqrt"]
matches_exp = [m for m in valid_methods_exp if m.startswith(parms_method)]
if len(matches_exp) != 1:
    raise ValueError("Invalid error method for Poisson")
method = valid_methods_exp.index(matches_exp[0]) + 1  # 1-based

# snip.rpart — find row indices of `id` elements NOT present in `toss`
# id and toss are numpy integer arrays
keepit = np.where(~np.isin(id, toss))[0]  # 0-based indices
```

**Explanation.**

| R | Python |
|---|--------|
| `is.na(match(x, table))` — scalar, not found | `x not in table` (for a single string) |
| `is.na(pmatch(s, choices))` — scalar, no unambiguous match | Check `len([c for c in choices if c.startswith(s)]) != 1` |
| `is.na(match(id, toss))` — vectorised, element not in set | `~np.isin(id, toss)` |
| `(1:ff.n)[is.na(match(id, toss))]` — 1-based indices | `np.where(~np.isin(id, toss))[0]` (0-based) |

For the vectorised case, `~np.isin(id, toss)` is the direct NumPy equivalent. Indexing is 0-based in Python, so the resulting index array is offset by 1 from R's 1-based result. When downstream code expects 1-based indices, add `+ 1` after `np.where(...)`.
