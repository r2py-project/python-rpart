# Conversion Guide: `inherits` (R to Python)

## 1. Overview of `inherits` in R

`inherits(x, what, which = FALSE)` tests whether an object `x` inherits from a named class (or set of classes). It is the idiomatic R way to perform class-based type checking.

- **`x`**: Any R object.
- **`what`**: A character vector of class names to test against.
- **`which`** (default `FALSE`): When `FALSE`, returns a single logical scalar — `TRUE` if `x` inherits from any of the classes listed in `what`. When `TRUE`, returns an integer vector indicating at which position in the class list each name in `what` appears (0 if absent).

In the rpart codebase `which` is never used, so every call reduces to the simple scalar boolean form: "does this object belong to class X?"

R objects can carry multiple classes simultaneously (stored as a character vector in the `class` attribute). `inherits` checks whether any element of `what` appears in that vector, making it equivalent to `any(what %in% class(x))`.

Typical usage pattern (as seen throughout rpart):

```r
if (!inherits(x, "rpart")) stop("Not a legitimate \"rpart\" object")
```

This is an input-validation guard placed at the top of every public function to ensure the caller has passed an object of the expected type.

---

## 2. Contextual Usage Analysis

The CSV contains 17 call sites across 15 source files. Two distinct class names are tested:

### Pattern A: Checking for class `"rpart"` (15 call sites)

Files: `meanvar.rpart.R`, `path.rpart.R`, `plot.rpart.R`, `plotcp.R`, `predict.rpart.R`, `print.rpart.R`, `printcp.R`, `residuals.rpart.R`, `roc.rpart.R`, `rsq.rpart.R`, `snip.rpart.R`, `summary.rpart.R`, `text.rpart.R`, `xpred.rpart.R`.

Every one of these is an entry-guard at the very start of a public function. The argument name varies (`x`, `tree`, `object`, `fit`) but the intent is identical: reject any value that is not an rpart model object and raise an error immediately.

Input type: the first parameter of each function — a user-supplied model object.
Return type: logical scalar (used only inside `if (!inherits(...))` to conditionally call `stop()`).

### Pattern B: Checking for class `"Surv"` (2 call sites)

Files: `rpart.R` (line 37), `rpart.exp.R` (line 14).

In `rpart.R` the check is used to auto-detect the response type and select the splitting method:

```r
method <- if (is.factor(Y) || is.character(Y)) "class"
          else if (inherits(Y, "Surv")) "exp"
          else if (is.matrix(Y)) "poisson"
          else "anova"
```

In `rpart.exp.R` the check is a guard that ensures the `y` argument is a survival object before proceeding with the exponential split routine.

Input type: a response vector/matrix `Y` or `y` that may be a `Surv` object (from the `survival` package).
Return type: logical scalar.

### Pattern C: Checking for class `"data.frame"` (1 call site)

File: `rpart.matrix.R` (line 11).

```r
if (!inherits(frame, "data.frame") || is.null(attr(frame, "terms")))
    return(as.matrix(frame))
```

This is a type-dispatch guard combined with an attribute check. If the input is not a data frame (or lacks a `terms` attribute), the function falls back to a simple matrix conversion.

Input type: `frame` — expected to be a model frame (a `data.frame` with a `"terms"` attribute).
Return type: logical scalar, combined with `||` for a compound condition.

---

## 3. Python Conversion Strategy

R's `inherits` maps directly to Python's built-in `isinstance()`. Both functions test whether an object is an instance of a given class (or its subclasses). No third-party library is needed.

Why `isinstance` rather than `type(x) == SomeClass`:

- `isinstance` respects inheritance, exactly mirroring R's class hierarchy semantics.
- Python custom objects representing rpart models or survival objects will naturally subclass a base class, so `isinstance` will work correctly for both direct instances and subclasses.
- `isinstance` also accepts a tuple of types as the second argument, directly paralleling R's ability to pass a vector of class names to `inherits`.

For the `"data.frame"` check, the Python equivalent is a `pandas.DataFrame`, so the check becomes `isinstance(frame, pd.DataFrame)`.

For the `"rpart"` check, the Python translation assumes the rpart model is represented by a custom Python class (e.g., named `RpartObject` or similar, consistent with the rest of the translated package).

For the `"Surv"` check, a survival object from the Python `lifelines` or a custom `Surv` class would be tested similarly.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Guard: Check for `"rpart"` class — reject invalid input

**Locations:** `meanvar.rpart.R::meanvar.rpart`, `path.rpart.R::path.rpart`, `plot.rpart.R::plot.rpart`, `plotcp.R::plotcp`, `predict.rpart.R::predict.rpart`, `print.rpart.R::print.rpart`, `printcp.R::printcp`, `residuals.rpart.R::residuals.rpart`, `roc.rpart.R::roc.rpart`, `rsq.rpart.R::rsq.rpart`, `snip.rpart.R::snip.rpart`, `summary.rpart.R::summary.rpart`, `text.rpart.R::text.rpart`, `xpred.rpart.R::xpred.rpart`

**Original R Context:**

- Input parameter: an R object (named `x`, `tree`, `object`, or `fit`) expected to be an rpart model.
- Return type of `inherits`: logical scalar.
- The call is always wrapped in `if (!inherits(...)) stop(...)`.

```r
# Generalized R pattern (argument name varies across files)
some_rpart_function <- function(x, ...) {
    if (!inherits(x, "rpart"))
        stop("Not a legitimate \"rpart\" object")
    # ... rest of function
}
```

