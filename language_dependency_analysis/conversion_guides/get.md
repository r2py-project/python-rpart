# Conversion Guide: `get` (R to Python)

---

### 1. Overview of `get` in R

`get(x, envir, inherits, mode, pos)` is a base R function that retrieves the value of the named object `x` from a given environment (or, by default, from the current scope and its parents). It returns whatever value is bound to that name.

Key parameters relevant to this codebase:

| Parameter | Type | Description |
|---|---|---|
| `x` | `character` | The name of the object to retrieve (as a string). |
| `envir` | `environment` | The R environment to search. Defaults to `parent.frame()`. |
| `inherits` | `logical` | If `TRUE` (the default), the search walks up the chain of enclosing environments. If `FALSE`, the lookup is strictly confined to `envir`. |
| `mode` | `character` | Optional filter on the storage mode of the retrieved object. Defaults to `"any"`. |

`get` is the standard mechanism in R for **dynamic dispatch by name**: constructing a function name at runtime as a string and then fetching and immediately calling the function it names.

---

### 2. Contextual Usage Analysis

The six call sites fall into two structurally distinct patterns.

**Pattern A — Dynamic function lookup by constructed name (lines 68, 71 of `rpart.R`; line 34 of `xpred.rpart.R`):**

A method name is assembled from the string `"rpart."` concatenated with a `method` string (one of `"anova"`, `"poisson"`, `"class"`, `"exp"`). The resulting name (e.g., `"rpart.anova"`) is looked up as a callable and immediately invoked. In `rpart.R` the lookup is scoped to `environment()` (the function's own lexical environment, which contains the named functions as sibling definitions); in `xpred.rpart.R` no `envir` argument is supplied so the global/package search path is used.

From `rpart.R` lines 63–72:
```r
## If this function is being retrieved from the rpart package, then
##   preferentially "get" the init function from there.  But don't
##   lock in the rpart package otherwise, so that we can still do
##   standalone debugging.
init <- if (missing(parms))
    get(paste("rpart", method, sep = "."),
        envir = environment())(Y, offset, , wt)
else
    get(paste("rpart", method, sep = "."),
        envir = environment())(Y, offset, parms, wt)
```

The retrieved object is always a function (e.g., `rpart.anova`, `rpart.class`, `rpart.poisson`, `rpart.exp`), each of which accepts `(Y, offset, parms, wt)` and returns a named list (`init`).

**Pattern B — Device-keyed parameter retrieval from a shared environment (line 11 of `rpart.branch.R`; line 8 of `rpartco.R`; line 10 of `snip.rpart.mouse.R`):**

A device key string (e.g., `"device2"`) is constructed and used to retrieve a previously stored parameter list from the package-level `rpart_env` environment (defined in `zzz.R` as `rpart_env <- new.env()`). The flag `inherits = FALSE` ensures the search is strictly confined to `rpart_env` and does not walk up to parent environments. This pattern always follows an `exists(pn, envir = rpart_env, inherits = FALSE)` guard.

From `rpart.branch.R` lines 8–12:
```r
pn <- paste0("device", dev.cur())
if (!exists(pn, envir = rpart_env, inherits = FALSE))
    stop("no information available on parameters from previous call to plot()")
parms <- get(pn, envir = rpart_env, inherits = FALSE)
branch <- parms$branch
```

The retrieved object is always a named list of plotting parameters (e.g., `branch`, `uniform`, `nspace`, `minbranch`), written earlier by `plot.rpart` via `assign(paste0("device", dev.cur()), parms, envir = rpart_env)`.

Argument types summary across all six sites:

| Argument | Type |
|---|---|
| `x` (first arg) | `character` scalar — a dynamically constructed name string |
| `envir` | `environment` (Pattern A: the function's own lexical env; Pattern B: the package-level `rpart_env`) |
| `inherits` | `logical` scalar; explicitly `FALSE` in Pattern B, omitted (defaults to `TRUE`) in Pattern A |
| Return value | A function object (Pattern A) or a named list (Pattern B) |

---

### 3. Python Conversion Strategy

The two patterns require different Python equivalents:

**Pattern A (dynamic function dispatch):** R's `get(name, envir = environment())` with an immediate call is R's mechanism for **name-based dynamic dispatch**. In Python the direct equivalent is a `dict` mapping method-name strings to the corresponding callables, followed by a standard dictionary lookup. A secondary option is Python's built-in `globals()` dict, but an explicit dispatch table is cleaner and more testable. No `numpy` or `scipy` is needed because the operation is purely a control-flow lookup, not a numerical computation.

**Pattern B (flat-env key retrieval):** As established in the companion `exists.md` guide, `rpart_env` with `inherits = FALSE` behaves exactly like a Python `dict`. The Python equivalent of `get(pn, envir = rpart_env, inherits = FALSE)` is a plain dict access `rpart_env[pn]`, safe to call after an `in` guard.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Dynamic Method Dispatch with `envir = environment()` (Pattern A — with `parms`)

**Locations:**
- `rpart/R/rpart.R` — function `rpart`, lines 71–72
- `rpart/R/xpred.rpart.R` — function `xpred.rpart`, line 34

**Original R Context:**

Input types:
- `method`: `character` scalar, one of `"anova"`, `"poisson"`, `"class"`, `"exp"`.
- `Y`: response vector or matrix (type depends on method).
- `offset`: numeric vector or `NULL`.
- `parms`: user-supplied parameter list or `NULL`.
- `wt`: numeric vector of observation weights.

Return value of `get(...)`: a function object; the result of calling it is a named list (`init`).

Generalized R snippet:

```r
# The candidate functions are defined in the same package scope:
#   rpart.anova(y, offset, parms, wt) -> list(...)
#   rpart.poisson(y, offset, parms, wt) -> list(...)
#   rpart.class(y, offset, parms, wt) -> list(...)
#   rpart.exp(y, offset, parms, wt) -> list(...)

method <- "anova"   # determined earlier by pmatch()
init <- get(paste("rpart", method, sep = "."),
            envir = environment())(Y, offset, parms, wt)
```

**Python Equivalent:**

```python
from rpart_anova import rpart_anova
from rpart_class import rpart_class
from rpart_poisson import rpart_poisson
from rpart_exp import rpart_exp

# Build the dispatch table once (module-level or inside the function)
_METHOD_DISPATCH: dict = {
    "anova":   rpart_anova,
    "poisson": rpart_poisson,
    "class":   rpart_class,
    "exp":     rpart_exp,
}

# Inside rpart() / xpred_rpart():
method = "anova"   # determined earlier by matching
init_fn = _METHOD_DISPATCH[method]
init = init_fn(Y, offset, parms, wt)
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `paste("rpart", method, sep = ".")` | `f"rpart.{method}"` (intermediate key) | String interpolation; the full name is used as a dict key in `_METHOD_DISPATCH`. |
| `get(name, envir = environment())` | `_METHOD_DISPATCH[method]` | Retrieves the callable from an explicit dict. Using the `method` string directly as the key avoids any need to reconstruct the `"rpart.anova"` name in Python, where the naming convention differs. |
| Immediate call `(...)(Y, offset, parms, wt)` | `init_fn(Y, offset, parms, wt)` | Standard Python call after lookup. |
| `envir = environment()` | (not needed) | In R this pins the lookup to the current lexical scope to prefer the package's own definitions. In Python the explicit dict already provides that same guarantee. |

---

#### 4.2 Dynamic Method Dispatch without `parms` (Pattern A — `parms` missing)

**Location:**
- `rpart/R/rpart.R` — function `rpart`, lines 68–69

**Original R Context:**

Identical to 4.1, except `parms` is absent (the user did not supply it). R uses an empty argument `(Y, offset, , wt)` — a trailing comma with nothing in the third position — to pass a missing value to the third parameter of the retrieved function.

Generalized R snippet:

```r
init <- get(paste("rpart", method, sep = "."),
            envir = environment())(Y, offset, , wt)
```

**Python Equivalent:**

```python
# Python has no "missing argument" concept; pass None as the sentinel.
init = init_fn(Y, offset, None, wt)
```

The receiving Python functions (`rpart_anova`, etc.) must accept `parms=None` as their third parameter and handle it accordingly, mirroring the R convention of testing `is.null(parms)`.

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `f(Y, offset, , wt)` — empty third argument | `init_fn(Y, offset, None, wt)` | R allows a positional "missing" argument. Python does not; `None` is the idiomatic sentinel. |
| Downstream `if (missing(parms))` in callee | `if parms is None:` in callee | The callee must be adapted to accept and test `None`. |

---

#### 4.3 Flat-Environment Key Retrieval with `inherits = FALSE` (Pattern B)

**Locations:**
- `rpart/R/rpart.branch.R` — function `rpart.branch`, line 11
- `rpart/R/rpartco.R` — function `rpartco`, line 8
- `rpart/R/snip.rpart.mouse.R` — function `snip.rpart.mouse`, line 10

**Original R Context:**

Input types:
- `pn`: `character` scalar — a device key such as `"device2"`, constructed via `paste0("device", dev.cur())`.
- `rpart_env`: package-level `environment` object, created once at load time in `zzz.R` via `rpart_env <- new.env()`.
- `inherits = FALSE`: `logical` — restricts the lookup strictly to `rpart_env`; no parent-environment walk.

Return value of `get(...)`: a named list of plotting parameters (keys include `branch`, `uniform`, `nspace`, `minbranch`).

Generalized R snippet:

```r
# Module-level (zzz.R):
rpart_env <- new.env()

# In plot.rpart (writer side):
assign(paste0("device", dev.cur()), parms, envir = rpart_env)

# In rpart.branch / rpartco / snip.rpart.mouse (reader side):
pn <- paste0("device", dev.cur())
if (!exists(pn, envir = rpart_env, inherits = FALSE))
    stop("no information available on parameters from previous call to plot()")
parms <- get(pn, envir = rpart_env, inherits = FALSE)
branch <- parms$branch
```

**Python Equivalent:**

```python
# Module-level (zzz.py equivalent):
rpart_env: dict = {}

# In plot_rpart (writer side):
#   rpart_env[f"device{dev_cur()}"] = parms

# In rpart_branch / rpartco / snip_rpart_mouse (reader side):
def rpart_branch(x, y, node, branch=None):
    if branch is None:
        pn = f"device{dev_cur()}"
        if pn not in rpart_env:
            raise RuntimeError(
                "no information available on parameters from previous call to plot()"
            )
        parms = rpart_env[pn]
        branch = parms["branch"]
    # ... rest of function
```

**Explanation:**

| R construct | Python equivalent | Notes |
|---|---|---|
| `rpart_env <- new.env()` | `rpart_env: dict = {}` | A module-level `dict` replaces the flat R environment. |
| `assign(pn, val, envir = rpart_env)` | `rpart_env[pn] = val` | Direct dict assignment on the writer side. |
| `get(pn, envir = rpart_env, inherits = FALSE)` | `rpart_env[pn]` | Direct dict key access. Safe to call only after the `in` guard has passed. |
| `inherits = FALSE` | (implicit in `dict`) | A Python `dict` has no inheritance chain, so `inherits = FALSE` semantics are provided automatically. |
| `parms$branch` | `parms["branch"]` | R's `$` list-member access maps to Python dict key access. |
| `stop("...")` | `raise RuntimeError("...")` | R's `stop()` maps to raising a Python exception. |
| `if (missing(branch))` | `if branch is None:` | R's `missing()` on an optional positional argument maps to a `None` default sentinel. |
| `paste0("device", dev.cur())` | `f"device{dev_cur()}"` | String concatenation using an f-string. |
