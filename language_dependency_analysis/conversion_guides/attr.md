# Conversion Guide: `attr` (R to Python)

---

## 1. Overview of `attr` in R

`attr(x, which)` is a base R function that **gets or sets a single named attribute** on any R object. Attributes in R are metadata attached to an object — they travel with it through most operations and can carry arbitrary named values.

**Getter form:**
```r
value <- attr(x, "name")
```
Returns the attribute named `"name"` from object `x`, or `NULL` if the attribute does not exist.

**Setter form:**
```r
attr(x, "name") <- value
```
Attaches `value` to `x` under the attribute name `"name"`.

Common built-in attributes managed via `attr` include:
- `"terms"` — a `terms` object describing a model formula (class, response variable index, term labels, ordering, offsets, data classes).
- `"xlevels"` — a named list mapping each categorical predictor to its factor levels.
- `"ylevels"` — a character vector of the response variable's factor levels (classification only).
- `"na.action"` — records indices of rows removed due to missing values.
- `"response"`, `"order"`, `"term.labels"`, `"offset"`, `"dataClasses"`, `"variables"` — sub-attributes queried from a `terms` object.

---

## 2. Contextual Usage Analysis

Across all 27 CSV rows, `attr` is used exclusively in **getter** form (reading metadata) except for two assignment rows in `rpart.R` lines 294–295. The calls fall into four logical groups:

### Group A — Reading model metadata from a `terms` object

`attr(m, "terms")`, `attr(x, "terms")`, `attr(frame, "terms")` — extract the `terms` object from a model frame. A `terms` object is itself an R object that carries further sub-attributes queried with additional `attr` calls:

- `attr(Terms, "response")` — integer index (1-based) of the response column in the model frame.
- `attr(Terms, "order")` — integer vector, interaction order of each term.
- `attr(Terms, "term.labels")` — character vector of predictor names from the formula.
- `attr(Terms, "offset")` — integer index of the offset variable, or `NULL`.
- `attr(Terms, "dataClasses")` — named character vector mapping each column to its storage class.
- `attr(Terms, "variables")` — a language object (call) listing all variables in the formula.

### Group B — Reading categorical level metadata from a fitted rpart object

`attr(object, "xlevels")` — a named list; keys are factor predictor names, values are character vectors of that factor's levels. Used to align new data factor levels during prediction.

`attr(object, "ylevels")` — a character vector of the response factor's levels. Used in classification to map integer `yval` back to class names.

### Group C — Reading missing-value action metadata

`attr(m, "na.action")` — retrieves the `na.action` attribute from a model frame; its value is a named integer vector of row indices that were dropped due to NA values.

### Group D — Assigning custom metadata to a fitted object

```r
attr(ans, "xlevels") <- xlevels   # rpart.R line 294
attr(ans, "ylevels") <- init$ylevels  # rpart.R line 295
```
These are setter calls that attach metadata dictionaries to the freshly built rpart result list before it is returned.

**Recurring pattern:** `attr` is consistently applied to objects that are either R model frames (data frames with a `"terms"` attribute), fitted `rpart` list objects, or `terms` objects themselves. In every case the attribute holds structured metadata (not raw data arrays), so the Python equivalent must be a metadata storage mechanism, not a numeric operation.

---

## 3. Python Conversion Strategy

R's `attr` has no single universal Python counterpart because Python objects carry metadata differently depending on their type. In the rpart Python port the primary equivalents are:

| R mechanism | Python equivalent |
|---|---|
| `attr(obj, "name")` getter | `obj.attrs["name"]` or `getattr(obj, "name", None)` |
| `attr(obj, "name") <- val` setter | `obj.attrs["name"] = val` or `setattr(obj, "name", val)` |
| `terms` object with sub-attributes | A plain Python `dict` or a lightweight dataclass carrying the same named fields |
| `attr(terms, "term.labels")` etc. | Direct field/key access on the Python terms representation |

The rpart port uses plain Python `dict`s and custom objects (typically `dict`-backed) to represent fitted models and model frames. Attributes that in R live as `attr(obj, "name")` are stored as either:

1. **Top-level dictionary keys** on the model/frame dict (e.g., `model["xlevels"]`, `model["ylevels"]`), or
2. **Fields of a `Terms` dataclass** for the sub-attributes of a `terms` object.

`numpy` and `pandas` are **not** involved in `attr` translation — `attr` is a metadata access operation, not an array computation.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Reading a `terms` object from a model frame

**Locations:** `model.frame.rpart.R::model.frame.rpart` (line 8), `na.rpart.R::na.rpart` (line 3), `rpart.R::rpart` (line 22), `rpart.matrix.R::rpart.matrix` (lines 12, 27)

**Original R Context:**

- Input: `m` is an R model frame (a `data.frame` with a `"terms"` attribute of class `terms`).
- Return: the `terms` object itself (an R language object with further attributes).

