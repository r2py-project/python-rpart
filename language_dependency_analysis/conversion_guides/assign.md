# Conversion Guide: `assign` in R

## 1. Overview of `assign` in R

`assign` is an R base function that binds a value to a variable name in a specified environment. Its signature is:

```r
assign(x, value, envir = parent.frame(), inherits = FALSE, immediate = TRUE)
```

Key parameters:
- `x` — a character string giving the name of the variable to create or overwrite.
- `value` — the R object to store under that name.
- `envir` — the environment in which the binding is created. Defaults to the calling frame, but can be any environment object created with `new.env()` or a package-level environment.

`assign` is the programmatic counterpart of the `<-` assignment operator. It is used when the variable name is not known at parse time (e.g., it is constructed at runtime from a string) or when the target environment must be specified explicitly rather than implicitly. The return value is `value`, invisibly.

---

## 2. Contextual Usage Analysis

The CSV covers two distinct files and two distinct functional patterns.

### Pattern A — Writing into a shared module-level environment (`plot.rpart.R`, line 23)

`plot.rpart` stores per-device plotting parameters into a package-level environment called `rpart_env`, which is declared at module load time in `zzz.R` as:

```r
rpart_env <- new.env()
```

The key name is constructed dynamically at runtime by concatenating the string `"device"` with the integer returned by `dev.cur()` (the current graphics device number). The value stored is `parms`, a named list of plotting parameters (`uniform`, `branch`, `nspace`, `minbranch`). Other functions in the package (`rpart.branch`, `rpartco`, `snip.rpart.mouse`) later retrieve this value from `rpart_env` using `get(pn, envir = rpart_env)`.

### Pattern B — Populating a fresh isolated environment for C callback use (`rpartcallback.R`, lines 100–108)

`rpartcallback` creates a fresh, isolated environment with `rho <- new.env()` and then populates it with nine named bindings using `assign`. The values cover four data types:

| Variable | R type | Description |
|---|---|---|
| `nback` | `integer(1L)` — length-1 integer vector | Scalar-like counter |
| `wback` | `double(nobs)` — numeric vector of length `nobs` | Case weights buffer |
| `xback` | `double(nobs)` — numeric vector of length `nobs` | Predictor buffer |
| `yback` | `double(nobs * numy)` — numeric vector of length `nobs * numy` | Response buffer |
| `user.eval` | R function object | User-supplied evaluation function |
| `user.split` | R function object | User-supplied split function |
| `numy` | integer scalar | Number of response columns |
| `numresp` | integer scalar | Number of response values per node |
| `parms` | list | User-supplied parameter object |

The comment in the source is explicit: these vectors act as shared buffers whose contents are overwritten repeatedly by C code via `.Call(C_init_rpcallback, rho, ...)`. The isolated environment `rho` is then passed directly to the C layer, which mutates `nback`, `wback`, `xback`, and `yback` in-place between successive R callback evaluations. The functions and scalars stored alongside them are read-only configuration.

---

## 3. Python Conversion Strategy

Python has no built-in environment object, but the two patterns map cleanly onto two different Python idioms:

**Pattern A (shared module-level namespace):** Use a plain `dict` at module scope. The dynamic key construction (`paste0("device", dev.cur())`) maps to an f-string or `str` concatenation, and the dict stores the value under that key. This mirrors `rpart_env` exactly: other functions import and look up from the same dict.

**Pattern B (isolated mutable namespace for C interop):** Use a Python `dict` or a simple data class (e.g., `types.SimpleNamespace`) as the container that is passed to the compiled extension. If the Python-side C extension is written with `ctypes` or a `cffi`-style interface, shared writable buffers become `ctypes` arrays or `numpy` arrays. For the writable buffer variables (`nback`, `wback`, `xback`, `yback`), `numpy` arrays are the direct equivalent of R's fixed-length typed vectors, and they can be mutated in-place by C code. For the function and scalar slots (`user.eval`, `user.split`, `numy`, `numresp`, `parms`), plain dict entries or `SimpleNamespace` attributes are sufficient.

`numpy` is chosen as the primary library because:
- R's `integer(n)` and `double(n)` produce zero-initialized fixed-length typed vectors. `numpy.zeros(n, dtype=np.int32)` and `numpy.zeros(n, dtype=np.float64)` are the direct equivalents, preserving type semantics and C-contiguous memory layout.
- `numpy` arrays can be passed by reference into C extensions, matching the in-place mutation pattern the C layer relies on.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Dynamic key, shared module-level environment

**Locations:** `plot.rpart.R`, function `plot.rpart`

**Original R Context**

`parms` is a named list (Python: `dict`). The key is an `integer` scalar returned by `dev.cur()`. `rpart_env` is an R environment declared at package scope. The assignment stores `parms` under a device-specific name so that other functions can retrieve it later.

```r
# In zzz.R (package load time):
rpart_env <- new.env()

# In plot.rpart:
parms <- list(uniform = uniform, branch = branch,
              nspace = nspace, minbranch = minbranch)
assign(paste0("device", dev.cur()), parms, envir = rpart_env)
```

Input types: key — `character`; value — named `list`; target — package-level `environment`.
Return value: `parms`, invisibly (not used by the caller).

**Python Equivalent**

