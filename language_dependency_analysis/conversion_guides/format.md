# Conversion Guide: `format` (R to Python)

---

## 1. Overview of `format` in R

R's built-in `format()` function converts R objects (numbers, strings, vectors, matrices) into uniformly-formatted character strings. Its most important properties are:

- **Width-padding**: by default it pads all elements in a vector to the same total width so that output columns align.
- **Significant digits / decimal places**: controlled via `digits` (significant figures) and `nsmall` (minimum digits to the right of the decimal point).
- **Justification**: the `justify` argument (`"left"`, `"right"`, `"centre"`, `"none"`) controls how strings are padded within the field width.
- **Vectorised**: when given a vector or matrix it formats every element and returns a character vector/matrix of equal-length strings.
- **Scalar use**: when given a single number it returns a single formatted string; this is used frequently for constructing `cat()` output lines.

Key signature (simplified):

```r
format(x, trim = FALSE, digits = NULL, nsmall = 0L,
       justify = "left", width = NULL, ...)
```

---

## 2. Contextual Usage Analysis

Across the CSV rows the dependency appears in four distinct functional patterns:

| Pattern | Files / Functions | Description |
|---|---|---|
| **A – format a scalar or vector of node ids / CP values** | `print.rpart.R::print.rpart`, `xpred.rpart.R::xpred.rpart` | Converts integer or numeric vectors to fixed-width strings for labels/dimnames. |
| **B – format a rounded/significant numeric scalar for `cat()` output** | `print.rpart.R::print.rpart`, `printcp.R::printcp`, `summary.rpart.R::summary.rpart`, `xpred.rpart.R` (dimnames) | `format(signif(x, digits))` or `format(x, digits=digits)` produces a single neatly-trimmed string inserted into printed text. |
| **C – format a rounded numeric column for a `data.frame` result** | `roc.rpart.R::roc.rpart` | `format(round(x, ndigits))` applied to numeric matrix columns; the result is a character vector stored as a data-frame column so all entries share the same width. |
| **D – format strings/character vectors with left/right justification** | `rpart.class.R::rpart.class`, `summary.rpart.R::summary.rpart` | `format(group, justify = "left")` pads character labels so they line up in columnar console output. |
| **E – format a numeric matrix to a character matrix with `nsmall`** | `rpart.class.R::rpart.class` | `format(yval[, ...], digits = digits, nsmall = nsmall)` converts a numeric sub-matrix to a character matrix, keeping at least `nsmall` decimal places. |

**Data types involved:**

- Inputs are either plain numeric scalars, numeric vectors, numeric matrices, integer vectors, or character vectors/strings.
- Return values are always character scalars, character vectors, or character matrices of equal-length strings.

**Recurring patterns:**

- `format(signif(x, digits))` — significance rounding then uniform width formatting.
- `format(round(x, n))` — decimal rounding then uniform width formatting.
- `format(x, digits = digits)` — format with significant-digit control.
- `format(x, justify = "left")` — left-pad a character vector to a common width.
- `format(x, digits = digits, nsmall = nsmall)` — format a matrix keeping minimum decimals.

---

## 3. Python Conversion Strategy

The primary Python equivalent is **`numpy`** together with **standard Python string formatting**. The reasoning:

- R's `format()` on numeric data is equivalent to Python's `numpy` operations combined with Python's built-in `str.format()` / f-strings / `format()` built-in.
- When the input is a **vector or matrix**, `numpy` handles the element-wise rounding/significant-figure operations; string formatting is then applied with list comprehensions or `numpy.vectorize`.
- When the input is a **scalar**, Python's built-in `format()` or f-strings are the simplest equivalent.
- For **column-alignment** (left/right justify to a common field width), Python's `str.ljust()` / `str.rjust()` or `format(x, '<N')` are the direct analogues.
- The `pandas` library may be used in contexts where the formatted strings end up as DataFrame columns, but the formatting itself relies on the same Python string tools.

No single third-party function replicates all the behaviour of R's `format()` in one call; the guide therefore provides composable snippets that together cover every pattern observed in the CSV.

---

## 4. Step-by-Step Conversion Examples

---

