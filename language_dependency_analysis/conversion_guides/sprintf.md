### 1. Overview of `sprintf` in R

`sprintf` is R's interface to the C standard library function of the same name. Its signature is:

```r
sprintf(fmt, ...)
```

`fmt` is a character string (or character vector) containing literal text interspersed with C-style conversion specifications that begin with `%` and end with a conversion letter. The remaining arguments (`...`) supply the values to be formatted.

Key format specifiers relevant to this codebase:

| Specifier | Meaning |
|---|---|
| `%f` | Fixed-point decimal (default 6 decimal places) |
| `%e` / `%E` | Scientific notation |
| `%g` / `%G` | Automatic: uses fixed-point unless the exponent is < -4 or >= precision, in which case scientific notation is used. Precision counts significant digits, not decimal places. |
| `%s` | Character string |
| `%%` | Literal `%` character |

Optional modifiers between `%` and the conversion letter control field width (`m`), precision (`.n`), left-alignment (`-`), sign (`+`), and zero-padding (`0`).

**Vectorization:** `sprintf` is fully vectorized. When `x` (or `fmt`) is a vector, the function recycles arguments to the length of the longest input and returns a character vector of the same length. Because matrices in R are internally vectors, a matrix `x` is formatted element-wise and a plain character vector is returned (the caller is responsible for reshaping back to a matrix if needed).

**Return type:** Always a `character` vector (or character matrix when the caller reshapes explicitly, as is done in `formatg`).

---

### 2. Contextual Usage Analysis

Source file: `/groups/jli9/Yufei/python-rpart/rpart/R/formatg.R`

The complete function is:

```r
formatg <- function(x, digits = getOption("digits"),
                    format = paste0("%.", digits, "g"))
{
    if (!is.numeric(x)) stop("'x' must be a numeric vector")

    temp <- sprintf(format, x)
    if (is.matrix(x)) matrix(temp, nrow = nrow(x)) else temp
}
```

Observations:

- `x` is always a numeric vector or numeric matrix (enforced by the guard on line 6).
- `format` defaults to `"%.Ng"` where `N` is the current `digits` option (typically 7). This uses the `%g` specifier with a caller-supplied precision, meaning significant-digit control rather than decimal-place control.
- `sprintf(format, x)` is called with a single scalar format string and a numeric vector (or matrix), so R's vectorization applies: the result `temp` is a `character` vector with the same number of elements as `x`.
- When `x` is a matrix, the result vector `temp` is immediately reshaped back into a matrix of the same row count using `matrix(temp, nrow = nrow(x))`.
- The `call_body` in the CSV, `sprintf(format, x)`, exactly matches this pattern: one format string applied uniformly across all elements of a numeric vector/matrix.

The usage is therefore a straightforward vectorized numeric-to-string conversion using the `%g` specifier, with a dynamically constructed format string.

---

### 3. Python Conversion Strategy

**Chosen library: NumPy (`numpy`)**

Rationale:

- `x` is guaranteed to be a numeric vector or matrix, which maps directly to a `numpy.ndarray`.
- NumPy's `numpy.char` module and, more idiomatically, Python's vectorized string formatting via `numpy.vectorize` or a list comprehension over a flat array provide a direct equivalent to R's vectorized `sprintf`.
- The most idiomatic NumPy approach for `%g`-style formatting is to use Python's built-in `%` string operator (or `format()`) applied element-wise via `numpy.vectorize`, or to use the `%` operator with a format string on a scalar inside a vectorized call.
- For the matrix-reshape step, `numpy.ndarray.reshape` with the same row count is the direct equivalent of R's `matrix(temp, nrow = nrow(x))`.
- `scipy` and `pandas` are not needed here; NumPy alone covers both the vectorized numeric input and the matrix-shape restoration.

Python's built-in `%` string operator supports the same C-style format specifiers as R's `sprintf`, including `%g` with precision modifiers (e.g., `"%.7g"`). This makes translation nearly one-to-one at the format string level.

---

### 4. Step-by-Step Conversion Examples

#### Example 1: Vectorized `%g` formatting of a numeric vector or matrix

**Locations:**
- File: `formatg.R`
- Function: `formatg`
- Line: 8

**Original R Context:**

