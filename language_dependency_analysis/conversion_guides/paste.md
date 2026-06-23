# Conversion Guide: `paste` (R to Python)

---

## 1. Overview of `paste` in R

`paste` is one of R's fundamental string manipulation functions. It converts its arguments to character strings and then concatenates them into a single character string (or a character vector if multiple arguments are vectors of length > 1).

**Key signature:**

```r
paste(..., sep = " ", collapse = NULL)
```

- `...`: One or more R objects that are coerced to character. When multiple objects are provided as positional arguments they are interleaved element-wise (recycling applies).
- `sep`: The string inserted between each pair of adjacent converted arguments. Defaults to a single space `" "`.
- `collapse`: If not `NULL`, a single string is returned by collapsing all elements of the intermediate character vector with `collapse` as the separator.

**Vectorised behaviour:** when the positional `...` arguments include vectors, `paste` operates element-wise across those vectors (recycling shorter vectors to match the longest). The result is a character vector of the same length as the longest argument — unless `collapse` is specified, in which case that vector is further collapsed to a single string.

`paste0(...)` is a shortcut for `paste(..., sep = "")`.

---

## 2. Contextual Usage Analysis

The CSV entries cover eight distinct source files. After reading all relevant source contexts the usages fall into four functional patterns:

| Pattern | Description | Key `sep` / `collapse` values |
|---------|-------------|-------------------------------|
| A | Join two or more scalars into one string (name-building, labelling) | `sep` only; no `collapse` |
| B | Collapse a character vector into one string with a custom separator | `collapse` only; no explicit `sep` |
| C | Element-wise concatenation of two equal-length character vectors, then use the resulting vector as-is | `sep = " "` (default); no `collapse` |
| D | Single-argument `paste` with no `sep`/`collapse` — identity-like call used as a no-op conversion to character | neither |

All arguments in the CSV are scalars or 1-D character vectors. No 2-D array (matrix) arguments appear.

---

## 3. Python Conversion Strategy

Because R's `paste` is inherently vectorised over its positional arguments, the primary Python equivalent depends on the shape of the data:

- **Scalar-only contexts** (patterns A and most of B): Python's built-in `str.join()` combined with f-strings or `+` concatenation is the most idiomatic choice, and no third-party library is required.
- **Vector / array contexts** (patterns C and D): `numpy` string operations (`np.char.add`, `numpy` array comprehensions) or `pandas` `Series.str.cat` are the most natural equivalents. For the rpart usages here the inputs are Python `list` objects rather than NumPy arrays, so `list` comprehensions (possibly with `zip`) are the cleanest translation.
- **`collapse`** maps directly to `str.join(sep, iterable)` in Python.

`numpy` is therefore the preferred library for any call that processes a vector of strings, while pure Python builtins (`str.join`, f-strings) handle scalar cases cleanly. No `scipy` or `pandas` is required for these usages.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Joining two scalar strings with a custom separator

**Locations:** `rpart.R` (`rpart`, lines 68 and 71), `xpred.rpart.R` (`xpred.rpart`, line 34).

**Original R Context:**

```r
# rpart.R, lines 67-72
init <- if (missing(parms))
    get(paste("rpart", method, sep = "."),
        envir = environment())(Y, offset, , wt)
else
    get(paste("rpart", method, sep = "."),
        envir = environment())(Y, offset, parms, wt)
```

Both `"rpart"` and `method` are scalar character strings. `sep = "."` replaces the default space. The return value is a single character scalar used as a function name to look up via `get()`.

```r
# xpred.rpart.R, line 34
init <- get(paste("rpart", method, sep = "."))(Y, offset, NULL)
```

**Python Equivalent:**

```python
# Both inputs are plain Python str scalars.
# R:  paste("rpart", method, sep = ".")
func_name = "rpart" + "." + method          # explicit concatenation
# or equivalently:
func_name = f"rpart.{method}"               # f-string — most idiomatic

# Lookup equivalent (replacing R's get()):
init_func = globals()[func_name]            # or getattr(module, func_name)
```

