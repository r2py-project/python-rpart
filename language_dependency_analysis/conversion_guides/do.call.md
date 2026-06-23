# Conversion Guide: `do.call` (R to Python)

---

## 1. Overview of `do.call` in R

`do.call` is a base-R function that calls a function by assembling its argument list from a pre-built list object rather than typing each argument individually at the call site.

**Signature:**

```r
do.call(what, args, quote = FALSE, envir = parent.frame())
```

**Parameters:**

- `what`: Either a function object or a character string naming the function to call.
- `args`: A named or unnamed list whose elements are passed as the positional and keyword arguments to `what`.
- `quote`: Logical. If `TRUE`, the arguments are not evaluated before the call (rarely used).
- `envir`: The environment in which to evaluate the call.

**Return value:**

Whatever `what(...)` returns when called with the arguments supplied in `args`. The return type therefore depends entirely on the called function.

**Core motivation:**

`do.call` is the idiomatic R way to invoke a function whose argument set is only known at runtime — for example, when extra arguments arrive through `...` and must be merged with a fixed argument list before the final call, or when a named list of control parameters must be "unpacked" and forwarded to a constructor function.

---

## 2. Contextual Usage Analysis

The two CSV occurrences represent two distinct patterns in which `do.call` is used inside the rpart source.

**Pattern A — merging a fixed argument list with runtime variadic arguments (`plotcp.R` line 20).**

Inside `plotcp`, the caller passes arbitrary extra graphical parameters through `...`. These are captured into `dots <- list(...)`. The call to `plot` requires several fixed positional and keyword arguments (`ns`, `xerror`, `axes`, `xlab`, `ylab`, `type`) that must appear alongside any user-supplied extras. `do.call(plot, c(list(...fixed...), dots))` concatenates the two lists into one and dispatches the merged list to `plot` in a single call. Without `do.call`, forwarding an unknown-length `dots` list to another function while also supplying fixed arguments would require awkward unpacking.

- `what`: `plot` (a base-R graphics function).
- `args`: a named list produced by `c(list(ns, xerror, axes = FALSE, xlab = "cp", ylab = "X-val Relative Error", type = "o"), dots)`.
- `ns`: integer vector (indices of cross-validation table rows).
- `xerror`: numeric vector (cross-validation relative errors).
- The remaining fixed args are scalars (logical / character).
- `dots`: a named list of zero or more additional graphical parameters.
- Return value: `NULL` (invisibly), called purely for its side effect of drawing a plot.

**Pattern B — unpacking a named control list into keyword arguments (`rpart.R` line 110).**

Inside `rpart`, the user may pass a pre-built named list `control` (e.g. `list(cp = 0.001, maxdepth = 5)`) instead of individual keyword arguments. `do.call(rpart.control, control)` treats each key-value pair in `control` as a named keyword argument to `rpart.control`, effectively doing `rpart.control(cp = 0.001, maxdepth = 5)`. This validates the supplied names and fills in defaults for any parameter not present in `control`.

- `what`: `rpart.control` (a package function that validates and returns a named list of tree-building parameters).
- `args`: `control`, a named list whose keys are a subset of `rpart.control`'s formal parameter names (`minsplit`, `minbucket`, `cp`, `maxcompete`, `maxsurrogate`, `usesurrogate`, `xval`, `surrogatestyle`, `maxdepth`).
- Return value: a named list of all control parameters with defaults applied for any key absent from `control`.

---

## 3. Python Conversion Strategy

Python's built-in `**` (double-star) unpacking operator is the direct and idiomatic equivalent for both patterns. When a function needs to be called with arguments stored in a dictionary, `func(**kwargs)` unpacks the dictionary as keyword arguments — exactly what `do.call(func, named_list)` does in R.

For Pattern A (merging fixed args with a variadic extras dict), Python additionally uses `{**fixed, **extras}` dictionary merging (available since Python 3.5) to combine the two argument sources before the call.

No third-party library (NumPy, pandas, etc.) is needed: `do.call` is a language-dispatch mechanism, not a numerical operation, so the translation is purely a Python language construct.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Merging fixed plot arguments with variadic extras

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/plotcp.R`, function `plotcp`, line 20.

**Original R context:**

```r
# dots is a named list of zero or more extra graphical parameters
# captured from the caller's ... arguments:
#   dots <- list(...)
#
# ns      -- integer vector, length = number of CP table rows
# xerror  -- numeric vector, same length as ns
# Fixed args: axes=FALSE, xlab="cp", ylab="X-val Relative Error", type="o"

do.call(plot, c(list(ns, xerror, axes = FALSE, xlab = "cp",
                     ylab = "X-val Relative Error", type = "o"), dots))
```

Input types:
- `ns`: integer vector.
- `xerror`: numeric vector of the same length.
- Fixed keyword arguments: logical / character scalars.
- `dots`: named list, size and contents determined at runtime.

Return type: `NULL` (invisible); called for its side effect of drawing a plot.

**Python equivalent:**

```python
import matplotlib.pyplot as plt

