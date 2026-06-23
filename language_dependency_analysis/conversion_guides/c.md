# Conversion Guide: `c` in R

## 1. Overview of `c` in R

`c()` is R's fundamental "combine" or "concatenate" function. It takes an arbitrary number of arguments and combines them into a single flat atomic vector (or a list, if any argument is a list). Key behaviours:

- **Flattening:** nested `c()` calls and vectors are always recursively flattened into a one-dimensional result.
- **Type coercion:** all elements are coerced to the most general common type (`logical` < `integer` < `double` < `complex` < `character`).
- **Named elements:** names on arguments (e.g. `c(shrink = 1L, method = 1L)`) are preserved in the result vector, producing a named vector.
- **NULL dropping:** `NULL` values are silently ignored, so `c(NULL, 1, 2)` is equivalent to `c(1, 2)`.
- **List promotion:** if any argument is a list, the result is a list rather than an atomic vector.
- **Return type:** an atomic vector (integer, double, character, logical) or a list, depending on inputs; always length equal to the total number of scalar elements supplied.

---

## 2. Contextual Usage Analysis

Across the CSV, `c()` is used in six functionally distinct patterns throughout the rpart R files:

| Pattern | Description | Example files |
|---|---|---|
| A | Prepend/append a scalar sentinel to a vector | `importance.R`, `rpart.exp.R`, `plotcp.R`, `xpred.rpart.R`, `roc.rpart.R` |
| B | Concatenate two or more vectors/arrays | `importance.R`, `rpartco.R`, `rpartcallback.R`, `snip.rpart.R`, `snip.rpart.mouse.R` |
| C | Build a character string vector (enum / name list) | `pred.rpart.R`, `rpart.R`, `rpart.exp.R`, `rpart.poisson.R`, `xpred.rpart.R` |
| D | Build a named numeric/integer vector (parameter record) | `rpart.exp.R`, `rpart.poisson.R` |
| E | Build a small fixed-length numeric vector (margin/offset tuple, margin spec, dim spec) | `plot.rpart.R`, `post.rpart.R`, `text.rpart.R`, `xpred.rpart.R`, `roc.rpart.R` |
| F | Flatten a matrix column/row into a 1-D vector | `plot.rpart.R`, `snip.rpart.mouse.R` |

Data types in arguments span: integer scalars, double scalars, character scalars, named numeric/integer vectors, and sub-vectors extracted from data-frame columns (`ff$ncompete`, `ff$nsurrogate`, etc.).

---

## 3. Python Conversion Strategy

**Primary replacement: `numpy`.**

Because R vectors are inherently array-like and all arithmetic over them is elementwise, `numpy` arrays are the natural Python equivalent. Specific mappings:

- Concatenating numeric arrays: `numpy.concatenate([a, b])` or `numpy.append(a, scalar)`.
- Prepending/appending a scalar sentinel: `numpy.concatenate([[sentinel], arr])` or `numpy.r_[sentinel, arr]`.
- Building a fixed-length numeric tuple used as a plot range or margin: a plain Python list or `numpy` array.
- Building a character string list (enum of method names, column names): a plain Python `list` of `str`.
- Building a named numeric record (parameter dict): a Python `dict` — this preserves the R-style named-vector semantics exactly.
- Flattening a 2-D matrix column into 1-D: `arr.ravel()` or `arr.flatten()`.

`math` is never appropriate here because every usage operates on arrays or multi-element tuples, never on isolated scalars.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Prepend or Append a Scalar Sentinel to a Numeric Vector

