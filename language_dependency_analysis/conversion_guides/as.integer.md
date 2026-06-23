# Conversion Guide: `as.integer` (R to Python)

---

## 1. Overview of `as.integer` in R

`as.integer` is a base R coercion function that converts its argument to integer type (32-bit signed integer). It is fully vectorized: when given a vector, list, or matrix, it applies the conversion element-wise and returns an integer vector of the same length.

Key behaviours:

- **Numeric input:** truncates toward zero (e.g. `as.integer(3.9)` → `3L`).
- **Logical input:** `TRUE` → `1L`, `FALSE` → `0L`.
- **Character input:** parses string representations of integers; non-parseable strings produce `NA_integer_` with a warning.
- **Factor input:** returns the underlying integer codes (level indices, 1-based), not the level labels.
- **`dim()` output:** `dim()` already returns an integer vector; `as.integer(dim(x))` is a belt-and-suspenders cast that ensures the `.Call` interface receives a plain `int *` array.
- **Named vectors / data frames:** when a data frame column or named vector is passed, `as.integer` strips names and returns a bare integer vector.
- **`row.names()`:** `row.names()` on an rpart frame returns character strings of node numbers (e.g. `"1"`, `"2"`, `"3"`). `as.integer(row.names(ff))` parses them back to numeric node IDs.
- **`is.na()` output:** `is.na()` returns a logical vector or matrix; `as.integer(is.na(x))` converts it to a 0/1 integer matrix suitable for C.
- **Arithmetic result:** `as.integer(cats * !isord)` first coerces the logical `!isord` to 0/1 integers, multiplies element-wise, and then casts to integer to guarantee type.

In the rpart package, virtually every `as.integer` call appears immediately before a `.Call` invocation, acting as explicit type safety to prevent R's automatic coercion from silently producing doubles instead of integers at the C interface.

---

## 2. Contextual Usage Analysis

Across all 33 CSV entries the calls fall into six clearly repeating patterns:

| Pattern | Representative call | Data type in → out |
|---|---|---|
| **A. Dimension / shape vectors** | `as.integer(dim(x))`, `as.integer(dim(frame)[1L])`, `as.integer(dim(fit$splits))` | integer/numeric vector → integer vector |
| **B. Row-name node IDs** | `as.integer(row.names(ff))` | character vector of decimal integers → integer vector |
| **C. Column-subset unlist** | `as.integer(unlist(frame[, c("n","ncompete","nsurrogate","index")]))` | data frame columns (numeric) → flat integer vector |
| **D. Scalar control flags / indices** | `as.integer(method.int)`, `as.integer(xval)`, `as.integer(numy)`, `as.integer(numresp)`, `as.integer(usesurrogate)`, `as.integer(return.all)` | single numeric or integer → scalar integer |
| **E. Arithmetic / logical-to-integer** | `as.integer(cats * !isord)`, `as.integer(cdir[i])`, `as.integer(fit$csplit - 2L)`, `as.integer(is.na(x))` | result of arithmetic or logical expression → integer vector/scalar |
| **F. Factor integer codes** | `as.integer(fy)` in `rpart.class` | factor → integer vector of 1-based level codes |

All occurrences appear in `.Call` argument lists (or in preparation for `.Call`). The exclusive purpose is to guarantee that C extension code receives `int` (or `int *`) typed memory rather than `double` or `SEXP`.

---

## 3. Python Conversion Strategy

The primary Python equivalent is **`numpy.ndarray` with `dtype=np.int32`** (or `np.intp` for shape/index values), accessed via:

- `np.array(..., dtype=np.int32)` — general-purpose cast of any array-like.
- `arr.astype(np.int32)` — in-place-style cast of an existing NumPy array.
- `int(scalar)` — for genuine Python scalars being passed to ctypes or cffi.

Rationale:

1. NumPy mirrors R's element-wise vectorization, so `np.array(x, dtype=np.int32)` is a direct conceptual replacement for `as.integer(x)` on a vector.
2. rpart's Python port calls C extensions through ctypes/cffi; both require `ctypes.c_int` or a contiguous `np.int32` array — exactly what NumPy provides.
3. For logical arrays (pattern E, `is.na` case), NumPy booleans cast to `np.int32` produce 0/1 values, matching R's behaviour.
4. For factor codes (pattern F), pandas `Categorical.codes` returns 0-based codes; adding 1 reproduces R's 1-based convention when needed.

`math` or plain Python `int` is acceptable only for isolated scalar arguments (patterns D/E single-element), but even there a 1-element `np.int32` array is preferred when the value is destined for a C call.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Dimension / Shape Vectors

**Locations:**
- `pred.rpart.R` / `pred.rpart`, lines 17–20
- `pred.rpart.R` / `pred.rpart`, line 19 (`dim(fit$splits)`)
- `pred.rpart.R` / `pred.rpart`, line 20 (conditional `dim(fit$csplit)`)

**Original R Context:**

`dim(x)` returns an integer vector of length 2 (rows, cols) for a matrix `x`. `dim(frame)[1L]` extracts only the first element (number of rows). The conditional on line 20 handles the case where `fit$csplit` is `NULL`, substituting a two-element zero vector.

```r
# x is a matrix; frame, fit$splits, fit$csplit are data frames / matrices
as.integer(dim(x))                    # e.g. c(150L, 5L)
as.integer(dim(frame)[1L])            # e.g. 37L
as.integer(dim(fit$splits))           # e.g. c(12L, 5L)
as.integer(
    if (is.null(fit$csplit)) rep(0L, 2L) else dim(fit$csplit)
)                                      # e.g. c(0L, 0L) or c(3L, 6L)
```

**Python Equivalent:**

```python
import numpy as np

# x is a 2-D numpy array; frame, splits, csplit are numpy arrays or None
np.array(x.shape, dtype=np.int32)                        # dim(x)
np.array([frame.shape[0]], dtype=np.int32)               # dim(frame)[1L]
np.array(splits.shape, dtype=np.int32)                   # dim(fit$splits)

csplit_dim = (
    np.zeros(2, dtype=np.int32)
    if csplit is None
    else np.array(csplit.shape, dtype=np.int32)
)                                                         # conditional dim
```

**Explanation:**
- `.shape` in NumPy returns a Python `tuple` of `int`; wrapping it with `np.array(..., dtype=np.int32)` matches R's integer vector exactly.
- The conditional `if (is.null(...)) rep(0L, 2L) else dim(...)` maps to a Python ternary expression, with `np.zeros(2, dtype=np.int32)` replacing `rep(0L, 2L)`.
- Indexing: R `dim(frame)[1L]` is 1-based; Python `frame.shape[0]` is 0-based but refers to the same first dimension (rows).

---

### 4.2 Pattern B — Row-Name Node IDs

**Locations:**
- `pred.rpart.R` / `pred.rpart`, line 21
- `prune.rpart.R` / `prune.rpart`, line 4
- `snip.rpart.R` / `snip.rpart`, line 14
- `snip.rpart.mouse.R` / `snip.rpart.mouse`, line 21
- `summary.rpart.R` / `summary.rpart`, line 34

**Original R Context:**

`row.names(ff)` on an rpart frame returns character strings such as `c("1", "3", "4", "7", "8")` — these are the binary node IDs of the tree. `as.integer()` parses them into a numeric integer vector used for tree navigation (parent = node `%/% 2`).

```r
ff <- fit$frame          # data.frame with character row names
id <- as.integer(row.names(ff))   # e.g. c(1L, 3L, 4L, 7L, 8L)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# frame is a pandas DataFrame whose index holds the node IDs
# (stored as strings or already as integers depending on how the frame was built)
id = np.array(frame.index, dtype=np.int32)

# If the index contains string labels:
id = np.array(frame.index.astype(int), dtype=np.int32)
```

