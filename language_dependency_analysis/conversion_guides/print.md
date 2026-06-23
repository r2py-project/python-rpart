# Conversion Guide: `print` in R (rpart Package)

---

## 1. Overview of `print` in R

`print` is R's generic output function. It dispatches to a method based on the class of its first argument — `print.default` for plain vectors and matrices, `print.matrix` for matrix objects, and so on. Its key behaviors relevant to this guide are:

- **Printing character vectors with `quote = FALSE`:** When called on a character vector, `print` displays each element surrounded by no quotation marks (when `quote = FALSE`), one element per line, with a positional index prefix like `[1]`.
- **Printing numeric matrices with `digits`:** When called on a numeric matrix or data frame, `print` formats every number to the given number of significant digits and renders a full tabular display with row and column labels.
- **Printing named numeric vectors:** When called on a named integer or double vector, `print` renders a two-row layout — names on top, values below — respecting the `digits` option in the session.
- **Side effects vs. return value:** `print` is called for its side effect (writing to stdout). It invisibly returns its first argument unchanged, which is why R code can use `print(x$cptable)` inside a function that later calls `invisible(x$cptable)` — the matrix value is passed through.

---

## 2. Contextual Usage Analysis

The four CSV rows span two files and three functionally distinct patterns.

**Pattern A — `print` on a sorted character vector (`quote = FALSE`).**
Location: `printcp.R`, line 22.
`used` is derived from `frame$var`, a character factor/vector of variable names that appeared as split variables in the tree. After `unique()` and `as.character()`, it is a plain character vector of variable-name strings. `sort()` orders it lexicographically. `print(..., quote = FALSE)` renders it without surrounding quotation marks, prefixed with a positional index (`[1] age sex ...`).

**Pattern B — `print` on a numeric matrix with `digits`.**
Locations: `printcp.R` line 37 and `summary.rpart.R` line 24.
`x$cptable` is a numeric matrix with named rows and named columns (columns include `CP`, `nsplit`, `rel error`, `xerror`, `xstd`). `print(x$cptable, digits = digits)` renders it as a formatted table to stdout, respecting significant-digit precision.

**Pattern C — `print` on a named integer vector filtered by a logical condition.**
Location: `summary.rpart.R`, line 29.
`x$variable.importance` is a named numeric vector (variable name to importance score). After rounding and percentage conversion it becomes a named integer vector `temp`. `temp[temp > 0]` subsets it to entries that are non-zero. `print(temp[temp > 0])` renders it as a named vector display (names on one line, values on the next).

The two occurrences of Pattern B (`printcp.R:37` and `summary.rpart.R:24`) are identical in structure and receive identical treatment; they are grouped into a single conversion example.

---

## 3. Python Conversion Strategy

The data types involved are:

- A sorted Python `list` of strings (Pattern A).
- A `numpy.ndarray` with named rows/columns — most naturally represented as a `pandas.DataFrame` (Pattern B).
- A `pandas.Series` with a string index (Pattern C).

**Library choices:**

- `pandas` is the primary tool. It provides `DataFrame` (matching R's named matrix) and `Series` (matching R's named vector), each with a `__repr__` and `to_string()` that closely mirrors R's tabular display.
- The standard `print()` built-in in Python replaces R's `print()` for the side-effect of writing to stdout.
- No `numpy` call is needed directly in the print step, though `x_cptable` may internally be a `numpy` array that is wrapped in a `DataFrame` upstream.

---

## 4. Step-by-Step Conversion Examples

---

### 4.1 Pattern A — Printing a Sorted Character Vector Without Quotes

**Locations:** `printcp.R`, function `printcp`, line 22.

**Original R Context**

```r
# used: character vector of variable names (strings) that appear as split
#       variables in the tree frame, after unique() and as.character()
# sort() returns a lexicographically ordered character vector
# print(..., quote = FALSE) renders without surrounding quotation marks

used <- unique(frame$var[!leaves])   # character vector, e.g. c("age", "sex", "pclass")

if (!is.null(used)) {
    cat("Variables actually used in tree construction:\n")
    print(sort(as.character(used)), quote = FALSE)
    cat("\n")
}
```

