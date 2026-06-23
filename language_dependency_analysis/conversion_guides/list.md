# Conversion Guide: `list` in R

## 1. Overview of `list` in R

R's `list()` is a fundamental constructor that creates a generic vector capable of holding elements of arbitrary and mixed types. Unlike atomic vectors (which require all elements to share the same type), a list can contain scalars, vectors, matrices, data frames, functions, other lists, `NULL`, environments, and any other R object simultaneously.

**Core functionality:**

- `list()` with no arguments returns an empty list of length 0.
- `list(...)` with `...` passed from a parent function collects caller-supplied named or unnamed arguments into a single list object, preserving their types and names.
- Named elements are created by supplying `name = value` pairs: `list(x = 1, y = "a")`.
- Unnamed elements may be mixed with named ones and are accessed by positional index.
- The resulting object has class `"list"`, supports `$` and `[[` access by name, and `[` access by index.
- Lists are the idiomatic way in R to group heterogeneous objects together — equivalent in spirit to a Python dictionary (when all elements are named) or a tuple/mixed container (when elements are unnamed or mixed).

**Typical inputs:** any R objects — scalars, vectors, matrices, functions, `NULL`, other lists.

**Typical outputs:** a list object whose length equals the number of arguments supplied.

---

## 2. Contextual Usage Analysis

Across the 34 CSV rows drawn from 13 R source files in the rpart package, `list()` is used in six distinct patterns:

**Pattern A — Empty list initialization (`list()`).**
Used in `path.rpart.R` (line 12) to create a mutable, growable container that is populated incrementally inside a loop by assigning to `path[[key]]`. In Python this maps to an empty `dict` (when keys are strings) or an empty `list` (when numeric indices are used).

**Pattern B — Capturing variadic arguments (`list(...)`).**
Used in `plotcp.R` (line 6) and `rpart.R` (line 94). The pattern `dots <- list(...)` or `extraArgs <- list(...)` captures all `...` arguments passed to the enclosing function so they can be inspected, subsetted, or forwarded. The captured object is an ordinary named list. In Python the equivalent is `**kwargs` (a `dict`).

**Pattern C — Named property-bag / configuration struct.**
The most common pattern. A `list(name1 = val1, name2 = val2, ...)` is returned or assigned to collect several related scalar or vector values under named keys. Examples span:
- Coordinate pairs: `list(x = x, y = y)` in `meanvar.rpart.R`, `plot.rpart.R`, `rpartco.R`, `rpart.branch.R`.
- Control parameters: `list(minsplit = minsplit, ..., xval = xval)` in `rpart.control.R`.
- Plotting parameters: `list(uniform = uniform, branch = branch, nspace = nspace, minbranch = minbranch)` in `plot.rpart.R`.
- Callback state: `list(expr1 = expr1, expr2 = expr2, rho = rho)` in `rpartcallback.R`.
- Bounding box: `list(columns = columns, rows = rows)` in `zzz.R`.
- Cross-validation context: `list(numresp = numresp, numy = numy, parms = parms)` in `xpred.rpart.R`.

**Pattern D — Method initialization return value (mixed scalars, vectors, and embedded functions).**
Functions such as `rpart.anova`, `rpart.class`, `rpart.exp`, `rpart.poisson` return a single `list` that bundles numeric scalars, numeric vectors, matrices, character vectors, and anonymous functions together. The consumer (the `rpart` main function) accesses members by name (e.g., `init$y`, `init$parms`, `init$summary`). This is idiomatic R for returning multiple values of mixed types from a function. In Python, a `dict` or a `dataclasses.dataclass` is the closest equivalent; when anonymous callables must be stored as values, `dict` with `lambda` or named function references is used.