**Explanation:** `paste("rpart", method, sep = ".")` with two scalar strings is identical to Python string concatenation. No vectorisation is involved. The `sep = "."` argument is simply inserted between the two parts, so `"rpart" + "." + method` or an f-string is the most readable translation.

---

### 4.2 Pattern A — Joining a scalar string and a variable with `sep = ""`

**Locations:** `post.rpart.R` (`post.rpart`, line 3).

**Original R Context:**

```r
# post.rpart.R, lines 2-6 (function signature default argument)
post.rpart <- function(tree, title.,
        filename = paste(deparse(substitute(tree)), ".ps", sep = ""),
        ...)
```

`deparse(substitute(tree))` returns a single character string (the name of the `tree` argument as the caller wrote it). `sep = ""` means no separator — the `.ps` extension is appended directly. The return value is a scalar filename string.

**Python Equivalent:**

```python
import inspect

# deparse(substitute(tree)) -> the variable name passed by the caller.
# In Python this is typically obtained via the calling frame.
tree_name = "tree"  # obtained via inspection or passed explicitly

filename = tree_name + ".ps"
# or:
filename = f"{tree_name}.ps"
```

**Explanation:** `paste(..., sep = "")` is R's `paste0`. When both parts are scalars the Python equivalent is simple string concatenation with `+` or an f-string. `sep = ""` means nothing is inserted between the two strings.

---

### 4.3 Pattern A — Joining a literal prefix and a scalar value

**Locations:** `post.rpart.R` (`post.rpart`, line 22), `summary.rpart.R` (`summary.rpart`, lines 48 and 50).

**Original R Context:**

```r
# post.rpart.R, line 22
title(paste("Endpoint =", temp), cex = 0.8)
# temp is a single expression object coerced to string by paste.

# summary.rpart.R, lines 47-50
cuts[i] <- if (temp[i] == -1L)
    paste("<", format(signif(x$splits[i, 4L], digits)))
else if (temp[i] == 1L)
    paste("<", format(signif(x$splits[i, 4L], digits)))
```

In all three cases `sep` is not specified so the default `" "` applies. Both operands are scalars (a string literal and a scalar string variable). The result is a single character string assigned to a scalar or passed to a display function.

**Python Equivalent:**

```python
# post.rpart.R line 22:
title_str = f"Endpoint = {temp}"

# summary.rpart.R lines 48/50:
import numpy as np

cut_str = f"< {format(round(float(x_splits_i_4), digits))}"
# or using Python's built-in formatting:
cut_str = "< " + f"{value:.{digits}g}"
```

**Explanation:** `paste("< ", value)` with default `sep = " "` inserts exactly one space between the literal and the formatted number. The f-string `f"< {value}"` is the cleanest Python translation. `format(signif(...))` corresponds to Python's `f"{value:.{digits}g}"` (significant-figure formatting).

---

### 4.4 Pattern A — Multi-part scalar label construction

**Locations:** `print.rpart.R` (`print.rpart`, line 27), `summary.rpart.R` (`summary.rpart`, lines 91 and 104).

**Original R Context:**

```r
# print.rpart.R, line 27 — multiple scalar/vector arguments, default sep=" "
z <- paste(indent, z, n, format(signif(frame$dev, digits)), yval, term)
# All arguments here are character vectors of the same length; result is a
# character vector of the same length with each element being the space-joined
# concatenation of the corresponding elements across all arguments.

# summary.rpart.R, line 91 — scalar concatenation with sep=""
cat(paste("      ", format(sname[j], justify = "left"), " ", temp,
          " improve=", format(signif(x$splits[j, 3L], digits)),
          ", (", nn - x$splits[j, 1L], " missing)", sep = ""),
    sep = "\n")

# summary.rpart.R, line 104 — same pattern for surrogate splits
cat(paste("      ", format(sname[j], justify = "left"), " ",
          temp,
          " agree=", format(round(agree, 3L)),
          ", adj=", format(round(adj, 3L)),
          ", (", x$splits[j, 1L], " split)", sep = ""),
    sep = "\n")
```

