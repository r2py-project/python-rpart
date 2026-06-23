### 1. Overview of `formals` in R

`formals()` is a base R introspection function that retrieves the **formal argument list** of a function object. Given a function as its sole required argument, it returns a named `pairlist` (a special R list type) whose names are the parameter names of the function and whose values are the corresponding default expressions (or an empty symbol `""` if no default exists).

- **Input:** A function object (e.g., `rpart.control`).
- **Output:** A named `pairlist` of length equal to the number of formal parameters. Calling `names()` on the result yields a character vector of the parameter names.

---

### 2. Contextual Usage Analysis

In `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`, `formals` appears at line 96 inside the `rpart` function body:

```r
extraArgs <- list(...)
if (length(extraArgs)) {
    controlargs <- names(formals(rpart.control))  # legal arg names
    indx <- match(names(extraArgs), controlargs, nomatch = 0L)
    if (any(indx == 0L))
        stop(gettextf("Argument %s not matched",
                      names(extraArgs)[indx == 0L]),
             domain = NA)
}
```

The pattern and data types involved are:

- `rpart.control` is a **function object** passed as the argument to `formals()`.
- `formals(rpart.control)` returns a **named pairlist** of all formal parameters of `rpart.control`.
- `names(formals(rpart.control))` extracts only the **parameter names** as a **character vector** (e.g., `c("minsplit", "minbucket", "cp", "maxcompete", ...)`).
- The resulting character vector (`controlargs`) is used as a **whitelist of legal argument names** against which the extra `...` arguments supplied to `rpart()` are validated via `match()`.

The sole purpose here is **introspective parameter validation**: retrieve the names of all valid parameters of `rpart.control`, then confirm that any extra user-supplied arguments are members of that set. No default values from the pairlist are used — only the names.

---

### 3. Python Conversion Strategy

The best Python equivalent is the **`inspect` module** from the standard library, specifically `inspect.signature()` or `inspect.getfullargspec()`.

**Why `inspect` over other options:**

- `inspect.signature(func)` returns a `Signature` object whose `.parameters` attribute is an ordered mapping of parameter names to `Parameter` objects. This is a direct structural analog to R's named pairlist returned by `formals()`.
- `inspect.getfullargspec(func)` provides a simpler flat list of argument names (`args`, `varargs`, `varkw`, `defaults`, etc.), which is convenient when only the names are needed.
- Both handle default values, which mirrors `formals()` returning both names and defaults.
- No third-party library (numpy, pandas, scipy) is appropriate here because `formals()` in this context is a **metaprogramming/introspection** operation, not a mathematical or data-manipulation one.

For the specific pattern in `rpart.R` — extracting only parameter names for membership testing — `inspect.signature()` is preferred because it handles keyword-only arguments, `*args`, and `**kwargs` cleanly and is the modern idiomatic approach.

---

### 4. Step-by-Step Conversion Examples

#### Usage: Validate extra keyword arguments against a function's legal parameter names

**Locations:**
- File: `rpart.R`
- Function: `rpart`

**Original R Context:**

- Input: `rpart.control` — a function object.
- `formals(rpart.control)` — returns a named pairlist; the names are the legal parameter names of `rpart.control`.
- `names(formals(rpart.control))` — a character vector of those parameter names.
- The result is used with `match()` to validate that every name in `extraArgs` (the `...` passed to `rpart`) is a recognized parameter of `rpart.control`.

Generalized R snippet:

```r
# extraArgs is a named list of extra keyword arguments
extraArgs <- list(...)
if (length(extraArgs)) {
    controlargs <- names(formals(rpart.control))   # character vector of legal param names
    indx <- match(names(extraArgs), controlargs, nomatch = 0L)
    if (any(indx == 0L))
        stop(gettextf("Argument %s not matched",
                      names(extraArgs)[indx == 0L]),
             domain = NA)
}
```

**Python Equivalent:**

```python
import inspect

def rpart_control(minsplit=20, minbucket=None, cp=0.01, maxcompete=4,
                  maxsurrogate=5, usesurrogate=2, xval=10,
                  surrogatestyle=0, maxdepth=30):
    # ... body of rpart_control ...
    pass


def rpart(formula, data, weights=None, subset=None,
          na_action=None, method=None, model=False,
          x=False, y=True, parms=None, control=None,
          cost=None, **extra_args):

    # Validate that any extra keyword arguments are legal parameters of rpart_control
    if extra_args:
        # Get the set of legal parameter names from rpart_control
        sig = inspect.signature(rpart_control)
        control_args = set(sig.parameters.keys())  # analogous to names(formals(rpart.control))

        illegal = [k for k in extra_args if k not in control_args]
        if illegal:
            raise ValueError(f"Argument(s) not matched: {', '.join(illegal)}")

    # Proceed with building controls from extra_args ...
```

**Explanation:**

| R | Python | Notes |
|---|--------|-------|
| `formals(rpart.control)` | `inspect.signature(rpart_control)` | Both retrieve the full formal parameter specification of a function. R returns a named pairlist; Python returns a `Signature` object. |
| `names(formals(rpart.control))` | `sig.parameters.keys()` | Both extract just the parameter names. `sig.parameters` is an `OrderedDict`-like mapping; `.keys()` gives the names. Convert to `set` for O(1) membership testing. |
| `match(names(extraArgs), controlargs, nomatch=0L)` | `[k for k in extra_args if k not in control_args]` | R's `match()` returns positional indices with `0` for non-matches; the Python list comprehension directly collects the unrecognized keys. |
| `...` captured as `list(...)` | `**extra_args` captured as a `dict` | R's `...` and Python's `**kwargs` both collect arbitrary extra keyword arguments. |
| `any(indx == 0L)` | `if illegal:` | Both check whether any unrecognized arguments were supplied. |

One nuance: `inspect.signature()` includes `*args` and `**kwargs` parameters as entries in `.parameters` (with `kind` attributes `VAR_POSITIONAL` and `VAR_KEYWORD`). If `rpart_control` accepts `**kwargs`, those would appear in the keys. In practice, `rpart_control` in the rpart package has only named parameters with defaults and no `**kwargs`, so `sig.parameters.keys()` directly mirrors `names(formals(rpart.control))` without any filtering needed. If filtering is ever required, it can be done with:

```python
control_args = {
    name
    for name, param in sig.parameters.items()
    if param.kind not in (
        inspect.Parameter.VAR_POSITIONAL,
        inspect.Parameter.VAR_KEYWORD,
    )
}
```
