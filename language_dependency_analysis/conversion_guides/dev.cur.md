# Conversion Guide: `dev.cur` (R to Python)

---

### 1. Overview of `dev.cur` in R

`dev.cur()` is part of R's `grDevices` package. It returns the **currently active graphics device** as a **length-one named integer vector**, where the integer is the device number and the name is the device type (e.g., `"RStudioGD"`, `"pdf"`, `"png"`). The null device (no active device) is represented by device number `1`.

Its primary use is to **identify which graphics device is currently open and active**, so that device-specific state, parameters, or metadata can be stored and retrieved using the device number as a key.

**Signature:**
```r
dev.cur()
# Returns: named integer vector of length 1, e.g., c(RStudioGD = 2)
```

**Key behavioural properties:**
- Returns `1` (the null device) when no graphics device is open.
- The returned integer uniquely identifies a device within the current R session.
- It is a pure query — it does not open, close, or modify any device.

---

### 2. Contextual Usage Analysis

Across all four call sites, `dev.cur()` is used in exactly one pattern: constructing a **per-device environment key** via `paste0("device", dev.cur())`. This string key is then used either to **store** plotting parameters into a shared environment (`rpart_env`) or to **retrieve** them. The logic forms a lightweight device-keyed cache so that functions called later (without explicit `parms` arguments) can look up the parameters that were active when the tree was originally plotted.

| File | Function | Line | Role |
|---|---|---|---|
| `plot.rpart.R` | `plot.rpart` | 23 | **Write:** stores `parms` into `rpart_env` under the key `"device<N>"` after opening the plot |
| `rpart.branch.R` | `rpart.branch` | 8 | **Read:** retrieves `parms` from `rpart_env` when the `branch` argument is missing |
| `rpartco.R` | `rpartco` | 5 | **Read:** retrieves `parms` from `rpart_env` when the `parms` argument is missing |
| `snip.rpart.mouse.R` | `snip.rpart.mouse` | 7 | **Read:** retrieves `parms` from `rpart_env` when the `parms` argument is missing |

The data type involved in every call is the same: the integer return value of `dev.cur()` is coerced to a string via `paste0`, producing keys such as `"device2"`. No arithmetic is performed on the device number; it is used purely as a unique token.

Because `dev.cur()` is a graphics-session concept tied to R's interactive device system, it has **no direct Python equivalent**. The Python translation must replicate the intent — a mutable, per-figure state store — using Python-native constructs.

---

### 3. Python Conversion Strategy

Python's `matplotlib` is the standard equivalent for R's graphics device system. A `matplotlib` figure is the closest analogue to an R graphics device:

- In R, `dev.cur()` returns an integer ID for the active device.
- In `matplotlib`, `matplotlib.pyplot.gcf()` returns the current `Figure` object, and `id(fig)` or `fig.number` provides a unique integer identifier.

The **recommended Python strategy** replaces the `rpart_env` dictionary keyed on `"device<N>"` with a plain Python `dict` keyed on `fig.number` (the matplotlib figure number, an integer analogous to the R device number). This preserves the exact semantics: each figure has its own parameter set, stored and retrieved by identity.

Where the rpart package uses:
```r
pn <- paste0("device", dev.cur())
assign(pn, parms, envir = rpart_env)   # store
get(pn, envir = rpart_env)             # retrieve
exists(pn, envir = rpart_env)          # check
```

The Python equivalent uses:
```python
import matplotlib.pyplot as plt

_rpart_device_parms: dict = {}         # module-level state store

fig_id = plt.gcf().number              # analogous to dev.cur()
_rpart_device_parms[fig_id] = parms   # store
parms = _rpart_device_parms[fig_id]   # retrieve
fig_id in _rpart_device_parms          # check
```

---

### 4. Step-by-Step Conversion Examples

#### 4.1 Writing Plot Parameters per Device — `plot.rpart`

**Location:** `rpart/R/plot.rpart.R`, function `plot.rpart`, line 23.

**Original R Context:**

- `dev.cur()` returns a named integer (e.g., `2`).
- `paste0("device", dev.cur())` produces the string key `"device2"`.
- `assign(key, parms, envir = rpart_env)` stores a named list of plotting parameters into a package-level environment, keyed by the active device number.

```r
# parms is a named list: list(uniform=..., branch=..., nspace=..., minbranch=...)
assign(paste0("device", dev.cur()), parms, envir = rpart_env)
```

**Python Equivalent:**