**Pattern E — `dimnames` list (mixed `NULL` and vector).**
`list(names(where), NULL)` and `list(names(where), ylevels)` in `predict.rpart.R`, and `list(NULL, format(cp), rownames(X))` and `list(rownames(X), format(cp))` in `xpred.rpart.R`, produce two- or three-element lists that are assigned to the `dimnames` attribute of a matrix. Elements may be `NULL` (meaning no labels for that dimension) or a character vector. In Python, `numpy` uses a tuple of arrays or `None` values for axis labels; `pandas` uses `Index` objects attached to `DataFrame` or `Series`.

**Pattern F — Default `parms` construction.**
`list(prior = counts/sum(counts), loss = matrix(...), split = 1)` in `rpart.class.R` builds a named list with heterogeneous element types (numeric vector, matrix, scalar integer) representing method parameters. The same pattern with two numeric scalars appears in other init functions.

**Pattern G — Incremental `functions` list assembly in `rpart.R`.**
Lines 263–265 build a `functions` list starting from `list(summary = ...)`, optionally extending it with `list(print = ...)` and `list(text = ...)` via `c(functions, list(...))`. This is the R idiom for conditionally appending named entries to a list. In Python the equivalent is dict merging with `|` (Python 3.9+) or `{**d1, **d2}`.

**Pattern H — `do.call` argument list.**
Line 20 of `plotcp.R` wraps arguments in `list(ns, xerror, axes = FALSE, ...)` as the argument list for `do.call(plot, ...)`. In Python, `**kwargs` dicts passed to function calls serve the same role.

**Data types involved:** numeric scalars, integer scalars, numeric vectors, integer vectors, character vectors, logical scalars, matrices (`matrix`), `NULL`, R environments, and R functions (closures). The resulting lists are heterogeneous in all cases.

---

## 3. Python Conversion Strategy

The primary Python equivalent of R's `list()` is the built-in **`dict`** when all (or most) elements are named, and a plain Python **`list`** when elements are positional and unnamed.

**Rationale for this choice:**

- R lists with named elements (`list(x = 1, y = 2)`) behave as dictionaries: elements are retrieved by string key. Python `dict` replicates this exactly with `{"x": 1, "y": 2}`.
- R lists used as `dimnames` (containing `None`/character vectors by position) map to Python `list` or `tuple`, since the positions carry meaning.
- R `list()` used to capture `...` maps to `**kwargs` (a `dict`) in Python function signatures.
- When a list is returned from a function to group multiple return values, Python idiomatically uses either `dict`, a named `tuple` (`collections.namedtuple`), or a `dataclasses.dataclass`. For the rpart init-return pattern (which includes callable values), `dict` is the most flexible and direct equivalent.
- `numpy` and `pandas` are relevant only when list elements are numeric arrays being assigned as `dimnames` to matrices. In those cases, the list wrapping is dissolved into pandas `Index` objects or numpy array `shape`/`dtype` attributes.

No single external library is universally required. The conversions rely on Python built-ins (`dict`, `list`, `tuple`) and, for the `dimnames` pattern, `numpy` or `pandas`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Empty List Initialization (Pattern A)

**Locations:** `path.rpart.R`, `path.rpart`, line 12.

**Original R Context:**

```r
# path is an empty list; string keys are added dynamically in a loop
path <- list()
# ...
path[[n[i]]] <- splits[which[, i]]
```

- Input: none.
- Output: a zero-length list that grows by assignment into named or positional slots.

**Python Equivalent:**

```python
# Use an empty dict when keys are strings (node names)
path = {}
# ...
path[n[i]] = splits[which[:, i]]
```

**Explanation:** R `list()` returns a zero-length, growable container. When elements will be assigned by string key (node names are character strings in R), the direct Python equivalent is an empty `dict`. If elements would be assigned by integer index only, use `[]` (empty `list`).

---

### 4.2 Capturing Variadic Arguments (Pattern B)

**Locations:** `plotcp.R`, `plotcp`, line 6; `rpart.R`, `rpart`, line 94.

**Original R Context:**

