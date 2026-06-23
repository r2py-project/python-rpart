# Conversion Guide: `nchar` (R to Python)

---

## 1. Overview of `nchar` in R

`nchar` is a base-R function that takes a character vector and returns an integer vector whose elements represent the "size" of each corresponding string element. The measurement unit is controlled by the `type` argument:

- `"bytes"` — number of bytes required to store the string (encoding-dependent).
- `"chars"` — number of human-readable Unicode characters (the default when `type` is omitted or `"chars"`).
- `"width"` — number of columns the string would occupy in a fixed-width (monospaced) terminal display. This accounts for double-width characters (e.g., CJK ideographs that occupy two columns) and zero-width characters.

**Signature:**
```r
nchar(x, type = "chars", allowNA = FALSE, keepNA = NA)
```

**Return value:** An integer vector of the same length as `x`. For `NA` inputs, the return is `NA_integer_` when `keepNA = TRUE` (the default for `type = "chars"` and `type = "bytes"`), or `2L` (the printed width of `"NA"`) when `keepNA = FALSE`.

In all three usages found in the rpart source, `type = "w"` is passed. R accepts the abbreviated form `"w"` as a shorthand for `"width"`, so every call in this codebase measures **display column width**, not character count or byte count.

---

## 2. Contextual Usage Analysis

### 2.1 `summary.rpart.R` — `summary.rpart`, lines 88 and 100

Both occurrences share the same pattern:

```r
temp <- if (all(nchar(cuts[j], "w") < 25L))
            format(cuts[j], justify = "left")
        else cuts[j]
```

- `cuts` is a `character` vector built earlier in `summary.rpart` that holds formatted split-condition strings such as `"< 3.14"` or `"splits as LLR,"`.
- `j` is an integer index vector produced by `seq(...)`, so `cuts[j]` is a **character sub-vector** (multiple elements).
- `nchar(cuts[j], "w")` therefore returns an **integer vector** — one display-column count per element.
- `all(... < 25L)` collapses that vector to a single logical: if every split label is at most 24 columns wide, they are left-justified and aligned with `format()`; otherwise they are printed as-is.

The `"w"` (width) type is used deliberately here: the rpart authors need to know how many terminal columns each label will consume, which matters for ASCII-art tree output. Using `"chars"` instead would give wrong results for strings containing tabs or multibyte characters.

### 2.2 `zzz.R` — `string.bounding.box`, line 15

```r
string.bounding.box <- function(s)
{
    s2 <- strsplit(s, "\n")
    rows <- sapply(s2, length)
    columns <- sapply(s2, function(x) max(nchar(x, "w")))
    list(columns = columns, rows = rows)
}
```

- `s` is a character vector of (possibly multi-line) strings.
- `strsplit(s, "\n")` splits each element on newlines, producing a **list of character vectors**.
- The inner anonymous function receives `x` — one character vector of lines — and calls `nchar(x, "w")` to get the display-column width of every line, then takes `max(...)` to find the widest line.
- `sapply` iterates over the list, so `columns` ends up as an integer vector: the maximum display width of any line in each input string.

Again, `"w"` (width) is the correct type because `string.bounding.box` is computing a visual bounding box for terminal rendering.

**Recurring pattern:** Every usage passes `type = "w"` and operates on a **character vector** (never a scalar). The result is always an integer vector that feeds a numeric comparison or a `max()` call.

---

## 3. Python Conversion Strategy

The chosen library is **`wcwidth`** (specifically `wcwidth.wcswidth`) for the display-column-width measurement, combined with standard Python list/NumPy operations for vectorization.

**Why not `len()` or `str.__len__`?**
Python's built-in `len()` counts Unicode code points, which corresponds to R's `nchar(x, "chars")`. It does **not** account for double-width or zero-width characters, so it would give wrong results wherever `type = "w"` is used.

**Why `wcwidth`?**
The POSIX `wcswidth` function (wrapped by the `wcwidth` Python package) implements the same display-width algorithm that R uses for `nchar(x, "width")`:
- Printable ASCII characters have width 1.
- CJK and other double-width code points have width 2.
- Zero-width combining marks, control characters, etc. have width 0.
- `wcswidth` returns `-1` for strings containing non-printable characters (analogous to R returning `NA` with `allowNA = TRUE`).

**Vectorization:** Because the inputs in all rpart usages are Python lists or NumPy arrays of strings, the natural Python idiom is a list comprehension or `np.vectorize`, mirroring R's implicit vectorization. NumPy is used where the downstream operation is numeric (comparison, `max`).

---

## 4. Step-by-Step Conversion Examples

### 4.1 Conditional formatting based on display width — `summary.rpart` (lines 88 and 100)

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/summary.rpart.R`, function `summary.rpart`, lines 88 and 100.

**Original R context:**

- Input: `cuts[j]` — a `character` vector of split-label strings (e.g., `["< 3.14,", "splits as LR,"]`).
- Return of `nchar(cuts[j], "w")`: an `integer` vector of display-column widths.
- The vector is tested with `all(... < 25L)` to decide whether to call `format()`.

```r
# Generalized pattern (both line 88 and line 100 are identical in structure)
temp <- if (all(nchar(cuts[j], "w") < 25L))
            format(cuts[j], justify = "left")
        else cuts[j]
