# Conversion Guide: `eval` in R to Python

---

## 1. Overview of `eval` in R

`eval` is a base R function that evaluates an R expression (typically a language object, call, name, or symbol) in a specified environment. Its signature is:

```r
eval(expr, envir = parent.frame(),
     enclos = if(is.list(envir) || is.pairlist(envir))
                  parent.frame() else baseenv())
```

**Arguments:**
- `expr`: The object to evaluate. This is most commonly an unevaluated call or symbol captured via `match.call()`, `sys.call()`, or direct indexing into a call object (e.g., `oc[[2L]]`, `oc$newdata`).
- `envir`: The environment in which to evaluate `expr`. Defaults to `parent.frame()` (the calling frame). Can also be a list, data frame, or `NULL`.
- `enclos`: When `envir` is a list or data frame, `enclos` provides the enclosing environment for variable lookups not found in `envir`.

**Return value:** The result of evaluating `expr` — this can be any R object (data frame, model object, another call, etc.).

`eval` is central to R's metaprogramming system. In the rpart package it is used to recover actual runtime objects from stored call objects — a pattern that has no direct single-function equivalent in Python, because Python does not store calls as first-class language objects in the same way.

---

## 2. Contextual Usage Analysis

All four usages occur in the single function `model.frame.rpart` in `rpart/R/model.frame.rpart.R`. The function receives an rpart model object as `formula` and reconstructs the model frame used to fit or predict from it.

The variable `oc` is always a **call object** — it is `formula$call`, the unevaluated R call that was captured when the rpart model was originally constructed (or when `predict` was called). Elements of a call object are themselves unevaluated language objects (symbols or nested calls); `eval` is used here to force their evaluation and retrieve the underlying runtime values.

**Recurring pattern:** The pattern `eval(oc$argname)` or `eval(oc[[index]])` is R's idiomatic way of saying "look up the symbol stored in position `argname` (or `index`) of this call, and evaluate it in the calling environment to get the actual value". This is a metaprogramming / late-binding pattern.

The four usages fall into three functionally distinct scenarios:

| Line | Call | Scenario |
|------|------|----------|
| 7 | `eval(oc$newdata)` | Evaluate a named argument symbol from a stored call to get a data frame |
| 9 | `eval(oc$object)` | Evaluate a named argument symbol from a stored call to get a model object |
| 15 | `eval(oc[[2L]])` | Evaluate the first positional argument of a nested call to unwrap the call chain |
| 18 | `eval(oc)` | Evaluate the entire reconstructed call object to re-execute a function call |

**Data types:** `eval(oc$newdata)` returns a data frame; `eval(oc$object)` returns a fitted rpart model object; `eval(oc[[2L]])` returns whatever the intermediate wrapped call returns (another model object whose `$call` is then inspected); `eval(oc)` returns a model frame (the result of the reconstructed `rpart` call with modified arguments).

---

## 3. Python Conversion Strategy

Python does not have a native equivalent of R's call objects or `eval` on language objects. However, the **intent** of each usage can be reproduced using standard Python patterns:

- **Storing and passing arguments by reference:** Python functions receive live objects, not unevaluated expressions. Arguments do not need to be "evaluated" — they are already bound values. The equivalent of `eval(oc$newdata)` is simply referencing the variable or attribute directly.
- **Re-executing a function call:** The equivalent of `eval(oc)` (evaluating a modified call object) is constructing a dict of keyword arguments and calling the function with `**kwargs`.
- **Unwrapping a call chain:** The equivalent of the `while` loop that calls `eval(oc[[2L]])` is traversing a chain of Python objects via attributes or a stored callable reference.

Because the `eval` usages here are all metaprogramming patterns (not numeric/array operations), **no NumPy or SciPy equivalent applies**. The Python conversion uses only built-in Python constructs: direct attribute access, `callable(**kwargs)`, and explicit call chains.

---

## 4. Step-by-Step Conversion Examples

---

### 4.1 Evaluating a Named Argument Symbol (Lines 7 and 9)

**Locations:**
- `model.frame.rpart.R` — function `model.frame.rpart`, lines 7 and 9.

**Original R Context:**

```r
# oc is formula$call — the captured call object from predict(object, newdata=...)
# oc$newdata is an unevaluated symbol/expression; eval forces its resolution
m <- eval(oc$newdata)       # returns the data frame passed as newdata
object <- eval(oc$object)   # returns the rpart model object passed as object
```

- Input: `oc` is a `call` object (class `"call"`); `oc$newdata` and `oc$object` are unevaluated symbols within that call.
- Return type: `eval(oc$newdata)` returns a `data.frame`; `eval(oc$object)` returns an rpart model object (a named list).

**Python Equivalent:**

```python
# In Python, a function receives live objects directly — no deferred evaluation.
# The Python equivalent of storing and later evaluating a call's named arguments
# is to store them explicitly in a dict or as attributes on a context object.

class PredictCallContext:
    """Stores the arguments that were passed to predict(), mirroring R's stored call object."""
    def __init__(self, obj, newdata):
        self.object = obj      # the fitted rpart model (Python object)
        self.newdata = newdata  # the new data (pandas DataFrame)

def model_frame_rpart(formula, **kwargs):
    m = formula.get("model")
    if m is not None:
        return m

    oc = formula.get("call")  # a PredictCallContext or similar dict

    if oc.is_predict_call:
        # R: m <- eval(oc$newdata)
        m = oc.newdata          # direct attribute access replaces eval()

        if not hasattr(m, "rpart_terms"):
            # R: object <- eval(oc$object)
            object_ = oc.object     # direct attribute access replaces eval()
            m = model_frame(object_["terms"], m, na_rpart)

        return m
```

