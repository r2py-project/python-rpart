# Conversion Guide: `max` in R

## 1. Overview of `max` in R

`max` returns the maximum value of a set of numeric, character, or logical values. Its signature is:

```r
max(..., na.rm = FALSE)
```

- `...` — one or more atomic R objects (scalars, vectors, or matrices). When multiple arguments are supplied they are all treated as a single flat collection of values.
- `na.rm` — logical; if `TRUE`, missing values (`NA`) are stripped before the computation.

Return value: a length-1 scalar of the same basic type as the inputs. For numeric inputs the result is always a double. When all values are `NA` and `na.rm = TRUE`, R returns `-Inf` with a warning.

R's `max` is inherently vectorized over its arguments: `max(a, b)` where `a` and `b` are vectors returns the single largest element found across **all** elements of both vectors, not an element-wise maximum. Element-wise pairwise maximum is handled by `pmax`.

## 2. Contextual Usage Analysis

The CSV covers twelve call sites across six files. All usages fall into three functional patterns:

**Pattern A — Maximum of an arithmetic combination of two numeric vectors (element-wise sum, then max):**
- `plotcp.R:19`: `max(xerror + xstd)` — `xerror` and `xstd` are numeric vectors extracted from columns of a matrix (`p.rpart`). Their element-wise sum is formed first, then the overall maximum is returned as a scalar used to set a plot's y-axis upper limit.
- `rsq.rpart.R:24`: `max(xerror + xstd)` — identical pattern, same data types, same purpose.

**Pattern B — Maximum of a single numeric vector (possibly with NA values, or with a scalar floor):**
- `rpart.class.R:7`: `max(y[!is.na(y)])` — `y` is an integer vector (class indices). NAs are pre-filtered by subsetting; the result is the number of classes (`numclass`), used as a scalar integer.
- `rpart.exp.R:42`: `max(time)` — `time` is a numeric vector of survival times; the result is a scalar appended to build the interval table `itable`.
- `rpartco.R:26` (first): `max(depth)` — `depth` is an integer vector of tree depths; result is a scalar divisor.
- `rpartco.R:26` (second): `max(depth, 4L)` — `depth` is an integer vector and `4L` is a scalar; all values are pooled and the single overall maximum is returned. This enforces a minimum denominator of 4.
- `rpartco.R:43`: `max(depth)` used as a divisor after deviance-based layout has been computed; same type as above.
- `zzz.R:45`: `max(lev)` — `lev` is a numeric vector of log-base-2 tree levels; the result is a scalar controlling a loop's starting index.

**Pattern C — Maximum of a derived character/integer property of a character vector:**
- `text.rpart.R:78`: `max(string.bounding.box(stat)$columns)` — `stat` is a character vector; `string.bounding.box` returns a list whose `$columns` element is an integer vector of per-string column widths. Result is a scalar integer used to compute box dimensions.
- `text.rpart.R:79`: `max(string.bounding.box(stat)$rows)` — same structure; `$rows` is an integer vector of line counts per string.
- `zzz.R:15`: `max(nchar(x, "w"))` — called inside `sapply` over a list; `x` is a character vector (lines of one string split on `"\n"`); `nchar(x, "w")` returns an integer vector of widths; the result is a scalar maximum width for that string.

**Recurring patterns:**
- Every call site produces a **scalar** result used immediately in arithmetic, indexing, or as an argument to another function.
- No call site passes `na.rm = TRUE`; NA handling is done via explicit subsetting (`y[!is.na(y)]`) before calling `max`.
- Two call sites (`rpartco.R:26`) pass two arguments to `max` to enforce a minimum value, a common R idiom equivalent to `max(value, floor_value)`.

## 3. Python Conversion Strategy

**Chosen library: `numpy`**

All inputs to `max` in this codebase are numeric vectors (R integer or double) or integer vectors derived from string operations. NumPy arrays are the natural Python analogue. `numpy.max` / `ndarray.max()` operates on arrays in exactly the same way R's `max` operates on vectors: it reduces the entire array to a single scalar. This matches every usage pattern found in the CSV.

For the two-argument pattern `max(a, b)` where one argument is a scalar floor, the direct translation is `max(np.max(a), b)` using Python's built-in `max` on two scalars, or equivalently `np.maximum(np.max(a), b)`. Because both `a` is always a 1-D array and `b` is always a known scalar constant, the simpler built-in `max()` call on two Python scalars is the clearest choice after `np.max(a)` reduces the array.

For Pattern C (max of integer widths derived from strings), NumPy is equally appropriate since the width arrays are computed with `np.array([len(line) for line in ...])` or similar list comprehensions.

