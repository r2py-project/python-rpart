# Conversion Guide: `x$functions$text` (R to Python)

---

## 1. Overview of `x$functions$text` in R

`x$functions$text` is not a standalone R language function. It is a **method dispatch pattern** specific to the rpart package. In R, `x` is an `"rpart"` S3 object whose `functions` field is a named list of callables assembled at tree-fitting time. The `text` entry in that list is a closure that formats node-level statistics as strings for display on a plotted tree.

The `functions` list is built inside `rpart()` (in `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`, lines 263–265):

```r
functions <- if (is.null(init$print)) list(summary = init$summary)
             else list(summary = init$summary, print = init$print)
if (!is.null(init$text)) functions <- c(functions, list(text = init$text))
```

Each split method (`rpart.anova`, `rpart.class`, `rpart.poisson`, `rpart.exp`) returns an init list that includes a `text` closure with a fixed signature:

```r
text = function(yval, dev, wt, ylevel, digits, n, use.n) { ... }
```

The four concrete implementations are:

- **anova** (`rpart.anova.R`, line 9): formats a scalar or vector of mean response values, optionally appending `"\nn=<count>"`.
- **class** (`rpart.class.R`, line 97): formats the majority class label, optionally appending class counts separated by `"/"`.
- **poisson** (`rpart.poisson.R`, line 43): formats estimated rate, optionally appending `"\n<events>/<n>"`.
- **exp** (`rpart.exp.R`, line 136): same structure as poisson — formats estimated (rescaled) rate with optional event/n suffix.

**Call signature (all four variants):**

| Parameter | R type | Meaning |
|-----------|--------|---------|
| `yval` | numeric vector OR numeric matrix | Node summary statistic(s): scalar mean for anova, 2-column matrix for poisson/exp, multi-column matrix for class |
| `dev` | numeric vector | Node deviances for the leaf nodes |
| `wt` | numeric vector | Node weights for the leaf nodes |
| `ylevel` | character vector or `NULL` | Class level labels; `NULL` for non-classification methods |
| `digits` | integer scalar | Number of significant digits for numeric formatting |
| `n` | integer vector | Observation counts per leaf node |
| `use.n` | logical scalar | Whether to append observation counts to the label |

**Return value:** a character vector of the same length as the number of leaf nodes. Each element is the display label for one leaf to be placed on the tree plot by `text.rpart`.

---

## 2. Contextual Usage Analysis

There is a single call site in the rpart package: `text.rpart` in `/groups/jli9/Yufei/python-rpart/rpart/R/text.rpart.R`, lines 52–57.

```r
leaves <- if (all) rep(TRUE, nrow(frame)) else frame$var == "<leaf>"

stat <-
    x$functions$text(yval = if (is.null(frame$yval2)) frame$yval[leaves]
                            else frame$yval2[leaves, ],
                     dev = frame$dev[leaves], wt = frame$wt[leaves],
                     ylevel = ylevels, digits = digits,
                     n = frame$n[leaves], use.n = use.n)
```

The `stat` character vector returned is subsequently used in two ways (lines 100–101):

```r
if (fancy) FUN(xy$x[leaves], xy$y[leaves] + 0.5 * cxy[2L], stat, ...)
else       FUN(xy$x[leaves], xy$y[leaves] - 0.5 * cxy[2L], stat, adj = 0.5, ...)
```

where `FUN` defaults to R's `text()` function, which draws character strings on an open graphics device.

**Argument data types at the call site:**

| Argument | Source | Type when `yval2` is `NULL` (anova/poisson/exp) | Type when `yval2` is set (class) |
|----------|--------|--------------------------------------------------|----------------------------------|
| `yval` | `frame$yval[leaves]` or `frame$yval2[leaves, ]` | 1-D numeric vector | 2-D numeric matrix (subset of rows) |
| `dev` | `frame$dev[leaves]` | 1-D numeric vector | 1-D numeric vector |
| `wt` | `frame$wt[leaves]` | 1-D numeric vector | 1-D numeric vector |
| `ylevel` | `attr(x, "ylevels")` | `NULL` | character vector |
| `digits` | function argument | integer scalar | integer scalar |
| `n` | `frame$n[leaves]` | integer vector | integer vector |
| `use.n` | function argument | logical scalar | logical scalar |

**Recurring patterns across the four implementations:**

