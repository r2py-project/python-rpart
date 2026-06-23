### 1. Overview of `match.call` in R

`match.call()` is a base R function that captures the call to the currently-executing function as an unevaluated language object of class `call`. When invoked inside a function body, it returns a complete, name-matched representation of how that function was invoked — meaning every argument is recorded with its full formal name, not as a positional or partially-matched name.

**Signature:**
```r
match.call(definition = sys.function(sys.parent()),
           call = sys.call(sys.parent()),
           expand.dots = TRUE,
           envir = parent.frame(2L))
```

**Key characteristics:**
- Returns an object of class `call` (an unevaluated R language object).
- All arguments in the returned call are identified by their full formal parameter names.
- Subsetting the result with `[` or `[[` lets callers extract individual argument expressions from the captured call for forwarding to other functions (e.g., `model.frame`).
- Only works inside interpreted functions (closures), not primitive functions.
- Has two canonical use cases in model-fitting packages: (1) storing the call expression on the fitted object for display/reproducibility, and (2) extracting and re-routing a subset of the arguments to a helper like `model.frame`.

---

### 2. Contextual Usage Analysis

**File:** `rpart/R/rpart.R`
**Function:** `rpart` (lines 4–298)

`match.call()` appears on line 8, immediately upon entry into the `rpart` function:

```r
Call <- match.call()
```

The captured call object `Call` is then used in two distinct ways throughout the function body:

**Use 1 — Argument extraction and forwarding to `model.frame` (lines 13–19):**

```r
indx <- match(c("formula", "data", "weights", "subset"),
              names(Call), nomatch = 0L)
if (indx[1] == 0L) stop("a 'formula' argument is required")
temp <- Call[c(1L, indx)]        # keep only the desired arguments
temp$na.action <- na.action      # inject a default argument
temp[[1L]] <- quote(stats::model.frame)  # replace the function name
m <- eval.parent(temp)           # evaluate the modified call
```

Here `Call` is treated as a list-like language object. Its `names()` return the argument names; subsetting it with integer indices produces a sub-call; element replacement with `[[1L]]` swaps the function symbol; and `eval.parent()` executes the modified call in the parent frame. This is a standard R pattern for delegating data preparation to `model.frame` without re-specifying arguments.

**Use 2 — Storing the call on the fitted object (line 273):**

```r
ans <- list(frame = frame,
            where = where,
            call = Call, ...)
```

The captured `Call` is embedded in the returned `rpart` object under the key `call`. This allows users to later inspect — e.g., via `print.rpart` or `update()` — exactly how the model was fitted, reproducing the original invocation.

**Data type summary:**
- Input: no arguments are required; it captures the enclosing call automatically.
- Output: an object of class `call`, which behaves similarly to a named list of unevaluated R expressions. `names(Call)` returns a character vector of argument names; `Call[[i]]` returns individual argument expressions.

---

### 3. Python Conversion Strategy

R's `match.call()` has no single direct Python equivalent because Python functions do not natively carry unevaluated call expressions. The idiom must be decomposed into its two functional roles:

**Role 1 — Storing the call for introspection/reproducibility:**
Python's `inspect` module provides `inspect.currentframe()` and `inspect.stack()`, but these do not recover the original source call the way R does. The idiomatic Python substitute is to capture the function's bound arguments using `inspect.signature` and `inspect.BoundArguments`. For model-fitting classes (the primary rpart use case), the standard Python convention is to store constructor arguments as instance attributes (e.g., `self.formula`, `self.data`), which achieves the same goal of reproducibility without needing a raw call expression.

**Role 2 — Forwarding a subset of arguments to a helper function:**
R's call-manipulation pattern (`Call[c(1L, indx)]`, `temp[[1L]] <- quote(...)`, `eval.parent(temp)`) translates directly to Python dictionary construction and ordinary function calls. The equivalent is to collect the desired arguments into a `dict` and unpack them with `**kwargs` when calling the helper.