```r
# Capture all ... args into a named list for later inspection/subsetting
dots <- list(...)
# Check membership and use a field
if (! "ylim" %in% names(dots))
    dots$ylim <- c(min(xerror - xstd) - 0.1, max(xerror + xstd) + 0.1)

# Separately, capture and validate extra args against legal names
extraArgs <- list(...)
if (length(extraArgs)) {
    controlargs <- names(formals(rpart.control))
    indx <- match(names(extraArgs), controlargs, nomatch = 0L)
    ...
}
```

- Input: variadic R arguments (`...`), which may be named or unnamed.
- Output: a named list (dict-like).

**Python Equivalent:**

```python
import numpy as np

def plotcp(x, minline=True, lty=3, col=1, upper="size", **kwargs):
    # kwargs is already a dict; check for a key and set default if absent
    if "ylim" not in kwargs:
        kwargs["ylim"] = (np.min(xerror - xstd) - 0.1, np.max(xerror + xstd) + 0.1)

def rpart(formula, data, ..., **extra_args):
    # Validate that only legal rpart.control argument names were supplied
    control_args = set(inspect.signature(rpart_control).parameters.keys())
    invalid = set(extra_args) - control_args
    if invalid:
        raise ValueError(f"Argument {invalid} not matched")
```

**Explanation:** R's `list(...)` inside a function body collects all `...` arguments into a named list. Python uses `**kwargs` in the function signature to achieve the same result — it is already a `dict`. Membership checks like `"ylim" %in% names(dots)` become `"ylim" in kwargs`. Argument validation uses `set` operations on `kwargs` keys.

---

### 4.3 Named Coordinate / Configuration Property-Bag (Pattern C)

**Locations:**
- `meanvar.rpart.R`, `meanvar.rpart`, line 15
- `plot.rpart.R`, `plot.rpart`, lines 12 and 33
- `rpart.branch.R`, `rpart.branch`, line 25
- `rpartco.R`, `compress`, lines 93, 101, 132; `rpartco`, lines 64 and 138
- `rpartcallback.R`, `rpartcallback`, line 111
- `rpart.control.R`, `rpart.control`, line 30
- `zzz.R`, `string.bounding.box`, line 16

**Original R Context:**

```r
# Coordinate pair returned from a plotting function
invisible(list(x = x, y = y, label = label))

# Plotting control parameters
parms <- list(uniform = uniform, branch = branch, nspace = nspace,
              minbranch = minbranch)

# Recursive tree compression state
list(left = x[lson], right = x[lson], depth = depth + 1L, sons = lson)

# Control parameter struct
list(minsplit = minsplit, minbucket = minbucket, cp = cp,
     maxcompete = maxcompete, maxsurrogate = maxsurrogate,
     usesurrogate = usesurrogate,
     surrogatestyle = surrogatestyle, maxdepth = maxdepth, xval = xval)

# Callback state
list(expr1 = expr1, expr2 = expr2, rho = rho)

# Bounding box
list(columns = columns, rows = rows)
```

- Input: mix of scalars (numeric, integer, logical), numeric vectors, and other objects.
- Output: a named list used as a structured record.

**Python Equivalent:**