- All four return a character vector of length equal to the number of selected leaf nodes.
- All four use `formatg()` (an internal rpart helper wrapping `sprintf` with `"%.<digits>g"` format) to format numeric values.
- All four conditionally append count information via `paste0(..., "\n", ...)` when `use.n` is `TRUE`.
- The `class` variant additionally uses `format(group, justify = "left")` to align class label strings.
- The `poisson` and `exp` variants guard against the no-split case by coercing `yval` to a matrix: `if (!is.matrix(yval)) yval <- matrix(yval, nrow = 1L)`.

---

## 3. Python Conversion Strategy

**Chosen library:** Python standard library (`str.format` / f-strings) combined with **`numpy`** for array indexing and **`pandas`** (optionally) for the classification variant.

**Rationale:**

The core work of each `text` closure is string formatting of numeric arrays and conditional string concatenation — not mathematical computation. `numpy` is required because:

1. `yval`, `dev`, `wt`, and `n` are all numpy arrays (1-D or 2-D) in the Python translation of the rpart frame.
2. Indexing operations such as `frame$yval[leaves]` become `frame["yval"][leaves]` where `leaves` is a boolean numpy array, which requires numpy-style boolean indexing.
3. `formatg()` — called inside every text closure — formats numeric vectors element-wise and is most naturally replaced with numpy-vectorized string formatting using `np.vectorize` or list comprehensions over numpy array elements.

The `x$functions$text(...)` dispatch pattern itself translates to a Python dict lookup followed by a function call: `x["functions"]["text"](...)`.

No `scipy` or `pandas` dependency is strictly required for the formatting logic, though `pandas` `DataFrame` is the natural home for the rpart `frame` object, making `frame["yval"][leaves]` natural pandas Series indexing.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Dispatching the `text` Method from the rpart Object

**Locations:** `text.rpart.R`, `text.rpart`, lines 52–57.

**Original R Context**

`x` is an `"rpart"` S3 object (a named list). `x$functions` is a named list of closures. `x$functions$text` is the formatting closure for the method the tree was fit with. `leaves` is a logical vector selecting rows of `frame`.

```r
# R
leaves <- if (all) rep(TRUE, nrow(frame)) else frame$var == "<leaf>"

stat <-
    x$functions$text(yval = if (is.null(frame$yval2)) frame$yval[leaves]
                            else frame$yval2[leaves, ],
                     dev = frame$dev[leaves], wt = frame$wt[leaves],
                     ylevel = ylevels, digits = digits,
                     n = frame$n[leaves], use.n = use.n)
```

- `frame$yval[leaves]`: 1-D numeric vector of length `sum(leaves)` (anova/poisson/exp).
- `frame$yval2[leaves, ]`: 2-D numeric matrix with `sum(leaves)` rows (class).
- Return: character vector of length `sum(leaves)`.

**Python Equivalent**

```python
import numpy as np

# x is a dict; x["functions"] is a dict of callables
# frame is a pandas DataFrame (or dict of numpy arrays)

leaves = (
    np.ones(len(frame), dtype=bool)
    if all_nodes
    else (frame["var"] == "<leaf>").to_numpy()
)

yval2 = frame.get("yval2")   # None when the method does not set yval2
yval = (
    frame["yval"].to_numpy()[leaves]
    if yval2 is None
    else yval2[leaves, :]          # 2-D numpy array subset
)

stat = x["functions"]["text"](
    yval=yval,
    dev=frame["dev"].to_numpy()[leaves],
    wt=frame["wt"].to_numpy()[leaves],
    ylevel=ylevels,
    digits=digits,
    n=frame["n"].to_numpy()[leaves],
    use_n=use_n,
)
```

**Explanation**

| R construct | Python equivalent | Notes |
|-------------|-------------------|-------|
| `x$functions$text` | `x["functions"]["text"]` | Two levels of dict key access replace two levels of `$` list access. The retrieved value is a callable. |
| `x$functions$text(yval=..., ...)` | `x["functions"]["text"](yval=..., ...)` | Python passes keyword arguments in the same syntactic position. `use.n` becomes `use_n` (dots become underscores). |
| `frame$var == "<leaf>"` | `(frame["var"] == "<leaf>").to_numpy()` | Pandas Series comparison; `.to_numpy()` gives a boolean numpy array for downstream indexing. |
| `frame$yval[leaves]` | `frame["yval"].to_numpy()[leaves]` | Boolean-index a 1-D numpy array. |
| `frame$yval2[leaves, ]` | `yval2[leaves, :]` | Boolean-index rows of a 2-D numpy array. |
| `is.null(frame$yval2)` | `yval2 is None` | `None` replaces R's `NULL`; dict `.get()` returns `None` when the key is absent. |
| `rep(TRUE, nrow(frame))` | `np.ones(len(frame), dtype=bool)` | Create a boolean array of all `True`. |