**Library choice:** `inspect` (standard library) covers introspection. For a faithful model-class implementation, plain Python instance attribute storage is preferred over any third-party library. No `numpy` or `scipy` is needed for this particular dependency.

---

### 4. Step-by-Step Conversion Examples

#### 4.1 — Storing the Call on the Fitted Object

**Locations:** `rpart.R`, function `rpart`, line 8 and line 273.

**Original R Context:**

Inputs to `match.call()`: none (it captures its enclosing call implicitly). Output type: `call` object (language expression). The returned value is stored as-is on the model object for later display.

```r
# Types: Call is of class 'call' (language object)
rpart <- function(formula, data, weights, subset,
                  na.action = na.rpart, method,
                  model = FALSE, x = FALSE, y = TRUE,
                  parms, control, cost, ...) {
    Call <- match.call()  # capture full, name-matched invocation
    # ... (fitting logic) ...
    ans <- list(
        frame   = frame,
        call    = Call,   # store the call expression on the result
        # ...
    )
    class(ans) <- "rpart"
    ans
}
```

**Python Equivalent:**

```python
import inspect

class Rpart:
    def __init__(
        self,
        formula,
        data,
        weights=None,
        subset=None,
        na_action=None,
        method=None,
        model=False,
        x=False,
        y=True,
        parms=None,
        control=None,
        cost=None,
        **kwargs,
    ):
        # Capture the call: bind the actual arguments to the formal parameters.
        sig = inspect.signature(self.__init__)
        bound = sig.bind(
            formula, data,
            weights=weights, subset=subset, na_action=na_action,
            method=method, model=model, x=x, y=y,
            parms=parms, control=control, cost=cost,
            **kwargs,
        )
        bound.apply_defaults()
        # Store a human-readable representation of the call,
        # mirroring R's `call = Call` on the ans list.
        self.call = {k: v for k, v in bound.arguments.items()}

        # ... (fitting logic populates self.frame, self.where, etc.) ...

    def __repr__(self):
        args_str = ", ".join(
            f"{k}={v!r}" for k, v in self.call.items()
            if v is not None
        )
        return f"Rpart({args_str})"


# Usage
import pandas as pd
data = pd.DataFrame({"y": [1, 0, 1], "x": [2.0, 3.0, 1.5]})
model = Rpart(formula="y ~ x", data=data)
print(model.call)
# {'formula': 'y ~ x', 'data': <DataFrame>, 'model': False, ...}
```

**Explanation:**

- R's `match.call()` returns a `call` object that names every argument by its formal parameter name, including those passed positionally. `inspect.signature` + `BoundArguments.apply_defaults()` replicates this: every parameter (including defaulted ones not supplied by the caller) is captured.
- R stores the call on `ans$call` in a plain list; in Python the natural home for this is a class attribute (`self.call`) holding a dictionary of `{parameter_name: value}` pairs.
- R's `call` object stores unevaluated *expressions*; Python stores already-evaluated values. For model introspection this difference is generally inconsequential — the goal is knowing what arguments were passed, which a dict satisfies.
- `**kwargs` is included to mirror R's `...` (dots), which `match.call()` captures when `expand.dots=TRUE` (the default).

---

#### 4.2 — Extracting and Forwarding Arguments to a Helper (`model.frame` pattern)

**Locations:** `rpart.R`, function `rpart`, lines 13–19.

**Original R Context:**

After capturing `Call`, the code extracts only the `formula`, `data`, `weights`, and `subset` entries from it, injects `na.action`, replaces the function symbol with `stats::model.frame`, and evaluates the result. Input types: `Call` is a `call` object; `indx` is an integer vector of matching positions; the output is a data frame `m` returned by `model.frame`.

```r
# Types:
#   Call   : call  (language object, list-like)
#   indx   : integer vector
#   temp   : call  (modified sub-call)
#   m      : data.frame (result of model.frame)

indx <- match(c("formula", "data", "weights", "subset"),
              names(Call), nomatch = 0L)
if (indx[1] == 0L) stop("a 'formula' argument is required")
temp <- Call[c(1L, indx)]
temp$na.action <- na.action
temp[[1L]] <- quote(stats::model.frame)
m <- eval.parent(temp)
```