For `print.rpart` line 27, all six arguments (`indent`, `z`, `n`, `dev`, `yval`, `term`) are character vectors of equal length. `paste` joins them element-wise with a space.

For `summary.rpart` lines 91 and 104, multiple scalar parts are assembled with `sep = ""` into a single structured string per split entry. Each call produces a character vector (one string per element of `sname[j]` / `agree` / `temp`).

**Python Equivalent:**

```python
import numpy as np

# --- print.rpart line 27: element-wise join of parallel character arrays ---
# indent, z, n, dev_str, yval, term are all Python lists (or np.ndarray of str)
# of the same length.

rows = [
    " ".join([indent[k], z[k], str(n[k]), dev_str[k], yval[k], term[k]])
    for k in range(len(z))
]

# Using numpy for a more vectorised style:
rows_np = np.char.add(
    np.char.add(np.char.add(np.char.add(np.char.add(
        indent_arr + " ", z_arr + " "), n_arr + " "), dev_arr + " "), yval_arr + " "), term_arr
)

# --- summary.rpart line 91: multi-part scalar assembly with sep="" ---
# j is an integer index (or array of indices); each expression is a scalar
# or a vector of the same length as j.
lines_out = [
    "      " + fmt_sname + " " + cut_str + " improve=" + fmt_improve
    + ", (" + str(missing_count) + " missing)"
    for fmt_sname, cut_str, fmt_improve, missing_count
    in zip(format_sname_j, temp_j, format_improve_j, missing_j)
]

# --- summary.rpart line 104: surrogate splits ---
lines_surr = [
    "      " + fmt_sname + " " + cut_str
    + " agree=" + fmt_agree + ", adj=" + fmt_adj
    + ", (" + str(n_split) + " split)"
    for fmt_sname, cut_str, fmt_agree, fmt_adj, n_split
    in zip(format_sname_j, temp_j, format_agree_j, format_adj_j, splits_j)
]
print("\n".join(lines_out))
print("\n".join(lines_surr))
```

**Explanation:** When `paste` receives multiple equal-length vector arguments with no `collapse`, the operation is element-wise — R's recycling rule applies. The Python equivalent is a `zip`-based list comprehension. When `sep = ""` is used, the Python equivalent is plain string concatenation with `+` (no space inserted). `cat(..., sep = "\n")` becomes `print("\n".join(...))`.

---

### 4.5 Pattern B — Collapsing a vector of strings to a single string

**Locations:** `print.rpart.R` (`print.rpart`, line 11), `zzz.R` (`node.match`, lines 26 and 30), `labels.rpart.R` (`labels.rpart`, lines 80 and 82), `summary.rpart.R` (`summary.rpart`, line 51).

**Original R Context:**

```r
# print.rpart.R, line 11 — collapse a repeated-character vector to one string
indent <- paste(rep(" ", spaces * 32L), collapse = "")
# rep(" ", 64) produces a character vector of 64 spaces.
# collapse="" joins them all into a single 64-character string.

# zzz.R, lines 26 and 30 — collapse integer node numbers to comma-separated string
paste(bad, collapse = ",")
paste(good[leaves], collapse = ",")
# bad / good[leaves] are integer vectors; paste coerces them to character first.

# labels.rpart.R, lines 80 and 82 — collapse factor level labels
lsplit[j] <- paste((xlevels[[cindex[i]]])[splits == 1L], collapse = cl)
rsplit[j] <- paste((xlevels[[cindex[i]]])[splits == 3L], collapse = cl)
# The subset is a character vector of category level abbreviations.
# cl is either "" (minlength == 1) or "," (minlength > 1).

# summary.rpart.R, line 51 — nested paste: inner collapse, outer collapse
paste("splits as ",
      paste(c("L", "-", "R")[x$csplit[x$splits[i, 4L], 1:temp[i]]],
            collapse = "", sep = ""),
      collapse = "")
# Inner paste: collapses a character vector (L/R/-) into a single run of letters.
# Outer paste: collapses the resulting length-1 vector — effectively a no-op here.
```