---

### 4.2 The `anova` Method `text` Closure

**Locations:** `rpart.anova.R`, `rpart.anova`, line 9.

**Original R Context**

`yval` is a 1-D numeric vector (one mean per leaf). The closure formats each mean with `formatg()` and optionally appends `"\nn=<count>"`.

```r
# R — inside rpart.anova return list
text = function(yval, dev, wt, ylevel, digits, n, use.n) {
    if (use.n) paste0(formatg(yval, digits), "\nn=", n)
    else       formatg(yval, digits)
}
```

- Input `yval`: 1-D numeric numpy array of length `L` (number of selected leaves).
- Input `n`: 1-D integer numpy array of length `L`.
- Return: list/array of `L` strings.

**Python Equivalent**

```python
import numpy as np

def text_anova(yval, dev, wt, ylevel, digits, n, use_n):
    """Format leaf node labels for an anova (regression) rpart tree."""
    fmt = f"%.{digits}g"
    # formatg equivalent: element-wise sprintf with "%.<digits>g"
    formatted_yval = np.array([fmt % v for v in np.asarray(yval).ravel()])
    if use_n:
        return np.array([f"{y}\nn={ni}" for y, ni in zip(formatted_yval, n)])
    else:
        return formatted_yval
```

**Explanation**

| R | Python | Notes |
|---|--------|-------|
| `formatg(yval, digits)` | `[f"%.{digits}g" % v for v in yval]` | `formatg` wraps `sprintf(paste0("%.", digits, "g"), x)` applied element-wise. Python's `%g` format is the direct equivalent. Wrap in `np.array(...)` for a homogeneous string array. |
| `paste0(a, "\nn=", n)` | `[f"{a}\nn={ni}" for a, ni in zip(...)]` | `paste0` with `"\n"` creates multi-line labels. Python f-strings replicate this. `n` is a numpy integer array; iteration via `zip` is safe. |
| `if (use.n) ... else ...` | `if use_n: ... else: ...` | Scalar boolean branch; no change in logic. |

---

### 4.3 The `class` Method `text` Closure

**Locations:** `rpart.class.R`, `rpart.class`, line 97.

**Original R Context**

`yval` is a multi-column numeric matrix. Column 1 is the integer class index. Columns `2` through `nclass+1` are per-class counts. The closure formats class label strings (optionally with counts joined by `"/"`).

```r
# R — inside rpart.class return list
text = function(yval, dev, wt, ylevel, digits, n, use.n) {
    nclass <- (ncol(yval) - 2L) / 2L
    group  <- yval[, 1L]                       # integer class indices, 1-based
    counts <- yval[, 1L + (1L:nclass)]         # per-class count sub-matrix
    if (!is.null(ylevel)) group <- ylevel[yval[, 1L]]  # map int -> label string

    temp1 <- formatg(counts, digits)
    if (nclass > 1L)
        temp1 <- apply(matrix(temp1, ncol = nclass), 1L, paste, collapse = "/")
    if (use.n) paste0(format(group, justify = "left"), "\n", temp1)
    else       format(group, justify = "left")
}
```

- Input `yval`: 2-D numeric numpy array, shape `(L, 2*nclass + 2)`.
- Input `ylevel`: `None` or list of class-label strings.
- Return: list of `L` strings.

**Python Equivalent**

```python
import numpy as np

def text_class(yval, dev, wt, ylevel, digits, n, use_n):
    """Format leaf node labels for a classification rpart tree."""
    yval = np.asarray(yval)
    if yval.ndim == 1:
        yval = yval.reshape(1, -1)

    nclass = (yval.shape[1] - 2) // 2
    group_idx = yval[:, 0].astype(int)          # 1-based integer class indices
    counts = yval[:, 1:nclass + 1]              # shape (L, nclass)

    # Map integer class index to label string (R uses 1-based indexing)
    if ylevel is not None:
        group = np.array([ylevel[i - 1] for i in group_idx])
    else:
        group = group_idx.astype(str)

    fmt = f"%.{digits}g"
    # Format counts matrix element-wise
    temp1_matrix = np.array([[fmt % v for v in row] for row in counts])

    if nclass > 1:
        # Join each row with "/" — equivalent to apply(..., paste, collapse="/")
        temp1 = np.array(["/".join(row) for row in temp1_matrix])
    else:
        temp1 = temp1_matrix[:, 0]

    # Left-justify group labels to a common width (equivalent to format(..., justify="left"))
    max_len = max(len(s) for s in group)
    group_fmt = np.array([s.ljust(max_len) for s in group])

    if use_n:
        return np.array([f"{g}\n{c}" for g, c in zip(group_fmt, temp1)])
    else:
        return group_fmt
```

