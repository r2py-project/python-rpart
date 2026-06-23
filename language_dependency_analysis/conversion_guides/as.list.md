# Conversion Guide: `as.list` in R

## 1. Overview of `as.list` in R

`as.list` is a base R coercion function that converts its argument into an R `list`. A `list` in R is an ordered collection of named or unnamed elements, where each element can hold any R object of any type. The function is defined in base R (no package required).

Key behaviors:

- When given a **named vector** (e.g., `c(shrink = 1L, method = 1L)`), it produces a named list where each element corresponds to one scalar value from the vector, preserving names.
- When given an **existing list**, it is effectively a no-op — it returns the list unchanged.
- When given an **unnamed vector**, it produces an unnamed list of scalar elements.
- The conversion is shallow: it does not recursively convert nested structures.

This makes `as.list` the idiomatic R pattern for accepting a parameter argument that may arrive as either a named vector or a named list, and then uniformly treating it as a list so that `$`-style named element access (e.g., `parms$method`) works on either input type.

---

## 2. Contextual Usage Analysis

Both CSV rows describe the same structural pattern appearing in two closely related initializer functions in the rpart package.

**Locations and context:**

- `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.exp.R`, function `rpart.exp`, line 111
- `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.poisson.R`, function `rpart.poisson`, line 16

Both functions share the signature `function(y, offset, parms, wt)`. The `parms` argument is an optional user-supplied parameter bundle. In both functions, the identical guard-and-normalize block appears:

```r
if (missing(parms)) parms <- c(shrink = 1L, method = 1L)
else {
    parms <- as.list(parms)
    if (is.null(names(parms))) stop("You must input a named list for parms")
    parmsNames <- c("method", "shrink")
    indx <- pmatch(names(parms), parmsNames, 0L)
    if (any(indx == 0L))
        stop(gettextf("'parms' component not matched: %s",
                      names(parms)[indx == 0L]), domain = NA)
    else names(parms) <- parmsNames[indx]

    if (is.null(parms$method)) method <- 1L
    else method <- pmatch(parms$method, c("deviance", "sqrt"))
    ...
    if (is.null(parms$shrink)) shrink <- 2L - method
    else shrink <- parms$shrink
    ...
    parms <- c(shrink = shrink, method = method)
}
```

**Role of `as.list(parms)` in this context:**

`parms` is accepted from the caller and may be either a named vector (e.g., `c(method = "deviance")`) or an already-constructed named list. The call `as.list(parms)` normalizes `parms` into a list so that named-element access via `parms$method` and `parms$shrink` works regardless of how the caller constructed it.

**Data types involved:**

- Input `parms`: a named R vector (typically `c(method = ..., shrink = ...)`) or a named R list. The values are either integer scalars (`1L`, `2L`) or character strings (`"deviance"`, `"sqrt"`).
- Output: a named Python `dict` holding up to two keys: `"method"` and `"shrink"`.
- The downstream usage accesses named elements only (`parms$method`, `parms$shrink`) and checks for absence via `is.null(...)`.

**Recurring pattern:** The `as.list` call is used purely as a defensive type-normalization step — it guarantees the code can use named-element access safely regardless of whether the user passed a vector or a list.

---

## 3. Python Conversion Strategy

`as.list` in this context does not involve numerical computation. It is a **type coercion / normalization** operation on a heterogeneous, named parameter container. Therefore `numpy` and `pandas` are not appropriate here.

The correct Python equivalent is the built-in `dict`. In Python, a `dict` directly maps to R's named list:

- Named element access: `parms["method"]` mirrors `parms$method`.
- Absence check: `parms.get("method") is None` mirrors `is.null(parms$method)`.
- Construction from a named vector equivalent: a Python `dict` literal or `dict()` call mirrors `c(method = "deviance", shrink = 1)`.

Because the caller may supply `parms` as either a `dict` already or potentially as some other mapping-compatible type, the normalization step in Python is `dict(parms)` — which is the direct counterpart to `as.list(parms)`.

No `numpy`, `scipy`, or `pandas` import is needed for this conversion. The entire pattern is handled with pure Python built-ins.

---

## 4. Step-by-Step Conversion Examples

### 4.1 `as.list(parms)` — Named Parameter Bundle Normalization

**Locations:**
- `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.exp.R` — function `rpart.exp`
- `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.poisson.R` — function `rpart.poisson`

Both locations use `as.list(parms)` identically, so they share a single conversion example.

**Original R Context**

