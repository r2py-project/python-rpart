# Conversion Guide: `paste0` (R to Python)

---

## 1. Overview of `paste0` in R

`paste0(...)` is R's zero-separator string concatenation function. It is equivalent to `paste(..., sep = "")` — it takes one or more vectors of character (or coercible) values and concatenates them element-wise with no separator between parts. When the input vectors differ in length, R recycles the shorter one to match the length of the longest. The return value is a character vector of the same length as the longest input.

Key characteristics:
- Accepts any number of positional arguments (scalars, character vectors, or objects coercible to character).
- Performs element-wise (vectorized) concatenation across all arguments, recycling shorter inputs.
- Returns a `character` vector. When all inputs are scalar, the result is a length-1 character vector (a single string).
- Has no `sep` argument (separator is always `""`). For non-empty separators use `paste(..., sep=...)`.

---

## 2. Contextual Usage Analysis

The CSV covers 24 call sites across 9 R source files. Two broad structural patterns appear:

**Pattern A — Scalar string construction (single-string result):**
The inputs are all scalars or reduce to a single string at the call site. This occurs when building environment-keyed variable names (e.g., `paste0("device", dev.cur())`), format strings (e.g., `paste0("%.", digits, "g")`), and multi-part summary/text labels where each argument is itself a single formatted string.

**Pattern B — Vectorized element-wise concatenation (vector result):**
At least one argument is a character vector, so the output is also a character vector of the same length. This covers split-label assembly in `labels.rpart` (e.g., prepending `"< "` or `">="` to each element of a `cutpoint` vector), the `print` function in `rpart.class` (building per-node label strings), and the `text`/`summary` closures in `rpart.anova`, `rpart.class`, `rpart.exp`, and `rpart.poisson` (formatting per-node diagnostic strings from matrix columns).

In almost every call the individual string fragments are produced by `formatg()`, `format()`, or `ifelse()`, all of which themselves return character vectors of the same length as their inputs — so the final `paste0` output length matches the number of tree nodes or split entries being processed.

---

## 3. Python Conversion Strategy

Python's built-in `str` operations (`+`, `f-strings`, `str.format`) handle the scalar case natively and idiomatically. For the vectorized (element-wise) case, **NumPy's `np.char.add()`** or **list comprehensions** are the standard equivalents.

- `np.char.add(a, b)` concatenates two string arrays element-wise with no separator, directly mirroring `paste0` with two arguments. For three or more arguments it can be chained.
- For multi-argument calls with several mixed-type fragments, a list comprehension or `np.vectorize` is often cleaner than repeated `np.char.add`.
- Pure scalar calls can use Python f-strings or plain `+` string concatenation.

The guide below lists NumPy as the primary tool for any call where at least one argument is a vector, and f-strings/`+` for purely scalar calls.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Format-string construction (scalar)

**Locations:** `formatg.R` — `formatg` (line 4)

**Original R Context:**

```r
# digits: integer scalar (e.g. 4)
# Returns a single character string, e.g. "%.4g"
format <- paste0("%.", digits, "g")
```

**Python Equivalent:**

```python
fmt = f"%.{digits}g"
# Or equivalently:
fmt = "%." + str(digits) + "g"
```

**Explanation:** All three arguments are scalars. R's `paste0` with scalar inputs is identical to Python f-string interpolation. The f-string `f"%.{digits}g"` is the most readable and idiomatic choice. No NumPy import is required.

---

### 4.2 Prepending a direction prefix to a numeric cutpoint vector

**Locations:** `labels.rpart.R` — `labels.rpart` (lines 48–49)

**Original R Context:**

```r
# temp1, temp2: character vectors (e.g. c("< ", ">=", "< ", ...)), length = k
# cutpoint:     character vector produced by formatg(), same length k
# Result: character vector of length k, e.g. c("< 0.5", ">= 1.2", ...)
lsplit[ncat < 2L] <- paste0(temp1, cutpoint)
rsplit[ncat < 2L] <- paste0(temp2, cutpoint)
```

