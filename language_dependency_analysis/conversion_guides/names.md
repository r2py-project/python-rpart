# Conversion Guide: `names` in R

## 1. Overview of `names` in R

`names()` is a base R function that serves a dual role:

- **Getter:** `names(x)` returns a character vector containing the names (labels) of the elements of `x`. If `x` has no names attribute, it returns `NULL`.
- **Setter:** `names(x) <- value` assigns a character vector of element names to `x`, modifying `x` in place by attaching or replacing its `names` attribute.

`x` may be an atomic vector, a list, a named numeric vector, a data frame column, or virtually any R object that can carry a `names` attribute. The return value of the getter form is always a `character` vector (or `NULL`), one element per element of `x`.

In the rpart codebase the two roles appear everywhere:

- **Reading names** — to test whether a name is present (`"ylim" %in% names(dots)`), to subset by name, to reorder or reindex by name, or to propagate names into downstream objects.
- **Writing names** — to attach row-identifier strings or matched argument names to a newly-created vector so that downstream code can look values up by name.

---

## 2. Contextual Usage Analysis

The CSV covers six distinct R files. Across all usages two structural patterns dominate:

### Pattern A — getter: interrogating or reading names
`names(x)` is called on lists, named vectors, data frame columns, or formal-argument lists in order to:

- Check membership: `"ylim" %in% names(dots)` (plotcp.R:18)
- Obtain legal argument names: `names(formals(rpart.control))` (rpart.R:96)
- Retrieve keys for matching: `names(extraArgs)` (rpart.R:97, 100), `names(control)` / `names(controls)` (rpart.R:108)
- Retrieve keys stored in a named parameter list: `names(parms)` (rpart.class.R:17–22, rpart.exp.R:112–118, rpart.poisson.R:17–23)
- Retrieve column names of a data frame: `names(frame)` (text.rpart.R:16)
- Retrieve names of a named list (`fit$call`): `names(fit$call)` (xpred.rpart.R:22)
- Subset a named vector or list by matching: `names(xlevels)` (rpart.R:87, xpred.rpart.R:55–56)

The objects involved are either:
- Named **lists** (e.g., `dots`, `parms`, `extraArgs`, `control`, `fit$call`)
- Named **vectors** (e.g., `where`, `temp`, `resid`, `pred`, `xlevels`)
- **Data frames** (e.g., `frame`), where `names()` returns column names

### Pattern B — setter: assigning names to an output vector
`names(x) <- value` assigns the names of one vector to another, propagating row-label or element-label information:

- `names(temp) <- rownames(x)` (pred.rpart.R:29) — attach row identifiers to a C-returned integer vector
- `names(pred) <- names(where)` (predict.rpart.R:26, 34) — propagate observation labels from `where` to predictions
- `names(resid) <- names(y)` (residuals.rpart.R:45) — propagate observation labels from the response to residuals
- `names(where) <- row.names(m)` (rpart.R:269) — attach model-frame row names to the node-assignment vector
- `names(parms)[indx == 0L]` used as a getter inside an error message (rpart.exp.R:117, rpart.poisson.R:22)
- `names(parms) <- parmsNames[indx]` (rpart.exp.R:118, rpart.poisson.R:23) — rename matched parameter keys

---

## 3. Python Conversion Strategy

Python does not have a single built-in equivalent to R's `names()` because the same concept is scattered across different data structures:

| R structure | Python equivalent | Names mechanism |
|---|---|---|
| Named vector / named list | `dict` or `pandas.Series` | dict keys / `Series.index` |
| Named list (mixed types) | `dict` | dict keys via `dict.keys()` |
| Data frame | `pandas.DataFrame` | column labels via `df.columns` |
| Integer/double vector returned from C | `numpy.ndarray` or `pandas.Series` | `Series.index` |

