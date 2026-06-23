# Conversion Guide: `missing` in R

## 1. Overview of `missing` in R

`missing(x)` is a built-in R function that tests whether a formal argument of the currently executing function was supplied by the caller. It returns `TRUE` if the argument was not provided (i.e., is absent from the call), and `FALSE` if the argument was explicitly passed — even when the value passed is `NULL` or matches the default value.

Key behavioral properties:

- `missing(x)` can only be called inside a function body, and `x` must be one of the formal parameters of that function.
- It is distinct from checking `is.null(x)` or `is.na(x)`. A caller can pass `NULL` explicitly, and `missing` will return `FALSE`, but an `is.null` check would return `TRUE`.
- When a function has a default value for a parameter, `missing` still returns `TRUE` if the argument was not explicitly provided by the caller.
- It is commonly used in R to allow functions to distinguish between "the caller did not pass this argument" (absent) and "the caller passed the value `NULL`" (present but null), or to trigger fallback behaviors that depend on whether companion arguments were provided.

Typical inputs: any formal parameter name of the enclosing function.
Return value: a scalar logical (`TRUE` or `FALSE`).

---

## 2. Contextual Usage Analysis

Across the 30 CSV rows spanning 14 source files, `missing` is used exclusively in one pattern: as a boolean guard inside function bodies to branch on whether an optional argument was explicitly supplied by the caller. The identified sub-patterns are:

### Pattern A: Simple "was it given?" guard — take a default action branch

Used when the omission of an argument should trigger a fallback behavior that differs from whatever the default value provides. The function tests `if (missing(arg))` and assigns or computes a value differently than when the caller passed something.

Examples:
- `rpart.R` lines 35, 49, 67, 107, 139, 285
- `rpart.exp.R` line 109
- `rpart.poisson.R` line 14
- `rpart.class.R` line 11
- `rpart.branch.R` line 7
- `rpartco.R` line 4
- `snip.rpart.mouse.R` line 6
- `path.rpart.R` line 13
- `snip.rpart.R` line 8
- `post.rpart.R` line 20
- `print.rpart.R` line 6
- `xpred.rpart.R` line 61
- `zzz.R` line 28

### Pattern B: Compound condition — two arguments are in a dependency relationship

Used when two arguments interact, and the intended behavior depends on which subset was supplied. The idiom `if (missing(a) && !missing(b))` reads "use `b` to derive a value for `a`, but only when `a` was not given".

Examples:
- `labels.rpart.R` line 19: `if (missing(minlength) && !missing(pretty))`
- `rpart.control.R` line 17: `if (missing(minsplit) && !missing(minbucket))`
- `text.rpart.R` line 32: `if (!missing(pretty) && missing(minlength))`

### Pattern C: Capture missing status before consuming the argument

Used when the argument is passed to another function (e.g., `match.arg`) that would mark it as no longer missing, so the raw missing status must be saved first.

Example:
- `predict.rpart.R` line 7: `mtype <- missing(type)` captures the missing status before `type <- match.arg(type)` consumes the argument.

### Data types involved

Arguments tested with `missing` in this codebase span several types:
- Scalars/options (integer or numeric): `cp`, `minlength`, `minsplit`, `minbucket`, `branch`, `nspace`
- Strings: `title.`, `file`, `method`
- Lists or named lists: `parms`, `control`, `cost`
- Logical/NULL: `pretty`, `label`
- Vectors of node numbers: `nodes`, `toss`, `leaves`
- Data frames or matrices: `newdata`, `y`

---

## 3. Python Conversion Strategy

Python does not have a runtime `missing()` predicate. Instead, the idiomatic Python equivalent is to give the parameter a **sentinel default value** and test for it at runtime. The recommended sentinel is a module-level `_MISSING` object created from `object()`. Using `None` as a sentinel is also common but is ambiguous when `None` is a valid caller-supplied value (which happens in several rpart functions).

The strategy is:

1. Declare `_MISSING = object()` once at the top of the module (or reuse a shared sentinel).
2. Replace `def f(..., arg, ...)` with `def f(..., arg=_MISSING, ...)`.
3. Replace `if (missing(arg))` with `if arg is _MISSING`.
4. Replace `if (!missing(arg))` with `if arg is not _MISSING`.
5. For Pattern B (compound tests), compose sentinel checks with `and`/`or` in the same way.
6. For Pattern C (capture-before-consume), assign `arg_missing = (arg is _MISSING)` before any code that would overwrite `arg`.

When `None` is not a valid caller value for that parameter, `None` may be used directly as the default instead of a custom sentinel, simplifying the check to `if arg is None`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Simple absent/present guard

#### 4.1.1 Absent parameter triggers a lookup from stored state

**Locations:** `rpart/R/rpartco.R` (`rpartco`, line 4); `rpart/R/rpart.branch.R` (`rpart.branch`, line 7); `rpart/R/snip.rpart.mouse.R` (`snip.rpart.mouse`, line 6)

**Original R Context:**

`parms` is a list; its type is a named list with numeric entries. When absent the function retrieves it from a module-level environment keyed by the current graphics device.

```r
rpartco <- function(tree, parms) {
    if (missing(parms)) {
        pn <- paste0("device", dev.cur())
        if (!exists(pn, envir = rpart_env, inherits = FALSE))
            stop("no information available on parameters from previous call to plot()")
        parms <- get(pn, envir = rpart_env, inherits = FALSE)
    }
    # ... use parms ...
}
```

**Python Equivalent:**

```python
_MISSING = object()

def rpartco(tree, parms=_MISSING):
    if parms is _MISSING:
        pn = f"device{dev_cur()}"
        if pn not in rpart_env:
            raise RuntimeError(
                "no information available on parameters from previous call to plot()"
            )
        parms = rpart_env[pn]
    # ... use parms ...
```

**Explanation:** The R environment lookup (`exists` + `get` on `rpart_env`) maps directly to a Python dict membership test and retrieval. The sentinel `_MISSING` is checked with `is`, guaranteeing that an explicit `parms=None` caller call is handled correctly.

---

#### 4.1.2 Absent parameter sets a default scalar value

**Locations:** `rpart/R/rpart.branch.R` (`rpart.branch`, line 7)

**Original R Context:**

`branch` is a numeric scalar. When absent the function reads it from stored plot parameters.

```r
rpart.branch <- function(x, y, node, branch) {
    if (missing(branch)) {
        parms <- get(paste0("device", dev.cur()), envir = rpart_env, inherits = FALSE)
        branch <- parms$branch
    }
    # ... use branch ...
}
```

**Python Equivalent:**

```python
def rpart_branch(x, y, node, branch=_MISSING):
    if branch is _MISSING:
        parms = rpart_env[f"device{dev_cur()}"]
        branch = parms["branch"]
    # ... use branch ...
```

**Explanation:** Identical sentinel pattern. The R named list accessor `parms$branch` becomes `parms["branch"]` when `parms` is a Python dict.

---

#### 4.1.3 Absent parameter activates interactive mouse-based input

**Locations:** `rpart/R/path.rpart.R` (`path.rpart`, line 13); `rpart/R/snip.rpart.R` (`snip.rpart`, line 8)

**Original R Context:**

`nodes`/`toss` are integer vectors. When absent the function starts an interactive selection loop.

```r
path.rpart <- function(tree, nodes, pretty = 0, print.it = TRUE) {
    # ...
    if (missing(nodes)) {
        xy <- rpartco(tree)
        while (length(i <- identify(xy, n = 1L, plot = FALSE)) > 0L) {
            # interactive path
        }
    } else {
        # batch path using nodes
    }
}
```

**Python Equivalent:**

```python
def path_rpart(tree, nodes=_MISSING, pretty=0, print_it=True):
    # ...
    if nodes is _MISSING:
        xy = rpartco(tree)
        # interactive selection loop
    else:
        # batch path using nodes
        pass
```

**Explanation:** The conditional structure translates directly. In Python the interactive branch would use matplotlib or similar tooling to replace R's `identify()`.

---

#### 4.1.4 Absent optional output file — write to stdout instead of a file

**Locations:** `rpart/R/summary.rpart.R` (`summary.rpart`, line 9)

