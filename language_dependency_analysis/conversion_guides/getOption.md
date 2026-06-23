## Conversion Guide: `getOption` in R

---

### 1. Overview of `getOption` in R

`getOption` is a base R function that retrieves the current value of a named global option from R's session-wide options store. Its signature is:

```r
getOption(x, default = NULL)
```

- `x`: a character string naming the option to retrieve.
- `default`: the value to return if the named option has not been set (defaults to `NULL`).

The options store is a mutable, process-global key-value map managed by R's runtime. Users and packages can read from it (`getOption`) or write to it (`options(...)`). The store is populated with a standard set of defaults at session start, the most relevant of which for this codebase is `"digits"`.

**The `"digits"` option** controls the number of significant digits used when printing or formatting numeric values. Its default value is `7`, and it accepts integers in the range 1 through 22. It is a session-level preference — it can be changed by the user at any time via `options(digits = N)`, which is why code reads it dynamically at call time rather than using a hard-coded literal.

---

### 2. Contextual Usage Analysis

Both CSV rows retrieve the same option, `"digits"`, used in the same way: as a **default argument value** in a function signature. This is a classic R idiom for making a function's formatting behaviour respect the user's session-wide preference while still allowing callers to override it explicitly.

**`formatg.R` — `formatg`, line 3**

```r
formatg <- function(x, digits = getOption("digits"),
                    format = paste0("%.", digits, "g"))
```

`getOption("digits")` seeds the `digits` default parameter (an integer, e.g. `7`). `digits` is then interpolated into a C-style `sprintf` format string (`"%.<digits>g"`), which is applied element-wise over the numeric vector `x` using `sprintf`. The `"g"` format specifier causes R/C to choose between fixed and scientific notation, suppressing trailing zeros. The return value is a character vector (or character matrix when `x` is a matrix).

**`post.rpart.R` — `post.rpart`, line 4**

```r
post.rpart <- function(tree, title.,
    filename = paste(deparse(substitute(tree)), ".ps", sep = ""),
    digits = getOption("digits") - 2, pretty = TRUE,
    use.n = TRUE, horizontal = TRUE, ...)
```

Here `getOption("digits")` is again the default source for `digits`, but with an arithmetic offset of `−2` applied (yielding `5` under the R default of `7`). The resulting integer is passed downstream to `text(tree, ..., digits = digits, ...)` to control how numeric node labels are formatted in a PostScript plot of the decision tree.

**Recurring pattern:** In both locations, `getOption("digits")` is used exclusively as a **default parameter initializer**, not as a run-time lookup inside the function body. The retrieved value is always an integer scalar. No list indexing, no `NULL` fallback handling, and no other option names appear in the CSV data.

---

### 3. Python Conversion Strategy

R's global options system has no direct built-in equivalent in Python. The closest idiomatic translation depends on the role `getOption("digits")` plays:

- Because it is used solely to provide a **default integer value** for a function parameter, the correct Python equivalent is to read from a **module-level or package-level configuration object** rather than from any numeric library.
- `numpy` and `pandas` maintain their own display precision settings (`numpy.get_printoptions()["precision"]`, `pandas.get_option("display.precision")`), but these control *printing* only, not the formatting logic inside user functions, and they are not the idiomatic place to store application-level defaults.
- The most faithful and Pythonic translation is to define a **module-level constant** (e.g., `DIGITS = 7`) that mirrors R's default, and allow callers to override it at the call site — exactly as R callers can pass an explicit `digits=` argument. If dynamic, session-wide configurability is required (to match a user calling `options(digits = N)` in R), a simple **configuration dictionary or dataclass** at the package level provides that capability.
- For the actual numeric formatting that `digits` drives (`sprintf("%.<digits>g", x)` applied over a vector), `numpy` is the correct library because `x` is always a numeric vector (or matrix) in `formatg`, making vectorized formatting essential.