**Primary strategy:** Use `pandas.Series` for numeric vectors that need named access (replacing R's named vectors), and plain Python `dict` or `dict.keys()` for R named lists. Use `pandas.DataFrame.columns` for data frame column names. `numpy.ndarray` is used for pure computation but does not support named axes, so whenever names must be preserved on a numeric result, wrap in a `pandas.Series`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Getter on a named list — checking key membership

**Locations:** `plotcp.R` → `plotcp` (line 18)

**Original R Context:**
```r
# dots is a list built from ...
dots <- list(...)
if (! "ylim" %in% names(dots))
    dots$ylim <- c(...)
```
`names(dots)` returns a `character` vector of the list's keys. The result is tested with `%in%`.

**Python Equivalent:**
```python
# dots is a plain Python dict built from **kwargs
dots = dict(**kwargs)
if "ylim" not in dots:
    dots["ylim"] = (...)
```

**Explanation:** Python `dict` keys play the same role as R list names. Membership testing with the `in` operator on a dict checks keys directly, so `names(dots)` maps to the implicit key set of the dict (no explicit call needed). The assignment `dots$ylim <- ...` maps to `dots["ylim"] = ...`.

---

### 4.2 Setter — attaching row identifiers to a C-returned vector

**Locations:** `pred.rpart.R` → `pred.rpart` (line 29)

**Original R Context:**
```r
# temp is an integer vector returned from .Call(C_pred_rpart, ...)
# rownames(x) is a character vector of the same length
temp <- .Call(C_pred_rpart, ...)
names(temp) <- rownames(x)
```
`temp` is an unlabeled numeric/integer vector; after assignment it becomes a named vector so callers can look values up by row name.

**Python Equivalent:**
```python
import pandas as pd

# temp is a numpy array or list returned from the C extension
# row_names is a list/array of string row identifiers matching len(temp)
temp = c_pred_rpart(...)          # returns numpy array or list
temp = pd.Series(temp, index=row_names)
```

**Explanation:** `pandas.Series` carries an explicit `index` that is the direct analogue of R's `names` attribute on a vector. Constructing `pd.Series(data, index=labels)` is equivalent to the two-step R pattern of creating a vector and then assigning `names()`.

---

### 4.3 Setter — propagating observation labels from one vector to another

**Locations:** `predict.rpart.R` → `predict.rpart` (lines 26, 34); `residuals.rpart.R` → `residuals.rpart` (line 45)

**Original R Context:**
```r
# where is a named integer vector: node assignments keyed by observation id
# pred / resid is an unlabeled result vector of the same length
pred <- frame$yval[where]
names(pred) <- names(where)

resid <- ...computed result...
names(resid) <- names(y)
```
The pattern copies the `names` of a source vector onto a newly-created result vector of identical length.

**Python Equivalent:**
```python
import pandas as pd

# where is a pd.Series with observation-id index
# pred / resid is a numpy array or raw list of the same length
pred = frame_yval.iloc[where.values - 1]   # R is 1-indexed; adapt as needed
pred = pd.Series(pred.values, index=where.index)

# residuals case
resid = pd.Series(resid_values, index=y.index)
```

**Explanation:** When `where` is stored as a `pd.Series`, its `.index` directly holds the observation labels. Constructing a new `pd.Series` with that same `.index` replicates `names(pred) <- names(where)`. For `names(resid) <- names(y)`, the same approach applies using `y.index`.

---

### 4.4 Setter — attaching model-frame row names to the node-assignment vector

**Locations:** `rpart.R` → `rpart` (line 269)

**Original R Context:**
```r
where <- rpfit$which    # integer vector, node assignment per observation
names(where) <- row.names(m)   # m is the model.frame; row.names gives obs ids
```

**Python Equivalent:**
```python
import pandas as pd

# where is the raw node-assignment array from the C call
# m is a pandas DataFrame; m.index holds the row identifiers
where = pd.Series(rpfit_which, index=m.index)
```

**Explanation:** `row.names(m)` in R is equivalent to `m.index` on a `pandas.DataFrame`. Wrapping the raw integer array as a `pd.Series` indexed by `m.index` accomplishes the same naming in one step instead of two.

---

### 4.5 Getter — obtaining legal argument names from a function signature

**Locations:** `rpart.R` → `rpart` (line 96)

**Original R Context:**
```r
controlargs <- names(formals(rpart.control))   # character vector of param names
indx <- match(names(extraArgs), controlargs, nomatch = 0L)
if (any(indx == 0L))
    stop(...)
```
`formals(f)` returns a named list of default values; `names()` extracts the parameter names.

**Python Equivalent:**
```python
import inspect

def rpart(formula, data, ..., control=None, **extra_args):
    control_params = set(inspect.signature(rpart_control).parameters.keys())
    unmatched = [k for k in extra_args if k not in control_params]
    if unmatched:
        raise ValueError(f"Argument {unmatched[0]} not matched")
```

**Explanation:** Python's `inspect.signature(func).parameters` returns an `OrderedDict` of parameter names, which is the structural equivalent of `formals(f)`. Using `.keys()` on it mirrors `names(formals(f))`. Membership testing with `in` replaces R's `match(..., nomatch = 0L)` pattern.

---

### 4.6 Getter — reading and matching keys of a named argument list

**Locations:** `rpart.R` → `rpart` (lines 97, 100, 108); `xpred.rpart.R` → `xpred.rpart` (line 22)

**Original R Context:**
```r
extraArgs <- list(...)
indx <- match(names(extraArgs), controlargs, nomatch = 0L)
if (any(indx == 0L))
    stop(gettextf("Argument %s not matched",
                  names(extraArgs)[indx == 0L]))

# xpred.rpart.R line 22:
m <- fit$call[match(c("", "formula", ...), names(fit$call), 0L)]
```
`names()` on a list returns its key strings for use in matching/filtering.

**Python Equivalent:**
```python
# extra_args is a dict from **kwargs
extra_args = kwargs
control_params = set(rpart_control_params)   # set of legal param names

unmatched_keys = [k for k in extra_args if k not in control_params]
if unmatched_keys:
    raise ValueError(f"Argument {unmatched_keys[0]} not matched")

# xpred.rpart equivalent: filter call dict by key membership
wanted = {"", "formula", "data", "weights", "subset", "na.action"}
m = {k: v for k, v in fit_call.items() if k in wanted}
```

**Explanation:** Python dict keys replace R list names. Iteration over `dict.keys()` and set membership testing replace `names(list)` combined with `match()`. The `xpred.rpart` usage — subsetting a named list by matching a set of target keys — maps directly to a dict comprehension.

---

### 4.7 Getter — checking and renaming keys of a named parameter list

**Locations:** `rpart.class.R` → `rpart.class` (lines 17–22); `rpart.exp.R` → `rpart.exp` (lines 112–118); `rpart.poisson.R` → `rpart.poisson` (lines 17–23)

**Original R Context (rpart.class.R):**
```r
parms <- list(prior = ..., loss = ..., split = ...)   # or user-supplied
if (is.null(names(parms))) stop("The parms list must have names")
temp <- pmatch(names(parms), c("prior", "loss", "split"), 0L)
if (any(temp == 0L))
    stop(gettextf("'parms' component not matched: %s",
                  names(parms)[temp == 0L]))
names(parms) <- c("prior", "loss", "split")[temp]
```

**Original R Context (rpart.exp.R / rpart.poisson.R):**
```r
parms <- as.list(parms)
if (is.null(names(parms))) stop("You must input a named list for parms")
parmsNames <- c("method", "shrink")
indx <- pmatch(names(parms), parmsNames, 0L)
if (any(indx == 0L))
    stop(gettextf("'parms' component not matched: %s",
                  names(parms)[indx == 0L]))
else names(parms) <- parmsNames[indx]
```

In both cases `names(parms)` reads the current keys of a dict-like list, validates them by partial matching against a set of legal keys, and then overwrites the keys with the canonical (fully-spelled-out) versions.

**Python Equivalent:**
```python
# rpart.class equivalent
def _validate_parms_class(parms: dict) -> dict:
    legal = ["prior", "loss", "split"]
    if parms is None or len(parms) == 0:
        return {}
    keys = list(parms.keys())
    resolved = {}
    for k in keys:
        # partial match: find unique legal key that starts with k
        matches = [l for l in legal if l.startswith(k)]
        if len(matches) != 1:
            raise ValueError(f"'parms' component not matched: {k}")
        resolved[matches[0]] = parms[k]
    return resolved

# rpart.exp / rpart.poisson equivalent
def _validate_parms_exp(parms: dict) -> dict:
    legal = ["method", "shrink"]
    keys = list(parms.keys())
    resolved = {}
    for k in keys:
        matches = [l for l in legal if l.startswith(k)]
        if len(matches) != 1:
            raise ValueError(f"'parms' component not matched: {k}")
        resolved[matches[0]] = parms[k]
    return resolved
```

**Explanation:** `names(parms)` maps to `list(parms.keys())`. The R `pmatch()` partial-matching idiom has no direct Python equivalent; it is replaced by a prefix-search loop over legal names. The setter `names(parms) <- parmsNames[indx]` — which renames existing keys — maps to rebuilding the dict with canonical keys (`resolved`). This is equivalent because Python dicts are unordered by insertion order (Python 3.7+), and the values are preserved while only the keys change.

---

### 4.8 Getter — reading data frame column names

**Locations:** `text.rpart.R` → `text.rpart` (line 16)

**Original R Context:**
```r
frame <- x$frame   # a data.frame
col <- names(frame)   # character vector of column names
```

**Python Equivalent:**
```python
import pandas as pd

frame = x_frame   # a pandas DataFrame
col = list(frame.columns)   # list of column name strings
```

**Explanation:** `names()` applied to an R `data.frame` returns column names, which is equivalent to `pandas.DataFrame.columns`. Converting to a `list` gives a plain Python list of strings for further manipulation consistent with downstream string operations.

---

### 4.9 Getter — filtering a named list by key membership

**Locations:** `rpart.R` → `rpart` (line 87); `xpred.rpart.R` → `xpred.rpart` (lines 55–56)

**Original R Context (rpart.R:87):**
```r
xlevels <- .getXlevels(Terms, m)   # named list: varname -> factor levels
if (!is.null(xlevels)) {
    indx <- match(names(xlevels), colnames(X), nomatch = 0)
    cats[indx] <- (unlist(lapply(xlevels, length)))[indx > 0]
}
```

**Original R Context (xpred.rpart.R:55–56):**
```r
xlevels <- attr(fit, "xlevels")
if (!is.null(xlevels)) {
    xlevels <- xlevels[names(xlevels) %in% colnames(X)]
    cats[match(names(xlevels), colnames(X))] <- unlist(lapply(xlevels, length))
}
```
Both usages read the keys of a named list to align it against the columns of a matrix.

**Python Equivalent:**
```python
import numpy as np

# xlevels is a dict mapping variable name -> list of factor levels
# X is a pandas DataFrame; X.columns are the variable names

# rpart.R variant
if xlevels is not None:
    col_names = list(X.columns)
    for varname, levels in xlevels.items():
        if varname in col_names:
            idx = col_names.index(varname)
            cats[idx] = len(levels)

# xpred.rpart.R variant — filter first, then assign
if xlevels is not None:
    col_set = set(X.columns)
    xlevels = {k: v for k, v in xlevels.items() if k in col_set}
    for varname, levels in xlevels.items():
        idx = list(X.columns).index(varname)
        cats[idx] = len(levels)
```

**Explanation:** `names(xlevels)` retrieves dict keys. The R `match(names(xlevels), colnames(X), nomatch=0)` pattern — finding the position of each key in a column list — is replaced by `list.index()`. The R subsetting `xlevels[names(xlevels) %in% colnames(X)]` — keeping only entries whose key appears in a target set — maps to a dict comprehension with `k in col_set`.