**Original R Context:**

`file` is a character string (a file path). When absent the function writes to the console; when present it redirects output to the file via `sink`.

```r
summary.rpart <- function(object, cp = 0, digits = getOption("digits"), file, ...) {
    if (!missing(file)) {
        sink(file)
        on.exit(sink())
    }
    # ... print output ...
}
```

**Python Equivalent:**

```python
import sys
from contextlib import redirect_stdout

def summary_rpart(object, cp=0, digits=7, file=_MISSING):
    if file is not _MISSING:
        with open(file, "w") as fh, redirect_stdout(fh):
            _summary_rpart_body(object, cp, digits)
    else:
        _summary_rpart_body(object, cp, digits)
```

**Explanation:** R's `sink` redirects all `cat`/`print` output to a file connection. The Python equivalent uses `contextlib.redirect_stdout` combined with a standard `open` context manager to achieve the same effect without modifying internal print calls.

---

#### 4.1.5 Absent parameter triggers auto-derivation of `method` from data type

**Locations:** `rpart/R/rpart.R` (`rpart`, line 35)

**Original R Context:**

`method` is a character string. When absent the function inspects the response variable `Y` to infer the correct method.

```r
rpart <- function(formula, data, ..., method, ...) {
    # ... build Y ...
    if (missing(method)) {
        method <- if (is.factor(Y) || is.character(Y)) "class"
                  else if (inherits(Y, "Surv")) "exp"
                  else if (is.matrix(Y)) "poisson"
                  else "anova"
    }
    # ...
}
```

**Python Equivalent:**

```python
import pandas as pd
import numpy as np

def rpart(formula, data, method=_MISSING, **kwargs):
    # ... build Y ...
    if method is _MISSING:
        if hasattr(Y, "cat") or Y.dtype == object:
            method = "class"
        elif isinstance(Y, SurvivalObject):
            method = "exp"
        elif isinstance(Y, np.ndarray) and Y.ndim == 2:
            method = "poisson"
        else:
            method = "anova"
    # ...
```

**Explanation:** R's `is.factor(Y) || is.character(Y)` maps to checking whether the pandas Series has a categorical dtype or object dtype. `inherits(Y, "Surv")` maps to an `isinstance` check on a Python survival object class. `is.matrix(Y)` maps to checking that the array is two-dimensional.

---

#### 4.1.6 Absent optional list parameter — use computed defaults

**Locations:** `rpart/R/rpart.R` (`rpart`, lines 49, 67); `rpart/R/rpart.class.R` (`rpart.class`, line 11); `rpart/R/rpart.exp.R` (`rpart.exp`, line 109); `rpart/R/rpart.poisson.R` (`rpart.poisson`, line 14)

**Original R Context:**

`parms` is either absent (use computed defaults) or a named list (validate and override). The pattern occurs in all four split-method initialization functions.

```r
rpart.poisson <- function(y, offset, parms, wt) {
    if (missing(parms)) {
        parms <- c(shrink = 1L, method = 1L)
    } else {
        # validate and process parms
    }
}
```

**Python Equivalent:**

```python
def rpart_poisson(y, offset, parms=_MISSING, wt=None):
    if parms is _MISSING:
        parms = {"shrink": 1, "method": 1}
    else:
        parms = dict(parms)
        # validate and process parms
```

**Explanation:** The R named vector `c(shrink=1L, method=1L)` translates to a Python dict. The `missing` check maps directly to the sentinel test. Note that `parms=None` is not used here because `None` is a meaningful value in `rpart.class.R`: `if (missing(parms) || is.null(parms))` treats both absence and `NULL` as equivalent triggers for the default, so the Python version should handle both:

```python
def rpart_class(y, offset, parms=_MISSING, wt=None):
    if parms is _MISSING or parms is None:
        # compute default parms from counts
        pass
    else:
        # validate and process parms
        pass
```

---

#### 4.1.7 Absent cost vector — fill with ones

**Locations:** `rpart/R/rpart.R` (`rpart`, line 139)

**Original R Context:**

`cost` is a numeric vector of length equal to the number of predictor variables. When absent every variable gets weight 1.

