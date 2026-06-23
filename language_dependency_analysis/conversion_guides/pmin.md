# Conversion Guide: `pmin` (R to Python)

---

## 1. Overview of `pmin` in R

`pmin(..., na.rm = FALSE)` is a base-R function that computes the **parallel (element-wise) minimum** across two or more vectors. Given vectors of the same (or recyclable) length it returns a single vector where each element is the minimum of the corresponding elements taken from all input vectors.

Key properties:

- **Vectorized by design.** All inputs are treated as vectors and compared position-by-position.
- **Recycling.** If inputs have unequal lengths, shorter inputs are recycled to match the length of the longest input (with a warning when lengths are not multiples of each other).
- **NA propagation.** With the default `na.rm = FALSE`, any `NA` at a given position causes `NA` in the output at that position. Setting `na.rm = TRUE` ignores `NA` values, but the result is still `NA` if *all* parallel elements are `NA`.
- **Return type.** The return type follows the hierarchy `integer < double < character`; the highest type present among the inputs is used.
- **Attribute inheritance.** Names and other attributes are copied from the first argument where applicable.

Typical signature:

```r
pmin(..., na.rm = FALSE)
```

---

## 2. Contextual Usage Analysis

The CSV data lists two call sites, both using `pmin` to cap or select element-wise minima between integer vectors.

### Usage 1 — `labels.rpart.R`, line 68

```r
c(letters, LETTERS)[pmin(seq_along(z), 52L)]
```

Inside a `lapply` callback over `xlevels`, `z` is a character vector of factor levels. `seq_along(z)` produces the integer sequence `1, 2, ..., length(z)`. `pmin(seq_along(z), 52L)` clamps every index to at most `52`, ensuring that when a factor has more than 52 levels the index stays within the 52-element `c(letters, LETTERS)` alphabet. The result is a length-`length(z)` integer vector used as a subscript.

Data types involved:
- `seq_along(z)`: integer vector of length `n` (number of factor levels)
- `52L`: integer scalar (recycled to length `n`)
- Return: integer vector of length `n` with values in `[1, 52]`

### Usage 2 — `rpartco.R`, line 129, inside `compress()`

```r
templ[1L:mind] <- pmin(templ[1L:mind], left$left)
```

Inside the recursive `compress` helper, `templ` is a numeric (double) vector of left-boundary x-coordinates indexed by depth. `left$left` is a numeric vector of corresponding left-boundary values returned from the recursive call. `pmin` takes the element-wise minimum of the two sub-vectors so that `templ` retains the narrowest (leftmost) boundary at each depth level where both subtrees overlap.

Data types involved:
- `templ[1L:mind]`: numeric (double) vector of length `mind`
- `left$left`: numeric (double) vector of length `mind`
- Return: numeric (double) vector of length `mind`

**Recurring pattern.** In both usages `pmin` is called with exactly two arguments — an integer or numeric vector and either a scalar (usage 1) or a same-length vector (usage 2) — with no `na.rm` argument, relying on the default `na.rm = FALSE`.

---

## 3. Python Conversion Strategy

The chosen Python library is **NumPy**, specifically `numpy.minimum`.

**Why NumPy:**

- R's `pmin` is inherently a vectorized operation; NumPy is the canonical Python library for vectorized array arithmetic.
- `numpy.minimum(x1, x2)` computes the element-wise minimum of two arrays and supports broadcasting, mirroring R's recycling of scalar arguments.
- For the integer-clamping pattern in usage 1, `numpy.minimum` with a scalar cap is idiomatic and produces results identical to R's `pmin` when no `NA`/`NaN` values are present.
- For the numeric boundary-merging pattern in usage 2, `numpy.minimum` on equal-length 1-D arrays is a direct drop-in.