# ns      -- list or 1-D array of int, indices of CP table rows
# xerror  -- list or 1-D array of float, cross-validation relative errors
# dots    -- dict of extra keyword arguments supplied by the caller (**kwargs)

def plotcp(x, minline=True, lty="dashed", col="black", upper="size", **dots):
    # ... earlier setup code ...

    fixed_args = dict(
        axes=False,       # axes=FALSE in R  -> handled manually below
        xlab="cp",
        ylab="X-val Relative Error",
        marker="o",       # type="o" in R means points + lines
        linestyle="-",
    )

    # Merge fixed args with caller-supplied extras, letting extras override.
    # Equivalent to: c(list(...fixed...), dots)  then passed to do.call(plot, ...)
    plot_kwargs = {**fixed_args, **dots}

    plt.plot(ns, xerror, **plot_kwargs)
    # Remaining axis / annotation calls follow...
```

**Explanation:**

- `{**fixed_args, **dots}` is the Python equivalent of `c(list(...fixed...), dots)` — it merges two dictionaries, with `dots` taking precedence on key collisions (matching R's list-concatenation behavior where later elements overwrite earlier ones for duplicate names).
- `plt.plot(ns, xerror, **plot_kwargs)` corresponds to `do.call(plot, merged_list)`. The `**` operator unpacks the merged dictionary as keyword arguments, exactly replicating what `do.call` does with a named list.
- R's `plot(x, y, type = "o")` draws lines with points. The closest Matplotlib equivalent is `marker="o", linestyle="-"`.
- The `axes = FALSE` argument in R suppresses automatic axis drawing; in Matplotlib, axes are always present by default, so the translation must handle axis visibility separately (e.g. `ax.set_axis_off()` or by manually controlling tick labels).

---

### 4.2 Unpacking a named control list into a constructor call

**Locations:** `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`, function `rpart`, line 110.

**Original R context:**

```r
# control is a named list supplied by the user, e.g.:
#   control = list(cp = 0.001, maxdepth = 5)
# Its keys must be a subset of rpart.control()'s formal parameters.
#
# rpart.control() signature (rpart/R/rpart.control.R):
#   rpart.control(minsplit=20L, minbucket=round(minsplit/3), cp=0.01,
#                 maxcompete=4L, maxsurrogate=5L, usesurrogate=2L,
#                 xval=10L, surrogatestyle=0L, maxdepth=30L, ...)

if (!missing(control)) {
    if (!all(names(control) %in% names(controls)))
        stop("unknown named elements in 'control'")
    controls <- do.call(rpart.control, control)
}
```

Input types:
- `control`: a named list; keys are a subset of `rpart.control`'s parameter names; values are scalars of the appropriate type (integer, numeric, logical).

Return type: a named list (dict in Python) containing all nine validated control parameters with defaults filled in for any key absent from `control`.

**Python equivalent:**

```python
def rpart_control(minsplit=20, minbucket=None, cp=0.01,
                  maxcompete=4, maxsurrogate=5, usesurrogate=2,
                  xval=10, surrogatestyle=0, maxdepth=30):
    """Python equivalent of R's rpart.control()."""
    if minbucket is None:
        minbucket = round(minsplit / 3)
    # ... validation logic ...
    return dict(minsplit=minsplit, minbucket=minbucket, cp=cp,
                maxcompete=maxcompete, maxsurrogate=maxsurrogate,
                usesurrogate=usesurrogate, surrogatestyle=surrogatestyle,
                maxdepth=maxdepth, xval=xval)


def rpart(formula, data, control=None, ...):
    # ... earlier setup ...

    controls = rpart_control()   # apply defaults first

    if control is not None:
        valid_keys = set(controls.keys())
        unknown = set(control.keys()) - valid_keys
        if unknown:
            raise ValueError(f"Unknown named elements in 'control': {unknown}")

        # do.call(rpart.control, control)  -->  rpart_control(**control)
        controls = rpart_control(**control)

    # ...
```

**Explanation:**

- `rpart_control(**control)` is the direct Python equivalent of `do.call(rpart.control, control)`. The `**` operator unpacks the dictionary `control` as named keyword arguments, so `rpart_control(**{"cp": 0.001, "maxdepth": 5})` is identical to `rpart_control(cp=0.001, maxdepth=5)`.
- The pre-call validation (`if (!all(names(control) %in% names(controls)))`) is replicated by checking `set(control.keys()) - valid_keys` before the unpacking call. Without this guard, Python would raise a `TypeError` on an unexpected keyword argument anyway, but the explicit check produces a more informative error message that matches R's behavior.
- There is no need for any import: `**` unpacking is a core Python language feature available in all versions >= 3.5.
- Note that `rpart_control` has a computed default (`minbucket = round(minsplit/3)`). Python does not support expression-based defaults in function signatures, so the `None`-sentinel pattern shown above handles this correctly, exactly as R's `round(minsplit/3)` is evaluated at call time.