```r
# R
Terms <- attr(m, "terms")
# Terms is then used as: attr(Terms, "response"), attr(Terms, "term.labels"), etc.

# Guard pattern (rpart.matrix.R line 12):
if (is.null(attr(frame, "terms"))) return(as.matrix(frame))
```

**Python Equivalent:**

```python
# Python — assuming m is a dict representing the model frame
# The terms object is stored under the key "terms"

terms = m.get("terms")  # returns None if not present

# Guard pattern equivalent:
if terms is None:
    import numpy as np
    return np.array(frame)
```

**Explanation:** R stores the `terms` object as the `"terms"` attribute of a model frame. In Python the model frame is represented as a `dict` (or a pandas `DataFrame` with a companion metadata dict), so the terms object lives under the key `"terms"`. Use `.get("terms")` to mirror R's behaviour of returning `NULL`/`None` when absent.

---

### 4.2 Reading sub-attributes of a `terms` object

**Locations:** `na.rpart.R::na.rpart` (line 4), `rpart.R::rpart` (lines 23, 153), `xpred.rpart.R::xpred.rpart` (line 32), `post.rpart.R::post.rpart` (line 21), `predict.rpart.R::predict.rpart` (line 15)

**Original R Context:**

- Input: `Terms` is an R `terms` object (itself the result of `attr(m, "terms")`).
- Possible attribute names and their types:

| R call | R type | Meaning |
|---|---|---|
| `attr(Terms, "response")` | integer (1-based column index) | Which column is the response |
| `attr(Terms, "order")` | integer vector | Interaction order per term |
| `attr(Terms, "term.labels")` | character vector | Predictor names from formula |
| `attr(Terms, "offset")` | integer or NULL | Offset column index |
| `attr(Terms, "dataClasses")` | named character vector | Storage class per column |
| `attr(Terms, "variables")` | language/call object | All variables in formula |

```r
# R
yvar   <- attr(Terms, "response")     # integer, 1-based
order  <- attr(Terms, "order")        # integer vector
labels <- attr(Terms, "term.labels")  # character vector
offset <- attr(Terms, "offset")       # integer or NULL
cl     <- attr(Terms, "dataClasses")  # named character vector
vars   <- attr(Terms, "variables")    # language object (call)
```

**Python Equivalent:**

```python
# Python — Terms is a dict (or dataclass) built when parsing the formula
# Example structure:
# terms = {
#     "response": 0,             # 0-based index in Python
#     "order": [1, 1, 2],        # list of ints
#     "term_labels": ["x1", "x2"],
#     "offset": None,            # or int index
#     "data_classes": {"x1": "numeric", "x2": "factor"},
#     "variables": ["y", "x1", "x2"],
# }

yvar        = terms.get("response")       # int (0-based) or None
order       = terms.get("order")          # list[int]
term_labels = terms.get("term_labels")    # list[str]
offset      = terms.get("offset")         # int or None
data_cls    = terms.get("data_classes")   # dict[str, str]
variables   = terms.get("variables")      # list[str]
```

**Explanation:** Each named attribute of an R `terms` object maps directly to a key in a Python dict. The critical index translation: R's `attr(Terms, "response")` is **1-based** (value `1` means the first column). In Python use **0-based** indexing, so subtract 1 when using the value to index a list or DataFrame column. `attr(Terms, "variables")[2L]` in R (used in `post.rpart.R` line 21) fetches the second element of the variables language call with 1-based indexing; the Python equivalent is `variables[1]`.

---

### 4.3 Reading `xlevels` from a fitted rpart object

**Locations:** `labels.rpart.R::labels.rpart` (line 53), `predict.rpart.R::predict.rpart` (line 14), `xpred.rpart.R::xpred.rpart` (line 53)

**Original R Context:**

- Input: `object` is a fitted `rpart` list object.
- Return: `xlevels` is a named list; each key is a factor predictor name and each value is a character vector of that factor's levels.

```r
# R
xlevels <- attr(object, "xlevels")
# xlevels is NULL for regression trees (no factors)
# Example value: list(color = c("blue", "green", "red"))
if (!is.null(xlevels)) {
    cindex <- match(vnames, names(xlevels))
}
```

**Python Equivalent:**

```python
# Python — object (fitted rpart) is a dict
xlevels = object.get("xlevels")  # dict[str, list[str]] or None

# Null-guard pattern:
if xlevels is not None:
    # names(xlevels) -> list(xlevels.keys())
    cindex = [list(xlevels.keys()).index(v) if v in xlevels else -1
              for v in vnames]
```

**Explanation:** `attr(object, "xlevels")` in R returns a named list; in Python it is stored as a plain `dict` keyed by predictor name. R's `names(xlevels)` maps to `list(xlevels.keys())`. R's `match(vnames, names(xlevels))` (1-based) maps to a list comprehension using `.index()` or `dict` key lookup (0-based, with `-1` for not-found). The null check `!is.null(xlevels)` translates directly to `if xlevels is not None`.

