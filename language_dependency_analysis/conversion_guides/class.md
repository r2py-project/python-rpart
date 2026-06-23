# Conversion Guide: `class` in R

## 1. Overview of `class` in R

`class` is a base-R built-in that serves a dual role:

**As a getter** — `class(x)` returns a character vector containing the S3 class label(s) assigned to the object `x`. If no class has been explicitly set, R infers a default (e.g., `"matrix"`, `"data.frame"`, `"numeric"`).

**As a setter / assignment form** — `class(x) <- value` assigns one or more S3 class labels to `x`, storing them in its `"class"` attribute. This is the mechanism behind R's S3 dispatch system: when a generic function such as `print`, `predict`, or `summary` is called, R looks up the class vector on the object and searches for a method named `generic.classname`.

Key characteristics:
- The class attribute is a plain character vector; prepending a new class label to an existing one (`c("new.class", class(x))`) gives the object multiple classes and allows method dispatch to fall through to parent-class methods.
- Setting the class does not change any data; it only changes how generic functions dispatch on that object.
- `class(x) <- "rpart"` on a plain list is the idiomatic way to turn an anonymous list into a typed S3 object.

---

## 2. Contextual Usage Analysis

There are three CSV rows covering two distinct usage patterns across two files.

### Pattern A — Singleton class assignment (setter)

File `rpart/R/rpart.R`, function `rpart`, line 296.

`ans` is a plain R list assembled from dozens of computed fields (frame, splits, cptable, functions, etc.). After all fields are populated, the single statement `class(ans) <- "rpart"` stamps the list with the S3 class `"rpart"`. The function then returns `ans`. From that point forward every generic (`print`, `predict`, `summary`, `plot`, …) dispatches to an `rpart`-aware method. No reading of the existing class is involved; the previous class of a plain list would simply be `"list"` and is discarded entirely.

### Pattern B — Prepend class to existing class vector (both getter and setter)

File `rpart/R/rpart.matrix.R`, function `rpart.matrix`, line 30.

```r
class(X) <- c("rpart.matrix", class(X))   # setter + getter combined
```

`X` is a numeric matrix produced by `model.matrix(...)`. A matrix in R already carries the class `"matrix"` (and in newer R, also `"array"`), so `class(X)` returns `c("matrix", "array")`. The prepend operation produces `c("rpart.matrix", "matrix", "array")`, which is then written back. This multi-class pattern is used so that downstream code (which checks for `"rpart.matrix"`) can detect the type while numeric-matrix operations continue to work via the existing `"matrix"` class.

The CSV lists `class(X)` on line 30 as a second row because the dependency extractor records both the assignment target expression and the nested read as separate call sites. They are part of the same single statement.

---

## 3. Python Conversion Strategy

R's S3 class system has no direct Python counterpart, but the intent maps cleanly onto Python's native class/instance mechanism:

- **An R S3 object is a named list + a class attribute.** The Python equivalent is an instance of a class whose attributes mirror the list fields.
- **S3 generic dispatch** (`print.rpart`, `predict.rpart`, …) maps to Python dunder methods (`__repr__`) and regular instance/class methods.
- **Multi-class inheritance** (`c("rpart.matrix", "matrix")`) maps to Python's multiple-inheritance MRO or to `isinstance()` checks against a base class.

For the specific patterns in this CSV the recommended strategy is:

| R pattern | Python strategy |
|---|---|
| `class(x) <- "rpart"` on a plain list | Instantiate a dedicated Python class (`RpartResult`) whose `__init__` accepts or builds the same fields. |
| `class(X) <- c("rpart.matrix", class(X))` on a matrix | Define an `RpartMatrix` subclass of `numpy.ndarray` and return an instance of it, preserving all ndarray behaviour. |
| `class(X)` as a getter to inspect existing classes | Use `type(x).__name__` for a single class, or `[c.__name__ for c in type(x).__mro__]` for the full chain; for ndarray subclasses `isinstance(x, np.ndarray)` suffices. |