`math.max` does not exist; the standard library `math` module has no multi-element `max`. Python's built-in `max()` works correctly on lists or arrays but does not compose as naturally with array arithmetic as `np.max()`.

## 4. Step-by-Step Conversion Examples

### 4.1 Maximum of element-wise vector sum (Pattern A)

**Locations:** `plotcp.R` — `plotcp`; `rsq.rpart.R` — `rsq.rpart`

**Original R Context:**

Input types: `xerror` and `xstd` are numeric vectors (doubles) of equal length extracted from matrix columns. Their element-wise sum produces a numeric vector. `max` reduces it to a scalar double.

```r
# xerror: numeric vector, e.g. c(1.0, 0.8, 0.75)
# xstd:   numeric vector of same length
ylim_upper <- max(xerror + xstd) + 0.1
```

**Python Equivalent:**

```python
import numpy as np

# xerror: np.ndarray, shape (n,), dtype float64
# xstd:   np.ndarray, shape (n,), dtype float64
ylim_upper = np.max(xerror + xstd) + 0.1
```

**Explanation:** R's `+` on two vectors and Python's `+` on two NumPy arrays are both element-wise, so `xerror + xstd` produces an array of the same length in both languages. `np.max()` then reduces it to a Python float scalar, matching R's scalar double result exactly.

---

### 4.2 Maximum of a vector with NA pre-filtering (Pattern B — with NA removal)

**Locations:** `rpart.class.R` — `rpart.class`

**Original R Context:**

Input type: `y` is an integer vector that may contain `NA` values (converted from a factor). The subsetting `y[!is.na(y)]` removes NAs before passing to `max`, yielding a clean integer vector. The result is a scalar integer representing the number of classes.

```r
# y: integer vector (may contain NA)
numclass <- max(y[!is.na(y)])
```

**Python Equivalent:**

```python
import numpy as np

# y: np.ndarray, dtype int (may contain np.nan if stored as float,
#    or use a masked array)
numclass = int(np.max(y[~np.isnan(y)]))
```

**Explanation:**
- `~np.isnan(y)` is the NumPy equivalent of `!is.na(y)`, producing a boolean mask.
- Boolean indexing `y[~np.isnan(y)]` filters the array, matching R's `y[!is.na(y)]`.
- If `y` is stored as a true integer dtype (`np.int32`/`np.int64`), NumPy integers cannot hold `NaN`; in that case NA values should be represented as a sentinel (e.g., `-1`) or via `np.ma.masked_array`. The guard becomes `np.max(y[y != sentinel])`.
- The `int()` cast converts the NumPy scalar to a plain Python int, consistent with using the result as a class count.

---

### 4.3 Maximum of a plain numeric vector (Pattern B — no NA concern)

**Locations:** `rpart.exp.R` — `rpart.exp`; `rpartco.R` — `rpartco` (lines 26 first usage, 43)

**Original R Context:**

Input type: a numeric (double) vector with no NA values. Result is a scalar double used in arithmetic or as a vector element.

```r
# time: numeric vector of positive survival times
itable <- c(0, dtimes[-length(dtimes)], max(time))

# depth: integer vector of tree node depths
y <- (1 + max(depth) - depth) / max(depth, 4L)   # see Pattern B-floor below
fudge <- minbranch * diff(range(y)) / max(depth)
```

**Python Equivalent:**

```python
import numpy as np

# time: np.ndarray, shape (n,), dtype float64
itable = np.concatenate([[0.0], dtimes[:-1], [np.max(time)]])

# depth: np.ndarray, shape (n,), dtype int
max_depth = np.max(depth)
fudge = minbranch * np.ptp(y) / max_depth   # np.ptp = peak-to-peak = diff(range())
```

**Explanation:**
- `np.max(time)` directly replaces `max(time)`.
- `np.concatenate` with singleton lists replaces R's `c()`.
- `np.ptp(y)` replaces `diff(range(y))` (peak-to-peak = max − min).
- `max_depth` is computed once and reused, matching the two separate `max(depth)` calls in the same expression.

---

### 4.4 Maximum of a vector with a scalar floor (Pattern B — two-argument max)

**Locations:** `rpartco.R` — `rpartco` (line 26, second usage)

**Original R Context:**

Input types: `depth` is an integer vector; `4L` is a scalar integer. R pools all values from both arguments into one collection and returns the single largest value. This idiom enforces a minimum denominator of 4.

```r
# depth: integer vector
y <- (1 + max(depth) - depth) / max(depth, 4L)
```

**Python Equivalent:**

