# Conversion Guide: `lapply` (R to Python)

---

## 1. Overview of `lapply` in R

`lapply` is a base R function that applies a given function to each element of a list or vector and returns a **list** of the same length as the input.

**Signature:**
```r
lapply(X, FUN, ...)
```

**Parameters:**
- `X`: A list, atomic vector, or any object coercible to a list. Each element is passed individually to `FUN`.
- `FUN`: The function to apply. Can be an anonymous function (`function(x) ...`) or a named function reference (e.g., `length`, `abbreviate`).
- `...`: Additional fixed arguments passed through to every call of `FUN`, after the current element of `X`.

**Return value:** Always a named or unnamed **list** of length `length(X)`, where element `i` contains the result of `FUN(X[[i]], ...)`. Unlike `sapply`, `lapply` never simplifies the output to a vector or matrix — the caller must do so explicitly (e.g., via `unlist()`).

When `X` is a named list, the returned list preserves those names. When the input is a plain atomic vector, `lapply` splits it into length-one elements, calling `FUN` once per scalar.

---

## 2. Contextual Usage Analysis

Across the six call sites in this codebase, `lapply` is used in three functionally distinct patterns:

**Pattern A — Compute a derived list from `xlevels` using an anonymous function (labels.rpart.R line 68).**
`xlevels` is a named list where each element is a character vector of factor levels for one predictor variable. The anonymous function maps those level strings to single-letter abbreviations drawn from the 52-element `c(letters, LETTERS)` pool, clamping any index beyond 52 with `pmin`.

**Pattern B — Apply a named function with extra positional arguments to every element of `xlevels` (labels.rpart.R line 70).**
`abbreviate` is called on each character-vector element of `xlevels`, forwarding `minlength` and any `...` args from the enclosing function. The result replaces `xlevels` in-place (reassignment).

**Pattern C — Compute the integer length of each element of `xlevels`, then immediately flatten to a vector via `unlist()` (rpart.R line 88, xpred.rpart.R line 57).**
The purpose is to produce an integer vector of category counts aligned to the columns of the predictor matrix `X`.

**Pattern D — Apply a locally-defined predicate function to a subset of the model frame (rpart.R line 154).**
`m[labs]` is a data-frame subset (itself a list of columns). `tfun` tests whether each column is an ordered factor, handling the matrix-column edge case. The result is immediately flattened with `unlist()` to a logical vector `isord`.

**Pattern E — Convert each column of a data-frame to a numeric type using an anonymous function with branching logic (rpart.matrix.R line 18).**
`frame[]` (the bracket-assignment form) replaces every column in place while preserving the data-frame structure. Each column is converted: character columns become `as.numeric(factor(x))`, non-numeric non-character columns become `as.numeric(x)`, and already-numeric columns are left unchanged.

A recurring structural pattern across all sites: `lapply` is called on a named list, and in several cases the result is consumed either by `unlist()` (for scalar aggregation) or used directly as a transformed list (for element-wise replacement).

---

## 3. Python Conversion Strategy

The primary Python equivalent is a combination of:

- **`[f(x) for x in ...]` list comprehensions** for straightforward element-wise transformations over Python lists or dict values.
- **`{k: f(v) for k, v in d.items()}` dict comprehensions** when the input is a named structure (equivalent to R's named list) and names must be preserved.
- **`numpy` operations** (`np.minimum`, `np.arange`) where R uses vectorized primitives on array-like objects inside the applied function.
- **`pandas` DataFrame column operations** for Pattern E, since the input is a model frame (a data frame), and pandas is the natural equivalent for column-wise transformations.

`numpy.vectorize` is deliberately avoided: it is a convenience wrapper with no performance benefit over a Python loop and is not idiomatic for this kind of named-list mapping. Pure list/dict comprehensions are cleaner and more readable for the patterns seen here.

`unlist()` in R is translated to a flat Python structure: either concatenation (for list-of-lists) or direct extraction when each list element is a scalar, using a dict of scalars or `numpy.array(list(...))`.

---

## 4. Step-by-Step Conversion Examples

---

### 4.1 Pattern A — Map factor levels to single-letter abbreviations

**Locations:** `labels.rpart.R`, function `labels.rpart`, line 68.

**Original R Context:**

`xlevels` is a named list; each element is a character vector of factor level strings. The integer length of each element may exceed 52. The call abbreviates each element's levels to single letters, capping at index 52.

```r
# xlevels: named list, e.g. list(color = c("red","green","blue"), size = c("S","M","L","XL"))
xlevels <- lapply(xlevels, function(z) c(letters, LETTERS)[pmin(seq_along(z), 52L)])
# returns: named list of same length; each element is a character vector of single letters
```

**Python Equivalent:**

```python
import numpy as np

# xlevels: dict mapping str -> list[str], e.g. {"color": ["red","green","blue"], "size": ["S","M","L","XL"]}
_alphabet = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")  # 52 elements

xlevels = {
    k: [_alphabet[min(i, 51)] for i in range(len(v))]
    for k, v in xlevels.items()
}
# result: dict[str, list[str]]; each value is a list of single-letter abbreviations
```

**Explanation:**
- R's `seq_along(z)` produces `1, 2, ..., len(z)` (1-based). Python uses `range(len(v))` (0-based), so the cap is `min(i, 51)` (index into a 0-based list of 52 elements), equivalent to `pmin(seq_along(z), 52L)` minus the 1-based offset.
- R's `c(letters, LETTERS)` is a 52-element character vector; the Python equivalent is `list("abc...xyzABC...XYZ")` defined as `_alphabet`.
- The dict comprehension preserves the named-list semantics of R's `lapply` on a named list.

---

### 4.2 Pattern B — Abbreviate factor level strings with a named function and extra arguments

**Locations:** `labels.rpart.R`, function `labels.rpart`, line 70.

**Original R Context:**

`xlevels` is a named list of character vectors. `minlength` is an integer scalar. `...` are additional keyword arguments forwarded to `abbreviate`. The result replaces `xlevels`.

```r
# xlevels: named list of character vectors
# minlength: integer scalar (>= 2)
# ...: additional args for abbreviate()
xlevels <- lapply(xlevels, abbreviate, minlength, ...)
# returns: named list; each element is a named character vector of abbreviated strings
```

**Python Equivalent:**

R's `abbreviate` truncates strings to a minimum unique length. The closest standard Python equivalent is a custom abbreviation function or, for display purposes, simple slicing. A robust drop-in is shown below:

```python
def abbreviate(strings: list[str], minlength: int) -> list[str]:
    """Shorten each string to at least minlength characters while keeping uniqueness."""
    result = [s[:minlength] for s in strings]
    # Extend duplicates one character at a time until all are unique
    length = minlength
    while len(set(result)) < len(result) and length < max(len(s) for s in strings):
        length += 1
        result = [s[:length] for s in strings]
    return result

# xlevels: dict[str, list[str]]
# minlength: int
xlevels = {k: abbreviate(v, minlength) for k, v in xlevels.items()}
```

**Explanation:**
- R's `lapply(xlevels, abbreviate, minlength, ...)` passes `minlength` as the second positional argument to `abbreviate` for each element. In the dict comprehension, this is written as `abbreviate(v, minlength)`.
- R's `abbreviate` guarantees uniqueness; the helper function above replicates this by extending the prefix length until uniqueness is achieved.
- If the project already has an `abbreviate` utility, replace the helper call with that utility.

---

### 4.3 Pattern C — Compute per-element length and flatten to a vector

**Locations:** `rpart.R`, function `rpart`, line 88; `xpred.rpart.R`, function `xpred.rpart`, line 57.

**Original R Context:**

`xlevels` is a named list of character vectors. `unlist(lapply(xlevels, length))` produces an integer vector of level counts, one per predictor variable. In `rpart.R`, the result is indexed by `indx > 0` before being assigned into `cats`.

```r
# xlevels: named list of character vectors
# cats: integer vector of length ncol(X), initialized to 0
cats[indx] <- (unlist(lapply(xlevels, length)))[indx > 0]

# In xpred.rpart.R (simpler form):
cats[match(names(xlevels), colnames(X))] <- unlist(lapply(xlevels, length))
```

**Python Equivalent:**

```python
import numpy as np

# xlevels: dict[str, list[str]]
# cats: np.ndarray of int, shape (nvar,), initialized to 0
# indx: np.ndarray of int, column indices into cats (0-based); -1 means no match (nomatch=0 -> nomatch=-1 in Python)

# Equivalent to unlist(lapply(xlevels, length)):
level_lengths = np.array([len(v) for v in xlevels.values()], dtype=np.int32)

# rpart.R pattern (filter by indx > 0, then assign):
valid_mask = indx > 0          # boolean mask over xlevels entries that matched a column
cats[indx[valid_mask] - 1] = level_lengths[valid_mask]   # convert 1-based R index to 0-based

# xpred.rpart.R pattern (direct match):
col_names = list(X.columns) if hasattr(X, "columns") else list(range(X.shape[1]))
for name, length in zip(xlevels.keys(), level_lengths):
    if name in col_names:
        cats[col_names.index(name)] = length
```

**Explanation:**
- `lapply(xlevels, length)` visits each list element and returns its length. The Python equivalent is `[len(v) for v in xlevels.values()]`.
- `unlist()` on a list of scalars produces a flat integer vector; `np.array([...])` is the direct equivalent.
- R uses 1-based indexing. `indx` in R is `match(..., nomatch=0)`, so valid matches satisfy `indx > 0`. In Python, using `nomatch` equivalent of `-1` (not found) the valid mask becomes `indx >= 0` and index access uses `indx[mask]` directly (0-based).

---

### 4.4 Pattern D — Apply a predicate to each column of a data-frame subset

**Locations:** `rpart.R`, function `rpart`, line 154.

**Original R Context:**

`m` is a model frame (data frame). `labs` is a character vector of term labels (column names). `tfun` is a locally defined function that returns `TRUE` if a column is an ordered factor (handling matrix columns). The result is immediately flattened to a logical vector `isord`.

```r
tfun <- function(x)
    if (is.matrix(x)) rep(is.ordered(x), ncol(x)) else is.ordered(x)
labs <- sub("^`(.*)`$", "\\1", attr(Terms, "term.labels"))
isord <- unlist(lapply(m[labs], tfun))
# isord: logical vector, one entry per column of X (accounting for matrix columns)
```

**Python Equivalent:**

```python
import re
import numpy as np
import pandas as pd

# m: pd.DataFrame (model frame)
# term_labels: list[str] from the formula terms
# labs: strip backtick quoting from term labels
labs = [re.sub(r"^`(.*)`$", r"\1", lbl) for lbl in term_labels]

def tfun(col: pd.Series) -> list[bool]:
    """
    Return a list of bool indicating ordered-factor status.
    A single column maps to one bool; a 2-D column (matrix equivalent)
    maps to one bool repeated for each sub-column.
    """
    if isinstance(col.dtype, pd.CategoricalDtype) and col.cat.ordered:
        return [True]
    # ndarray block: handle matrix-valued columns stored as object arrays
    if col.dtype == object and isinstance(col.iloc[0], np.ndarray):
        ncols = col.iloc[0].shape[0] if col.iloc[0].ndim > 0 else 1
        # is.ordered on a matrix checks the class of the matrix, not per-column
        ordered = hasattr(col, "_ordered") and col._ordered
        return [ordered] * ncols
    return [False]

isord = np.array(
    [flag for col_name in labs for flag in tfun(m[col_name])],
    dtype=bool
)
```

**Explanation:**
- `m[labs]` in R subsets a data frame to named columns, producing a list of column vectors. In pandas, `m[labs]` produces a DataFrame; iterating over column names and calling `tfun` on each `m[col_name]` replicates the per-element behavior.
- `is.ordered(x)` in R returns `TRUE` if `x` is an ordered factor. In pandas, this corresponds to a `CategoricalDtype` with `ordered=True`.
- The matrix-column case (`rep(is.ordered(x), ncol(x))`) expands a single ordered flag across all sub-columns of a matrix predictor. The Python implementation handles this by inspecting the dtype and element shape.
- `unlist()` on a list of length-one booleans collapses to a flat logical vector; `np.array([...], dtype=bool)` with a flattening list comprehension achieves the same.

---

### 4.5 Pattern E — In-place column-wise type coercion on a data frame

**Locations:** `rpart.matrix.R`, function `rpart.matrix`, line 18.

**Original R Context:**

`frame` is a model frame (data frame). `frame[] <- lapply(...)` replaces every column in-place (the `[]` assignment preserves the data-frame structure, including its `"terms"` attribute). The anonymous function coerces each column: character to numeric-encoded factor, non-numeric (e.g. logical, ordered factor) to numeric, and already-numeric columns are passed through unchanged.

```r
# frame: data.frame with a "terms" attribute
frame[] <- lapply(frame, function(x) {
    if (is.character(x)) as.numeric(factor(x))
    else if (!is.numeric(x))  as.numeric(x)
    else x
})
# frame: same data.frame object; columns replaced in-place with numeric values
```

**Python Equivalent:**

```python
import pandas as pd

# frame: pd.DataFrame (model frame); must preserve its attributes after transformation

def coerce_column(col: pd.Series) -> pd.Series:
    """
    Replicate R's anonymous coercion:
      - character (object/string dtype) -> numeric factor codes (1-based to match R)
      - non-numeric (bool, categorical, etc.) -> float via pd.to_numeric
      - already numeric -> unchanged
    """
    if col.dtype == object or pd.api.types.is_string_dtype(col):
        # as.numeric(factor(x)): encode categories as 1-based integers
        return pd.Categorical(col).codes.astype(float) + 1.0
    elif not pd.api.types.is_numeric_dtype(col):
        # as.numeric(x): coerce logicals, categoricals, etc.
        return pd.to_numeric(col, errors="coerce")
    else:
        return col

# Apply in-place, preserving the DataFrame object and its index/columns
for col_name in frame.columns:
    frame[col_name] = coerce_column(frame[col_name])
```

**Explanation:**
- R's `frame[] <- lapply(frame, ...)` iterates over columns (a data frame is a list of equal-length vectors in R) and replaces them in-place while keeping all data-frame attributes. In pandas, a column-by-column loop with `frame[col_name] = ...` achieves the same in-place update without creating a new DataFrame.
- `as.numeric(factor(x))` in R returns 1-based integer codes. `pd.Categorical(col).codes` is 0-based, so `+ 1.0` aligns it with R's convention.
- `as.numeric(x)` in R coerces logicals (TRUE/FALSE -> 1/0), ordered factors, and other atomic types to double. `pd.to_numeric(..., errors="coerce")` handles the equivalent coercions, inserting `NaN` for values that cannot be converted (R would give `NA`).
- The `else x` branch (already numeric) maps directly to the `else: return col` branch, returning the series unchanged.