```python
import numpy as np

# Coordinate pair
def meanvar_rpart(tree, xlab="ave(y)", ylab="ave(deviance)"):
    # ... compute x, y, label as numpy arrays ...
    return {"x": x, "y": y, "label": label}

# Plotting control parameters
parms = {
    "uniform": uniform,
    "branch": branch,
    "nspace": nspace,
    "minbranch": minbranch,
}

# Recursive tree compression state (returned from inner function)
def compress(x, me, depth):
    lson = me + 1
    if is_leaf[lson]:
        left = {"left": x[lson], "right": x[lson], "depth": depth + 1, "sons": np.array([lson])}
    # ...
    return {
        "x": x,
        "left": np.concatenate([[x[me] - nspace * (x[me] - x[lson])], templ]),
        "right": np.concatenate([[x[me] - nspace * (x[me] - x[rson])], tempr]),
        "depth": maxd + depth,
        "sons": np.concatenate([[me], left["sons"], right["sons"]]),
    }

# Control parameter struct
def rpart_control(minsplit=20, minbucket=None, cp=0.01, maxcompete=4,
                  maxsurrogate=5, usesurrogate=2, xval=10,
                  surrogatestyle=0, maxdepth=30):
    if minbucket is None:
        minbucket = round(minsplit / 3)
    return {
        "minsplit": minsplit, "minbucket": minbucket, "cp": cp,
        "maxcompete": maxcompete, "maxsurrogate": maxsurrogate,
        "usesurrogate": usesurrogate, "surrogatestyle": surrogatestyle,
        "maxdepth": maxdepth, "xval": xval,
    }

# Callback state
result = {"expr1": expr1, "expr2": expr2, "rho": rho}

# Bounding box
return {"columns": columns, "rows": rows}
```

**Explanation:** Every R `list(name = val, ...)` with exclusively named elements maps directly to a Python `dict` literal `{"name": val, ...}`. Access syntax changes from `parms$branch` or `parms[["branch"]]` in R to `parms["branch"]` or `parms.get("branch")` in Python. For numeric vector fields (`x`, `y`, `left`, `right`, `sons`), the values are `numpy` arrays rather than R numeric vectors — the container (`dict`) stays the same but the stored values use numpy.

---

### 4.4 `do.call` Argument List (Pattern H)

**Locations:** `plotcp.R`, `plotcp`, line 20.

**Original R Context:**

```r
# Build an argument list and pass it to plot() via do.call
dots <- list(...)
do.call(plot, c(list(ns, xerror, axes = FALSE, xlab = "cp",
                     ylab = "X-val Relative Error", type = "o"), dots))
```

- Input: positional args (`ns`, `xerror`), keyword args, and a merged extras dict.
- Output: the list is consumed by `do.call` as function arguments; no standalone use.

**Python Equivalent:**

```python
import matplotlib.pyplot as plt

# Merge fixed keyword args with caller-supplied kwargs
fixed_kwargs = {"axes": False, "xlab": "cp", "ylab": "X-val Relative Error", "type": "o"}
merged_kwargs = {**fixed_kwargs, **kwargs}   # kwargs from **kwargs in function signature

# Call the equivalent plotting function
plt.plot(ns, xerror, **merged_kwargs)
```

**Explanation:** R's `do.call(f, c(list(pos1, pos2, kw=val), dots))` merges positional arguments, keyword arguments, and an extras list into a single call. In Python, positional args are passed directly and keyword args are merged with `{**dict1, **dict2}` syntax. The `list()` wrapper used to build the argument collection dissolves entirely — its role is replaced by the `**` unpacking mechanism.

---

### 4.5 Method Initialization Return Value with Embedded Functions (Pattern D)

**Locations:**
- `rpart.anova.R`, `rpart.anova`, line 4
- `rpart.class.R`, `rpart.class`, line 55
- `rpart.exp.R`, `rpart.exp`, line 130
- `rpart.poisson.R`, `rpart.poisson`, line 37

**Original R Context:**

```r
# rpart.anova: returns y (numeric vector), NULL parms, scalars, and two closures
list(y = y, parms = NULL, numresp = 1L, numy = 1L,
     summary = function(yval, dev, wt, ylevel, digits) { ... },
     text    = function(yval, dev, wt, ylevel, digits, n, use.n) { ... })

# rpart.class: returns y (integer vector), parms (named list), scalars,
#              character vector, counts vector, and three closures
list(y = y, parms = parms, numresp = numclass + 2L, counts = counts,
     ylevels = levels(fy), numy = 1L,
     print   = function(...) { ... },
     summary = function(...) { ... },
     text    = function(...) { ... })

# rpart.exp / rpart.poisson: returns a 2-column matrix y, numeric parms,
#                             scalars, and two closures
list(y = cbind(newy, y[, 2L]), parms = parms, numresp = 2L, numy = 2L,
     summary = function(...) { ... },
     text    = function(...) { ... })
```