**Python Equivalent:**

```python
import pandas as pd

def _build_model_frame(
    formula: str,
    data: pd.DataFrame,
    weights=None,
    subset=None,
    na_action=None,
) -> pd.DataFrame:
    """
    Python equivalent of:
        temp <- Call[c(1L, indx)]
        temp$na.action <- na.action
        temp[[1L]] <- quote(stats::model.frame)
        m <- eval.parent(temp)

    Constructs a 'model frame': a DataFrame containing only the columns
    referenced by the formula, optionally filtered and with NAs handled.
    """
    # Step 1: replicate Call[c(1L, indx)] — keep only the desired arguments.
    desired_args = {}
    if formula is None:
        raise ValueError("a 'formula' argument is required")
    desired_args["formula"] = formula
    if data is not None:
        desired_args["data"] = data
    if weights is not None:
        desired_args["weights"] = weights
    if subset is not None:
        desired_args["subset"] = subset

    # Step 2: replicate temp$na.action <- na.action
    desired_args["na_action"] = na_action

    # Step 3: replicate temp[[1L]] <- quote(stats::model.frame)
    #         i.e., call model_frame with the assembled arguments.
    return _model_frame(**desired_args)


def _model_frame(
    formula: str,
    data: pd.DataFrame,
    weights=None,
    subset=None,
    na_action=None,
) -> pd.DataFrame:
    """
    Simplified Python analogue of stats::model.frame.
    Extracts the columns named in the formula and applies subset / na handling.
    """
    import re

    # Parse column names from a simple "y ~ x1 + x2" formula string.
    lhs, rhs = formula.replace(" ", "").split("~")
    response = [lhs]
    predictors = [t for t in re.split(r"[+\-\*]", rhs) if t and t != "."]
    columns = response + predictors

    # Apply subset filter.
    if subset is not None:
        data = data.loc[subset]

    frame = data[columns].copy()

    # Apply NA action.
    if na_action == "na.omit" or na_action is None:
        frame = frame.dropna()

    # Attach weights as a column if provided.
    if weights is not None:
        frame["(weights)"] = weights

    return frame


# --- Usage (mirrors the rpart internal flow) ---
import pandas as pd

data = pd.DataFrame({
    "y":       [1,   0,   1,   None],
    "x1":      [2.0, 3.0, 1.5, 4.0],
    "x2":      [0.1, 0.2, 0.3, 0.4],
    "weights": [1.0, 1.0, 2.0, 1.0],
})

m = _build_model_frame(
    formula="y ~ x1 + x2",
    data=data,
    weights=data["weights"],
    na_action="na.omit",
)
print(m)
#      y   x1   x2  (weights)
# 0  1.0  2.0  0.1        1.0
# 1  0.0  3.0  0.2        1.0
# 2  1.0  1.5  0.3        2.0
```

**Explanation:**

- R's `names(Call)` enumerates argument names from the captured call; in Python the same information is available directly from the function's local variables and their formal names, so a plain `if arg is not None` guard selects which arguments to forward.
- R's `Call[c(1L, indx)]` is an in-place subsetting of the call object to drop unneeded arguments before forwarding. Python replaces this with building a `desired_args` dict containing only the chosen keys — semantically identical, syntactically straightforward.
- R's `temp[[1L]] <- quote(stats::model.frame)` replaces the function symbol in the call object; in Python this is simply a direct call to the target function (`_model_frame(**desired_args)`), which requires no symbolic manipulation.
- R's `eval.parent(temp)` executes the modified call in the parent frame (to resolve variable references from the caller's scope). Python's default scoping rules make this unnecessary: function arguments are already resolved values at call time.
- R's `na.action` parameter accepts a function or name like `na.rpart`; in Python the simplest equivalent is a string sentinel (`"na.omit"`) or a callable, depending on how generalized the implementation needs to be.