**Explanation**

| R | Python | Notes |
|---|--------|-------|
| `ncol(yval)` | `yval.shape[1]` | Number of columns in a 2-D numpy array. |
| `yval[, 1L]` | `yval[:, 0]` | R is 1-based; Python is 0-based. Column 1 in R = column 0 in Python. |
| `yval[, 1L + (1L:nclass)]` | `yval[:, 1:nclass + 1]` | R column range `1L + 1:nclass` = columns 2 through `nclass+1` (1-based) = Python slice `1:nclass+1` (0-based). |
| `ylevel[yval[, 1L]]` | `[ylevel[i - 1] for i in group_idx]` | R vector indexing is 1-based; subtract 1 for Python list indexing. |
| `formatg(counts, digits)` then `matrix(temp1, ncol=nclass)` | `[[fmt % v for v in row] for row in counts]` | R `formatg` returns a flat character vector; `matrix(..., ncol=nclass)` reshapes it. Python directly builds a 2-D list of strings. |
| `apply(mat, 1L, paste, collapse="/")` | `["/".join(row) for row in temp1_matrix]` | Row-wise string joining. |
| `format(group, justify = "left")` | `[s.ljust(max_len) for s in group]` | Pad each string to a common width with spaces on the right. |
| `paste0(a, "\n", b)` | `[f"{a}\n{b}" for a, b in ...]` | Multi-line label concatenation via f-strings. |

---

### 4.4 The `poisson` Method `text` Closure

**Locations:** `rpart.poisson.R`, `rpart.poisson`, line 43.

**Original R Context**

`yval` is a 2-column numeric matrix: column 1 is the estimated Poisson rate, column 2 is the event count. When there are no splits, `yval` may be a vector; the closure guards against this.

```r
# R — inside rpart.poisson return list
text = function(yval, dev, wt, ylevel, digits, n, use.n) {
    if (!is.matrix(yval)) yval <- matrix(yval, nrow = 1L)
    if (use.n) paste0(formatg(yval[, 1L], digits), "\n",
                      formatg(yval[, 2L]), "/", n)
    else paste(formatg(yval[, 1L], digits))
}
```

- Input `yval`: 2-D numeric numpy array of shape `(L, 2)`, or a 1-D array when `L == 1`.
- Return: list of `L` strings.

**Python Equivalent**

```python
import numpy as np

def text_poisson(yval, dev, wt, ylevel, digits, n, use_n):
    """Format leaf node labels for a Poisson rpart tree."""
    yval = np.asarray(yval)
    if yval.ndim == 1:
        yval = yval.reshape(1, -1)     # guard: ensure 2-D when no splits

    fmt_d = f"%.{digits}g"
    rate_str   = np.array([fmt_d % v for v in yval[:, 0]])
    events_str = np.array([f"{v:.6g}" for v in yval[:, 1]])  # formatg default digits

    if use_n:
        return np.array([f"{r}\n{e}/{ni}" for r, e, ni in zip(rate_str, events_str, n)])
    else:
        return rate_str
```

**Explanation**

| R | Python | Notes |
|---|--------|-------|
| `if (!is.matrix(yval)) yval <- matrix(yval, nrow = 1L)` | `if yval.ndim == 1: yval = yval.reshape(1, -1)` | Promote a 1-D array to a 2-D array with one row. |
| `yval[, 1L]` | `yval[:, 0]` | First column: estimated rate (R 1-based -> Python 0-based). |
| `yval[, 2L]` | `yval[:, 1]` | Second column: event count. |
| `formatg(yval[, 2L])` | `[f"{v:.6g}" for v in yval[:, 1]]` | `formatg` with default `digits = getOption("digits")` (typically 7 in R). Using `6` significant figures is a safe default; pass explicit `digits` if required. |
| `paste0(a, "\n", b, "/", n)` | `[f"{r}\n{e}/{ni}" for r, e, ni in zip(...)]` | Three-part label with embedded newline. |
| `paste(formatg(...))` | `rate_str` (already a numpy string array) | `paste` on a character vector in R is a no-op when `sep=" "` and there is no collapse; a numpy string array is the direct equivalent. |