```r
if (missing(cost)) cost <- rep(1, nvar)
else {
    if (length(cost) != nvar) stop("Cost vector is the wrong length")
    if (any(cost <= 0)) stop("Cost vector must be positive")
}
```

**Python Equivalent:**

```python
import numpy as np

if cost is _MISSING:
    cost = np.ones(nvar)
else:
    cost = np.asarray(cost, dtype=float)
    if len(cost) != nvar:
        raise ValueError("Cost vector is the wrong length")
    if np.any(cost <= 0):
        raise ValueError("Cost vector must be positive")
```

**Explanation:** R's `rep(1, nvar)` maps to `np.ones(nvar)`. Validation logic translates directly using `np.any`.

---

#### 4.1.8 Absent optional control list — use existing computed controls

**Locations:** `rpart/R/rpart.R` (`rpart`, line 107)

**Original R Context:**

`control` is a named list of control parameters. When absent the function leaves the computed `controls` unchanged; when present it overrides entries.

```r
controls <- rpart.control(...)
if (!missing(control)) {
    if (!all(names(control) %in% names(controls)))
        stop("unknown named elements in 'control'")
    controls <- do.call(rpart.control, control)
}
```

**Python Equivalent:**

```python
controls = rpart_control(**kwargs)
if control is not _MISSING:
    if not all(k in controls for k in control):
        raise ValueError("unknown named elements in 'control'")
    controls = rpart_control(**control)
```

**Explanation:** R's `do.call(rpart.control, control)` is equivalent to Python's `rpart_control(**control)` when `control` is a dict.

---

#### 4.1.9 Absent response variable `y` — suppress saving it in the output

**Locations:** `rpart/R/rpart.R` (`rpart`, line 285)

**Original R Context:**

`y` is a logical argument controlling whether the response vector is stored in the fitted object. When the `model` frame was supplied and `y` was not explicitly given, `y` defaults to `FALSE`.

```r
if (model) {
    ans$model <- m
    if (missing(y)) y <- FALSE
}
if (y) ans$y <- Y
```

**Python Equivalent:**

```python
if model:
    ans["model"] = m
    if y is _MISSING:
        y = False
if y:
    ans["y"] = Y
```

**Explanation:** Direct translation. The sentinel check replaces `missing(y)` before the conditional store.

---

#### 4.1.10 Absent `cp` parameter — derive it from the fitted model's cp table

**Locations:** `rpart/R/xpred.rpart.R` (`xpred.rpart`, line 61); `rpart/R/print.rpart.R` (`print.rpart`, line 6)

**Original R Context:**

In `xpred.rpart`, `cp` is a numeric vector. When absent the function derives geometric-mean cp values from the fitted model's cp table. In `print.rpart`, when `cp` is provided the tree is first pruned.

```r
# xpred.rpart
if (missing(cp)) {
    cp <- fit$cptable[, 1L]
    cp <- sqrt(cp * c(10, cp[-length(cp)]))
    cp[1L] <- (1 + fit$cptable[1L, 1L]) / 2
}

# print.rpart
if (!missing(cp)) x <- prune.rpart(x, cp = cp)
```

**Python Equivalent:**

```python
import numpy as np

# xpred_rpart
if cp is _MISSING:
    cp = fit["cptable"][:, 0]
    cp = np.sqrt(cp * np.concatenate([[10], cp[:-1]]))
    cp[0] = (1 + fit["cptable"][0, 0]) / 2

# print_rpart
if cp is not _MISSING:
    x = prune_rpart(x, cp=cp)
```

**Explanation:** R's 1-based column index `[, 1L]` becomes 0-based `[:, 0]` in NumPy. `c(10, cp[-length(cp)])` — prepend 10 and drop the last element — becomes `np.concatenate([[10], cp[:-1]])`.

---

#### 4.1.11 Absent `title.` — derive title from the response variable name

**Locations:** `rpart/R/post.rpart.R` (`post.rpart`, line 20)

**Original R Context:**

`title.` is a character string. When absent the function extracts the response variable name from the model terms.