- `parms` type at the call site: a named R vector such as `c(method = "deviance", shrink = 1)`, or a named R list. May contain character or integer scalar values.
- Return type of `as.list(parms)`: an R named list.
- Downstream access uses `parms$method` and `parms$shrink` (named-element access), and `is.null(parms$method)` to test for a missing key.

```r
# R — full parms normalization block (generalized)
if (missing(parms)) {
    parms <- c(shrink = 1L, method = 1L)
} else {
    parms <- as.list(parms)
    if (is.null(names(parms))) stop("You must input a named list for parms")

    parmsNames <- c("method", "shrink")
    indx <- pmatch(names(parms), parmsNames, 0L)
    if (any(indx == 0L))
        stop("'parms' component not matched")
    else
        names(parms) <- parmsNames[indx]

    if (is.null(parms$method)) method <- 1L
    else method <- pmatch(parms$method, c("deviance", "sqrt"))

    if (is.null(parms$shrink)) shrink <- 2L - method
    else shrink <- parms$shrink

    parms <- c(shrink = shrink, method = method)
}
```

**Python Equivalent**

```python
# Python — equivalent parms normalization block

VALID_PARMS_KEYS = {"method", "shrink"}
VALID_METHODS = ["deviance", "sqrt"]   # 1-based index position maps to method code

def normalize_parms(parms=None):
    """
    Normalize the parms argument to a dict, mirroring R's as.list(parms) pattern.
    Returns a dict with keys 'shrink' (int) and 'method' (int, 1-based index).
    """
    if parms is None:
        # Default: shrink=1, method=1 (mirrors R's c(shrink=1L, method=1L))
        return {"shrink": 1, "method": 1}

    # as.list(parms): coerce to dict regardless of whether caller passed a dict
    # or another mapping-compatible object
    parms = dict(parms)

    if not parms:
        raise ValueError("You must input a named dict for parms")

    # Validate and canonicalize keys (mirrors R's pmatch on names)
    canonical_keys = {}
    for key in parms:
        matches = [k for k in VALID_PARMS_KEYS if k.startswith(key)]
        if len(matches) != 1:
            raise ValueError(f"'parms' component not matched: {key!r}")
        canonical_keys[key] = matches[0]
    parms = {canonical_keys[k]: v for k, v in parms.items()}

    # Resolve method (mirrors R's pmatch(parms$method, c("deviance","sqrt")))
    if parms.get("method") is None:
        method = 1
    else:
        method_val = parms["method"]
        try:
            method = VALID_METHODS.index(method_val) + 1  # 1-based, like R
        except ValueError:
            raise ValueError("Invalid error method for Poisson")

    # Resolve shrink
    if parms.get("shrink") is None:
        shrink = 2 - method
    else:
        shrink = parms["shrink"]

    if not isinstance(shrink, (int, float)) or shrink < 0:
        raise ValueError("Invalid shrinkage value")

    return {"shrink": shrink, "method": method}


# Example usage
result = normalize_parms({"method": "deviance"})
# -> {"shrink": 1, "method": 1}

result = normalize_parms({"shrink": 2, "method": "sqrt"})
# -> {"shrink": 2, "method": 2}

result = normalize_parms()
# -> {"shrink": 1, "method": 1}
```

**Explanation**

| R concept | Python equivalent | Notes |
|---|---|---|
| `as.list(parms)` | `dict(parms)` | Coerces any mapping-like input to a plain `dict`; no-op if already a `dict` |
| `is.null(names(parms))` | `not parms` (empty dict check) | An unnamed R vector has no `names`; a Python dict with no keys is empty |
| `parms$method` | `parms.get("method")` | Named element access; returns `None` instead of `NULL` when absent |
| `is.null(parms$method)` | `parms.get("method") is None` | Absence/NULL test |
| `pmatch(names(parms), parmsNames, 0L)` | Prefix-match loop against `VALID_PARMS_KEYS` | R's `pmatch` does partial string matching; Python requires an explicit implementation |
| `pmatch(parms$method, c("deviance","sqrt"))` | `VALID_METHODS.index(method_val) + 1` | R returns 1-based integer index; Python `list.index` is 0-based, so `+1` aligns them |
| `c(shrink=shrink, method=method)` | `{"shrink": shrink, "method": method}` | Named vector becomes a `dict` |

Key nuance: R's `pmatch` performs **partial matching** (e.g., `"meth"` matches `"method"`). The Python equivalent must replicate this with an explicit prefix-match loop. The `dict(parms)` call for `as.list(parms)` itself is trivial; the surrounding logic requires the most careful translation.