**Python Equivalent:**

```python
import numpy as np

# temp1, temp2: np.ndarray of dtype str or list of str, length k
# cutpoint:     np.ndarray of dtype str, same length k
lsplit[ncat < 2] = np.char.add(temp1, cutpoint)
rsplit[ncat < 2] = np.char.add(temp2, cutpoint)

# Or with a list comprehension:
lsplit[ncat < 2] = [t + c for t, c in zip(temp1, cutpoint)]
rsplit[ncat < 2] = [t + c for t, c in zip(temp2, cutpoint)]
```

**Explanation:** `paste0(a, b)` over two equal-length character vectors maps exactly to `np.char.add(a, b)`, which concatenates string arrays element-wise. The list comprehension using `zip` is an equally valid and often more readable alternative when the arrays are Python lists.

---

### 4.3 Prepending an `"="` prefix based on a condition, then combining with split labels

**Locations:** `labels.rpart.R` — `labels.rpart` (lines 93–94)

**Original R Context:**

```r
# ncat: integer vector, length = number of splitting variables
# lsplit, rsplit: character vectors of same length
# ifelse(ncat < 2L, "", "=") produces a character vector of "" or "="
lsplit <- paste0(ifelse(ncat < 2L, "", "="), lsplit)
rsplit <- paste0(ifelse(ncat < 2L, "", "="), rsplit)
```

**Python Equivalent:**

```python
import numpy as np

prefix = np.where(ncat < 2, "", "=")   # np.where mirrors R's ifelse for arrays
lsplit = np.char.add(prefix, lsplit)
rsplit = np.char.add(prefix, rsplit)

# Or with a list comprehension:
lsplit = [("" if nc < 2 else "=") + s for nc, s in zip(ncat, lsplit)]
rsplit = [("" if nc < 2 else "=") + s for nc, s in zip(ncat, rsplit)]
```

**Explanation:** `ifelse` in R is the vectorized conditional, equivalent to `np.where`. The result is fed directly into `paste0`, which chains naturally with `np.char.add`. The list comprehension form is cleaner when `ncat` and the split arrays are Python lists.

---

### 4.4 Combining a variable name vector with a split label vector

**Locations:** `labels.rpart.R` — `labels.rpart` (lines 105–106)

**Original R Context:**

```r
# varname: character vector of variable names, indexed by parent[odd] / parent[!odd]
# rsplit, lsplit: character vectors of split labels
# Result: character vector, one label per node
labels[odd]  <- paste0(varname[parent[odd]],  rsplit[parent[odd]])
labels[!odd] <- paste0(varname[parent[!odd]], lsplit[parent[!odd]])
```

**Python Equivalent:**

```python
import numpy as np

labels[odd]  = np.char.add(varname[parent[odd]],  rsplit[parent[odd]])
labels[~odd] = np.char.add(varname[parent[~odd]], lsplit[parent[~odd]])

# Or with list comprehensions:
labels[odd]  = [v + s for v, s in zip(varname[parent[odd]],  rsplit[parent[odd]])]
labels[~odd] = [v + s for v, s in zip(varname[parent[~odd]], lsplit[parent[~odd]])]
```

**Explanation:** Both sides are subsets of character arrays indexed by boolean or integer index arrays. The pattern is the same as Section 4.2: element-wise concatenation of two equal-length string arrays. Note that R uses `!odd` for boolean negation, while NumPy uses `~odd` (or `np.logical_not(odd)`).

---

### 4.5 Building a device-keyed environment variable name (scalar)

**Locations:**
- `plot.rpart.R` — `plot.rpart` (line 23)
- `rpart.branch.R` — `rpart.branch` (line 8)
- `rpartco.R` — `rpartco` (line 5)
- `snip.rpart.mouse.R` — `snip.rpart.mouse` (line 7)

**Original R Context:**