```python
import numpy as np

# depth: np.ndarray, shape (n,), dtype int
y = (1 + np.max(depth) - depth) / max(int(np.max(depth)), 4)
```

**Explanation:**
- R's `max(depth, 4L)` returns `max(max_of_vector, 4)`. In Python, `max(int(np.max(depth)), 4)` achieves the same result by comparing two scalars with the built-in `max`.
- Alternatively: `np.maximum(np.max(depth), 4)` is equally valid and stays within NumPy.
- Do **not** use `np.max(depth, 4)` — the second positional argument to `np.max` is `axis`, not a comparison value, which would raise an error.

---

### 4.5 Maximum of tree depth levels (scalar loop bound)

**Locations:** `zzz.R` — `descendants`

**Original R Context:**

Input type: `lev` is a numeric vector of `floor(log2(nodes))` values. Result is a scalar numeric used as the starting value of a `for` loop iterating down through levels.

```r
# lev: numeric vector of tree levels
for (i in max(lev):2L) { ... }
```

**Python Equivalent:**

```python
import numpy as np

# lev: np.ndarray, shape (n,), dtype float64 or int
for i in range(int(np.max(lev)), 1, -1):
    ...
```

**Explanation:**
- R's `max(lev):2L` generates a decreasing integer sequence from the maximum level down to 2 inclusive.
- Python's `range(int(np.max(lev)), 1, -1)` produces the equivalent sequence (stop is exclusive, so `1` excludes 2 — wait: `range(start, 1, -1)` yields `start, start-1, ..., 2`, which matches R's `max(lev):2L`).
- `int(np.max(lev))` converts the NumPy scalar to a Python int, as `range` requires integer arguments.

---

### 4.6 Maximum character width of string lines (Pattern C — inner `sapply` usage)

**Locations:** `zzz.R` — `string.bounding.box`

**Original R Context:**

Inside `string.bounding.box`, each string in `s` is split on `"\n"` to yield a character vector `x` of lines. `nchar(x, "w")` returns an integer vector of display widths (Unicode-aware); `max(...)` returns the widest line as a scalar integer. This is called via `sapply` over all strings in `s`.

```r
string.bounding.box <- function(s) {
    s2 <- strsplit(s, "\n")
    rows <- sapply(s2, length)
    columns <- sapply(s2, function(x) max(nchar(x, "w")))
    list(columns = columns, rows = rows)
}
```

**Python Equivalent:**

```python
# s: list of str (each may contain embedded newlines)
def string_bounding_box(s):
    s2 = [item.split("\n") for item in s]
    rows = np.array([len(lines) for lines in s2])
    columns = np.array([max(len(line) for line in lines) for lines in s2])
    return {"columns": columns, "rows": rows}
```

**Explanation:**
- R's `strsplit(s, "\n")` becomes a list comprehension using Python's `str.split("\n")`.
- R's `nchar(x, "w")` with type `"w"` measures display width (counts wide/CJK characters as 2). Python's built-in `len()` counts Unicode code points, not display columns. For exact Unicode-width parity, use `wcwidth.wcswidth(line)` from the `wcwidth` package. In ASCII-only contexts `len(line)` is sufficient.
- Python's built-in `max()` on a generator is appropriate here because the input is a plain Python list of strings; NumPy is used only to collect the per-string scalar results into an array.

---

### 4.7 Maximum of bounding-box integer vectors (Pattern C — outer usage)

**Locations:** `text.rpart.R` — `text.rpart` (lines 78–79)

**Original R Context:**

`string.bounding.box(stat)` returns a list with `$columns` (integer vector of per-label column widths) and `$rows` (integer vector of per-label line counts). `max(...)` reduces each to a scalar integer used to size ovals/rectangles on the plot.

```r
# stat: character vector of node label strings
maxlen <- max(string.bounding.box(stat)$columns) + 1L
maxht  <- max(string.bounding.box(stat)$rows) + 1L
```

**Python Equivalent:**

```python
import numpy as np

# stat: list of str
bbox = string_bounding_box(stat)          # returns dict with "columns" and "rows"
maxlen = int(np.max(bbox["columns"])) + 1
maxht  = int(np.max(bbox["rows"])) + 1
```

**Explanation:**
- `string_bounding_box` (defined in section 4.6) returns NumPy arrays for `"columns"` and `"rows"`.
- `np.max()` reduces each array to a scalar, then `int()` converts to a plain Python int before adding `1`, matching R's `+ 1L`.
- The two calls in the original R code evaluate `string.bounding.box(stat)` twice; in Python it is more efficient to call `string_bounding_box(stat)` once and reuse the result.