```r
if (missing(title.)) {
    temp <- attr(tree$terms, "variables")[2L]
    title(paste("Endpoint =", temp), cex = 0.8)
} else if (nzchar(title.)) title(title., cex = 0.8)
```

**Python Equivalent:**

```python
if title_ is _MISSING:
    temp = tree["terms"].column_names[1]  # second variable is the response
    plt.title(f"Endpoint = {temp}", fontsize=8)
elif title_:
    plt.title(title_, fontsize=8)
```

**Explanation:** R's `attr(tree$terms, "variables")[2L]` extracts the response variable name from the model's term attributes (1-based, index 2 = second element = response). In Python the equivalent depends on how model terms are stored; `column_names[1]` represents a typical 0-based equivalent. The trailing dot in `title.` is replaced with an underscore (`title_`) to comply with Python naming rules. `nzchar(title.)` (non-zero-character string test) maps to Python's truthiness check on a non-empty string.

---

### 4.2 Pattern B — Compound condition: two arguments in a dependency relationship

**Locations:** `rpart/R/labels.rpart.R` (`labels.rpart`, line 19); `rpart/R/rpart.control.R` (`rpart.control`, line 17); `rpart/R/text.rpart.R` (`text.rpart`, line 32)

**Original R Context:**

Two arguments interact. The historical argument (`pretty`) overrides the modern argument (`minlength`) only when `minlength` was not explicitly given. Similarly, `minsplit` is derived from `minbucket` only when `minsplit` was omitted.

```r
# labels.rpart
labels.rpart <- function(object, digits = 4, minlength = 1L, pretty,
                         collapse = TRUE, ...) {
    if (missing(minlength) && !missing(pretty)) {
        minlength <- if (is.null(pretty)) 1L
                     else if (is.logical(pretty)) {
                         if (pretty) 4L else 0L
                     } else 0L
    }
    # ...
}

# rpart.control
rpart.control <- function(minsplit = 20L, minbucket = round(minsplit/3), ...) {
    if (missing(minsplit) && !missing(minbucket)) minsplit <- minbucket * 3L
    # ...
}

# text.rpart
text.rpart <- function(x, ..., pretty = NULL, minlength = 1L, ...) {
    rows <- if (!missing(pretty) && missing(minlength))
                labels(x, pretty = pretty)
            else
                labels(x, minlength = minlength)
}
```

**Python Equivalent:**

```python
_MISSING = object()

# labels_rpart
def labels_rpart(object, digits=4, minlength=_MISSING, pretty=_MISSING,
                 collapse=True, **kwargs):
    if minlength is _MISSING and pretty is not _MISSING:
        if pretty is None:
            minlength = 1
        elif isinstance(pretty, bool):
            minlength = 4 if pretty else 0
        else:
            minlength = 0
    if minlength is _MISSING:
        minlength = 1  # apply the declared default after dependency resolution
    # ...

# rpart_control
def rpart_control(minsplit=_MISSING, minbucket=_MISSING, cp=0.01, ...):
    if minbucket is _MISSING:
        minbucket = round((minsplit if minsplit is not _MISSING else 20) / 3)
    if minsplit is _MISSING and minbucket is not _MISSING:
        minsplit = minbucket * 3
    if minsplit is _MISSING:
        minsplit = 20
    # ...

# text_rpart
def text_rpart(x, splits=True, pretty=_MISSING, minlength=_MISSING, ...):
    if pretty is not _MISSING and minlength is _MISSING:
        rows = labels_rpart(x, pretty=pretty)
    else:
        effective_minlength = 1 if minlength is _MISSING else minlength
        rows = labels_rpart(x, minlength=effective_minlength)
    # ...
```

**Explanation:** The compound `missing(a) && !missing(b)` R test translates to `a is _MISSING and b is not _MISSING`. In Python the default-evaluation order matters: since `minbucket`'s default in R is `round(minsplit/3)` (a dependent default that references `minsplit`), Python cannot express this directly in the function signature. Both parameters must default to `_MISSING` and the dependency is resolved in the function body.

---

### 4.3 Pattern C — Capture missing status before consuming the argument