**Locations:**
- `importance.R` / `importance` line 12: `c(0, 1 + ff$ncompete[fpri] + ff$nsurrogate[fpri])`
- `labels.rpart.R` / `labels.rpart` lines 34–35: `c(1, ff$ncompete + ff$nsurrogate + !is.leaf)`, `c(whichrow, FALSE)`
- `summary.rpart.R` / `summary.rpart` line 40: `c(1L, ff$ncompete + ff$nsurrogate + !is.leaf)`
- `plotcp.R` / `plotcp` line 17: `c(Inf, cp0[-length(cp0)])`
- `rpart.exp.R` / `rpart.exp` line 42: `c(0, dtimes[-length(dtimes)], max(time))`
- `rpart.exp.R` / `rpart.exp` line 103: `c(0, rate * diff(itable))`
- `rpart.exp.R` / `drate2` lines 83 and 88: `c(temp[-1L], 0)` and `c(0, temp[-ngrp])`
- `roc.rpart.R` / `roc.rpart` lines 12, 19, 25: `c(0, 1, ...)`, `c(NA, cutoffs)`, `c(cutoffs, NA)`
- `xpred.rpart.R` / `xpred.rpart` line 63: `c(10, cp[-length(cp)])`
- `snip.rpart.R` / `snip.rpart` line 41: `c(toss, id[xx])`
- `snip.rpart.mouse.R` / `snip.rpart.mouse` lines 49, 54: `c(id, node[temp])`, `c(toss, node[choose])`
- `pred.rpart.R` / `pred.rpart` line 10: `c(0L, cumsum(...))`

**Original R Context:**

Inputs are a scalar (or small constant) prepended/appended to a numeric or logical vector. Return value is a vector of the same element type, one element longer.

```r
# Prepend 0 then append max(time) around a trimmed vector
itable <- c(0, dtimes[-length(dtimes)], max(time))

# Prepend Inf to a vector with its last element dropped
cp <- sqrt(cp0 * c(Inf, cp0[-length(cp0)]))

# Prepend 0 to a cumsum result (integer vector)
frame$index <- 1L + c(0L, cumsum(...))[-(nrow(frame) + 1L)]
```

**Python Equivalent:**

```python
import numpy as np

# Prepend 0 then append max(time) around a trimmed vector
itable = np.concatenate([[0], dtimes[:-1], [np.max(time)]])

# Prepend Inf to a vector with its last element dropped
cp = np.sqrt(cp0 * np.concatenate([[np.inf], cp0[:-1]]))

# Prepend 0 to a cumsum result
index_arr = np.concatenate([[0], np.cumsum(condition_array)])[:-1]
```

**Explanation:**
- R's `x[-length(x)]` drops the last element; Python equivalent is `x[:-1]`.
- R's `c(scalar, vector)` is `np.concatenate([[scalar], vector])`. Wrapping the scalar in `[...]` ensures `concatenate` receives sequences, not bare scalars.
- `np.inf` is the Python equivalent of R's `Inf`.
- `np.r_[0, arr]` is a more concise alternative to `np.concatenate([[0], arr])` for simple prepend cases.

---

### 4.2 Pattern B — Concatenate Two or More Existing Vectors

**Locations:**
- `importance.R` / `importance` lines 37–38: `c(scaled.imp, unlist(sval))`, `c(as.character(ff$var[fpri]), unlist(sname))`
- `importance.R` / `importance` line 40: `c(import)` (identity / coerce to vector)
- `rpart.R` / `rpart` lines 265–266: `c(functions, list(text = init$text))`, `c(functions, mlist)`
- `rpartco.R` / `compress` lines 133–135: `c(x[me] - nspace * ...)`, `c(me, left$sons, right$sons)`
- `rpartcallback.R` / `rpartcallback` lines 39, 58, 68, 89
- `snip.rpart.R` / `snip.rpart` line 41: `c(toss, id[xx])`

**Original R Context:**

Two or more vectors of the same type are joined end-to-end. The result is a flat vector.

```r
# Concatenate numeric vectors from two sources
import_vals   <- c(scaled.imp, unlist(sval))
import_names  <- c(as.character(ff$var[fpri]), unlist(sname))

# Accumulate node indices in a loop
toss <- c(toss, id[xx])

# Concatenate integer index arrays
sons_all <- c(me, left$sons, right$sons)

# Merge two lists (R list concatenation)
functions <- c(functions, list(text = init$text))
```

**Python Equivalent:**