### Pattern A – Formatting a numeric / integer vector as fixed-width strings (node ids, CP values)

**Locations:**
- `print.rpart.R` :: `print.rpart` (lines 15–16)
- `xpred.rpart.R` :: `xpred.rpart` (lines 138, 142)

**Original R Context:**

Inputs are a numeric/integer vector (`node` holding tree node numbers, or `cp` holding complexity-parameter values). `format()` is called without extra arguments, so R uses its default width-equalisation behaviour — every element is converted to a string of the same total character width.

```r
# node is a numeric vector of integer-valued node IDs
# cp is a numeric vector of complexity parameter values
format(node)   # -> character vector, all same width
format(cp)     # -> character vector, all same width, used as dimnames
```

**Python Equivalent:**

```python
import numpy as np

def format_vector(x):
    """
    Mimic R's format() on a plain numeric/integer vector.
    Returns a list of strings all padded to the same width,
    matching R's default left-padding with spaces.
    """
    strings = [str(v) for v in np.asarray(x)]
    max_width = max(len(s) for s in strings)
    return [s.rjust(max_width) for s in strings]

# Example usage (node IDs)
node = np.array([1, 2, 3, 4, 7, 8, 15])
formatted_node = format_vector(node)
# -> ['  1', '  2', '  3', '  4', '  7', '  8', ' 15']

# Example usage (CP values used as dimnames in xpred.rpart)
cp = np.array([0.1, 0.05, 0.02, 0.01])
formatted_cp = format_vector(cp)
```

**Explanation:**

- R's default `format()` right-justifies within the widest element's width.
- `str(v)` converts each numpy element to a string; `rjust(max_width)` applies the same right-padding.
- For integer-valued floats (node IDs stored as `numeric` in R), converting via `int()` first avoids trailing `.0`: `str(int(v))`.

---

### Pattern B – Format a significant-figure-rounded scalar for printed output

**Locations:**
- `print.rpart.R` :: `print.rpart` (lines 22, 27)
- `printcp.R` :: `printcp` (lines 27, 29)
- `summary.rpart.R` :: `summary.rpart` (lines 48, 50, 74, 92, 106, 107)

**Original R Context:**

A single numeric scalar (or a length-1 numeric vector) is first rounded to `digits` significant figures with `signif()`, then converted to a string with `format()`. The result is embedded directly into `cat()` or `paste()` output.

```r
# x is a scalar numeric; digits is an integer (e.g. 4)
format(signif(x$splits[i, 4L], digits))   # -> single character string
format(signif(frame$yval, digits))         # -> character vector (one per node)
format(signif(frame$dev, digits))          # -> character vector (one per node)
format(frame$dev[1L], digits = digits)     # -> single character string
format(frame$dev[1L]/frame$n[1L], digits = digits)  # -> single character string
format(signif(ff$complexity[i], digits))   # -> single character string
format(round(agree, 3L))                   # -> character vector
format(round(adj, 3L))                     # -> character vector
```

**Python Equivalent:**

```python
import numpy as np

def format_signif(x, digits):
    """
    Equivalent of format(signif(x, digits)) in R.
    Works element-wise on scalars, lists, or numpy arrays.
    Returns a string (scalar input) or list of strings (array input).
    """
    arr = np.asarray(x, dtype=float)
    scalar_input = arr.ndim == 0
    arr = np.atleast_1d(arr)

    result = []
    for v in arr:
        if np.isnan(v) or np.isinf(v):
            result.append(str(v))
        else:
            # sigfig rounding: shift to unit scale, round, shift back
            from math import floor, log10
            if v == 0:
                result.append('0')
            else:
                magnitude = floor(log10(abs(v)))
                factor = 10 ** (digits - 1 - magnitude)
                rounded = round(v * factor) / factor
                # Use Python's g-format to drop trailing zeros like R does
                result.append(f'{rounded:.{digits}g}')

    return result[0] if scalar_input else result

def format_digits(x, digits):
    """
    Equivalent of format(x, digits = digits) in R.
    Formats a scalar or array to `digits` significant figures.
    """
    return format_signif(x, digits)

# Example: format(signif(frame$dev, 4))
dev = np.array([10.5678, 3.14159, 0.00123])
formatted_dev = format_signif(dev, digits=4)
# -> ['10.57', '3.142', '0.001230']

# Example: format(frame$dev[1], digits=digits)
root_dev = 42.789
formatted_root = format_digits(root_dev, digits=4)
# -> '42.79'

# Example: format(round(agree, 3))
agree = np.array([0.8765, 0.9123])
formatted_agree = [f'{v:.3f}' for v in np.round(agree, 3)]
# -> ['0.877', '0.912']
```