**Python Equivalent:**

```python
# Assumes the rpart model is represented by a class named RpartObject
# (replace with the actual class used in the translated package)

class RpartObject:
    pass  # placeholder — the actual translated rpart model class

def some_rpart_function(x, **kwargs):
    if not isinstance(x, RpartObject):
        raise TypeError('Not a legitimate "rpart" object')
    # ... rest of function
```

**Explanation:**

- `inherits(x, "rpart")` becomes `isinstance(x, RpartObject)`.
- R's `stop()` maps to Python's `raise` with an appropriate exception. `TypeError` is the most semantically accurate choice for a wrong-type argument, though `ValueError` is also common in Python libraries.
- The negation `!inherits(...)` maps directly to `not isinstance(...)`.
- No imports are required; `isinstance` is a Python built-in.

---

### 4.2 Type-dispatch: Check for `"Surv"` class to select the splitting method

**Locations:** `rpart.R::rpart` (line 37)

**Original R Context:**

- Input: `Y` — the response extracted from the model frame; could be a factor, character vector, `Surv` object, matrix, or plain numeric vector.
- Return type of `inherits`: logical scalar used inside a chained `if/else if` to select `method`.

```r
method <- if (is.factor(Y) || is.character(Y)) "class"
          else if (inherits(Y, "Surv")) "exp"
          else if (is.matrix(Y)) "poisson"
          else "anova"
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

# Assumes a Surv class exists in the translated package (e.g. from survival module)
# Replace with the actual Surv class used in the Python translation.
from survival import Surv  # illustrative import

def select_method(Y):
    if isinstance(Y, (pd.Categorical, pd.Series)) and hasattr(Y, 'cat'):
        method = "class"
    elif isinstance(Y, str) or (isinstance(Y, np.ndarray) and Y.dtype.kind in ('U', 'S')):
        method = "class"
    elif isinstance(Y, Surv):
        method = "exp"
    elif isinstance(Y, np.ndarray) and Y.ndim == 2:
        method = "poisson"
    else:
        method = "anova"
    return method
```

**Explanation:**

- `inherits(Y, "Surv")` becomes `isinstance(Y, Surv)`, where `Surv` is the Python class that represents a survival-time response object.
- R's `is.factor(Y) || is.character(Y)` maps to checks on pandas Categorical dtype or numpy string dtype.
- R's `is.matrix(Y)` maps to `isinstance(Y, np.ndarray) and Y.ndim == 2`.
- The ordering of conditions is preserved because the R `if/else if` chain is short-circuit evaluated top-to-bottom, and the Python equivalent must match that precedence.

---

### 4.3 Guard: Check for `"Surv"` class — reject non-survival response

**Locations:** `rpart.exp.R::rpart.exp` (line 14)

**Original R Context:**

- Input: `y` — the response argument passed into `rpart.exp`, expected to be a `Surv` object.
- Return type of `inherits`: logical scalar.

```r
rpart.exp <- function(y, offset, parms, wt) {
    if (!inherits(y, "Surv"))
        stop("Response must be a 'survival' object - use the 'Surv()' function")
    # ...
}
```

**Python Equivalent:**

```python
from survival import Surv  # illustrative import — replace with actual package

def rpart_exp(y, offset, parms=None, wt=None):
    if not isinstance(y, Surv):
        raise TypeError(
            "Response must be a 'survival' object - use the Surv() constructor"
        )
    # ... rest of function
```

**Explanation:**

- Identical pattern to 4.1 but testing for `Surv` instead of `RpartObject`.
- The error message is preserved as closely as possible from the R original.
- No library imports beyond the custom `Surv` class definition are required.

---

### 4.4 Type-dispatch with compound condition: Check for `"data.frame"` class

**Locations:** `rpart.matrix.R::rpart.matrix` (line 11)

**Original R Context:**

- Input: `frame` — expected to be a model frame, which is an R `data.frame` with an additional `"terms"` attribute.
- The check is combined with an attribute test in a compound `||` condition.
- If either condition fails the function falls back to a simple `as.matrix(frame)`.

```r
rpart.matrix <- function(frame) {
    if (!inherits(frame, "data.frame") || is.null(attr(frame, "terms")))
        return(as.matrix(frame))
    # ... model.matrix logic
}
```

**Python Equivalent:**

```python
import numpy as np
import pandas as pd

def rpart_matrix(frame):
    # Check: must be a DataFrame AND must carry a 'terms' attribute
    if not isinstance(frame, pd.DataFrame) or not hasattr(frame, 'terms'):
        return np.asarray(frame, dtype=float)
    # ... model matrix logic
```

**Explanation:**

- `inherits(frame, "data.frame")` becomes `isinstance(frame, pd.DataFrame)`. A pandas `DataFrame` is the direct Python equivalent of R's `data.frame`.
- R's `is.null(attr(frame, "terms"))` becomes `not hasattr(frame, 'terms')`. In the translated Python code, model frame metadata (like `terms`) would be attached as an attribute on the `DataFrame` instance or stored in a wrapper.
- The compound `||` maps to Python's `or` with identical short-circuit semantics.
- R's `as.matrix(frame)` maps to `np.asarray(frame, dtype=float)`, which converts the DataFrame to a NumPy 2D array. The `dtype=float` matches rpart's expectation of numeric matrix content.
- No `numpy` vectorization is needed here because the check itself operates on a single object (scalar semantics), not element-wise over an array.