- Input: computed R objects of mixed types, including anonymous functions.
- Output: a heterogeneous named list — the central "init" object consumed by `rpart()`.
- Consumer accesses: `init$y`, `init$parms`, `init$numresp`, `init$numy`, `init$summary`, `init$print`, `init$text`, `init$counts`, `init$ylevels`.

**Python Equivalent:**

```python
import numpy as np

# rpart.anova equivalent
def rpart_anova(y, offset, parms, wt):
    if offset is not None:
        y = y - offset

    def summary_fn(yval, dev, wt, ylevel, digits):
        return f"  mean={yval:.{digits}g}, MSE={dev/wt:.{digits}g}"

    def text_fn(yval, dev, wt, ylevel, digits, n, use_n):
        return f"{yval:.{digits}g}\nn={n}" if use_n else f"{yval:.{digits}g}"

    return {
        "y": y,
        "parms": None,
        "numresp": 1,
        "numy": 1,
        "summary": summary_fn,
        "text": text_fn,
    }

# rpart.class equivalent (abbreviated)
def rpart_class(y, offset, parms, wt):
    # ... validation and parms setup ...
    return {
        "y": y,            # numpy int array
        "parms": parms,    # dict with "prior", "loss", "split"
        "numresp": numclass + 2,
        "counts": counts,  # numpy array
        "ylevels": ylevels,  # list of strings
        "numy": 1,
        "print": print_fn,
        "summary": summary_fn,
        "text": text_fn,
    }

# rpart.exp / rpart.poisson equivalent (abbreviated)
def rpart_exp(y, offset, parms, wt):
    # ... compute newy ...
    return {
        "y": np.column_stack([newy, y[:, 1]]),  # 2-column numpy array
        "parms": parms,                          # numpy array or dict
        "numresp": 2,
        "numy": 2,
        "summary": summary_fn,
        "text": text_fn,
    }
```

**Explanation:** R's ability to store functions inside a list is replicated in Python by storing callable objects (`lambda` or named functions) as `dict` values. The caller accesses `init["summary"]` and calls it as `init["summary"](...)` instead of R's `init$summary(...)`. For the `y` field, R's `cbind(newy, y[, 2L])` becomes `np.column_stack([newy, y[:, 1]])` — a 2-column `numpy` array. The `parms` field, a named numeric vector in R, becomes either a `numpy` array (for numeric-only parms) or a `dict` (when parms have named fields).

An alternative to `dict` for the init return value is `dataclasses.dataclass`, which enforces a fixed schema and allows attribute-style access (`init.summary` instead of `init["summary"]`):

```python
from dataclasses import dataclass, field
from typing import Callable, Optional
import numpy as np

@dataclass
class RpartInit:
    y: np.ndarray
    parms: Optional[dict]
    numresp: int
    numy: int
    summary: Callable
    text: Callable
    print: Optional[Callable] = None
    counts: Optional[np.ndarray] = None
    ylevels: Optional[list] = None
```

---

### 4.6 Default `parms` Named List Construction (Pattern F)

**Locations:** `rpart.class.R`, `rpart.class`, lines 12 and 51.

**Original R Context:**

```r
# Default parms: prior (numeric vector), loss (matrix), split (integer scalar)
parms <- list(prior = counts / sum(counts),
              loss  = matrix(rep(1, numclass^2) - diag(numclass), numclass),
              split = 1)

# After validation, rebuild parms from temp, temp2, temp3
parms <- list(prior = temp, loss = matrix(temp2, numclass), split = temp3)
```

