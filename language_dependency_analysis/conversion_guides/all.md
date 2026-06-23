# Conversion Guide: `all` (R to Python)

---

## 1. Overview of `all` in R

`all` is a base R primitive that tests whether **every element** in one or more logical vectors is `TRUE`. It reduces an arbitrary-length logical vector to a single scalar `logical` (`TRUE` or `FALSE`).

**Signature:**
```r
all(..., na.rm = FALSE)
```

**Parameters:**
- `...` — One or more logical vectors (or objects coercible to logical). Zero-length vectors are silently ignored.
- `na.rm` — Logical scalar (default `FALSE`). When `TRUE`, `NA` values are excluded before evaluation.

**Return value:** A single `bool`-equivalent scalar:
- `TRUE` if every element is `TRUE` (vacuously `TRUE` for an empty vector).
- `FALSE` if at least one element is `FALSE`.
- `NA` when `na.rm = FALSE`, no element is `FALSE`, but at least one `NA` is present.

`all` is inherently a **reduction operation**: it collapses a vector into one value. It is the logical counterpart of `any`, and is commonly used as a guard condition in `if` statements rather than as a vectorized mapping.

---

## 2. Contextual Usage Analysis

Across all five CSV rows, `all` is used exclusively as a **scalar guard condition** inside `if` or `else if` statements. In every case the argument is already a logical vector produced by a comparison or predicate function, and the result determines which branch of control flow is taken. The function is never used with `na.rm = TRUE` in this codebase, so NA propagation is the default.

Three distinct logical argument patterns appear:

| Pattern | Source file | Argument type | Meaning |
|---|---|---|---|
| Boolean vector from matrix row-sum | `na.rpart.R` | Logical vector (one element per data row) | All rows have at least one non-missing predictor |
| Boolean vector from element-wise equality | `rpart.exp.R` | Logical vector (one element per observation) | Every survival status value equals zero |
| Boolean vector from `nchar` comparison | `summary.rpart.R` (x2) | Logical vector (one element per split label) | Every formatted cut string is shorter than 25 wide characters |

In all cases the input is a **1-D logical vector of varying length** and the output is consumed directly as a single `bool`.

---

## 3. Python Conversion Strategy

The direct Python equivalent is **`numpy.all()`** (or `bool(numpy_array.all())`).

**Why NumPy over the built-in `all`:**

- The arguments to R's `all` in this codebase are always the result of vectorized R comparisons (e.g., `keep`, `status == 0`, `nchar(...) < 25L`), which translate to NumPy boolean arrays in Python. `numpy.all()` operates natively on such arrays without requiring conversion to a Python list.
- `numpy.all()` returns a NumPy scalar that behaves like a Python `bool` in `if` tests, so no explicit casting is needed in practice.
- Using the built-in `all()` on a NumPy array works but forces iteration over the array in Python, which is less efficient and less idiomatic when the upstream computation is already NumPy-based.

`numpy.all(a)` with no additional keyword arguments matches R's `all(..., na.rm = FALSE)` default for non-NA inputs. For inputs that may contain `numpy.nan`, `numpy.all()` treats `nan` as truthy (non-zero), which differs slightly from R's `NA` propagation; this distinction does not affect the rpart usages here because none of the arguments can contain `NA`/`nan` at the point of the call.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Guard: all rows have at least one non-missing predictor

**Locations:** `na.rpart.R` — function `na.rpart`, line 16.

**Original R Context:**

`keep` is a logical vector with one element per data-frame row, constructed from a matrix product that counts missing values across columns. `all(keep)` is `TRUE` when no row is entirely missing, in which case the original data frame `x` is returned unchanged.

```r
# keep: logical vector, length = nrow(x)
# TRUE  => row has at least one non-missing predictor value
# FALSE => row is all-missing and must be dropped
if (all(keep)) x
else {
    temp <- seq(keep)[!keep]
    ...
}
```

**Python Equivalent:**

```python
import numpy as np

# keep: np.ndarray of dtype bool, shape (n_rows,)
if np.all(keep):
    result = x          # return x unchanged (pandas DataFrame)
else:
    temp = np.where(~keep)[0]   # 0-based indices of dropped rows
    # ... apply omit logic
```

