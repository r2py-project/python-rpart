# Conversion Guide: `is.function` (R to Python)

---

## 1. Overview of `is.function` in R

`is.function(x)` is a base R predicate that tests whether an object `x` is a function. It returns `TRUE` for any callable R object — including user-defined closures, anonymous functions, and built-in primitive functions — and `FALSE` for everything else (e.g., `NULL`, lists, numeric vectors, environments).

- **Input:** A single R object `x` of any type.
- **Output:** A scalar `logical` (`TRUE` or `FALSE`).
- **Scope:** Broader than `is.primitive()`. Both user-defined functions (closures) and primitive functions pass the `is.function()` test.

---

## 2. Contextual Usage Analysis

All three CSV rows come from a single function, `rpartcallback`, defined in `/groups/jli9/Yufei/python-rpart/rpart/R/rpartcallback.R`.

The function receives `mlist`, a user-supplied list that must contain exactly three named entries — `init`, `split`, and `eval` — each of which must be a callable function. Lines 8, 10, and 12 perform guard checks on these three entries using `is.function`, immediately raising an error with `stop()` if any entry is not a function.

```r
if (!is.function(mlist$init))
    stop("User written method does not contain an 'init' function")
if (!is.function(mlist$split))
    stop("User written method does not contain a 'split' function")
if (!is.function(mlist$eval))
    stop("User written method does not contain an 'eval' function")
```

The pattern is identical across all three uses:

- **Subject:** A named element extracted from a list (`mlist$init`, `mlist$split`, `mlist$eval`).
- **Expected type:** Any callable (R closure or primitive function).
- **Action on failure:** Immediately raise an exception via `stop()`.
- **Scalar context:** Each check operates on a single object, not a vector; the return value is always a single `TRUE` or `FALSE`.

There are no vectorized or broadcasting scenarios here. The sole purpose of `is.function` in this file is runtime type validation for elements of a named list.

---

## 3. Python Conversion Strategy

The direct Python equivalent is the built-in `callable()` function from the Python standard library.

`callable(obj)` returns `True` if `obj` appears callable (i.e., its class defines a `__call__` method), and `False` otherwise. This covers:

- Plain functions defined with `def` or `lambda`.
- Instance methods and static methods.
- Classes (since calling a class invokes `__init__`).
- Any object whose class implements `__call__`.

This maps precisely to R's `is.function()` in the context seen in `rpartcallback`: the goal is to verify that a value retrieved from a dict (equivalent of R's named list) is something that can be called. Neither `numpy` nor any other scientific library is relevant here, because the check is purely structural/type-based and operates on a single object, not an array. The standard library `callable()` is the idiomatic, dependency-free choice.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Validating callable entries in a named list / dict

**Locations:** `rpartcallback.R` — function `rpartcallback`, lines 8, 10, 12.

**Original R Context**

`mlist` is an R list whose elements are expected to be functions (closures). `mlist$init`, `mlist$split`, and `mlist$eval` are each a single R object. `is.function()` returns a scalar `logical`.

```r
# R
rpartcallback <- function(mlist, nobs, init) {
    if (length(mlist) < 3L)
        stop("User written methods must have 3 functions")
    if (!is.function(mlist$init))
        stop("User written method does not contain an 'init' function")
    if (!is.function(mlist$split))
        stop("User written method does not contain a 'split' function")
    if (!is.function(mlist$eval))
        stop("User written method does not contain an 'eval' function")
    # ... rest of function
}
```

**Python Equivalent**

```python
# Python
def rpartcallback(mlist: dict, nobs: int, init: dict):
    if len(mlist) < 3:
        raise ValueError("User written methods must have 3 functions")
    if not callable(mlist.get("init")):
        raise ValueError("User written method does not contain an 'init' function")
    if not callable(mlist.get("split")):
        raise ValueError("User written method does not contain a 'split' function")
    if not callable(mlist.get("eval")):
        raise ValueError("User written method does not contain an 'eval' function")
    # ... rest of function
```

**Explanation**

| R | Python | Notes |
|---|--------|-------|
| `mlist$init` | `mlist.get("init")` | R's `$` accessor on a list becomes dict key access in Python. Using `.get()` avoids a `KeyError` if the key is absent, returning `None` instead, which `callable()` correctly evaluates as `False`. |
| `is.function(x)` | `callable(x)` | Direct 1-to-1 mapping. Both return a single boolean. `callable()` is part of Python's built-in namespace — no import is required. |
| `stop("message")` | `raise ValueError("message")` | R's `stop()` raises a runtime error; `ValueError` is the idiomatic Python equivalent for invalid argument types or values. |
| `!is.function(x)` | `not callable(x)` | The logical negation translates directly. |

No third-party libraries (`numpy`, `scipy`, etc.) are needed. The entire pattern is expressible with Python built-ins.