- `format` — `character` scalar, e.g., `"%.7g"` (constructed as `paste0("%.", digits, "g")`)
- `x` — `numeric` vector or `numeric` matrix
- Return value of `sprintf(format, x)` — `character` vector of the same length as `x`
- The caller then conditionally reshapes the result back into a matrix with `matrix(temp, nrow = nrow(x))`

Generalized R snippet:

```r
# digits comes from getOption("digits"), typically 7
digits <- getOption("digits")          # integer scalar, e.g. 7
format <- paste0("%.", digits, "g")    # character scalar, e.g. "%.7g"

# x is a numeric vector or matrix
x <- c(0.000123456789, 1234567.89, -0.1, 1e-5)

temp <- sprintf(format, x)
# temp is a character vector:
# [1] "0.0001234568" "1234568"      "-0.1"         "1e-05"

# Matrix case:
x_mat <- matrix(c(1.23456789, 0.000012, 9876543.21, -0.00001), nrow = 2)
temp_mat <- sprintf(format, x_mat)          # character vector, length 4
result    <- matrix(temp_mat, nrow = nrow(x_mat))  # 2x2 character matrix
```

**Python Equivalent:**

```python
import numpy as np

def formatg(x, digits=7):
    """
    Format numeric array using C's '%g' format, equivalent to R's formatg().

    Parameters
    ----------
    x : array-like of float
        Numeric vector or 2-D array (matrix). Must be numeric.
    digits : int, optional
        Number of significant digits. Defaults to 7 (R's default for getOption("digits")).

    Returns
    -------
    numpy.ndarray of str
        Character array of the same shape as x.
    """
    x = np.asarray(x, dtype=float)          # enforce numeric; raises ValueError otherwise
    fmt = f"%.{digits}g"                    # e.g. "%.7g" — mirrors paste0("%.", digits, "g")

    # Vectorized sprintf: apply Python's % string operator element-wise
    vectorized_fmt = np.vectorize(lambda val: fmt % val)
    temp = vectorized_fmt(x)                # ndarray of str, same shape as x

    # Shape is already preserved by np.vectorize, so no reshape step is needed.
    # (np.vectorize preserves the input array shape, unlike R's sprintf which
    #  always returns a flat vector that must be re-shaped manually.)
    return temp


# --- Vector example ---
x_vec = np.array([0.000123456789, 1234567.89, -0.1, 1e-5])
print(formatg(x_vec))
# ['0.0001234568' '1234568' '-0.1' '1e-05']

# --- Matrix (2-D array) example ---
x_mat = np.array([[1.23456789, 9876543.21],
                  [0.000012,   -0.00001]])
print(formatg(x_mat))
# [['1.234568' '9876543']
#  ['1.2e-05'  '-1e-05']]
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `paste0("%.", digits, "g")` | `f"%.{digits}g"` | Both produce a format string such as `"%.7g"`. |
| `sprintf(format, x)` with vector `x` | `np.vectorize(lambda val: fmt % val)(x)` | `np.vectorize` applies the scalar `%` operation to every element while broadcasting over the full array shape. |
| `matrix(temp, nrow = nrow(x))` | (not needed) | In R, `sprintf` always flattens its output to a vector, requiring an explicit `matrix()` reshape. `np.vectorize` preserves the input shape automatically, so no reshape step is required. |
| `is.numeric(x)` guard | `np.asarray(x, dtype=float)` | Passing a non-numeric value raises a `ValueError` during conversion, achieving the same protective effect as R's `stop()` call. |
| `%g` significant-digit behaviour | `%g` in Python's `%` operator | Both delegate to the C standard library's `printf` `%g` implementation, so the output strings are identical for normal finite values. Behaviour for `inf`, `-inf`, and `nan` may differ slightly in edge cases (Python outputs `'inf'`, `'-inf'`, `'nan'`; R outputs `"Inf"`, `"-Inf"`, `"NaN"`). |

One additional nuance: if only a single scalar float needs formatting (not an array), the overhead of `np.vectorize` is unnecessary. In that case a plain Python f-string or `%` format is sufficient:

```python
val = 0.000123456789
digits = 7
result = f"%.{digits}g" % val   # '0.0001234568'
```

Reserve `np.vectorize` for the general case where `x` may be a vector or matrix, which is the only context that appears in `formatg`.