```

**Python equivalent:**

```python
import numpy as np
from wcwidth import wcswidth

def display_width(s: str) -> int:
    """Return the terminal display-column width of a string.
    Returns -1 if the string contains non-printable characters
    (mirrors R's nchar(x, 'width') with allowNA=TRUE behaviour).
    """
    w = wcswidth(s)
    return w if w >= 0 else len(s)  # graceful fallback for non-printable chars

def nchar_width(strings):
    """Vectorised equivalent of R's nchar(x, 'w').

    Parameters
    ----------
    strings : list[str] or np.ndarray[str]
        Character vector to measure.

    Returns
    -------
    np.ndarray[int]
        Integer array of display-column widths.
    """
    return np.array([display_width(s) for s in strings])


# Generalised equivalent of the R pattern at lines 88 and 100:
#
#   temp <- if (all(nchar(cuts[j], "w") < 25L))
#               format(cuts[j], justify = "left")
#           else cuts[j]
#
# Assume `cuts_j` is a Python list (or np.ndarray) of strings
# corresponding to R's cuts[j].

def format_cuts(cuts_j):
    widths = nchar_width(cuts_j)
    if np.all(widths < 25):
        # left-justify each label to the same width (mirrors R's format(..., justify="left"))
        max_w = int(widths.max()) if len(widths) > 0 else 0
        temp = [s.ljust(max_w) for s in cuts_j]
    else:
        temp = list(cuts_j)
    return temp
```

**Explanation:**

| R | Python |
|---|--------|
| `nchar(cuts[j], "w")` | `nchar_width(cuts_j)` — list comprehension over `wcswidth` |
| `all(... < 25L)` | `np.all(widths < 25)` |
| `format(cuts[j], justify = "left")` | `[s.ljust(max_w) for s in cuts_j]` |
| Integer vector result | `np.ndarray` of `int` |

`wcswidth` from the `wcwidth` package is the direct counterpart of R's `"width"` mode. The `ljust` call pads each string to the same length with spaces on the right, reproducing R's `format(..., justify = "left")` behaviour for character vectors.

---

### 4.2 Computing the visual bounding box of multi-line strings — `string.bounding.box` (line 15)

**Location:** `/groups/jli9/Yufei/python-rpart/rpart/R/zzz.R`, function `string.bounding.box`, line 15.

**Original R context:**

- Input `s`: a `character` vector of strings, each of which may contain embedded newline characters.
- `strsplit(s, "\n")` produces a list of character vectors (one per input element).
- `nchar(x, "w")` is called on each inner character vector `x` (the lines of one string) to get a width-per-line integer vector.
- `max(...)` picks the widest line.
- Return: a named `list` with `columns` (integer vector, max display width per input string) and `rows` (integer vector, line count per input string).

```r
string.bounding.box <- function(s)
{
    s2      <- strsplit(s, "\n")
    rows    <- sapply(s2, length)
    columns <- sapply(s2, function(x) max(nchar(x, "w")))
    list(columns = columns, rows = rows)
}
```

**Python equivalent:**

```python
import numpy as np
from wcwidth import wcswidth

def display_width(s: str) -> int:
    """Terminal display-column width of a single string."""
    w = wcswidth(s)
    return w if w >= 0 else len(s)

def string_bounding_box(s):
    """Python equivalent of R's string.bounding.box(s).

    Parameters
    ----------
    s : list[str]
        Character vector of (possibly multi-line) strings.

    Returns
    -------
    dict with keys:
        'columns' : np.ndarray[int]  — max display-column width per element of s
        'rows'    : np.ndarray[int]  — number of lines per element of s
    """
    s2      = [elem.split("\n") for elem in s]          # equivalent to strsplit(s, "\n")
    rows    = np.array([len(lines) for lines in s2])    # sapply(s2, length)
    columns = np.array([
        max(display_width(line) for line in lines) if lines else 0
        for lines in s2
    ])                                                   # sapply(s2, function(x) max(nchar(x, "w")))
    return {"columns": columns, "rows": rows}
```

**Explanation:**

| R | Python |
|---|--------|
| `strsplit(s, "\n")` | `[elem.split("\n") for elem in s]` |
| `sapply(s2, length)` | `np.array([len(lines) for lines in s2])` |
| `nchar(x, "w")` (inner vector) | `[display_width(line) for line in lines]` |
| `max(nchar(x, "w"))` | `max(display_width(line) for line in lines)` |
| `sapply(..., max(...))` | outer list comprehension wrapped in `np.array(...)` |
| `list(columns=..., rows=...)` | `{"columns": ..., "rows": ...}` |

The key translation is replacing R's implicit vectorization (R applies `nchar` element-wise automatically) with an explicit list comprehension in Python. The `wcwidth.wcswidth` function operates on a whole string, so it is applied to each line individually rather than the whole multi-line block. The `display_width` helper shields callers from the `-1` sentinel that `wcswidth` returns for non-printable input.
