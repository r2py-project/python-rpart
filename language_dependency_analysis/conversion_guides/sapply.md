### 1. Overview of `sapply` in R

`sapply` is a member of R's `*apply` family of higher-order functions. It iterates over a list or vector, applies a supplied function to each element, and then attempts to simplify the result into the most compact structure possible — returning a named vector if each call returns a scalar, a matrix if each call returns a vector of equal length, or a list if simplification is not possible.

**Signature:**
```r
sapply(X, FUN, ..., simplify = TRUE, USE.NAMES = TRUE)
```

- `X`: a list or vector to iterate over.
- `FUN`: the function to apply to each element of `X`.
- `simplify`: if `TRUE` (the default), the result is simplified to a vector or matrix where possible.
- `USE.NAMES`: if `TRUE` and `X` is a character vector, the names of `X` are used as names of the result.

When every call to `FUN` returns a single scalar value, `sapply` behaves like a vectorized `map` that immediately flattens the results into a plain atomic vector (integer, double, character, etc.).

---

### 2. Contextual Usage Analysis

**Source file:** `/groups/jli9/Yufei/python-rpart/rpart/R/zzz.R`, function `string.bounding.box` (lines 11–17).

The function accepts `s`, a character vector where each element may contain embedded newline characters `\n`. `strsplit(s, "\n")` converts `s` into `s2`, a list where each element is itself a character vector — the individual lines of that original string.

Both `sapply` calls iterate over `s2` (a list of character vectors) and each produces a simplified integer vector whose length equals `length(s2)` (i.e., `length(s)`):

**Usage 1 — counting rows (lines 13–14):**
```r
s2 <- strsplit(s, "\n")
rows <- sapply(s2, length)
```
- Input to `FUN`: each element of `s2` is a `character` vector (the split lines of one input string).
- `length(x)` returns an integer scalar — the number of lines in that string.
- Result type: integer vector, one element per input string.

**Usage 2 — measuring column width (line 15):**
```r
columns <- sapply(s2, function(x) max(nchar(x, "w")))
```
- Input to `FUN`: same character vector of lines `x`.
- `nchar(x, "w")` computes the display width (in terminal columns) of each line, returning an integer vector.
- `max(...)` collapses that to a single integer — the widest line in the string.
- Result type: integer vector, one element per input string.

Both results are returned in a list: `list(columns = columns, rows = rows)`. The recurring pattern is: apply a scalar-returning function to each element of a list and collect results into a flat vector — the canonical `sapply` use case.

The `"w"` argument to `nchar` selects width-in-columns counting (i.e., double-wide CJK characters count as 2), as opposed to the default `"chars"` (Unicode code points) or `"bytes"`.

---

### 3. Python Conversion Strategy

Because `sapply` in these usages maps a function over a Python-list-of-lists and collects scalar results into a flat array, the natural Python equivalents are:

- A **list comprehension** or `[f(x) for x in s2]` pattern for simple, readable element-wise application.
- **`numpy.array(...)`** wrapping the comprehension to produce a typed array equivalent to R's simplified integer vector.

`numpy` is chosen as the primary library because:

1. R's `sapply` with scalar-returning functions produces a typed atomic vector; `numpy.array` is the closest structural equivalent (contiguous, typed, supports vectorized downstream arithmetic).
2. The `nchar(..., "w")` width computation has no direct NumPy primitive — it requires Python's `unicodedata.east_asian_width` for accurate display-width counting — so the inner loop is handled with a helper function, and `numpy` wraps the outer result.
3. A pure list comprehension without `numpy` is also valid where the caller only needs a Python list; both forms are shown.

For `nchar(x, "w")`, the standard library function `unicodedata.east_asian_width` is used to replicate R's display-width semantics. Each character is classified and assigned a width of 2 if it is full-width or wide, and 1 otherwise.

---

### 4. Step-by-Step Conversion Examples

#### Usage 1: `sapply(s2, length)` — count lines per string

**Locations:** `zzz.R`, function `string.bounding.box`, line 14.

**Original R Context**

- `s`: character vector of strings (possibly containing `\n`).
- `s2`: list of character vectors produced by `strsplit(s, "\n")`.
- `length` applied to each element returns the number of lines in that string.
- Return type: integer vector of length `length(s)`.

```r
# Generalized R snippet
s <- c("hello\nworld", "foo\nbar\nbaz")
s2 <- strsplit(s, "\n")
rows <- sapply(s2, length)
# rows => c(2L, 3L)
```

**Python Equivalent**

```python
import numpy as np

s = ["hello\nworld", "foo\nbar\nbaz"]

# Replicate strsplit(s, "\n")
s2 = [item.split("\n") for item in s]

# Replicate sapply(s2, length)
rows = np.array([len(x) for x in s2], dtype=int)
# rows => array([2, 3])
```

**Explanation**

- `strsplit(s, "\n")` becomes a list comprehension calling `str.split("\n")` on each element.
- `sapply(s2, length)` maps Python's built-in `len` over each sub-list. The list comprehension `[len(x) for x in s2]` is the direct equivalent.
- Wrapping with `np.array(..., dtype=int)` produces a typed integer array, matching R's simplified integer vector. Where a plain Python list suffices downstream, `np.array` can be omitted.

---

#### Usage 2: `sapply(s2, function(x) max(nchar(x, "w")))` — maximum display width per string

**Locations:** `zzz.R`, function `string.bounding.box`, line 15.

**Original R Context**

- `s2`: list of character vectors (same as Usage 1).
- For each element `x` (a character vector of lines), `nchar(x, "w")` returns an integer vector of display widths — double-wide characters (e.g., CJK) count as 2, ordinary characters as 1.
- `max(...)` reduces to the widest line's display-column count.
- Return type: integer vector of length `length(s)`.

```r
# Generalized R snippet
s <- c("hello\nworld", "foo\nbar\nbaz")
s2 <- strsplit(s, "\n")
columns <- sapply(s2, function(x) max(nchar(x, "w")))
# columns => c(5L, 3L)   ("hello" and "world" are 5; "foo","bar","baz" are 3)
```

**Python Equivalent**

```python
import unicodedata
import numpy as np

def display_width(text: str) -> int:
    """Return the terminal display width of a string.

    Replicates R's nchar(x, type='w'): full-width and wide Unicode
    characters (e.g., CJK) count as 2 columns; all others count as 1.
    """
    width = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        width += 2 if eaw in ("W", "F") else 1
    return width

s = ["hello\nworld", "foo\nbar\nbaz"]

# Replicate strsplit(s, "\n")
s2 = [item.split("\n") for item in s]

# Replicate sapply(s2, function(x) max(nchar(x, "w")))
columns = np.array(
    [max(display_width(line) for line in x) for x in s2],
    dtype=int,
)
# columns => array([5, 3])
```

**Explanation**

- `nchar(x, "w")` computes display widths. Python's `len(str)` counts Unicode code points (equivalent to R's `nchar(x, "chars")`), not display columns. To match `"w"` semantics, `unicodedata.east_asian_width` must be used. The helper `display_width` replicates this for a single string; it is applied inside a generator expression to each line.
- `max(nchar(x, "w"))` becomes `max(display_width(line) for line in x)` — a generator expression whose result is reduced by Python's built-in `max`.
- The outer `sapply` over `s2` becomes the enclosing list comprehension `[max(...) for x in s2]`.
- `np.array(..., dtype=int)` again produces the typed integer array matching R's simplified vector output.
- `unicodedata` is part of the Python standard library; no third-party installation is required.