`numpy` is the correct primary library for the matrix case because `model.matrix` output is always a 2-D numeric matrix, and `numpy.ndarray` subclassing is the idiomatic way to carry extra metadata on an array while keeping all vectorised operations intact.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Singleton class assignment: `class(ans) <- "rpart"`

**Locations:** `rpart/R/rpart.R`, function `rpart`, line 296.

**Original R context**

`ans` is constructed as an anonymous list and assigned the S3 class `"rpart"` immediately before being returned. Input types: all fields are scalars, vectors, matrices, or nested lists produced by the fitting engine. Return type: an S3 object of class `"rpart"` (still a list internally).

```r
# Generalised illustration
ans <- list(frame = frame, where = where, call = Call, ...)
class(ans) <- "rpart"
ans   # returned to the caller
```

**Python equivalent**

```python
import numpy as np


class RpartResult:
    """Python equivalent of an R object of class 'rpart'."""

    def __init__(
        self,
        frame,
        where,
        call,
        terms,
        cptable,
        method,
        parms,
        control,
        functions,
        numresp,
        splits=None,
        csplit=None,
        variable_importance=None,
        model=None,
        y=None,
        x=None,
        wt=None,
        ordered=None,
        na_action=None,
        xlevels=None,
        ylevels=None,
    ):
        self.frame = frame
        self.where = where
        self.call = call
        self.terms = terms
        self.cptable = cptable
        self.method = method
        self.parms = parms
        self.control = control
        self.functions = functions
        self.numresp = numresp
        self.splits = splits
        self.csplit = csplit
        self.variable_importance = variable_importance
        self.model = model
        self.y = y
        self.x = x
        self.wt = wt
        self.ordered = ordered
        self.na_action = na_action
        self.xlevels = xlevels
        self.ylevels = ylevels

    def __repr__(self):
        return f"RpartResult(method={self.method!r}, numresp={self.numresp})"


# Usage — replacing the two R lines:
#   class(ans) <- "rpart"
#   ans
def rpart(...) -> RpartResult:
    # ... build all intermediate variables ...
    ans = RpartResult(
        frame=frame,
        where=where,
        call=Call,
        terms=Terms,
        cptable=cptable,
        method=method,
        parms=init["parms"],
        control=controls,
        functions=functions,
        numresp=init["numresp"],
        splits=splits if nsplit else None,
        csplit=catmat if ncat > 0 else None,
        variable_importance=importance(ans_dict) if nsplit else None,
        ordered=isord,
        xlevels=xlevels,
        ylevels=init.get("ylevels") if method == "class" else None,
    )
    return ans
```

**Explanation**

- In R, `class(ans) <- "rpart"` adds a tag to an existing list without changing its data. In Python the equivalent is to collect all fields in the constructor of a dedicated class. The list fields become instance attributes.
- R's S3 generic dispatch (`print.rpart`, `predict.rpart`, …) maps to methods on `RpartResult` or to standalone functions that check `isinstance(obj, RpartResult)`.
- There is no `class()` setter to translate verbatim; instead, the class membership is established at instantiation time.
- The getter form `class(ans)` translates to `type(ans).__name__` (returns `"RpartResult"`), and `isinstance(ans, RpartResult)` is the idiomatic dispatch check.

---

### 4.2 Pattern B — Prepend to existing class vector: `class(X) <- c("rpart.matrix", class(X))`

**Locations:** `rpart/R/rpart.matrix.R`, function `rpart.matrix`, line 30 (both the setter and the embedded getter).

**Original R context**

`X` is a 2-D numeric matrix returned by `model.matrix()`. Its existing class is `c("matrix", "array")`. After prepending, the class becomes `c("rpart.matrix", "matrix", "array")`. The multi-class vector allows downstream code to check `inherits(X, "rpart.matrix")` while all standard matrix operations remain available via the `"matrix"` / `"array"` classes.

```r
# Generalised illustration
X <- model.matrix(attr(frame, "terms"), frame)[, -1L, drop = FALSE]
colnames(X) <- sub("^`(.*)`", "\\1", colnames(X))
class(X) <- c("rpart.matrix", class(X))   # getter + setter in one line
X
```

**Python equivalent**