```python
import numpy as np

# Concatenate numeric arrays
import_vals  = np.concatenate([scaled_imp, np.concatenate(list(sval))])  # unlist -> np.concatenate
import_names = np.concatenate([np.array(ff_var_fpri, dtype=str),
                                np.concatenate(list(sname))])

# Accumulate indices in a loop (start with empty array)
toss = np.array([], dtype=int)
# inside loop:
toss = np.concatenate([toss, id[xx]])

# Concatenate integer index arrays
sons_all = np.concatenate([[me], left_sons, right_sons])

# Merge two dicts / lists (R list concatenation -> Python dict merge)
functions = {**functions, "text": init["text"]}
# or for list: combined = functions + [{"text": init["text"]}]
```

**Explanation:**
- R's `unlist(list_of_vectors)` flattens a list of vectors into one vector; in Python this is `np.concatenate(list_of_arrays)`.
- R's accumulation pattern `toss <- c(toss, new_items)` inside a loop is best replaced by `np.concatenate([toss, new_items])` each iteration, or by collecting into a Python list and calling `np.array(collected)` once after the loop for performance.
- R's `c(list1, list2)` for joining two named lists maps to Python dict merging `{**d1, **d2}` (Python 3.5+).
- The bare `c(import)` on line 40 of `importance.R` is an identity / coerce-to-vector idiom; in Python with a numpy array this is a no-op, or `np.asarray(import_val)` if the type is uncertain.

---

### 4.3 Pattern C — Build a Character String Vector (Enum / Name List)

**Locations:**
- `pred.rpart.R` / `pred.rpart` lines 9, 22: `c("ncompete", "nsurrogate")`, `c("n", "ncompete", "nsurrogate", "index")`
- `rpart.R` / `rpart` lines 13, 58, 60, 180, 181, 184, 187: e.g. `c("formula", "data", "weights", "subset")`, `c("anova", "poisson", "class", "exp")`, `c("CP", "nsplit", "rel error")`, `c("<leaf>", colnames(X))`, `c("count", "ncat", "improve", "index", "adj")`
- `rpart.exp.R` / `rpart.exp` lines 113, 121: `c("method", "shrink")`, `c("deviance", "sqrt")`
- `rpart.poisson.R` / `rpart.poisson` lines 18, 26: same pattern
- `xpred.rpart.R` / `xpred.rpart` lines 10, 21: `c("anova", "poisson", "class", "user", "exp")`, `c("", "formula", "data", "weights", "subset", "na.action")`
- `summary.rpart.R` / `summary.rpart` line 52: `c("L", "-", "R")`
- `labels.rpart.R` / `labels.rpart` line 68: `c(letters, LETTERS)`

**Original R Context:**

All elements are string literals (or built-in character vectors like `letters`). The result is a character vector used for column name selection, method lookup (`pmatch`), or label arrays.

```r
nc <- frame[, c("ncompete", "nsurrogate")]   # column selection
method.int <- pmatch(method, c("anova", "poisson", "class", "exp"))
dimnames(rpfit$cptable) <- list(c("CP", "nsplit", "rel error"), ...)
xlevels <- lapply(xlevels, function(z) c(letters, LETTERS)[pmin(...)])
```

**Python Equivalent:**

```python
# Column selection from a DataFrame
nc = frame[["ncompete", "nsurrogate"]]

# Method lookup (pmatch equivalent)
method_options = ["anova", "poisson", "class", "exp"]
method_int = next((i + 1 for i, m in enumerate(method_options)
                   if m.startswith(method)), None)

# Setting axis labels on a numpy array / DataFrame
import numpy as np
cp_table.index = ["CP", "nsplit", "rel error"]

# letters + LETTERS equivalent
import string
letters_upper = list(string.ascii_lowercase) + list(string.ascii_uppercase)
```

**Explanation:**
- R character vectors map directly to Python `list[str]`. No numpy import is needed for purely string data.
- R's `c(letters, LETTERS)` (all 52 ASCII letters) becomes `list(string.ascii_lowercase) + list(string.ascii_uppercase)`.
- Column selection from an R data frame with a character vector maps to pandas `DataFrame[["col1", "col2"]]`.
- String-based `pmatch` (partial matching) has no direct Python equivalent; a `next(... if m.startswith(method) ...)` or `difflib.get_close_matches` can replicate it.