R output example:
```
Variables actually used in tree construction:
[1] age    pclass sex
```

**Python Equivalent**

```python
import numpy as np

# used: a Python list or numpy array of variable name strings
# equivalent of sort(as.character(used))
used_sorted = sorted(str(v) for v in used)

if used_sorted:
    print("Variables actually used in tree construction:")
    # R prints a positional index prefix; reproduce it for fidelity
    # For a compact single-line display matching R's default width behaviour:
    line = "  ".join(used_sorted)
    print(f"[1] {line}")
    print()
```

For closer fidelity to R's line-wrapping index prefix behaviour (handling long lists):

```python
def print_char_vector(vec, width=80):
    """Mimic R's print.default for a character vector with quote=FALSE."""
    items = list(vec)
    prefix_len = len(f"[{len(items)}]") + 1   # width of the widest index label
    col_width = max(len(s) for s in items) + 2  # padded item width
    cols = max(1, (width - prefix_len) // col_width)
    for i in range(0, len(items), cols):
        chunk = items[i:i + cols]
        label = f"[{i + 1}]"
        row = label.ljust(prefix_len) + "".join(s.ljust(col_width) for s in chunk)
        print(row)

if used_sorted:
    print("Variables actually used in tree construction:")
    print_char_vector(used_sorted)
    print()
```

**Explanation**

| R | Python |
|---|--------|
| `as.character(used)` | `[str(v) for v in used]` — explicit string coercion |
| `sort(...)` | `sorted(...)` — returns a new sorted list |
| `print(..., quote = FALSE)` | `print(...)` — Python's built-in never adds quotation marks around bare string values |
| Positional index `[1]` | Must be reproduced manually; R generates it automatically for vectors |

The `quote = FALSE` argument has no direct Python analogue because Python's `print()` on a plain string never adds surrounding quotes. The index prefix (`[1]`, `[4]`, ...) is the only visual element that requires manual reconstruction for full display fidelity.

---

### 4.2 Pattern B — Printing a Numeric Matrix with Digit Precision

**Locations:** `printcp.R` function `printcp` line 37; `summary.rpart.R` function `summary.rpart` line 24. Both are structurally identical.

**Original R Context**

```r
# x$cptable: a numeric matrix, rows named by node index,
#             columns: CP, nsplit, rel error, xerror, xstd
# digits: integer, default getOption("digits") - 2  (printcp) or
#                           getOption("digits")      (summary.rpart)
# print.matrix renders a formatted table to stdout

print(x$cptable, digits = digits)
```

R output example:
```
          CP nsplit rel error  xerror     xstd
1 0.10526316      0 1.0000000 1.00000 0.102062
2 0.01000000      3 0.6842105 0.89474 0.095857
```

**Python Equivalent**

```python
import pandas as pd

# cptable: pandas.DataFrame with the same column names as R's matrix
# digits: int — number of significant digits

def print_cptable(cptable: pd.DataFrame, digits: int) -> None:
    """Mimic R's print(x$cptable, digits=digits)."""
    # pandas float_format applies significant-digit rounding for display
    formatted = cptable.to_string(
        float_format=lambda v: f"{v:.{digits}g}"
    )
    print(formatted)

# Usage inside the converted printcp / summary_rpart functions:
print_cptable(x_cptable, digits=digits)
```

If `x_cptable` is stored as a raw `numpy.ndarray` with separate row/column name lists:

```python
import numpy as np
import pandas as pd

# col_names: list of str  e.g. ["CP", "nsplit", "rel error", "xerror", "xstd"]
# row_names: list of str  e.g. ["1", "2", "3", ...]
cptable_df = pd.DataFrame(x_cptable, index=row_names, columns=col_names)
print_cptable(cptable_df, digits=digits)
```

**Explanation**

| R | Python |
|---|--------|
| `print(matrix, digits = digits)` | `df.to_string(float_format=lambda v: f"{v:.{digits}g}")` then `print()` |
| R's `digits` = significant digits | Python's `g` format code also counts significant digits |
| Row/column names embedded in the matrix object | Stored as `index` and `columns` of the `DataFrame` |
| Returns matrix invisibly | `print_cptable` returns `None`; caller ignores the return value |