```python
import numpy as np
import re
import pandas as pd


class RpartMatrix(np.ndarray):
    """
    Subclass of numpy.ndarray carrying the 'rpart.matrix' class label.

    Equivalent to an R matrix whose class vector is
    c("rpart.matrix", "matrix", "array").
    """

    def __new__(cls, input_array):
        obj = np.asarray(input_array).view(cls)
        return obj

    def __array_finalize__(self, obj):
        # Nothing extra to copy for now; extend here if metadata is added.
        pass

    def __repr__(self):
        return f"RpartMatrix(shape={self.shape}, dtype={self.dtype})"


# ── R getter equivalent ────────────────────────────────────────────────────────
# R: class(X)           -> c("matrix", "array")   (before assignment)
# Python equivalent (introspect MRO):
def r_class(obj):
    """Return a list of class names analogous to R's class() getter."""
    return [c.__name__ for c in type(obj).__mro__ if c is not object]
# e.g. r_class(x) for an ndarray -> ['ndarray']
#      r_class(x) for an RpartMatrix -> ['RpartMatrix', 'ndarray']


# ── Full rpart_matrix conversion ───────────────────────────────────────────────
def rpart_matrix(frame: pd.DataFrame) -> "RpartMatrix":
    """
    Python equivalent of R's rpart.matrix().

    Returns an RpartMatrix (numpy.ndarray subclass) with columns matching
    the model terms, intercept dropped, and backtick-quoted names cleaned.
    """
    # Failsafe: if not a proper model frame, return plain matrix
    if not isinstance(frame, pd.DataFrame):
        return np.asarray(frame, dtype=float)

    # Convert non-numeric columns (mirrors R lapply coercion)
    converted = frame.copy()
    for col in converted.columns:
        if converted[col].dtype == object:
            converted[col] = pd.Categorical(converted[col]).codes.astype(float)
        elif not pd.api.types.is_numeric_dtype(converted[col]):
            converted[col] = converted[col].astype(float)

    # Drop intercept column (mirrors R's [, -1L, drop = FALSE])
    X_raw = converted.values[:, 1:]

    # Strip backtick quoting from column names (mirrors R sub call)
    col_names = [re.sub(r"^`(.*)`$", r"\1", c) for c in converted.columns[1:]]

    # Wrap in RpartMatrix — equivalent to class(X) <- c("rpart.matrix", class(X))
    X = RpartMatrix(X_raw)
    X.column_names = col_names
    return X


# ── isinstance checks replace R's inherits() ──────────────────────────────────
# R: inherits(X, "rpart.matrix")
assert isinstance(X, RpartMatrix)    # True — rpart.matrix check
# R: inherits(X, "matrix")
assert isinstance(X, np.ndarray)     # True — matrix/array check
```

**Explanation**

- **Getter side** (`class(X)` embedded in the expression): In R this returns the current class vector of `X` so it can be prepended. In Python the equivalent introspection is `type(X).__mro__`, but in practice the getter is only needed when you want to preserve existing class labels. Because `np.ndarray` subclassing already handles MRO-based dispatch, no explicit getter call is required at construction time.
- **Setter side** (`class(X) <- c("rpart.matrix", class(X))`): The prepend-and-assign idiom is reproduced by subclassing `numpy.ndarray` as `RpartMatrix`. The `__new__` / `__array_finalize__` protocol is the standard numpy pattern for ndarray subclasses and ensures that the class label survives slicing and arithmetic that returns a new array view.
- **`c("rpart.matrix", class(X))` → MRO order**: Python's MRO naturally places `RpartMatrix` before `ndarray`, mirroring R's left-to-right precedence in the class vector.
- **`inherits(X, "rpart.matrix")`** translates to `isinstance(X, RpartMatrix)`.
- **`inherits(X, "matrix")`** translates to `isinstance(X, np.ndarray)`.
- The intercept column is dropped at index `1:` (Python 0-based slice `[:, 1:]`) matching R's `[, -1L, drop = FALSE]`.
- The backtick-stripping regex `sub("^\`(.*)\`", "\\1", ...)` translates directly to `re.sub(r"^\`(.*)\`$", r"\1", col)`.