```r
# dev.cur() returns a single integer (the active graphics device index)
# Result: a single string used as a key in a named environment, e.g. "device2"
pn <- paste0("device", dev.cur())
assign(pn, parms, envir = rpart_env)
```

**Python Equivalent:**

```python
# dev_cur() is the Python equivalent of dev.cur()
pn = "device" + str(dev_cur())
# Or:
pn = f"device{dev_cur()}"

rpart_env[pn] = parms
```

**Explanation:** `dev.cur()` returns a scalar integer. In the Python port, `rpart_env` is a plain `dict`. The key is formed by simple scalar string concatenation via an f-string or `str()` coercion. No NumPy is needed.

---

### 4.6 Multi-fragment node label for `print.rpart` (mixed scalar/vector)

**Locations:** `print.rpart.R` — `print.rpart` (lines 15–16)

**Original R Context:**

```r
# depth: integer vector, one entry per tree node
# indent: character vector of indentation strings, one per depth level
# format(node): character vector of formatted node numbers
# Two branches depending on whether the tree has more than one node:
indent <- paste0(c("", indent[depth]), format(node), ")")
# or for a single-node tree:
indent <- paste0(format(node), ")")
```

**Python Equivalent:**

```python
import numpy as np

# Multi-node case:
prefix = np.concatenate([[""], indent])[depth]   # equivalent to c("", indent)[depth]
indent = np.char.add(np.char.add(prefix, format_node), ")")

# Single-node case (all scalars):
indent = format_node + ")"
```

**Explanation:** R's `c("", indent[depth])` prepends an empty string to the indent array and then indexes by `depth`. In Python this is `np.concatenate([[""], indent])[depth]`. The three-argument `paste0` is then two chained `np.char.add` calls. For the single-node branch, all inputs are scalar strings so plain `+` suffices.

---

### 4.7 Per-node ANOVA summary and text strings

**Locations:** `rpart.anova.R` — `rpart.anova` (lines 6, 10)

**Original R Context:**

```r
# yval, dev, wt: numeric vectors, one element per tree node
# digits: integer scalar
# Each formatg() call returns a character vector of the same length as its input.
# Result: character vector, one summary string per node.
summary_str <- paste0("  mean=", formatg(yval, digits),
                      ", MSE=" , formatg(dev/wt, digits))

text_str <- paste0(formatg(yval, digits), "\nn=", n)
```

**Python Equivalent:**

```python
import numpy as np

# formatg(x, digits) -> np.array of str, same length as x
summary_str = np.char.add(
    np.char.add("  mean=", formatg(yval, digits)),
    np.char.add(", MSE=",  formatg(dev / wt, digits))
)

text_str = np.char.add(
    np.char.add(formatg(yval, digits), "\nn="),
    n.astype(str)
)

# Alternatively, with a list comprehension when arrays are Python lists:
summary_str = [
    f"  mean={fy}, MSE={fd}"
    for fy, fd in zip(formatg(yval, digits), formatg(dev / wt, digits))
]

text_str = [
    f"{fy}\nn={ni}"
    for fy, ni in zip(formatg(yval, digits), n)
]
```

**Explanation:** `formatg()` returns a string vector of the same length as `yval`. Mixing a scalar string literal with a character vector in R's `paste0` broadcasts the literal across every element — equivalent to Python's `np.char.add("  mean=", arr)`. For multi-fragment calls, chaining two `np.char.add` calls is necessary, or use a list comprehension with f-strings for clarity.

---

### 4.8 Classification node print labels (iterative multi-part concatenation)

**Locations:** `rpart.class.R` — `rpart.class` (lines 69, 71)

**Original R Context:**

```r
# temp: character vector of predicted class names, length = number of nodes
# yprob[, 1L]: character vector of first-class probabilities (already formatted)
# The for-loop appends remaining probability columns.
temp <- paste0(temp, " (", yprob[, 1L])
for (i in 2L:ncol(yprob)) temp <- paste(temp, yprob[, i], sep = " ")
temp <- paste0(temp, ")")
```

**Python Equivalent:**