**Explanation:**
- In the Python port the rpart frame is a `pandas.DataFrame`; the row index corresponds to R's `row.names`. Converting with `.astype(int)` before wrapping in `np.array` handles string-typed indices safely.
- The result is a 1-D `int32` array whose arithmetic (`id // 2` for parent node) is identical to R's `id %/% 2L`.

---

### 4.3 Pattern C — Column-Subset Unlist

**Locations:**
- `pred.rpart.R` / `pred.rpart`, line 22

**Original R Context:**

The frame data frame has integer columns `n`, `ncompete`, `nsurrogate`, and `index`. `unlist` concatenates them column-by-column into a single flat vector; `as.integer` enforces integer type before the C call.

```r
# frame is a data.frame; columns are integer/numeric
as.integer(unlist(frame[, c("n", "ncompete", "nsurrogate", "index")]))
# Result: flat integer vector of length 4 * nrow(frame)
```

**Python Equivalent:**

```python
import numpy as np

# frame is a pandas DataFrame
flat = frame[["n", "ncompete", "nsurrogate", "index"]].to_numpy(dtype=np.int32).ravel(order='F')
# 'F' (Fortran / column-major) order mirrors R's column-by-column unlist
```

**Explanation:**
- R's `unlist(df[, cols])` iterates columns first (column-major), so `.ravel(order='F')` (or equivalently `.T.ravel()`) reproduces the correct element order.
- `.to_numpy(dtype=np.int32)` performs the cast in one step, equivalent to the combination of `unlist` (which strips the data-frame structure) and `as.integer`.

---

### 4.4 Pattern D — Scalar Control Flags and Index Variables

**Locations:**
- `pred.rpart.R` / `pred.rpart`, lines 26 (`usesurrogate`)
- `rpart.R` / `rpart`, lines 162 (`method.int`), 165 (`xval`), 166 (`xgroups`), 170 (`numy`)
- `rpartcallback.R` / `rpartcallback`, line 109 (`numy`, `numresp`)
- `xpred.rpart.R` / `xpred.rpart`, lines 121 (`method.int`), 124 (`xval`), 125 (`xgroups`), 129 (`numy`), 131 (`return.all`), 134 (`numresp`)

**Original R Context:**

These are single-element numeric or integer scalars (sometimes already `integer` class) being cast to guarantee they are typed as `int` at the C interface.

```r
as.integer(method.int)          # e.g. 3L  — splitting method code
as.integer(xval)                # e.g. 10L — number of cross-validation folds
as.integer(xgroups)             # integer vector of fold assignments
as.integer(numy)                # e.g. 1L
as.integer(numresp)             # e.g. 5L
as.integer((fit$control)$usesurrogate)   # 0L, 1L, or 2L
as.integer(return.all)          # 0L or 1L (logical coerced to integer)
```

**Python Equivalent:**

```python
import numpy as np
import ctypes

# For a Python int scalar being passed to a ctypes C function:
method_int_c = ctypes.c_int(int(method_int))

# For a numpy scalar or 0-d array:
method_int_np = np.int32(method_int)

# For a 1-D numpy array (e.g. xgroups — vector of fold assignments):
xgroups_arr = np.array(xgroups, dtype=np.int32)

# Logical-to-integer (return.all is a Python bool):
return_all_int = np.int32(int(return_all))   # False→0, True→1
```

**Explanation:**
- When calling a C extension via ctypes, scalar integers must be `ctypes.c_int`. When passed to a cffi or Cython wrapper that accepts a `np.int32` array, a 0-dimensional `np.int32` scalar suffices.
- `int(return_all)` converts a Python `bool` to 0 or 1 before the final cast, mirroring R's `as.integer(TRUE)` → `1L`.

---

### 4.5 Pattern E — Arithmetic / Logical Expression Results