```python
import numpy as np

# In a module-level initialization (equivalent of zzz.R):
rpart_env: dict = {}

# Placeholder for the active graphics device identifier.
# In a headless/non-interactive Python port this is typically a fixed
# integer or a matplotlib figure number.
def dev_cur() -> int:
    """Return the current device number (matplotlib figure number, or 1)."""
    import matplotlib.pyplot as plt
    managers = plt.get_fignums()
    return managers[-1] if managers else 1

# In plot_rpart:
def plot_rpart(x, uniform=False, branch=1, compress=False,
               nspace=None, margin=0, minbranch=0.3,
               branch_col=1, branch_lty=1, branch_lwd=1):
    # ... plotting logic ...
    parms = {
        "uniform": uniform,
        "branch": branch,
        "nspace": nspace,
        "minbranch": minbranch,
    }
    # R: assign(paste0("device", dev.cur()), parms, envir = rpart_env)
    key = f"device{dev_cur()}"
    rpart_env[key] = parms
```

**Explanation**

- `paste0("device", dev.cur())` becomes the f-string `f"device{dev_cur()}"`. Both produce a string like `"device1"`.
- `assign(key, value, envir = rpart_env)` is `rpart_env[key] = value`. A Python `dict` is the natural analog of an R environment used purely as a key-value store.
- No `numpy` is needed here because the value is a small parameter dict, not a numeric array.

---

### 4.2 Pattern B — Populating an isolated environment as a C callback namespace

**Locations:** `rpartcallback.R`, function `rpartcallback`, lines 100–108

**Original R Context**

`nobs` is an integer scalar (number of observations). `numy` is an integer scalar (number of response columns). `numresp` is an integer scalar. `parms` is a user-supplied list. `user.eval` and `user.split` are R function objects.

The nine `assign` calls collectively initialize a fresh environment `rho` that is then passed to a C routine. The buffer variables (`nback`, `wback`, `xback`, `yback`) are zero-initialized typed vectors whose memory will be overwritten repeatedly by the C layer.

```r
rho <- new.env()
assign("nback",      integer(1L),         envir = rho)
assign("wback",      double(nobs),        envir = rho)
assign("xback",      double(nobs),        envir = rho)
assign("yback",      double(nobs * numy), envir = rho)
assign("user.eval",  user.eval,           envir = rho)
assign("user.split", user.split,          envir = rho)
assign("numy",       numy,                envir = rho)
assign("numresp",    numresp,             envir = rho)
assign("parms",      parms,               envir = rho)
.Call(C_init_rpcallback, rho, as.integer(numy), as.integer(numresp),
      expr1, expr2)
```

Input types: buffer variables — zero-initialized integer/double vectors; config variables — scalars, list, callables.
Return value: each `assign` call returns its value invisibly; the return values are not used.

**Python Equivalent**

```python
import numpy as np
import types

def rpartcallback(mlist, nobs, init):
    user_eval  = mlist["eval"]
    user_split = mlist["split"]

    numresp = init["numresp"]
    numy    = init["numy"]
    parms   = init["parms"]

    # ... build expr1 / expr2 callables ...

    # R: rho <- new.env()
    # A SimpleNamespace acts as a named-attribute container analogous to
    # an R environment; attributes are mutable and addressable by name.
    rho = types.SimpleNamespace()

    # R: assign("nback", integer(1L), envir = rho)
    # integer(1L) -> zero-initialized int32 array of length 1
    rho.nback = np.zeros(1, dtype=np.int32)

    # R: assign("wback", double(nobs), envir = rho)
    # double(nobs) -> zero-initialized float64 array of length nobs
    rho.wback = np.zeros(nobs, dtype=np.float64)

    # R: assign("xback", double(nobs), envir = rho)
    rho.xback = np.zeros(nobs, dtype=np.float64)

    # R: assign("yback", double(nobs * numy), envir = rho)
    rho.yback = np.zeros(nobs * numy, dtype=np.float64)

    # R: assign("user.eval",  user.eval,  envir = rho)
    # R: assign("user.split", user.split, envir = rho)
    # Python attribute names cannot contain dots; use underscores.
    rho.user_eval  = user_eval
    rho.user_split = user_split

    # R: assign("numy",    numy,    envir = rho)
    # R: assign("numresp", numresp, envir = rho)
    # R: assign("parms",   parms,   envir = rho)
    rho.numy    = int(numy)
    rho.numresp = int(numresp)
    rho.parms   = parms

    # Pass rho to the C extension (the extension reads/writes the numpy
    # arrays in rho.nback, rho.wback, rho.xback, rho.yback in-place).
    # C_init_rpcallback(rho, int(numy), int(numresp), expr1, expr2)
    return {"expr1": expr1, "expr2": expr2, "rho": rho}
```

**Explanation**

- `new.env()` becomes `types.SimpleNamespace()`. A `SimpleNamespace` is a lightweight object whose attributes can be set and read by name at runtime, closely matching R's environment semantics. A plain `dict` would also work but requires bracket access (`rho["nback"]`) instead of attribute access (`rho.nback`); attribute access matches the R `.` accessor style more naturally and is what any Python C extension would expect when accessing named fields via the Python C API.
- `integer(1L)` — R's zero-initialized integer vector of length 1 — maps to `np.zeros(1, dtype=np.int32)`. Using `numpy` rather than `[0]` ensures the C extension can receive a typed, contiguous memory buffer.
- `double(n)` — R's zero-initialized double vector of length `n` — maps to `np.zeros(n, dtype=np.float64)`, preserving IEEE 754 double precision and C-contiguous layout for in-place C mutation.
- R variable names containing dots (e.g., `user.eval`, `user.split`) are renamed with underscores (`user_eval`, `user_split`) because dots are not valid in Python identifiers.
- Scalar integers (`numy`, `numresp`) are stored as Python `int` via `int(...)` rather than single-element numpy arrays, because R scalars in configuration roles do not need buffer semantics and are never mutated by the C layer.
- `parms` is stored as-is (a Python `dict` equivalent to R's named list), since it is consumed as a read-only parameter object by `user.eval` and `user.split`.