---

### 4.4 Pattern D — Build a Named Numeric/Integer Vector (Parameter Record)

**Locations:**
- `rpart.exp.R` / `rpart.exp` lines 109, 128: `c(shrink = 1L, method = 1L)`, `c(shrink = shrink, method = method)`
- `rpart.poisson.R` / `rpart.poisson` lines 14, 34: same pattern

**Original R Context:**

Named integer or numeric scalars are packaged into a single vector with element names. The result is used as a parameter bundle passed to C code via `unlist(parms)`.

```r
parms <- c(shrink = 1L, method = 1L)
# later: as.double(unlist(parms)) -> c(1.0, 1.0) in C call order
```

**Python Equivalent:**

```python
# Represent as a dict to preserve names
parms = {"shrink": 1, "method": 1}

# When the C call needs an ordered double array:
import numpy as np
parms_array = np.array([parms["shrink"], parms["method"]], dtype=float)
```

**Explanation:**
- R named vectors carry both values and names; a Python `dict` is the closest semantic match.
- When the downstream code calls `as.double(unlist(parms))` to pass to C, the Python equivalent is extracting values in insertion order: `list(parms.values())` (Python 3.7+ dicts maintain insertion order) then converting to a numpy float array.
- Alternatively, if the names are never used and only the ordered values matter, a plain `numpy` array or Python list suffices.

---

### 4.5 Pattern E — Build a Small Fixed-Length Numeric Vector (Margin / Dim / Range Spec)

**Locations:**
- `plot.rpart.R` / `plot.rpart` lines 19–20: `c(-margin, margin)` (used as xlim/ylim extension)
- `post.rpart.R` / `post.rpart` lines 9, 12: `c(2,2,4,2)` (margin spec for `par(mar=...)`)
- `plotcp.R` / `plotcp` line 19: `c(min(xerror-xstd)-0.1, max(xerror+xstd)+0.1)` (ylim)
- `text.rpart.R` / `rectangle` lines 72–73: `c(a, a, -a, -a)`, `c(b, -b, -b, b)` (polygon coordinates)
- `roc.rpart.R` / `roc.rpart` line 38: `c(cutoff.n, 2L, 2L)` (array dimensions)
- `xpred.rpart.R` / `xpred.rpart` line 137: `c(numresp, length(cp), nrow(X))` (array dimensions)
- `summary.rpart.R` / `summary.rpart` line 78: `c(0L, 1L)` (index range for son computation)

**Original R Context:**

A small, fixed-size numeric vector is constructed from two to four scalar expressions. It is used directly as a plotting range, margin parameter, or dimension tuple.

```r
temp1 <- range(xx) + diff(range(xx)) * c(-margin, margin)  # xlim
par(mar = c(2,2,4,2) + 0.1)                                 # margin widths
ss.table <- array(0, c(cutoff.n, 2L, 2L))                   # 3-D array dims
newx <- middlex + c(a, a, -a, -a)                           # polygon x-coords
```

**Python Equivalent:**

```python
import numpy as np
import matplotlib.pyplot as plt

# Plot range extension
xx_range = np.ptp(xx)  # equivalent to diff(range(xx))
temp1 = np.array([np.min(xx), np.max(xx)]) + xx_range * np.array([-margin, margin])

# Margin spec (matplotlib uses fig.subplots_adjust or axes padding, not a 4-vector)
# Closest matplotlib equivalent for c(2,2,4,2) bottom/left/top/right pad in lines:
fig.subplots_adjust(bottom=0.1, left=0.1, top=0.2, right=0.1)

# 3-D array dimension tuple
ss_table = np.zeros((cutoff_n, 2, 2))

# Polygon coordinates
newx = middlex + np.array([a, a, -a, -a])
newy = middley + np.array([b, -b, -b, b])

# ylim 2-element tuple
ylim = (np.min(xerror - xstd) - 0.1, np.max(xerror + xstd) + 0.1)
```