**Chosen strategy:** Replace `getOption("digits")` with a module-level constant `DIGITS = 7` (R's default), and use Python's built-in `format` / `numpy` vectorized operations for the downstream formatting work.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 `formatg` — Formatting a numeric vector with `"g"` notation

**Locations:** `rpart/R/formatg.R`, function `formatg`

**Original R Context**

- Input `x`: a numeric vector or numeric matrix.
- Input `digits`: an integer scalar (default from session option, typically `7`).
- Input `format`: a `sprintf`-style format string, defaulting to `"%.<digits>g"`.
- Return value: a character vector, or a character matrix when `x` is a matrix.

```r
formatg <- function(x, digits = getOption("digits"),
                    format = paste0("%.", digits, "g"))
{
    if (!is.numeric(x)) stop("'x' must be a numeric vector")
    temp <- sprintf(format, x)
    if (is.matrix(x)) matrix(temp, nrow = nrow(x)) else temp
}
```

**Python Equivalent**

```python
import numpy as np

DIGITS = 7  # mirrors R's default value for getOption("digits")

def formatg(x, digits=DIGITS, fmt=None):
    """Format numeric values using C's 'g' format (suppresses trailing zeros,
    switches between fixed and scientific notation automatically)."""
    x = np.asarray(x)
    if not np.issubdtype(x.dtype, np.number):
        raise TypeError("'x' must be a numeric array")

    if fmt is None:
        fmt = f"%.{digits}g"

    # Apply the format string element-wise over the array
    vectorized_fmt = np.vectorize(lambda v: format(v, f".{digits}g"))
    temp = vectorized_fmt(x)

    return temp  # shape is preserved (1-D array or 2-D matrix)
```

**Explanation**

| R construct | Python equivalent | Notes |
|---|---|---|
| `getOption("digits")` | `DIGITS = 7` (module constant) | R's default is `7`; callers may pass an explicit integer to override |
| `paste0("%.", digits, "g")` | `f"%.{digits}g"` | Python f-string builds the same format specifier |
| `sprintf(format, x)` over a vector | `np.vectorize(lambda v: format(v, ...))(x)` | `np.vectorize` applies the scalar format call element-wise, preserving array shape |
| `is.matrix(x)` branch | Handled automatically | `np.asarray` preserves 2-D shape; no separate branch needed |
| `is.numeric(x)` guard | `np.issubdtype(x.dtype, np.number)` | Equivalent dtype check for NumPy arrays |

The `"g"` format specifier behaves identically in Python's `format()` and C's `sprintf` — it suppresses trailing zeros and selects between fixed and exponential notation based on the magnitude of the value, making this a clean one-to-one translation.

---

#### 4.2 `post.rpart` — Digits precision for decision tree node labels

**Locations:** `rpart/R/post.rpart.R`, function `post.rpart`

**Original R Context**

- Input `digits`: an integer scalar, defaulting to `getOption("digits") - 2` (i.e., `5` under R's default of `7`).
- The value is passed directly to R's `text()` plotting function as a formatting hint for numeric labels on tree nodes.
- Return value: `None` (the function is called for its PostScript plotting side-effect).

```r
post.rpart <- function(tree, title.,
        filename = paste(deparse(substitute(tree)), ".ps", sep = ""),
        digits = getOption("digits") - 2, ...)
{
    # ... plotting setup ...
    text(tree, all = TRUE, digits = digits, ...)
}
```

**Python Equivalent**

```python
DIGITS = 7  # mirrors R's default value for getOption("digits")

def post_rpart(tree, title=None,
               filename=None,
               digits=DIGITS - 2,   # default = 5, matching R's getOption("digits") - 2
               pretty=True,
               use_n=True,
               horizontal=True,
               **kwargs):
    """
    Generate a PostScript plot of an rpart decision tree.
    'digits' controls the number of significant digits shown in node labels.
    """
    effective_digits = digits  # integer scalar, e.g. 5
    # Pass effective_digits to the tree-text rendering function
    # text_rpart(tree, all=True, digits=effective_digits, pretty=pretty, ...)
```

**Explanation**

| R construct | Python equivalent | Notes |
|---|---|---|
| `getOption("digits") - 2` | `DIGITS - 2` | Arithmetic is evaluated once at module load time when used as a default argument value; this matches R's behaviour of evaluating the default at call time against a stable session default |
| `digits` parameter type | `int` | In both R and Python this is a plain integer scalar, never a vector |
| `options(digits = N)` (user override) | Pass `digits=N` explicitly at call site, or reassign `DIGITS` at module level | Python has no session-wide options store; the module constant is the closest equivalent |

**Important nuance — default argument evaluation:** In R, `getOption("digits")` in a default argument is evaluated *at call time*, so if the user changes `options(digits = 10)` mid-session, subsequent calls to `post.rpart()` without an explicit `digits=` will pick up the new value. Python default argument expressions are evaluated **once at function definition time**, so `digits=DIGITS - 2` is fixed when the module is imported. To replicate R's dynamic behaviour exactly, use a sentinel `None` default and resolve inside the function body:

```python
def post_rpart(tree, digits=None, ...):
    if digits is None:
        digits = DIGITS - 2  # read the current module-level value at call time
```

This sentinel pattern lets callers update `module.DIGITS` and have subsequent calls reflect the change, faithfully replicating R's `getOption` semantics.