---

### 4.5 The `exp` Method `text` Closure

**Locations:** `rpart.exp.R`, `rpart.exp`, line 136.

**Original R Context**

Structurally identical to the Poisson closure: a 2-column `yval` matrix where column 1 is the rescaled hazard rate and column 2 is the event count.

```r
# R — inside rpart.exp return list
text = function(yval, dev, wt, ylevel, digits, n, use.n) {
    if (use.n) paste0(formatg(yval[, 1L], digits), "\n",
                      formatg(yval[, 2L]), "/", n)
    else paste(formatg(yval[, 1L], digits))
}
```

Note: unlike the Poisson variant, this closure does not include the `!is.matrix(yval)` guard. In practice `yval` will always be a 2-column matrix for the exp method because the data (`Surv` object) always has at least two columns.

**Python Equivalent**

```python
import numpy as np

def text_exp(yval, dev, wt, ylevel, digits, n, use_n):
    """Format leaf node labels for a rescaled-exponential (survival) rpart tree."""
    yval = np.asarray(yval)
    # yval is always 2-D for the exp method, but be defensive
    if yval.ndim == 1:
        yval = yval.reshape(1, -1)

    fmt_d = f"%.{digits}g"
    rate_str   = np.array([fmt_d % v for v in yval[:, 0]])
    events_str = np.array([f"{v:.6g}" for v in yval[:, 1]])

    if use_n:
        return np.array([f"{r}\n{e}/{ni}" for r, e, ni in zip(rate_str, events_str, n)])
    else:
        return rate_str
```

**Explanation**

The conversion is identical to section 4.4. The only difference from the Poisson variant is the absence of the `!is.matrix` guard in the R source, which in Python is replaced by a defensive `reshape` regardless. In the Python translation, sharing a single implementation for both `text_poisson` and `text_exp` is idiomatic and reduces duplication.

---

### 4.6 Assembling and Storing the `functions` Dict (context for the call site)

**Locations:** `rpart.R`, `rpart`, lines 263–265 and 278.

To complete the picture: in the Python translation of `rpart()`, the `functions` dict is assembled from the init object and stored on the returned rpart result, exactly mirroring how `x$functions$text` is later accessed.

**Original R Context**

```r
functions <- if (is.null(init$print)) list(summary = init$summary)
             else list(summary = init$summary, print = init$print)
if (!is.null(init$text)) functions <- c(functions, list(text = init$text))

ans <- list(..., functions = functions, ...)
```

**Python Equivalent**

```python
# init is the dict returned by rpart_anova / rpart_class / rpart_poisson / rpart_exp
if init.get("print") is None:
    functions = {"summary": init["summary"]}
else:
    functions = {"summary": init["summary"], "print": init["print"]}

if init.get("text") is not None:
    functions["text"] = init["text"]

ans = {
    # ... other fields ...
    "functions": functions,
    # ...
}
```

Later, in `text_rpart`:

```python
# x is the ans dict (the rpart result object)
stat = x["functions"]["text"](
    yval=yval,
    dev=frame["dev"].to_numpy()[leaves],
    wt=frame["wt"].to_numpy()[leaves],
    ylevel=ylevels,
    digits=digits,
    n=frame["n"].to_numpy()[leaves],
    use_n=use_n,
)
```

**Explanation**

| R | Python | Notes |
|---|--------|-------|
| `x$functions` | `x["functions"]` | Top-level list access becomes dict key access. |
| `x$functions$text` | `x["functions"]["text"]` | Nested list access becomes nested dict key access. The value is a Python callable. |
| `x$functions$text(yval=..., use.n=...)` | `x["functions"]["text"](yval=..., use_n=...)` | Call the retrieved callable. R argument name `use.n` becomes `use_n` (dot to underscore). |
| `c(functions, list(text = init$text))` | `functions["text"] = init["text"]` | In-place dict mutation; no need for R's list-merge idiom. |
| `is.null(init$text)` | `init.get("text") is None` | `.get()` returns `None` if the key is absent, which is the Python equivalent of `NULL`. |