The `g` format specifier in Python (`:.{digits}g`) is the closest analogue to R's `signif(x, digits)` display behaviour: it uses the given number of significant figures and automatically switches between fixed and scientific notation at the same thresholds R uses.

---

### 4.3 Pattern C — Printing a Named Integer Vector Filtered by Positive Values

**Location:** `summary.rpart.R`, function `summary.rpart`, line 29.

**Original R Context**

```r
# x$variable.importance: named numeric vector  {var_name -> importance_score}
# After percentage-rounding it becomes a named integer vector
# temp[temp > 0] subsets to non-zero entries (a named integer vector)
# print renders: names on line 1, values on line 2, with positional index prefix

if (!is.null(temp <- x$variable.importance)) {
    temp <- round(100 * temp / sum(temp))   # named integer vector, sums to ~100
    if (any(temp > 0)) {
        cat("\nVariable importance\n")
        print(temp[temp > 0])               # subset then print
    }
}
```

R output example:
```
Variable importance
   age pclass    sex 
    36     34     30 
```

**Python Equivalent**

```python
import pandas as pd
import numpy as np

# variable_importance: pandas.Series  {str -> float},  index = variable names
# Replicate R's computation then print

if variable_importance is not None:
    temp = (100 * variable_importance / variable_importance.sum()).round().astype(int)
    temp_nonzero = temp[temp > 0]
    if len(temp_nonzero) > 0:
        print("\nVariable importance")
        print(temp_nonzero.to_string())
```

For exact R-style two-row layout (names above, values below, right-aligned columns):

```python
def print_named_int_vector(series: pd.Series) -> None:
    """Mimic R's print.default for a named integer vector."""
    names = [str(idx) for idx in series.index]
    values = [str(int(v)) for v in series.values]
    col_widths = [max(len(n), len(v)) for n, v in zip(names, values)]
    name_row  = "  ".join(n.rjust(w) for n, w in zip(names, col_widths))
    value_row = "  ".join(v.rjust(w) for v, w in zip(values, col_widths))
    print(name_row)
    print(value_row)

if variable_importance is not None:
    temp = (100 * variable_importance / variable_importance.sum()).round().astype(int)
    temp_nonzero = temp[temp > 0]
    if len(temp_nonzero) > 0:
        print("\nVariable importance")
        print_named_int_vector(temp_nonzero)
```

**Explanation**

| R | Python |
|---|--------|
| `temp <- round(100 * temp / sum(temp))` | `(100 * series / series.sum()).round().astype(int)` |
| `temp[temp > 0]` | `temp[temp > 0]` — identical boolean-index syntax in pandas |
| `print(named_int_vector)` | `series.to_string()` or the custom `print_named_int_vector` helper |
| Names displayed above values | pandas `to_string()` places the index on the left; the helper reproduces the stacked R layout |
| `any(temp > 0)` | `len(temp_nonzero) > 0` or `(temp > 0).any()` |

The most important nuance is the display orientation: R's `print` for a named vector stacks names above values in columns, whereas pandas `Series.to_string()` places the index to the left of each value. For programmatic use (logging, downstream processing) `to_string()` is sufficient. For visual fidelity to R's output the `print_named_int_vector` helper reproduces the stacked layout exactly.

---

## Summary Table

| CSV Row | R call | Data type of first argument | Recommended Python equivalent |
|---|---|---|---|
| `printcp.R:22` | `print(sort(as.character(used)), quote=FALSE)` | `character vector` | `sorted(...)` + `print(...)` or `print_char_vector()` helper |
| `printcp.R:37` | `print(x$cptable, digits=digits)` | `numeric matrix` | `pd.DataFrame.to_string(float_format=...)` |
| `summary.rpart.R:24` | `print(x$cptable, digits=digits)` | `numeric matrix` | `pd.DataFrame.to_string(float_format=...)` (identical to above) |
| `summary.rpart.R:29` | `print(temp[temp > 0])` | `named integer vector` | `pd.Series.to_string()` or `print_named_int_vector()` helper |