**Locations:**
- `rpart.R` / `rpart`, line 161: `as.integer(cats * !isord)`
- `rpart.R` / `rpart`, lines 203–204: `as.integer(cdir[i])` (loop body)
- `rpart.R` / `rpart`, line 127: `as.integer(attr(m, "na.action"))`
- `pred.rpart.R` / `pred.rpart`, line 25: `as.integer(fit$csplit - 2L)`
- `pred.rpart.R` / `pred.rpart`, line 28: `as.integer(is.na(x))`
- `pred.rpart.R` / `pred.rpart`, line 23: `as.integer(vnum)` (`match()` result)
- `xpred.rpart.R` / `xpred.rpart`, line 78: `as.integer(fit$na.action)`
- `xpred.rpart.R` / `xpred.rpart`, line 120: `as.integer(cats * !fit$ordered)`

**Original R Context:**

`cats * !isord` multiplies an integer vector `cats` (number of categories per variable, 0 for continuous) by a logical negation of `isord` (TRUE for ordered factors). The product is numeric; `as.integer` truncates to integer. `is.na(x)` returns a logical matrix; `as.integer` converts it to a 0/1 integer matrix. `fit$csplit - 2L` is an arithmetic result. `attr(m, "na.action")` / `fit$na.action` returns a vector of observation indices to drop.

```r
as.integer(cats * !isord)         # integer vector, length = nvar
as.integer(fit$csplit - 2L)       # integer matrix (shifted csplit)
as.integer(is.na(x))              # 0/1 integer matrix, same dims as x
as.integer(vnum)                  # integer vector from match()
as.integer(cdir[i])               # scalar, element of splits column
as.integer(attr(m, "na.action"))  # integer vector of omitted row indices
```

**Python Equivalent:**

```python
import numpy as np

# cats is np.int32 array, is_ord is bool array
ncat = (cats * (~is_ord)).astype(np.int32)         # cats * !isord

# csplit is np.ndarray of floats/ints; shift by -2 and cast
csplit_shifted = (csplit - 2).astype(np.int32)

# x is a 2-D numpy array; produce 0/1 integer mask
is_na_x = np.isnan(x).astype(np.int32)            # for float arrays
# or for object/mixed arrays:
is_na_x = pd.isnull(x).astype(np.int32)

# vnum comes from np.searchsorted / list index lookup — already int-like
vnum_arr = np.array(vnum, dtype=np.int32)

# scalar element of a splits column
cdir_i = np.int32(cdir[i])

# na_action is a pandas Index or array of row positions
na_action_arr = np.array(fit_na_action, dtype=np.int32)
```

**Explanation:**
- NumPy's `~` operator inverts a boolean array, matching R's `!`.
- `.astype(np.int32)` on any NumPy array is the direct analogue of `as.integer()` on a vector — it truncates floats toward zero and converts bools to 0/1.
- `np.isnan` covers R's `is.na` for pure float arrays; `pd.isnull` is broader and covers `None`/`NaN`/`NaT` in mixed-type data.

---

### 4.6 Pattern F — Factor Integer Codes

**Locations:**
- `rpart.class.R` / `rpart.class`, line 6

**Original R Context:**

`fy` is a factor created by `as.factor(y)`. `as.integer(fy)` returns the integer level codes (1-based: level 1 → `1L`, level 2 → `2L`, etc.), not the factor labels. This is used to map class labels to sequential integers for the C splitting routine.

```r
fy <- as.factor(y)       # factor with levels, e.g. levels = c("A","B","C")
y  <- as.integer(fy)     # 1-based codes, e.g. c(1L, 3L, 2L, 1L, ...)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

fy = pd.Categorical(y)           # or pd.Series(y).astype("category")
# pandas codes are 0-based; add 1 to match R's 1-based convention
y_int = np.array(fy.codes + 1, dtype=np.int32)
```

**Explanation:**
- `pd.Categorical.codes` is the pandas equivalent of R's factor codes, but uses 0-based indexing. Adding `1` reproduces R's 1-based level numbering.
- The result is a `np.int32` array of the same length as the input, with values in `[1, numclass]` — exactly what the rpart C code expects.
- Level labels are preserved in `fy.categories`, corresponding to R's `levels(fy)`.