**Python Equivalent:**

```python
# print.rpart.R line 11: repeat and join
indent = " " * (spaces * 32)       # Python string repetition; direct and idiomatic

# zzz.R lines 26 and 30: collapse integer vector to comma-separated string
bad_str  = ",".join(str(x) for x in bad)
good_str = ",".join(str(x) for x in good_leaves)

# labels.rpart.R lines 80/82: collapse character subset with separator cl
cl = "" if minlength == 1 else ","
lsplit_j = cl.join(xlevels_cindex_i[splits == 1])
rsplit_j = cl.join(xlevels_cindex_i[splits == 3])

# summary.rpart.R line 51: nested collapse
import numpy as np

direction_map = {1: "L", 2: "-", 3: "R"}
csplit_row = x_csplit[x_splits_i_4, :temp_i]        # integer array of 1/2/3
letters = [direction_map[v] for v in csplit_row]
inner = "".join(letters)                              # collapse=""
result = "splits as  " + inner                        # outer collapse is a no-op
```

**Explanation:** `paste(x, collapse = sep)` is exactly `sep.join(str(v) for v in x)` in Python. When `collapse = ""` the join separator is the empty string. The `" " * n` Python idiom replaces `paste(rep(" ", n), collapse = "")` — string repetition is more direct than building a list of single spaces and joining them. For the nested `paste` in `summary.rpart`, the inner collapse produces a length-1 character vector; the outer `collapse = ""` then joins a length-1 vector, which is effectively a no-op, so only the inner join matters in Python.

---

### 4.6 Pattern C — Element-wise concatenation of two character vectors (default `sep`)

**Locations:** `rpart.class.R` (`rpart.class`, line 70).

**Original R Context:**

```r
# rpart.class.R, lines 62-71 (inside the print closure)
yprob <- format(yval[, 1L + nclass + 1L:nclass],
                digits = digits, nsmall = nsmall)
# yprob is a character matrix; temp is a character vector (one entry per node).
temp <- paste0(temp, " (", yprob[, 1L])
for (i in 2L:ncol(yprob))
    temp <- paste(temp, yprob[, i], sep = " ")
temp <- paste0(temp, ")")
```

`temp` and `yprob[, i]` are character vectors of the same length (one element per decision-tree node). The loop accumulates all class-probability columns into a space-separated string per node. The result is a character vector of the same length.

**Python Equivalent:**

```python
import numpy as np

# yprob is a 2-D numpy array of formatted strings, shape (n_nodes, n_classes).
# temp starts as a 1-D array of class-label strings.

temp = np.char.add(np.char.add(temp, " ("), yprob[:, 0])
for i in range(1, yprob.shape[1]):
    temp = np.char.add(np.char.add(temp, " "), yprob[:, i])
temp = np.char.add(temp, ")")

# Alternatively, using a list comprehension for clarity:
temp = [
    t + " (" + " ".join(yprob[k, :]) + ")"
    for k, t in enumerate(temp_list)
]
```

**Explanation:** R's `paste(vec_a, vec_b, sep = " ")` on two equal-length character vectors is element-wise string concatenation with a space. `numpy.char.add` performs element-wise string concatenation on arrays but does not insert a separator — the space must be added explicitly (as a separate `np.char.add` call or by padding the strings). The list-comprehension form is often clearer for this pattern when `n_classes` is small.

---

### 4.7 Pattern D — Single-argument `paste` (identity / vector-to-character coercion)

**Locations:** `rpart.class.R` (`rpart.class`, lines 86, 88, 106), `rpart.exp.R` (`rpart.exp`, line 139), `rpart.poisson.R` (`rpart.poisson`, line 49).

**Original R Context:**