**Explanation:**

- R's `signif(x, digits)` rounds to `digits` significant figures. Python's `round()` and the `:.{n}g` format specifier together replicate this.
- The `:.Ng` format already strips trailing zeros, matching R's default behaviour.
- `format(round(x, n))` in R is equivalent to `f'{round(x, n)}'` in Python for scalars, or a list comprehension for vectors.

---

### Pattern C – Format rounded numeric columns for a `data.frame` result

**Locations:**
- `roc.rpart.R` :: `roc.rpart` (lines 71–75)

**Original R Context:**

Numeric matrix columns (each is a `(cutoff.n x 1)` matrix produced by the ROC loop) are rounded to a fixed number of decimal places and then converted to character vectors. The resulting character vectors are stored as columns of the returned `data.frame`, so every entry in each column has the same string width.

```r
# cutoffs, sensitivity, specificity, pospred, negpred are numeric matrices (n x 1)
data.frame(
    cutoffs     = format(round(cutoffs,     3L)),
    sensitivity = format(round(sensitivity, 2L)),
    specificity = format(round(specificity, 2L)),
    pospred     = format(round(pospred,     2L)),
    negpred     = format(round(negpred,     2L))
)
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

def format_rounded_column(arr, decimals):
    """
    Equivalent of format(round(x, decimals)) applied to a numeric vector/matrix.
    Returns a list of strings, all padded to the same width.
    """
    arr = np.asarray(arr, dtype=float).ravel()
    rounded = np.round(arr, decimals)
    # Format each value to exactly `decimals` decimal places
    strings = [f'{v:.{decimals}f}' if not np.isnan(v) else 'NA'
               for v in rounded]
    # Pad to uniform width (R's format() does this)
    max_width = max(len(s) for s in strings)
    return [s.rjust(max_width) for s in strings]

# Example: building the ROC data frame
cutoffs     = np.array([np.nan, 0.0, 0.333, 0.667, 1.0, np.nan])
sensitivity = np.array([0.0, 0.25, 0.5, 0.75, 1.0, 1.0])
specificity = np.array([1.0, 0.9, 0.7, 0.5, 0.1, 0.0])
pospred     = np.array([np.nan, 0.5, 0.6, 0.7, 0.5, np.nan])
negpred     = np.array([1.0, 0.9, 0.85, 0.8, np.nan, np.nan])

roc_df = pd.DataFrame({
    'cutoffs':     format_rounded_column(cutoffs,     3),
    'sensitivity': format_rounded_column(sensitivity, 2),
    'specificity': format_rounded_column(specificity, 2),
    'pospred':     format_rounded_column(pospred,     2),
    'negpred':     format_rounded_column(negpred,     2),
})
```

**Explanation:**

- `np.round(arr, decimals)` is the direct equivalent of R's `round(x, ndigits)`.
- `f'{v:.{decimals}f}'` produces a fixed-decimal-place string, matching R's `format()` behaviour when the input has already been rounded.
- `.rjust(max_width)` replicates R's column-alignment padding.
- `NA` is used as the string representation for `NaN` inputs, matching R's output.

---

### Pattern D – Format character vectors with left justification

**Locations:**
- `rpart.class.R` :: `rpart.class` (lines 91, 107, 108)
- `summary.rpart.R` :: `summary.rpart` (lines 58, 89, 91, 101, 104)

**Original R Context:**

A character vector `group` (class labels) or `cuts` / `sname` (split description strings) is passed to `format()` with `justify = "left"`. R pads every element with trailing spaces so all elements reach the same total character width. This ensures columnar alignment when the strings are subsequently `paste()`d with numeric values.