---

### 4.4 Reading `ylevels` from a fitted rpart object

**Locations:** `print.rpart.R::print.rpart` (line 8), `residuals.rpart.R::residuals.rpart` (line 15), `roc.rpart.R::roc.rpart` (line 5), `predict.rpart.R::predict.rpart` (line 21), `summary.rpart.R::summary.rpart` (line 33), `text.rpart.R::text.rpart` (lines 17–18)

**Original R Context:**

- Input: `object` or `x` is a fitted `rpart` list; only set when `method == "class"`.
- Return: character vector of class label strings. `NULL` for non-classification trees.

```r
# R
ylevels <- attr(object, "ylevels")  # character vector or NULL
nclass  <- length(ylevels)          # 0 for regression trees
# Usage: factor(ylevels[frame$yval[where]], levels = ylevels)

# roc.rpart.R guard:
if (length(attr(object, "ylevels")) != 2L)
    stop("endpoint not a 2 level-factor")
```

**Python Equivalent:**

```python
# Python
ylevels = object.get("ylevels")  # list[str] or None
nclass  = len(ylevels) if ylevels is not None else 0

# Reconstruct factor predictions (predict.rpart equivalent):
import pandas as pd
pred = pd.Categorical(
    [ylevels[v - 1] for v in frame["yval"].iloc[where]],  # R yval is 1-based
    categories=ylevels
)

# roc.rpart guard:
if ylevels is None or len(ylevels) != 2:
    raise ValueError("endpoint not a 2 level-factor")
```

**Explanation:** `attr(object, "ylevels")` returns a character vector; in Python it is a `list[str]`. `length(ylevels)` maps to `len(ylevels)`. Note that R's `frame$yval` stores 1-based integer class indices, so `ylevels[frame$yval[where]]` requires a `- 1` offset when indexing the Python list. `pd.Categorical` is the Python counterpart to R's `factor()` with explicit `levels`.

---

### 4.5 Reading `na.action` from a model frame

**Locations:** `rpart.R::rpart` (lines 125, 127, 293)

**Original R Context:**

- Input: `m` is an R model frame built by `stats::model.frame`.
- Return: an integer vector of **1-based** row indices that were removed due to NA values, or `NULL` if none were removed. The vector has class `c("na.rpart", "omit")`.

```r
# R (rpart.R lines 124-133)
if (!is.null(attr(m, "na.action"))) {
    temp <- as.integer(attr(m, "na.action"))
    xval <- xval[-temp]   # drop the NA rows from the xval grouping vector
    ...
}

# rpart.R line 293
if (!is.null(attr(m, "na.action"))) ans$na.action <- attr(m, "na.action")
```

**Python Equivalent:**

```python
# Python
na_action = m.get("na.action")  # list[int] (0-based) or None

if na_action is not None:
    # Drop those indices from the cross-validation group vector
    xval = [v for i, v in enumerate(xval) if i not in set(na_action)]
    ...

# Propagate to output object:
if na_action is not None:
    ans["na.action"] = na_action
```

**Explanation:** R's `na.action` attribute is a named integer vector with 1-based indices. In Python it is stored as a `list[int]` (0-based). R's `xval[-temp]` (negative indexing = drop those positions) maps to a list comprehension that excludes the stored indices. The `NULL` check `!is.null(...)` translates to `if na_action is not None`.

---

### 4.6 Setting `xlevels` and `ylevels` on the output object (setter form)

**Locations:** `rpart.R::rpart` (lines 294–295)

**Original R Context:**

- These are the only setter (`<-`) usages of `attr` in the CSV.
- `ans` is the list being assembled as the return value of `rpart()`.
- Both calls conditionally attach metadata so that downstream functions (predict, print, etc.) can retrieve it.

```r
# R (rpart.R lines 293-295)
if (!is.null(attr(m, "na.action"))) ans$na.action <- attr(m, "na.action")
if (!is.null(xlevels))             attr(ans, "xlevels") <- xlevels
if (method == "class")             attr(ans, "ylevels") <- init$ylevels
class(ans) <- "rpart"
```

**Python Equivalent:**

```python
# Python — ans is a plain dict
if na_action is not None:
    ans["na.action"] = na_action

if xlevels is not None:
    ans["xlevels"] = xlevels          # dict[str, list[str]]

if method == "class":
    ans["ylevels"] = init["ylevels"]  # list[str]

ans["_class"] = "rpart"  # or use a wrapper class
```

**Explanation:** R's `attr(ans, "xlevels") <- xlevels` attaches the value as a named attribute distinct from the list's regular elements. In the Python dict representation this distinction disappears — both regular fields and R-style attributes are stored as top-level dict keys. The R convention that `attr` metadata is separate from `$` element access does not apply in Python; use ordinary key assignment. The `class(ans) <- "rpart"` assignment has no Python structural equivalent but can be represented by tagging a `"_class"` key or by using an `rpart` dataclass/namedtuple.