```python
import numpy as np

# temp: np.array of str, shape (n_nodes,)
# yprob: np.array of str, shape (n_nodes, n_classes) — already formatted

temp = np.char.add(np.char.add(temp, " ("), yprob[:, 0])
for i in range(1, yprob.shape[1]):
    temp = np.char.add(np.char.add(temp, " "), yprob[:, i])
temp = np.char.add(temp, ")")

# Or with a list comprehension (cleaner for many classes):
temp = [
    f"{cls} ({' '.join(row)})"
    for cls, row in zip(temp_classes, yprob_str)
]
```

**Explanation:** R's `paste0(temp, " (", yprob[, 1L])` is a three-argument concatenation: `np.char.add(np.char.add(temp, " ("), yprob[:, 0])`. Note R uses 1-based column indexing (`yprob[, 1L]`) while Python uses 0-based (`yprob[:, 0]`). The trailing `)` is appended by a second `paste0` call, again a simple `np.char.add(..., ")")`. The list comprehension using `str.join` is especially readable when the number of class columns is not known at write time.

---

### 4.9 Classification node summary (long multi-fragment concatenation)

**Locations:** `rpart.class.R` — `rpart.class` (line 91)

**Original R Context:**

```r
# All inputs are character vectors of equal length (one entry per node).
# group, dev, nodeprob, temp1, temp2 are all pre-formatted strings/vectors.
paste0("  predicted class=", format(group, justify = "left"),
       "  expected loss=",   formatg(dev, digits),
       "  P(node) =",        formatg(nodeprob, digits), "\n",
       "    class counts: ",  temp1, "\n",
       "   probabilities: ",  temp2)
```

**Python Equivalent:**

```python
import numpy as np

# All are np.arrays of str, shape (n_nodes,)
summary_str = (
    "  predicted class=" + group_fmt         # scalar + vector broadcasts
    + "  expected loss="  + formatg(dev, digits)
    + "  P(node) ="       + formatg(nodeprob, digits) + "\n"
    + "    class counts: " + temp1 + "\n"
    + "   probabilities: " + temp2
)

# NumPy string arrays support '+' for concatenation when dtype is '<U...'.
# Alternatively, using np.char.add for explicit clarity:
parts = [
    "  predicted class=", group_fmt,
    "  expected loss=", formatg(dev, digits),
    "  P(node) =", formatg(nodeprob, digits), "\n",
    "    class counts: ", temp1, "\n",
    "   probabilities: ", temp2,
]
import functools
summary_str = functools.reduce(np.char.add, parts)

# Or using a list comprehension:
summary_str = [
    f"  predicted class={g}  expected loss={e}  P(node) ={p}\n"
    f"    class counts: {c1}\n   probabilities: {c2}"
    for g, e, p, c1, c2 in zip(group_fmt, formatg(dev, digits),
                                formatg(nodeprob, digits), temp1, temp2)
]
```

**Explanation:** R's `paste0` happily takes any number of arguments and recycles scalar literals across the full vector. In NumPy, string dtype arrays (`dtype='<U...'`) support `+` for element-wise concatenation, making the multi-fragment form readable with plain Python operators. `functools.reduce(np.char.add, parts)` generalizes this for a list of parts. The list comprehension with f-strings is the most readable option when the number of elements is fixed.

---

### 4.10 Classification node text labels (conditional vector)

**Locations:** `rpart.class.R` — `rpart.class` (line 107)

**Original R Context:**

```r
# group: character vector of predicted class labels, length = number of nodes
# temp1: character vector of formatted class counts
# Returns a character vector of multi-line strings.
paste0(format(group, justify = "left"), "\n", temp1)
```

**Python Equivalent:**

```python
import numpy as np

text_str = np.char.add(np.char.add(group_fmt, "\n"), temp1)

# Or with a list comprehension:
text_str = [f"{g}\n{t}" for g, t in zip(group_fmt, temp1)]
```

**Explanation:** Three-argument `paste0` with two vector arguments and a scalar newline literal. Use two chained `np.char.add` calls or an f-string list comprehension.