- Input: `prior` is a numeric vector (class proportions), `loss` is a square matrix, `split` is an integer (1 = Gini, 2 = information gain).
- Output: a named list used as the `parms` argument to C code via `unlist(parms)`.

**Python Equivalent:**

```python
import numpy as np

# Default parms
parms = {
    "prior": counts / counts.sum(),              # 1-D numpy array
    "loss": np.ones((numclass, numclass)) - np.eye(numclass),  # 2-D numpy array
    "split": 1,                                  # int scalar
}

# After validation
parms = {
    "prior": temp,                       # 1-D numpy array
    "loss": np.array(temp2).reshape(numclass, numclass),
    "split": int(temp3),
}
```

**Explanation:** R `matrix(rep(1, numclass^2) - diag(numclass), numclass)` produces a `numclass x numclass` matrix with zeros on the diagonal and ones elsewhere. The Python equivalent is `np.ones((numclass, numclass)) - np.eye(numclass)`. The containing `list()` becomes a `dict`. When this `parms` dict is later passed to C code in the Python translation (replacing R's `as.double(unlist(parms))`), its numeric values are flattened with `np.concatenate([np.atleast_1d(np.ravel(v)) for v in parms.values() if v is not None]).astype(np.float64)`.

---

### 4.7 `dimnames` List for Matrix Labeling (Pattern E)

**Locations:**
- `predict.rpart.R`, `predict.rpart`, lines 29 and 37
- `xpred.rpart.R`, `xpred.rpart`, lines 138 and 142

**Original R Context:**

```r
# Assign row and column names to a matrix slice
dimnames(pred) <- list(names(where), NULL)      # rows labeled, cols unlabeled
dimnames(pred) <- list(names(where), ylevels)   # both labeled

# 3-D array dimnames
dimnames(temp) <- list(NULL, format(cp), rownames(X))

# 2-D matrix dimnames
dimnames(result) <- list(rownames(X), format(cp))
```

- Input: character vectors or `NULL`.
- Output: a list of length equal to the number of dimensions; each element is either `NULL` (no label) or a character vector of labels.

**Python Equivalent (numpy):**

```python
import numpy as np
import pandas as pd

# list(names(where), NULL) -> pandas DataFrame with only row index
pred_df = pd.DataFrame(pred_array, index=list(where.keys()))

# list(names(where), ylevels) -> pandas DataFrame with row and column labels
pred_df = pd.DataFrame(pred_array, index=list(where.keys()), columns=ylevels)

# 3-D array: numpy does not natively label axes; use xarray or just track separately
# list(NULL, format(cp), rownames(X)) equivalent in plain numpy:
#   axis 0 has no labels; axis 1 labels are format(cp); axis 2 labels are rownames(X)
# With pandas for 2-D slices:
result_df = pd.DataFrame(pred_array, index=row_names, columns=cp_labels)
```

**Explanation:** R's `dimnames` is a list where each position corresponds to one dimension of the array. `NULL` at a position means that dimension has no labels. In Python, `numpy` arrays do not carry axis labels natively. The standard approach is to convert to `pandas.DataFrame` (for 2-D data), which stores row labels as `index` and column labels as `columns`. For 3-D arrays, either use `xarray.DataArray` (which supports named, labeled dimensions) or store the label lists separately as Python `list` objects and apply them when constructing the final output DataFrame.

The R `list(NULL, format(cp), rownames(X))` itself — a positional list with `NULL` as one element — translates to a plain Python `list`: `[None, cp_labels, row_names]` where `cp_labels` and `row_names` are Python lists of strings.

---

### 4.8 Incremental Named List Assembly via `c()` (Pattern G)

**Locations:** `rpart.R`, `rpart`, lines 263–265.

**Original R Context:**

```r
# Build functions list conditionally, starting from a required entry
functions <- if (is.null(init$print)) list(summary = init$summary)
             else list(summary = init$summary, print = init$print)
if (!is.null(init$text)) functions <- c(functions, list(text = init$text))
if (method == "user")    functions <- c(functions, mlist)
```

- Input: callable R functions retrieved from the init object.
- Output: a named list that may contain `summary`, optionally `print`, and optionally `text` keys, plus any user-supplied method list.

**Python Equivalent:**

```python
# Build functions dict conditionally
if init.get("print") is None:
    functions = {"summary": init["summary"]}
else:
    functions = {"summary": init["summary"], "print": init["print"]}

if init.get("text") is not None:
    functions["text"] = init["text"]     # in-place update

if method == "user":
    functions = {**functions, **mlist}   # merge with user-supplied method dict
```

**Explanation:** R's `c(list1, list2)` merges two named lists into one. The Python equivalent for dicts is `{**d1, **d2}` (Python 3.5+) or `d1 | d2` (Python 3.9+). In-place addition of a single key is simply `functions["text"] = init["text"]`, which is more direct than R's `c(functions, list(text = init$text))`. The `is.null` checks become `is None` checks on dict `.get()` calls.

---

### 4.9 Single-Field Extraction from Inline `list(...)` (Pattern — `text.rpart.R`)

**Locations:** `text.rpart.R`, `text.rpart`, line 20.

**Original R Context:**

```r
# list(...) is constructed immediately to extract one field; the list is not stored
cxy <- par("cxy")
if (!is.null(srt <- list(...)$srt) && srt == 90) cxy <- rev(cxy)
```

- Input: `...` variadic arguments, one of which may be named `srt`.
- Output: the constructed list is used only to check and retrieve `srt`; the list itself is discarded.

**Python Equivalent:**

```python
cxy = get_par("cxy")   # equivalent to par("cxy") in R

# kwargs is the **kwargs dict in the function signature
srt = kwargs.get("srt")
if srt is not None and srt == 90:
    cxy = cxy[::-1]    # reverse, equivalent to rev(cxy)
```

**Explanation:** In R, `list(...)$srt` is a concise way to extract a named field from variadic arguments without declaring them explicitly. In Python, `**kwargs` is already a `dict`, so `kwargs.get("srt")` retrieves the value (returning `None` if absent, which replaces the `is.null` guard). The `list()` wrapper is not needed at all.

---

### 4.10 `rpart` Main Result Object (Pattern C — large named list)

**Locations:** `rpart.R`, `rpart`, line 271.

**Original R Context:**

```r
ans <- list(frame = frame,
            where = where,
            call = Call, terms = Terms,
            cptable = t(rpfit$cptable),
            method = method,
            parms = init$parms,
            control = controls,
            functions = functions,
            numresp = init$numresp)
```

- Input: data frame (`frame`), integer vector (`where`), R call object (`Call`), terms object (`Terms`), transposed matrix (`cptable`), string scalar (`method`), list (`parms`), list (`controls`), list (`functions`), integer scalar (`numresp`).
- Output: the primary `rpart` S3 object returned to the user.

**Python Equivalent:**

```python
import numpy as np

ans = {
    "frame": frame,            # pandas DataFrame
    "where": where,            # numpy int array or dict
    "call": call_str,          # string representation (no direct R equivalent)
    "terms": terms,            # custom object or dict describing the formula
    "cptable": cptable.T,      # transposed numpy 2-D array
    "method": method,          # str
    "parms": init_parms,       # dict or numpy array
    "control": controls,       # dict
    "functions": functions,    # dict of callables
    "numresp": int(init_numresp),
}
```

**Explanation:** The large named list that R uses as the S3 object result is represented in Python as a `dict`. Attributes added later (e.g., `attr(ans, "xlevels") <- xlevels`) become additional keys in the dict or attributes on a wrapper class. If a class-based approach is preferred, a `dataclasses.dataclass` named `RPart` with typed fields provides attribute access (`ans.frame`, `ans.cptable`) and is more robust for a full library translation.