**Locations:** `rpart/R/predict.rpart.R` (`predict.rpart`, lines 7 and 9)

**Original R Context:**

`type` is a character string that will be passed to `match.arg` (which consumes it and could alter the missing-detection semantic). `newdata` is a data frame used later in two places (lines 9 and 42).

```r
predict.rpart <- function(object, newdata,
                          type = c("vector", "prob", "class", "matrix"),
                          na.action = na.pass, ...) {
    mtype <- missing(type)      # capture BEFORE match.arg consumes it
    type <- match.arg(type)
    where <- if (missing(newdata)) object$where
             else {
                 # ... process newdata and call pred.rpart ...
             }
    # ...
    if (mtype && nclass > 0L) type <- "prob"
    # ...
    if (missing(newdata) && !is.null(object$na.action))  # second test of newdata
        pred <- naresid(object$na.action, pred)
}
```

**Python Equivalent:**

```python
_VALID_TYPES = ("vector", "prob", "class", "matrix")

def predict_rpart(object, newdata=_MISSING,
                  type=_MISSING, na_action=na_pass):
    type_missing = (type is _MISSING)           # capture BEFORE consuming
    if type is _MISSING:
        type = "vector"                          # first element default
    else:
        if type not in _VALID_TYPES:
            raise ValueError(f"'type' must be one of {_VALID_TYPES}")

    if newdata is _MISSING:
        where = object["where"]
    else:
        # process newdata
        where = pred_rpart(object, rpart_matrix(newdata))

    # ...
    if type_missing and nclass > 0:
        type = "prob"
    # ...
    if newdata is _MISSING and object.get("na_action") is not None:
        pred = naresid(object["na_action"], pred)
```

**Explanation:** The saved boolean `type_missing = (type is _MISSING)` is the direct Python counterpart of `mtype <- missing(type)`. Capture must occur before the variable is reassigned. The second `if (missing(newdata) ...)` test on line 42 simply re-evaluates `newdata is _MISSING`, which remains valid because `newdata` is never reassigned in the else branch.

---

### 4.4 Pattern A variant — Absent argument triggers warning, not error or default

**Locations:** `rpart/R/text.rpart.R` (`text.rpart`, line 15); `rpart/R/zzz.R` (`node.match`, line 28)

**Original R Context:**

`label` (deprecated argument): when it is present a warning is emitted. `leaves` (optional filter): when absent, all matching nodes are returned; when present, leaf nodes are filtered out.

```r
# text.rpart
text.rpart <- function(x, splits = TRUE, label, ...) {
    if (!missing(label)) warning("argument 'label' is no longer used")
    # ...
}

# node.match
node.match <- function(nodes, nodelist, leaves, print.it = TRUE) {
    # ...
    if (!missing(leaves) && any(leaves <- leaves[node.index])) {
        warning("supplied nodes are leaves")
        node.index[node.index > 0L][!leaves]
    } else node.index[node.index > 0L]
}
```

**Python Equivalent:**

```python
import warnings

# text_rpart
def text_rpart(x, splits=True, label=_MISSING, **kwargs):
    if label is not _MISSING:
        warnings.warn("argument 'label' is no longer used")
    # ...

# node_match
def node_match(nodes, nodelist, leaves=_MISSING, print_it=True):
    node_index = np.array([np.where(nodelist == n)[0][0]
                           if n in nodelist else 0 for n in nodes])
    bad = nodes[node_index == 0]
    if len(bad) > 0 and print_it:
        warnings.warn(f"supplied nodes {bad} are not in this tree")
    if leaves is not _MISSING:
        leaf_flags = leaves[node_index[node_index > 0] - 1]
        if np.any(leaf_flags):
            warnings.warn("supplied nodes are leaves")
            return node_index[node_index > 0][~leaf_flags]
    return node_index[node_index > 0]
```

**Explanation:** R's `warning()` maps to `warnings.warn()` from Python's standard library. The `!missing(label)` (not-absent) check translates to `label is not _MISSING`. For `node.match`, the `leaves` parameter is a logical vector; when absent all matching non-leaf nodes are returned; when present, leaf nodes are excluded via boolean indexing.