```python
import matplotlib.pyplot as plt

# Module-level state store (equivalent to rpart_env)
_rpart_device_parms: dict = {}

def plot_rpart(x, uniform=False, branch=1, compress=False,
               nspace=None, margin=0, minbranch=0.3,
               branch_col='black', branch_lty='solid', branch_lwd=1, **kwargs):
    # ... validation and coordinate computation ...

    parms = dict(uniform=uniform, branch=branch, nspace=nspace, minbranch=minbranch)

    # Store parms keyed by the current figure's number (analogous to dev.cur())
    fig = plt.gcf()
    _rpart_device_parms[fig.number] = parms

    # ... drawing logic ...
```

**Explanation:**
- `plt.gcf()` retrieves the currently active `matplotlib` Figure, mirroring `dev.cur()`.
- `fig.number` is `matplotlib`'s integer identifier for the figure, playing the same role as R's device number.
- A module-level `dict` replaces R's `rpart_env` environment; Python dicts are natively keyed by integers, eliminating the need for `paste0` string formatting.

---

#### 4.2 Reading Plot Parameters per Device — `rpart.branch`, `rpartco`, `snip.rpart.mouse`

**Locations:**
- `rpart/R/rpart.branch.R`, function `rpart.branch`, line 8.
- `rpart/R/rpartco.R`, function `rpartco`, line 5.
- `rpart/R/snip.rpart.mouse.R`, function `snip.rpart.mouse`, line 7.

**Original R Context:**

All three functions share identical guard logic: if an optional parameter (`branch` or `parms`) is not supplied by the caller, the function constructs the device key, verifies that parameters were stored for the current device, and retrieves them. If not found, an error is raised.

```r
# Runs when branch (or parms) argument is missing
pn <- paste0("device", dev.cur())
if (!exists(pn, envir = rpart_env, inherits = FALSE))
    stop("no information available on parameters from previous call to plot()")
parms <- get(pn, envir = rpart_env, inherits = FALSE)
branch <- parms$branch   # or use parms directly
```

**Python Equivalent:**

```python
import matplotlib.pyplot as plt

def rpart_branch(x, y, node, branch=None):
    if branch is None:
        fig_id = plt.gcf().number
        if fig_id not in _rpart_device_parms:
            raise RuntimeError(
                "no information available on parameters from previous call to plot()"
            )
        parms = _rpart_device_parms[fig_id]
        branch = parms['branch']

    # ... branch-drawing logic ...


def rpartco(tree, parms=None):
    if parms is None:
        fig_id = plt.gcf().number
        if fig_id not in _rpart_device_parms:
            raise RuntimeError(
                "no information available on parameters from previous call to plot()"
            )
        parms = _rpart_device_parms[fig_id]

    # ... coordinate computation ...


def snip_rpart_mouse(tree, parms=None):
    if parms is None:
        fig_id = plt.gcf().number
        if fig_id not in _rpart_device_parms:
            raise RuntimeError(
                "no information available on parameters from previous call to plot()"
            )
        parms = _rpart_device_parms[fig_id]

    # ... interactive snipping logic ...
```

**Explanation:**
- R's `missing(parms)` is translated to Python's `parms is None` with `None` as the sentinel default.
- R's `exists(pn, envir = rpart_env, inherits = FALSE)` maps to `fig_id in _rpart_device_parms`.
- R's `get(pn, envir = rpart_env, inherits = FALSE)` maps to `_rpart_device_parms[fig_id]`.
- R's `stop(...)` maps to Python's `raise RuntimeError(...)`.
- R's named-list field access `parms$branch` maps to Python dict access `parms['branch']`.
- Because `_rpart_device_parms` is a module-level dict, all functions share the same state store without needing to pass it explicitly — preserving the package-global semantics of `rpart_env`.

---

### Summary Table

| R construct | Python equivalent |
|---|---|
| `dev.cur()` | `matplotlib.pyplot.gcf().number` |
| `paste0("device", dev.cur())` | `plt.gcf().number` (integer key, no string formatting needed) |
| `assign(key, val, envir = rpart_env)` | `_rpart_device_parms[fig_id] = val` |
| `exists(key, envir = rpart_env, inherits = FALSE)` | `fig_id in _rpart_device_parms` |
| `get(key, envir = rpart_env, inherits = FALSE)` | `_rpart_device_parms[fig_id]` |
| `stop("...")` | `raise RuntimeError("...")` |
| `parms$branch` | `parms['branch']` |