**NA handling note.** `numpy.minimum` propagates `NaN` (equivalent to R's `NA_real_`), matching R's default `na.rm = FALSE` behaviour. If `na.rm = TRUE` semantics are ever needed, use `numpy.fmin` instead, which ignores `NaN` values.

**More-than-two-argument case.** R's `pmin` accepts an arbitrary number of vectors; NumPy's binary ufunc can be chained: `np.minimum(np.minimum(a, b), c)`, or use `np.minimum.reduce([a, b, c])` for the general case.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Clamping an Index Sequence to a Maximum Value

**Locations:** `labels.rpart.R` — function `labels.rpart`

**Original R Context**

```r
# z      : character vector of factor level names, length n (n may exceed 52)
# Returns: integer vector, length n, each element in [1, 52]
pmin(seq_along(z), 52L)
```

The broader expression in which this appears:

```r
xlevels <- lapply(xlevels, function(z)
    c(letters, LETTERS)[pmin(seq_along(z), 52L)])
```

For each factor's level vector `z`, this builds the 1-to-52 index sequence and clamps it so that any level index beyond 52 maps to the last letter (`"Z"`).

**Python Equivalent**

```python
import numpy as np

# alphabet is the Python equivalent of c(letters, LETTERS)
alphabet = list("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")  # 52 elements

def abbreviate_levels(z):
    """
    z : list or array-like of factor level strings, length n
    Returns a list of single-character abbreviations, length n.
    """
    # seq_along(z) in R is 1-based; Python uses 0-based indexing.
    indices_r = np.arange(1, len(z) + 1, dtype=np.int64)   # [1, 2, ..., n]
    clamped   = np.minimum(indices_r, 52)                    # pmin(..., 52L)
    # Convert back to 0-based Python indices for subscripting alphabet
    return [alphabet[i - 1] for i in clamped]

# Usage mirroring the lapply call:
# xlevels is a dict mapping factor names to lists of level strings
xlevels_abbrev = {name: abbreviate_levels(levels)
                  for name, levels in xlevels.items()}
```

**Explanation**

| R | Python |
|---|--------|
| `seq_along(z)` | `np.arange(1, len(z) + 1)` — produces 1-based integer indices |
| `pmin(..., 52L)` | `np.minimum(indices_r, 52)` — element-wise cap at 52 |
| `c(letters, LETTERS)[...]` | `[alphabet[i - 1] for i in clamped]` — 0-based subscript adjustment |

Because the scalar `52` is broadcast across the entire array by `numpy.minimum`, no explicit loop is required.

---

### 4.2 Element-wise Minimum of Two Numeric Vectors (Boundary Merging)

**Locations:** `rpartco.R` — function `compress` (nested inside `rpartco`)

**Original R Context**

```r
# templ        : numeric vector of left x-boundary coordinates, indexed by depth
# left$left    : numeric vector of left x-boundary coordinates from the left subtree,
#                same length as the slice being updated
# mind         : integer scalar — the number of shared depth levels between subtrees
# Returns      : numeric vector of length mind; each element is the smaller of the
#                two corresponding boundary values
templ[1L:mind] <- pmin(templ[1L:mind], left$left)
```

This keeps `templ` updated to the leftmost (minimum x) boundary at each shared depth level, combining information from the right subtree's `templ` and the left subtree's boundary.

**Python Equivalent**

```python
import numpy as np

# templ     : np.ndarray, dtype=float64, shape (max_depth,)
# left_left : np.ndarray, dtype=float64, shape (left_depth,)
# mind      : int — number of shared depth levels

# Slice notation: R's 1L:mind (1-based, inclusive) maps to Python [0:mind] (0-based, exclusive end)
templ[:mind] = np.minimum(templ[:mind], left_left[:mind])
```

**Explanation**

| R | Python |
|---|--------|
| `templ[1L:mind]` | `templ[:mind]` — R's 1-based inclusive slice `[1, mind]` equals Python's 0-based `[0:mind]` |
| `left$left` | `left_left` — the left-boundary array returned from the recursive call |
| `pmin(a, b)` | `np.minimum(a, b)` — element-wise minimum of two equal-length float arrays |
| In-place assignment `templ[...] <- result` | `templ[:mind] = result` — NumPy supports in-place slice assignment identically |

The critical indexing difference is the shift from R's 1-based to Python's 0-based array indexing. The semantic operation — retaining the smaller value at each depth position — is a direct mapping between `pmin` and `numpy.minimum`.
