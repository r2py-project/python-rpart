# Conversion Guide: `signif` (R to Python)

---

### 1. Overview of `signif` in R

`signif(x, digits)` rounds the values in `x` to the specified number of **significant digits** (also called significant figures). This is distinct from `round()`, which rounds to a fixed number of decimal places.

- **`x`**: a numeric scalar or vector (or complex vector). The function is inherently vectorized: when `x` is a vector, every element is rounded individually and the result is a vector of the same length and type.
- **`digits`**: a positive integer in the range 1–22 indicating how many significant figures to retain. The default is 6. Values outside the supported range are coerced to the nearest boundary.

**Examples in R:**

```r
signif(123.456, 2)   # → 120
signif(0.001234, 2)  # → 0.0012
signif(c(1.5678, 99.99), 3)  # → c(1.57, 100)
```

The key property is that the number of significant figures is measured from the first non-zero digit, regardless of the magnitude of the number.

---

### 2. Contextual Usage Analysis

All seven call sites in the CSV apply `signif` to **numeric vectors** (never scalars in isolation) with a user-supplied `digits` argument that defaults to `getOption("digits")` — R's global display precision, typically 7.

The usages fall into three functional patterns:

| Pattern | Locations | What is being rounded |
|---|---|---|
| Rounding a numeric vector for formatted display | `print.rpart.R` lines 22, 27 | `frame$yval` (node predicted values) and `frame$dev` (node deviances) — both 1-D numeric vectors of length equal to the number of nodes in the tree |
| Rounding a scalar extracted from a matrix column for inline string construction | `summary.rpart.R` lines 48, 50, 74, 92 | `x$splits[i, 4L]` (split point threshold), `ff$complexity[i]` (complexity parameter), `x$splits[j, 3L]` (improvement/agreement score) — each extracted as a single numeric value per loop iteration, but the loop processes a vector column element-by-element |
| Rounding a vector of geometric-mean CP values for axis labels | `plotcp.R` line 25 | `cp` — a numeric vector of CP values computed as geometric means, rounded to 2 significant figures before being converted to character strings for plot axis labels |

In every case the result of `signif` is either:
- passed directly to `format()` to produce a display string, or
- passed to `as.character()` for axis labelling.

No arithmetic is performed on the rounded values themselves; the rounding is purely for human-readable output.

---

### 3. Python Conversion Strategy

The primary Python equivalent is **`numpy.round_` / `numpy.format_float_scientific`** — but for significant-digit rounding the idiomatic choice is to implement it with **`numpy`** arithmetic or to use Python's built-in `round()` combined with a simple helper, because NumPy does not ship a direct `signif` function.

The recommended approach is a one-line helper built on `numpy`:

```python
import numpy as np

def signif(x, digits):
    x = np.asarray(x, dtype=float)
    return np.where(x == 0, 0, np.round(x, digits - 1 - np.floor(np.log10(np.abs(x))).astype(int)))
```

This is chosen over `math`-based alternatives because:

1. **Vectorization**: all call sites operate on arrays or matrix columns; `numpy` processes the entire array in one call, exactly matching R's vectorized behaviour.
2. **Type fidelity**: the result is a `numpy` array of `float64`, which integrates cleanly with `pandas` DataFrames (analogues of R's `frame`) and `numpy` matrices (analogues of `x$splits`).
3. **No extra dependency**: `numpy` is already required throughout the rpart Python port; no new import is introduced.

For the specific display context (converting the result to a string for printing), Python's `f"{value:.{digits}g}"` format specifier is a simpler, scalar-oriented alternative that exactly mirrors significant-figure behaviour and is appropriate when only a single formatted string is needed per value.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Axis Labels for CP Plot

**Locations:** `plotcp.R`, function `plotcp`, line 25.

**Original R Context:**

`cp` is a numeric vector of geometric-mean complexity-parameter values, one per row of the CP table. `signif(cp, 2L)` rounds every element to 2 significant figures. The result is then converted to character strings for use as tick labels on the x-axis of the cross-validation plot.

```r
# cp is a numeric vector, e.g. c(1.0, 0.023456, 0.00789)
labels <- as.character(signif(cp, 2L))
axis(1L, at = ns, labels = labels, ...)
```

**Python Equivalent:**

```python
import numpy as np

def signif(x, digits):
    x = np.asarray(x, dtype=float)
    return np.where(x == 0, 0,
                    np.round(x, digits - 1 - np.floor(np.log10(np.abs(x))).astype(int)))

# cp is a numpy array, e.g. np.array([1.0, 0.023456, 0.00789])
labels = [str(v) for v in signif(cp, 2)]
# Use labels for axis tick labelling in matplotlib:
# ax.set_xticklabels(labels)
```

**Explanation:**

- `2L` in R is the integer literal `2`; in Python pass plain `2`.
- `as.character()` on a numeric vector becomes a list comprehension over `str()`.
- The `signif` helper uses `np.log10(np.abs(x))` to determine the order of magnitude of each element, then calls `np.round` with a per-element number of decimal places. `np.where` guards against `x == 0` (log10 of zero is undefined).

---

#### 4.2 Formatting Node Predicted Values and Deviances

**Locations:** `print.rpart.R`, function `print.rpart`, lines 22 and 27.

**Original R Context:**

`frame$yval` is a numeric vector with one entry per tree node (predicted response values). `frame$dev` is likewise a numeric vector of per-node deviance values. Both are rounded to `digits` significant figures and then passed to `format()` to align columns in the printed tree output.

```r
# frame$yval and frame$dev are numeric vectors, length = number of tree nodes
# digits defaults to getOption("digits"), typically 7
yval_fmt  <- format(signif(frame$yval, digits))
dev_fmt   <- format(signif(frame$dev,  digits))
```

**Python Equivalent:**

```python
import numpy as np

def signif(x, digits):
    x = np.asarray(x, dtype=float)
    return np.where(x == 0, 0,
                    np.round(x, digits - 1 - np.floor(np.log10(np.abs(x))).astype(int)))

# frame["yval"] and frame["dev"] are pandas Series or numpy arrays
# digits is an int, typically 7
yval_rounded = signif(frame["yval"].to_numpy(), digits)
dev_rounded  = signif(frame["dev"].to_numpy(),  digits)

# Format for display (analogous to R's format())
yval_fmt = [f"{v:.{digits}g}" for v in yval_rounded]
dev_fmt  = [f"{v:.{digits}g}" for v in dev_rounded]
```

**Explanation:**

- `frame$yval` in R maps to `frame["yval"]` in a `pandas` DataFrame. `.to_numpy()` produces the underlying array for `signif`.
- R's `format()` applied to a rounded vector produces right-aligned strings padded to equal width. The `f"{v:.{digits}g}"` format specifier uses Python's `g` format, which selects significant figures (matching `signif`) and suppresses trailing zeros — the closest idiomatic Python equivalent. For full column alignment use `f"{v:{width}.{digits}g}"` once the required column width is known.
- `digits` comes from `getOption("digits")` in R; in the Python port this should be a configurable parameter with default value `7`.

---

#### 4.3 Formatting Split Thresholds Inline in String Construction

**Locations:** `summary.rpart.R`, function `summary.rpart`, lines 48 and 50.

**Original R Context:**

`x$splits` is a numeric matrix where column 4 (1-indexed) holds the split point or category index for each split. `temp[i]` encodes the direction flag (−1 for "less than", 1 for "greater than or equal to", ≥ 2 for categorical). For continuous splits, `x$splits[i, 4L]` is extracted as a scalar numeric and rounded to `digits` significant figures before being embedded in a character string.

```r
# x$splits is a numeric matrix; x$splits[i, 4L] is a scalar double
# digits is an int
for (i in seq_along(cuts)) {
    cuts[i] <- if (temp[i] == -1L)
        paste("<", format(signif(x$splits[i, 4L], digits)))
    else if (temp[i] == 1L)
        paste("<", format(signif(x$splits[i, 4L], digits)))
    else
        paste("splits as ", ...)
}
```

**Python Equivalent:**

```python
# x_splits is a 2-D numpy array (rows = splits, columns = split attributes)
# Column index 3 corresponds to R's column 4 (0-based indexing)
# digits is an int

cuts = []
for i in range(len(temp)):
    if temp[i] == -1 or temp[i] == 1:
        val = x_splits[i, 3]          # R's column 4 → Python index 3
        val_fmt = f"{val:.{digits}g}" # significant-figure formatting
        cuts.append(f"< {val_fmt}")
    else:
        # categorical split — handled separately
        cuts.append(...)
```

**Explanation:**

- R uses 1-based matrix indexing; Python uses 0-based. R's `x$splits[i, 4L]` becomes `x_splits[i, 3]` in Python.
- Because only a single scalar is extracted per loop iteration, `f"{val:.{digits}g}"` (Python's built-in significant-figure format specifier) is sufficient and more readable than calling the `signif` helper followed by `str()`.
- `paste("<", ...)` in R concatenates with a space separator by default; `f"< {val_fmt}"` replicates this exactly.

---

#### 4.4 Formatting the Complexity Parameter Inline

**Locations:** `summary.rpart.R`, function `summary.rpart`, line 74.

**Original R Context:**

`ff$complexity[i]` is a scalar double (the complexity parameter for node `i`). It is rounded to `digits` significant figures and embedded in a `cat()` output line.

```r
# ff$complexity is a numeric vector; ff$complexity[i] is a scalar double
cat("    complexity param=",
    format(signif(ff$complexity[i], digits)), "\n", sep = "")
```

**Python Equivalent:**

```python
# ff["complexity"] is a pandas Series or numpy array
# ff["complexity"][i] (or .iloc[i]) is a scalar float
val = ff_complexity[i]
val_fmt = f"{val:.{digits}g}"
print(f"    complexity param={val_fmt}")
```

**Explanation:**

- `cat(..., sep = "")` with `sep = ""` suppresses R's default space separator; Python's f-string produces the same output without extra spaces.
- `format(signif(...))` in R applies `signif` first (rounding to significant figures) then `format` (converting to a display string). `f"{val:.{digits}g}"` combines both steps in a single Python expression.

---

#### 4.5 Formatting Split Improvement and Agreement Scores

**Locations:** `summary.rpart.R`, function `summary.rpart`, line 92.

**Original R Context:**

`x$splits[j, 3L]` is a numeric vector (column 3, 1-indexed) extracted for a range of row indices `j` corresponding to primary splits for node `i`. The rounded values are embedded in a `paste()` call that builds the "Primary splits:" display block.

```r
# j is an integer vector (range of row indices); x$splits[j, 3L] is a numeric vector
cat(paste("      ", format(sname[j], justify = "left"), " ", temp,
          " improve=", format(signif(x$splits[j, 3L], digits)),
          ", (", nn - x$splits[j, 1L], " missing)", sep = ""),
    sep = "\n")
```

**Python Equivalent:**

```python
import numpy as np

def signif(x, digits):
    x = np.asarray(x, dtype=float)
    return np.where(x == 0, 0,
                    np.round(x, digits - 1 - np.floor(np.log10(np.abs(x))).astype(int)))

# j is a slice or list of integer indices
# x_splits is a 2-D numpy array; column 2 (0-based) = R's column 3
improve_vals = signif(x_splits[j, 2], digits)   # vector result
missing_vals = nn - x_splits[j, 0]               # R's column 1 → index 0

lines = []
for k in range(len(j)):
    improve_fmt = f"{improve_vals[k]:.{digits}g}"
    missing_fmt = int(missing_vals[k])
    lines.append(
        f"      {sname[j[k]]:<{name_width}} {cuts[j[k]]} improve={improve_fmt}, ({missing_fmt} missing)"
    )
print("\n".join(lines))
```

**Explanation:**

- `x$splits[j, 3L]` where `j` is a vector extracts an entire sub-vector at once; `x_splits[j, 2]` (0-based column index) does the same in NumPy using fancy indexing.
- The vectorized `signif` helper is appropriate here because `j` may contain multiple indices.
- `format(sname[j], justify = "left")` pads names to equal width; Python's `f"{name:<{name_width}}"` left-justifies to a computed column width.
- R's column 1 of `x$splits` (missing count) maps to index 0; column 3 (improvement) maps to index 2.
