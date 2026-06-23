# Conversion Guide: `exists` (R to Python)

---

### 1. Overview of `exists` in R

`exists(x, where, envir, inherits, mode, frame)` is a base R function that checks whether an object named `x` is defined in a given environment. It returns a single logical scalar: `TRUE` if the named object can be found, `FALSE` otherwise.

Key parameters relevant to this codebase:

| Parameter | Type | Description |
|---|---|---|
| `x` | `character` | The name of the object to look up (as a string). |
| `envir` | `environment` | The R environment to search in. |
| `inherits` | `logical` | If `FALSE`, the search is restricted strictly to `envir` and does not walk up the parent-environment chain. If `TRUE` (the default), parent environments are searched as well. |
| `mode` | `character` | Optional filter on the storage mode of the object. Defaults to `"any"`. |

`exists` is the standard guard used before `get()` to avoid errors when retrieving a named object from an environment that may not contain it yet.

---

### 2. Contextual Usage Analysis

All three call sites in the CSV share an identical pattern: each function checks whether a device-specific parameter record has been stored in the package-level `rpart_env` environment before attempting to retrieve it.

The pattern always appears inside a `if (missing(...))` guard:

```
pn <- paste0("device", dev.cur())          # key: a string like "device2"
if (!exists(pn, envir = rpart_env, inherits = FALSE))
    stop("no information available on parameters from previous call to plot()")
parms <- get(pn, envir = rpart_env, inherits = FALSE)
```

Context from `zzz.R` and `plot.rpart.R`:
- `rpart_env` is a package-level environment created once at load time via `rpart_env <- new.env()` (`zzz.R`, line 53).
- `plot.rpart` writes into it: `assign(paste0("device", dev.cur()), parms, envir = rpart_env)` (`plot.rpart.R`, line 23).
- The three functions (`rpart.branch`, `rpartco`, `snip.rpart.mouse`) all read from it using the same `exists` + `get` idiom.

The argument types are:
- `pn` is always a `character` scalar (the key).
- `rpart_env` is an `environment` object (a plain namespace/dict analog).
- `inherits = FALSE` is a `logical` scalar that intentionally prevents the search from escaping into parent environments — this is the critical non-default flag that enforces strict, flat-dictionary semantics.
- The return value of `exists(...)` is a `logical` scalar (`TRUE` / `FALSE`).

There is exactly one functional pattern across all three locations; no variation in argument usage exists.

---

### 3. Python Conversion Strategy

The R construct being converted is a **flat-dictionary key-existence check**. The `rpart_env` environment with `inherits = FALSE` behaves identically to a Python `dict`: keys are looked up in exactly one namespace with no inheritance chain.

The direct Python equivalent is the built-in `dict` method `__contains__` (i.e., the `in` operator), or alternatively `dict.get()` with a sentinel default. No `numpy`, `scipy`, or `pandas` import is required because:

1. The operation is a scalar boolean lookup, not a vectorized numerical computation.
2. The R environment in this context is being used purely as a key-value store (dict), not as a scoping mechanism.

The recommended Python equivalent is:

```python
# R: exists(pn, envir = rpart_env, inherits = FALSE)
# Python:
pn in rpart_env          # returns True / False
```

where `rpart_env` is a plain Python `dict`.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Guard-and-Retrieve Pattern (all three locations)

**Locations:**
- `rpart/R/rpart.branch.R` — function `rpart.branch`, line 9
- `rpart/R/rpartco.R` — function `rpartco`, line 6
- `rpart/R/snip.rpart.mouse.R` — function `snip.rpart.mouse`, line 8

**Original R Context:**

Input types:
- `pn`: `character` scalar — a dynamically constructed key string such as `"device2"`.
- `rpart_env`: `environment` — a package-level mutable namespace holding per-device parameter lists.
- `inherits = FALSE`: `logical` — restricts lookup to `rpart_env` only, not its parents.

Return value of `exists(...)`: `logical` scalar (`TRUE` or `FALSE`).

Generalized R snippet:

```r
# rpart_env is created once at package load time:
#   rpart_env <- new.env()         # zzz.R:53
# plot.rpart writes into it:
#   assign(paste0("device", dev.cur()), parms, envir = rpart_env)

rpart.branch <- function(x, y, node, branch) {
    if (missing(branch)) {
        pn <- paste0("device", dev.cur())
        if (!exists(pn, envir = rpart_env, inherits = FALSE))
            stop("no information available on parameters from previous call to plot()")
        parms <- get(pn, envir = rpart_env, inherits = FALSE)
        branch <- parms$branch
    }
    # ... rest of function
}
```

**Python Equivalent:**

```python
# rpart_env is a module-level dict, initialised once:
rpart_env: dict = {}

# In plot_rpart (the writer side):
#   rpart_env[f"device{dev_cur()}"] = parms

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
| `assign(pn, val, envir = rpart_env)` | `rpart_env[pn] = val` | Direct dict assignment. |
| `exists(pn, envir = rpart_env, inherits = FALSE)` | `pn in rpart_env` | The `in` operator performs an O(1) hash-table lookup, exactly equivalent to `exists` with `inherits = FALSE`. |
| `get(pn, envir = rpart_env, inherits = FALSE)` | `rpart_env[pn]` | Direct dict access; safe to call only after the `in` check has passed, mirroring the R guard. |
| `stop("...")` | `raise RuntimeError("...")` | R's `stop()` maps to raising a Python exception. |
| `if (missing(branch))` | `if branch is None:` | R's `missing()` check on an optional argument maps to a `None` default sentinel. |
| `paste0("device", dev.cur())` | `f"device{dev_cur()}"` | String concatenation using an f-string. |

The `inherits = FALSE` flag is the key behavioral detail: because the R environment is used as a strict flat store (no parent-environment traversal), a plain Python `dict` is the exact structural equivalent. No `numpy` or other numerical library is needed.