```r
# rpart.class.R, lines 84-89 (inside summary closure)
temp1 <- apply(matrix(temp1, ncol = nclass), 1L, paste, collapse = " ")
temp2 <- apply(matrix(temp2, ncol = nclass), 1L, paste, collapse = " ")

# rpart.class.R, line 105-106 (inside text closure)
temp1 <- apply(matrix(temp1, ncol = nclass), 1L, paste, collapse = "/")

# rpart.exp.R, line 139 (inside text closure, no-split case)
else paste(formatg(yval[, 1L], digits))

# rpart.poisson.R, line 49 (inside text closure, no-split case)
else paste(formatg(yval[, 1L], digits))
```

In `rpart.class.R` lines 86, 88, and 106, `paste` is passed as a function reference to `apply`. Each row of the character matrix is collapsed into a space-separated (or `/`-separated) string. In `rpart.exp.R` line 139 and `rpart.poisson.R` line 49, `paste` is called on a single character vector with no `sep` or `collapse`; this simply ensures the result is a character vector (effectively a no-op if `formatg` already returns strings).

**Python Equivalent:**

```python
import numpy as np

# rpart.class.R lines 86, 88 — apply(matrix, 1, paste, collapse = " ")
# temp1 is a 1-D array of formatted strings; reshaped to (n_rows, nclass).
temp1_mat = np.array(temp1).reshape(-1, nclass)
temp1_collapsed = np.array([" ".join(row) for row in temp1_mat])

temp2_mat = np.array(temp2).reshape(-1, nclass)
temp2_collapsed = np.array([" ".join(row) for row in temp2_mat])

# rpart.class.R line 106 — apply(matrix, 1, paste, collapse = "/")
temp1_mat = np.array(temp1).reshape(-1, nclass)
temp1_slash = np.array(["/".join(row) for row in temp1_mat])

# rpart.exp.R line 139 / rpart.poisson.R line 49 — identity-like paste
# formatg already returns a list/array of strings; no conversion needed.
result = formatg(yval[:, 0], digits)   # already a list of str; paste is a no-op
```

**Explanation:** When `paste` is passed as a functional argument to R's `apply(..., MARGIN = 1, FUN = paste, collapse = " ")`, it collapses each row of the matrix. The Python equivalent is a list comprehension over rows with `str.join`. For the single-argument `paste(formatg(...))` calls, `paste` in R returns a character vector unchanged when given one argument and no `collapse`; this is a no-op in Python if `formatg` already returns strings.

---

## Summary Table

| CSV line(s) | File / Function | R pattern | Python equivalent |
|-------------|-----------------|-----------|-------------------|
| rpart.R 68, 71; xpred.rpart.R 34 | `rpart`, `xpred.rpart` | `paste("rpart", method, sep=".")` | `f"rpart.{method}"` |
| post.rpart.R 3 | `post.rpart` | `paste(name, ".ps", sep="")` | `name + ".ps"` |
| post.rpart.R 22; summary.rpart.R 48,50 | `post.rpart`, `summary.rpart` | `paste("< ", value)` default sep | `f"< {value}"` |
| print.rpart.R 27; summary.rpart.R 91,104 | `print.rpart`, `summary.rpart` | `paste(v1,v2,...,sep="")` element-wise | `zip`-based list comprehension |
| print.rpart.R 11 | `print.rpart` | `paste(rep(" ",n), collapse="")` | `" " * n` |
| zzz.R 26, 30 | `node.match` | `paste(vec, collapse=",")` | `",".join(str(x) for x in vec)` |
| labels.rpart.R 80, 82 | `labels.rpart` | `paste(char_vec, collapse=cl)` | `cl.join(char_vec)` |
| summary.rpart.R 51 | `summary.rpart` | nested `paste(..., collapse="")` | `"".join(letters)` |
| rpart.class.R 70 | `rpart.class` | `paste(vec_a, vec_b, sep=" ")` | `np.char.add` or list comprehension |
| rpart.class.R 86, 88, 106 | `rpart.class` | `apply(..., paste, collapse=sep)` | `[sep.join(row) for row in matrix]` |
| rpart.exp.R 139; rpart.poisson.R 49 | `rpart.exp`, `rpart.poisson` | `paste(char_vec)` single-arg | identity / no-op |