**Explanation:**
- Two-element range/limit vectors become either a 2-tuple `(lo, hi)` (for matplotlib keyword args) or a 2-element `numpy` array (for arithmetic).
- Four-element margin vectors `c(2,2,4,2)` have no direct matplotlib equivalent; the semantics (bottom, left, top, right in "lines" units) map approximately to `plt.subplots_adjust` fractional parameters.
- For `array(0, c(cutoff.n, 2L, 2L))`, the dimension vector becomes a Python tuple passed to `np.zeros((cutoff_n, 2, 2))`.
- `c(a, a, -a, -a)` with scalar `a` maps directly to `np.array([a, a, -a, -a])`.

---

### 4.6 Pattern F — Flatten a Matrix Column into a 1-D Vector

**Locations:**
- `plot.rpart.R` / `plot.rpart` line 31: `c(temp$x)`, `c(temp$y)` where `temp` is the result of `rpart.branch()` returning a matrix
- `snip.rpart.mouse.R` / `snip.rpart.mouse` lines 53: `c(draw$x[, temp])`, `c(draw$y[, temp])`

**Original R Context:**

`c()` is applied to a matrix or a subset of a matrix to coerce it into a flat vector. R reads matrices column-major, so the resulting vector interleaves columns in that order.

```r
# rpart.branch returns lists with $x and $y as matrices (4 x n_branches)
lines(c(temp$x), c(temp$y), ...)       # flatten each to 1-D for lines()
lines(c(draw$x[, temp]), c(draw$y[, temp]), col = 0L)
```

**Python Equivalent:**

```python
import numpy as np

# Flatten a 2-D numpy array column-major (Fortran order) to match R's c() on a matrix
x_flat = temp_x.flatten(order='F')   # column-major, matching R
y_flat = temp_y.flatten(order='F')

# Or for a column subset:
x_flat = draw_x[:, temp_indices].flatten(order='F')
y_flat = draw_y[:, temp_indices].flatten(order='F')

# Then pass to matplotlib's plot (equivalent of R's lines())
import matplotlib.pyplot as plt
plt.plot(x_flat, y_flat)
```

**Explanation:**
- R stores matrices in column-major order, so `c(matrix)` reads down each column in turn. The Python equivalent is `ndarray.flatten(order='F')` (`'F'` for Fortran / column-major).
- If the matrix is already 1-D (a vector), `.flatten()` is a no-op and equivalent to `np.asarray(x)`.
- This pattern is purely a coercion/reshape; no arithmetic is involved.

---

### 4.7 Pattern G — Concatenate Mixed-Type Vectors for C API Argument Construction

**Locations:**
- `rpart.R` / `rpart` line 185: `c(rpfit$isplit[, 2:3], rpfit$dsplit)` (combining integer and double matrix columns)
- `pred.rpart.R` / `pred.rpart` line 10: `c(0L, cumsum((frame$var != "<leaf>") + nc[[1L]] + nc[[2L]]))` (integer 0 prepended to cumsum)

**Original R Context:**

Integer and double sub-matrices or vectors are combined. R coerces the result to the most general type (double).

```r
splits <- matrix(c(rpfit$isplit[, 2:3], rpfit$dsplit), ncol = 5L, ...)
```

**Python Equivalent:**

```python
import numpy as np

# Stack integer columns and double columns horizontally, then reshape to matrix
combined = np.concatenate([isplit[:, 1:3].astype(float), dsplit], axis=1)
# combined is already shape (n_splits, 5) if dsplit has 3 columns

# For the cumsum prepend pattern:
condition = (frame["var"] != "<leaf>").astype(int) + nc_col1 + nc_col2
index_arr = np.concatenate([[0], np.cumsum(condition)])[:-1]
frame["index"] = 1 + index_arr
```

**Explanation:**
- R's column-binding via `c(matrix1, matrix2)` followed by `matrix(..., ncol=5)` reconstructs a matrix by filling column-major. In Python, `np.concatenate([arr1, arr2], axis=1)` achieves horizontal stacking when both arrays have the same number of rows, which is the intended layout here.
- The integer-to-double coercion R performs automatically must be done explicitly in Python with `.astype(float)` when mixing integer and floating-point arrays if strict dtype consistency is required.