**Explanation:**

In R, `formula$call` is a language object capturing the unevaluated source expression of the original function call; `eval(oc$newdata)` traverses from symbol to value. In Python, function arguments are bound to values at call time — there is no deferred expression to evaluate. The direct replacement is attribute access (`oc.newdata`, `oc.object`) or dictionary lookup (`oc["newdata"]`). No special library is needed.

---

### 4.2 Evaluating a Positional Argument to Unwrap a Nested Call Chain (Line 15)

**Locations:**
- `model.frame.rpart.R` — function `model.frame.rpart`, line 15.

**Original R Context:**

```r
# This while loop walks up the call chain until it finds the innermost rpart call.
# oc[[1L]] is the function name (a symbol); oc[[2L]] is the first argument (another call).
# eval(oc[[2L]]) evaluates that nested call, returning an intermediate model object
# whose $call is then inspected on the next iteration.

while (!deparse(oc[[1L]]) %in% c("rpart", "rpart::rpart", "rpart:::rpart"))
    oc <- eval(oc[[2L]])$call
```

- Input: `oc` is a `call` object; `oc[[2L]]` is the first positional argument — itself a call expression (e.g., a call to a wrapper function that itself called `rpart`).
- Return type of `eval(oc[[2L]])`: A model/fitted object (a named list) whose `$call` element is the next call in the chain.

**Python Equivalent:**

```python
# In Python, the equivalent "call chain" is represented by a linked list of context
# objects or by storing a reference to the originating callable and its arguments.

RPART_FUNC_NAMES = {"rpart", "rpart::rpart", "rpart:::rpart"}

def unwrap_to_rpart_call(oc):
    """
    Walk up the call context chain until we reach the innermost rpart call context.

    Each 'oc' is expected to be a CallContext with:
      - oc.func_name: str — name of the function called
      - oc.first_arg_call: callable or CallContext — the first positional argument,
        which may itself be a call context or a callable that returns a model object
    """
    while oc.func_name not in RPART_FUNC_NAMES:
        # R: oc <- eval(oc[[2L]])$call
        # Evaluate the first positional argument (another call/model), then get its call context
        intermediate_model = oc.first_arg_call()   # call the stored callable
        oc = intermediate_model.call_context        # equivalent of $call
    return oc
```

**Explanation:**

`oc[[2L]]` in R is the first argument of the call (R uses 1-based indexing; index 1 is the function name, index 2 is the first argument). `eval(oc[[2L]])` executes that argument-expression and produces the intermediate object. In Python there is no such lazy call representation; instead, the design must either store a callable (closure) or the intermediate object directly. The `while` loop logic and the chain-traversal structure are preserved exactly; only the mechanism of "evaluating" changes from R's `eval` to Python's direct invocation or attribute lookup.

---

### 4.3 Evaluating a Reconstructed Call Object (Line 18)

**Locations:**
- `model.frame.rpart.R` — function `model.frame.rpart`, line 18.

**Original R Context:**

```r
# After finding the innermost rpart call, its arguments are patched in-place
# and the entire modified call is re-executed to produce the model frame.

oc$subset <- names(formula$where)
oc$method <- formula$method
eval(oc)   # re-executes the modified rpart(...) call; returns a model frame
```

- Input: `oc` is a `call` object with class `"call"`. It has been modified to add/override the `subset` and `method` arguments.
- Return type: The return value of `rpart(...)` with the patched arguments — a model frame (data frame with a `"terms"` attribute).

**Python Equivalent:**

```python
import rpart  # hypothetical Python rpart module

def rebuild_and_call_rpart(oc, formula):
    """
    Equivalent of patching an R call object and calling eval(oc).

    'oc' here is a dict of keyword arguments originally passed to rpart(),
    reconstructed from the stored call context.
    """
    # R: oc$subset <- names(formula$where)
    oc["subset"] = list(formula["where"].keys())

    # R: oc$method <- formula$method
    oc["method"] = formula["method"]

    # R: eval(oc)
    # Re-execute rpart() with the patched arguments
    func = oc.pop("_func")   # the callable (rpart function), stored separately
    return func(**oc)
```

**Explanation:**

In R, a `call` object is both a description of the function to call and its argument list; `eval(oc)` after in-place mutation re-runs the call with the new arguments. In Python, the idiomatic equivalent is to maintain a dict of keyword arguments (`oc` as `dict`) and call the target function with `func(**oc)` after updating the relevant keys. The `_func` key (or a separate variable) holds a reference to the callable (the rpart fitting function). The pattern `oc["key"] = value; func(**oc)` is a direct and readable Python translation of R's `oc$key <- value; eval(oc)`.

---

## Summary Table

| R pattern | Python equivalent |
|---|---|
| `eval(oc$argname)` | `oc.argname` or `oc["argname"]` — direct attribute/dict access |
| `eval(oc[[2L]])` | `oc.first_arg_call()` — invoke a stored callable or dereference an object |
| `eval(oc)` after mutation | `func(**oc)` — call a function with a keyword-argument dict |
| R call object (`call`) | Python `dict` of kwargs + a reference to the target callable |
| `match.call()` / `sys.call()` | Not needed in Python; arguments are live values at call time |