---

### 4.11 Survival/Poisson per-node summary and text strings

**Locations:**
- `rpart.exp.R` — `rpart.exp` (lines 132, 137)
- `rpart.poisson.R` — `rpart.poisson` (lines 39, 47)

**Original R Context:**

```r
# yval is a 2-column matrix: column 1 = estimated rate, column 2 = event count
# dev, wt, n: numeric vectors, one value per node
# All formatg() calls return character vectors of length equal to nrow(yval).
summary_str <- paste0("  events=",         formatg(yval[, 2L]),
                      ",  estimated rate=", formatg(yval[, 1L], digits),
                      " , mean deviance=",  formatg(dev/wt, digits))

text_str <- paste0(formatg(yval[, 1L], digits), "\n",
                   formatg(yval[, 2L]),          "/", n)
```

**Python Equivalent:**

```python
import numpy as np

# yval: np.ndarray, shape (n_nodes, 2); columns 0 and 1 in Python (0-based)
summary_str = (
    "  events="          + formatg(yval[:, 1])           # col index 1 (0-based) = R's [,2]
    + ",  estimated rate=" + formatg(yval[:, 0], digits)  # col index 0 (0-based) = R's [,1]
    + " , mean deviance="  + formatg(dev / wt, digits)
)

text_str = (
    formatg(yval[:, 0], digits)     # R's yval[, 1L]
    + "\n"
    + formatg(yval[:, 1])           # R's yval[, 2L]
    + "/"
    + n.astype(str)
)

# Using np.char.add explicitly:
summary_str = functools.reduce(np.char.add, [
    "  events=",          formatg(yval[:, 1]),
    ",  estimated rate=", formatg(yval[:, 0], digits),
    " , mean deviance=",  formatg(dev / wt, digits),
])

# Or with list comprehension:
summary_str = [
    f"  events={ev},  estimated rate={rate} , mean deviance={md}"
    for ev, rate, md in zip(formatg(yval[:, 1]),
                             formatg(yval[:, 0], digits),
                             formatg(dev / wt, digits))
]
text_str = [
    f"{rate}\n{ev}/{ni}"
    for rate, ev, ni in zip(formatg(yval[:, 0], digits),
                             formatg(yval[:, 1]),
                             n)
]
```

**Explanation:** R's matrix column indexing is 1-based (`yval[, 1L]` = first column, `yval[, 2L]` = second column). Python/NumPy uses 0-based indexing (`yval[:, 0]` and `yval[:, 1]`). This is the most important indexing offset to remember when translating these calls. The rest of the conversion follows the same pattern as Section 4.7.

---

### 4.12 Split-label suffix construction in `summary.rpart`

**Locations:** `summary.rpart.R` — `summary.rpart` (line 59)

**Original R Context:**

```r
# cuts: character vector, one entry per split in x$splits
# temp: integer vector (column 2 of x$splits), same length
# ifelse produces a character vector of ",", " to the right,", or " to the left, "
cuts <- paste0(cuts, ifelse(temp >= 2L, ",",
                            ifelse(temp == 1L, " to the right,", " to the left, ")))
```

**Python Equivalent:**

```python
import numpy as np

suffix = np.where(temp >= 2, ",",
         np.where(temp == 1, " to the right,", " to the left, "))
cuts = np.char.add(cuts, suffix)

# Or with a list comprehension:
cuts = [
    c + ("," if t >= 2 else (" to the right," if t == 1 else " to the left, "))
    for c, t in zip(cuts, temp)
]
```

**Explanation:** Nested `ifelse` in R maps to nested `np.where` in NumPy. The outer condition (`temp >= 2`) is checked first; if false, the inner `np.where` resolves the remaining two branches. The result is a string array of the same length as `cuts`, which is then appended via `np.char.add`. The list comprehension using nested ternary expressions is also clear and avoids a NumPy dependency if `cuts` and `temp` are already Python lists.