```r
# group is a character vector of class label strings
format(group, justify = "left")

# cuts and sname are character vectors of split description strings
format(cuts[temp < 2L], justify = "left")
format(sname[j],        justify = "left")
format(cuts[j],         justify = "left")
```

**Python Equivalent:**

```python
def format_left_justify(strings):
    """
    Equivalent of format(x, justify = "left") in R for character vectors.
    Pads each string with trailing spaces to match the longest element's width.
    """
    strings = list(strings)
    max_width = max(len(s) for s in strings) if strings else 0
    return [s.ljust(max_width) for s in strings]

# Example: class labels
group = ['setosa', 'versicolor', 'virginica']
formatted_group = format_left_justify(group)
# -> ['setosa    ', 'versicolor', 'virginica ']

# Example: split description strings
cuts = ['< 5.45', '< 2.45', 'splits as LRR']
formatted_cuts = format_left_justify(cuts)
# -> ['< 5.45       ', '< 2.45       ', 'splits as LRR']
```

**Explanation:**

- R's `format(x, justify = "left")` is a direct one-to-one mapping to Python's `str.ljust(width)`.
- `max_width` is computed across the whole vector first, then applied uniformly — exactly as R does.
- For `justify = "right"` (R's default for numeric strings) use `str.rjust(max_width)`.

---

### Pattern E – Format a numeric matrix to a character matrix with `nsmall`

**Locations:**
- `rpart.class.R` :: `rpart.class` (line 63)

**Original R Context:**

A numeric sub-matrix `yval[, 1L + nclass + 1L:nclass]` of class probability estimates is converted to a character matrix. The `digits` argument controls significant figures and `nsmall` sets the minimum number of digits after the decimal point, ensuring a consistent minimum precision even for values such as `1.0` that would otherwise be printed as `"1"`.

```r
# yval_sub is a numeric matrix of shape (n_nodes, nclass) with probability values in [0, 1]
format(yval[, 1L + nclass + 1L:nclass], digits = digits, nsmall = nsmall)
# -> character matrix of same shape, each entry uniformly formatted
```

**Python Equivalent:**

```python
import numpy as np

def format_matrix(mat, digits, nsmall):
    """
    Equivalent of format(mat, digits = digits, nsmall = nsmall) in R
    for a 2-D numeric matrix.

    digits : int  - number of significant figures
    nsmall : int  - minimum decimal places (R's nsmall)

    Returns a numpy array of strings with the same shape.
    """
    from math import floor, log10

    mat = np.asarray(mat, dtype=float)
    result = np.empty(mat.shape, dtype=object)

    for idx in np.ndindex(mat.shape):
        v = mat[idx]
        if np.isnan(v):
            result[idx] = 'NA'
            continue
        if v == 0.0:
            # nsmall decimal places minimum
            result[idx] = f'{v:.{nsmall}f}'
            continue
        # Determine number of decimal places needed for `digits` sig figs
        magnitude = floor(log10(abs(v)))
        sig_decimals = max(digits - 1 - magnitude, 0)
        # nsmall overrides to a minimum number of decimals
        decimals = max(sig_decimals, nsmall)
        result[idx] = f'{v:.{decimals}f}'

    # Pad every element to the same width (R's uniform-width behaviour)
    flat = result.ravel()
    max_width = max(len(s) for s in flat)
    padded = np.array([s.rjust(max_width) for s in flat], dtype=object)
    return padded.reshape(mat.shape)

# Example usage
import numpy as np

yval_sub = np.array([[0.7, 0.3],
                     [0.1, 0.9],
                     [1.0, 0.0]])
digits = 4
nsmall = 3   # keep at least 3 decimal places (common rpart default)

formatted = format_matrix(yval_sub, digits=digits, nsmall=nsmall)
# Each probability is shown with at least 3 decimal places,
# all padded to the same column width.
```

**Explanation:**

- R's `nsmall` guarantees a floor on the number of decimal places independently of the significant-figure count. The Python helper computes both the sig-fig-implied decimal count and `nsmall`, then takes the maximum.
- R formats an entire matrix with a single shared field width; the final `rjust(max_width)` loop replicates that.
- The returned `numpy` object array of strings can be sliced by column exactly like R's character matrix.