**Explanation:**
- `np.all(keep)` reduces the boolean array to a single `bool`, mirroring R's `all(keep)`.
- `~keep` is the NumPy element-wise negation, equivalent to R's `!keep`.
- `np.where(~keep)[0]` returns 0-based integer indices; R's `seq(keep)[!keep]` returns 1-based indices, so add 1 if 1-based indexing must be preserved for compatibility.

---

### 4.2 Guard: no events (all-censored data)

**Locations:** `rpart.exp.R` — function `rpart.exp`, line 22.

**Original R Context:**

`status` is a numeric vector extracted from a `Surv` object's last column. A value of `0` means censored; a non-zero value means an event occurred. `all(status == 0)` is `TRUE` when the dataset contains no events at all, which is an invalid state for survival modelling.

```r
status <- y[, ny]        # numeric vector, one element per observation
if (all(status == 0)) stop("No deaths in data set")
```

**Python Equivalent:**

```python
import numpy as np

status = y[:, ny - 1]   # numpy array; Python uses 0-based column indexing
if np.all(status == 0):
    raise ValueError("No deaths in data set")
```

**Explanation:**
- `y[, ny]` in R uses 1-based indexing for the last column; Python translates this to `y[:, ny - 1]`.
- `status == 0` produces a NumPy boolean array element-wise, exactly as in R.
- `np.all(...)` reduces it to a single `bool` used by the `if` guard.
- `stop(...)` maps to `raise ValueError(...)` in Python.

---

### 4.3 Guard: all formatted split labels fit within 25 character-widths

**Locations:** `summary.rpart.R` — function `summary.rpart`, lines 88 and 100.

**Original R Context:**

`cuts[j]` is a character vector of formatted split-condition strings (e.g., `"< 0.5,"` or `"splits as LR,"`). `nchar(cuts[j], "w")` returns the display width of each string (counting wide characters as 2 units). `all(nchar(cuts[j], "w") < 25L)` is `TRUE` when every label is short enough to be left-justified without overflowing the printed summary column; if any label is too wide the raw (un-padded) strings are used instead.

The same pattern appears twice: once for primary splits (`j` indexes `ff$ncompete[i] + 1` rows starting at `index[i]`) and once for surrogate splits (a different range of `j`).

```r
# cuts: character vector of split-condition strings
# j:    integer index vector selecting the relevant subset

# Primary splits (line 88):
temp <- if (all(nchar(cuts[j], "w") < 25L))
    format(cuts[j], justify = "left")
else
    cuts[j]

# Surrogate splits (line 100) — identical pattern with a different j:
temp <- if (all(nchar(cuts[j], "w") < 25L))
    format(cuts[j], justify = "left")
else
    cuts[j]
```

**Python Equivalent:**

```python
import numpy as np

# cuts: list or np.ndarray of str, one element per split
# j:    array-like of integer indices (0-based in Python)

widths = np.array([len(s.encode("utf-8")) for s in cuts[j]])
# Note: for pure ASCII content (typical in rpart cut strings) len() equals
# the display width. For full Unicode width parity use the `wcwidth` package:
#   from wcwidth import wcswidth
#   widths = np.array([wcswidth(s) for s in cuts[j]])

if np.all(widths < 25):
    # left-justify each string to the same width
    max_w = int(widths.max()) if len(widths) > 0 else 0
    temp = np.array([s.ljust(max_w) for s in cuts[j]])
else:
    temp = np.array(cuts[j])
```

**Explanation:**
- R's `nchar(x, "w")` measures the *display width* of strings, treating wide (e.g., CJK) characters as 2 units. For ASCII-only rpart output `len(s)` is sufficient; `wcwidth.wcswidth` provides full Unicode parity if needed.
- `np.all(widths < 25)` replaces R's `all(nchar(cuts[j], "w") < 25L)`.
- R's `format(cuts[j], justify = "left")` left-pads all strings to the same width; the Python equivalent is `s.ljust(max_width)` applied uniformly.
- The inline `if`/`else` expression in R (`temp <- if (...) A else B`) maps directly to a Python `if`/`else` block assigning to `temp`.
- Index offset: R's `j` is 1-based; ensure Python indices are adjusted to 0-based when translating the `j` computation from `index[i]` and `ff$ncompete[i]`.
