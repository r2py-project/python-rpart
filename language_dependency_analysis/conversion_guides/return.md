# Conversion Guide: `return` in R

## 1. Overview of `return` in R

`return` is a base R control-flow function that immediately exits the enclosing function and delivers a value back to the caller. It is used explicitly when an early exit is needed (e.g., a guard clause) or to make the return value unambiguous in complex branching logic.

Key characteristics:

- **Syntax:** `return(value)` — the argument is the value to be returned. Only one value can be passed, though that value may be any R object (scalar, vector, matrix, list, `NULL`, etc.).
- **Early exit:** When `return()` is encountered, execution of the enclosing function stops immediately; no subsequent statements in the function body are evaluated.
- **Implicit return:** In R, a function also returns the value of its last evaluated expression even without an explicit `return()`. Explicit `return()` is therefore most useful for guard clauses and mid-function exits.
- **`invisible()` wrapper:** `return(invisible(x))` returns `x` but suppresses automatic printing at the top-level REPL. This is a common convention for functions called primarily for their side-effects.
- **`return(invisible())`:** Calling `invisible()` with no argument is equivalent to `invisible(NULL)`, so the function silently returns `NULL`.

## 2. Contextual Usage Analysis

Across the nine call sites in the CSV, `return` is used exclusively for **early exits / guard clauses** — that is, when a special boundary condition is detected before the main body of the function needs to run. The following patterns appear:

| Pattern | Example call body | Returned type |
|---|---|---|
| Return a string literal | `return("root")` | character scalar |
| Return a 2-column character matrix | `return(cbind(ltemp, rtemp))` | matrix (character, n x 2) |
| Return a data-frame / model frame | `return(m)` | data.frame |
| Return `invisible(NULL)` (silent no-op) | `return(invisible())` | NULL (invisible) |
| Return the input object unchanged | `return(tree)` / `return(x)` | rpart object |
| Return a named list | `return(list(x = x, y = y))` | list with two numeric vectors |
| Return a boolean matrix | `return(matrix(TRUE, 1L, 1L))` | 1 x 1 logical matrix |

All uses are guards: they fire when the function detects a trivial or degenerate case and short-circuits normal computation.

## 3. Python Conversion Strategy

Python's `return` statement is the direct equivalent of R's `return()`. Both:

- immediately terminate function execution and pass a value back to the caller;
- can return any object (scalar, string, `None`, `list`, `dict`, NumPy array, pandas DataFrame, etc.);
- implicitly return `None` when no argument is given (analogous to R's `return(invisible())`).

Because `return` itself is a language control-flow construct rather than a vectorised data function, **no third-party library is required for the translation**. However, the *values being returned* often come from R functions that do require NumPy or pandas equivalents (e.g., `cbind`, `matrix`). Those are detailed per example below.

The `invisible()` wrapper has no direct Python equivalent because Python does not automatically print function return values at the interpreter level in scripts; the convention is simply to `return None` (or bare `return`).

## 4. Step-by-Step Conversion Examples

### 4.1 Early exit returning a string literal

**Locations:** `labels.rpart.R` — `labels.rpart` (line 28)

**Original R context:**

```r
# n is the number of rows in the frame; a tree with only one row has no splits
if (n == 1L) return("root")   # character scalar
```

The function `labels.rpart` builds split labels for each node. When the tree has only one node (the root), there are no splits to label, so it returns the string `"root"` immediately.

**Python equivalent:**

```python
def labels_rpart(obj, digits=4, minlength=1, collapse=True, **kwargs):
    ff = obj["frame"]
    n = len(ff)
    if n == 1:
        return "root"          # str — direct equivalent of R character scalar
    # ... rest of function
```

**Explanation:** Python's `return "root"` is identical in semantics to R's `return("root")`. Both produce a single-element string and stop execution of the enclosing function.

---

### 4.2 Early exit returning a two-column character matrix

**Locations:** `labels.rpart.R` — `labels.rpart` (line 90)

**Original R context:**

```r
if (!collapse) {
    ltemp <- rtemp <- rep("<leaf>", n)
    ltemp[whichrow] <- lsplit
    rtemp[whichrow] <- rsplit
    return(cbind(ltemp, rtemp))   # character matrix, shape (n, 2)
}
```

When `collapse = FALSE`, the function returns a two-column character matrix whose rows correspond to nodes and columns to left/right labels.

**Python equivalent:**

```python
import numpy as np

if not collapse:
    ltemp = np.full(n, "<leaf>", dtype=object)
    rtemp = np.full(n, "<leaf>", dtype=object)
    ltemp[whichrow] = lsplit
    rtemp[whichrow] = rsplit
    return np.column_stack([ltemp, rtemp])   # ndarray, shape (n, 2), dtype=object
```

**Explanation:** R's `cbind(ltemp, rtemp)` binds two character vectors into a matrix column-wise. `numpy.column_stack` is the idiomatic NumPy equivalent, producing an `(n, 2)` array. Using `dtype=object` preserves string content without truncation. The `return` statement itself is unchanged.

---

### 4.3 Early exit returning a data frame (model frame)

**Locations:** `model.frame.rpart.R` — `model.frame.rpart` (lines 4 and 12)

**Original R context:**

```r
model.frame.rpart <- function(formula, ...) {
    m <- formula$model
    if (!is.null(m)) return(m)          # line 4 — return cached model frame

    oc <- formula$call
    if (substring(deparse(oc[[1L]]), 1L, 7L) == "predict") {
        m <- eval(oc$newdata)
        if (is.null(attr(m, "terms"))) {
            object <- eval(oc$object)
            m <- model.frame(object$terms, m, na.rpart)
        }
        return(m)                        # line 12 — return freshly computed frame
    }
    # ...
}
```

Both `return(m)` calls short-circuit further computation. `m` is an R `data.frame` (the model frame used during fitting or prediction).

**Python equivalent:**

```python
import pandas as pd

def model_frame_rpart(formula, **kwargs):
    m = formula.get("model")            # dict-style attribute access
    if m is not None:
        return m                        # return cached DataFrame early

    oc = formula["call"]
    if _deparse(oc[0])[:7] == "predict":
        m = _eval(oc["newdata"])
        if _attr(m, "terms") is None:
            obj = _eval(oc["object"])
            m = model_frame(obj["terms"], m, na_rpart)
        return m                        # return freshly built DataFrame
    # ...
```

**Explanation:** Both R `return(m)` calls translate to Python `return m`. The object `m` is a `pandas.DataFrame` (or equivalent mapping) in the Python port. Guard-clause structure and return semantics are identical between the two languages.

---

### 4.4 Early exit returning `invisible(NULL)` (silent no-op)

**Locations:** `path.rpart.R` — `path.rpart` (line 24)

**Original R context:**

```r
if (length(nodes <- node.match(nodes, node)) == 0L)
    return(invisible())    # nothing matched; return NULL silently
```

`invisible()` with no argument returns `NULL` without triggering automatic printing at the R console. This is used when the function is called for side-effects (printing paths) and there is nothing meaningful to return.

**Python equivalent:**

```python
def path_rpart(tree, nodes=None, pretty=0, print_it=True):
    # ...
    nodes = node_match(nodes, node)
    if len(nodes) == 0:
        return None    # or bare `return` — equivalent to invisible(NULL)
    # ...
```

**Explanation:** Python never auto-prints function return values in scripts, so the `invisible()` wrapper is meaningless in Python. A bare `return` (which yields `None`) or `return None` is the correct translation. If the caller needs to distinguish an empty result from a real result, `return None` makes the intent explicit.

---

### 4.5 Early exit returning the input object unchanged

**Locations:**
- `prune.rpart.R` — `prune.rpart` (line 6): `return(tree)`
- `snip.rpart.R` — `snip.rpart` (line 10): `return(x)`

**Original R context (`prune.rpart`):**

```r
toss <- id[ff$complexity <= cp & ff$var != "<leaf>"]
if (length(toss) == 0L) return(tree)   # no pruning needed; return as-is
```

**Original R context (`snip.rpart`):**

```r
if (missing(toss) || length(toss) == 0L) {
    toss <- snip.rpart.mouse(x)
    if (length(toss) == 0L) return(x)  # nothing to snip; return as-is
}
```

Both are identity guards: if the operation would be a no-op, return the input immediately rather than running expensive downstream logic.

**Python equivalent:**

```python
# prune_rpart
def prune_rpart(tree, cp):
    ff = tree["frame"]
    toss = [i for i, (comp, var) in enumerate(zip(ff["complexity"], ff["var"]))
            if comp <= cp and var != "<leaf>"]
    if len(toss) == 0:
        return tree    # rpart object (dict or custom class) returned unchanged
    # ...

# snip_rpart
def snip_rpart(x, toss=None):
    if toss is None or len(toss) == 0:
        toss = snip_rpart_mouse(x)
        if len(toss) == 0:
            return x   # rpart object returned unchanged
    # ...
```

**Explanation:** In Python the rpart tree is represented as a dict or a dataclass. `return tree` / `return x` passes back the same reference — semantically identical to R's early `return(tree)` / `return(x)`.

---

### 4.6 Early exit returning a named list (coordinate pair)

**Locations:** `rpartco.R` — `rpartco` (line 64)

**Original R context:**

```r
if (nspace < 0) return(list(x = x, y = y))
# x: numeric vector of x-coordinates (length = number of nodes)
# y: numeric vector of y-coordinates (length = number of nodes)
```

When the caller passes `nspace < 0` (the default), no overlap compression is performed and the raw coordinate vectors are returned as a named list.

**Python equivalent:**

```python
import numpy as np

def rpartco(tree, parms=None):
    # ... compute x (np.ndarray, float64) and y (np.ndarray, float64) ...
    if nspace < 0:
        return {"x": x, "y": y}   # dict mirrors R named list
    # ...
```

**Explanation:** R's `list(x = x, y = y)` is a named list, best represented in Python as a `dict`. Both `x` and `y` are numeric vectors; in Python these become `numpy.ndarray` objects of dtype `float64`. Returning a `dict` from a Python function is semantically equivalent to returning a named list from an R function.

---

### 4.7 Early exit returning a 1x1 boolean matrix

**Locations:** `zzz.R` — `descendants` (line 38)

**Original R context:**

```r
descendants <- function(nodes, include = TRUE) {
    n <- length(nodes)
    if (n == 1L) return(matrix(TRUE, 1L, 1L))
    # ...
}
```

`matrix(TRUE, 1L, 1L)` creates a 1-row by 1-column logical matrix filled with `TRUE`. This handles the degenerate case where the tree has only a single node: the node is trivially its own descendant.

**Python equivalent:**

```python
import numpy as np

def descendants(nodes, include=True):
    n = len(nodes)
    if n == 1:
        return np.ones((1, 1), dtype=bool)   # shape (1,1), dtype bool, value True
    # ...
```

**Explanation:** R's `matrix(TRUE, 1L, 1L)` is equivalent to `np.ones((1, 1), dtype=bool)`, which creates a `(1, 1)` NumPy boolean array with value `True`. The `return` statement is otherwise unchanged. Note that R uses 1-based indexing but the shape of the matrix here is unambiguous regardless of indexing convention.
