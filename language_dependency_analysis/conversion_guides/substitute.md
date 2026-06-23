# Conversion Guide: `substitute` (R to Python)

---

## 1. Overview of `substitute` in R

`substitute(expr, env)` is a **non-standard evaluation (NSE)** primitive in R. Instead of evaluating `expr`, it returns the **parse tree** (an unevaluated language object) for the expression passed in, optionally substituting any symbols that are bound in `env` with their corresponding values.

**Signature:**
```r
substitute(expr, env)
```

**Key parameters:**
- `expr`: Any syntactically valid R expression. It is never evaluated; R captures it as an abstract syntax tree (AST) node.
- `env`: An environment or named list used for substitution. Defaults to the current evaluation environment. When `env` is the global environment (`.GlobalEnv`), symbols are left unchanged (no substitution occurs).

**Return value:** A language object — one of:
- `name` (mode `"name"`) when `expr` is a bare symbol (identifier), e.g. `substitute(tree)` called inside a function returns the symbol the caller passed as `tree`.
- `call` (mode `"call"`) when `expr` is a function call expression, e.g. `substitute(x + y)`.
- A constant of the appropriate base mode when `expr` is a literal value.

**How it differs from `quote()`:**

| Feature | `quote(expr)` | `substitute(expr)` |
|---|---|---|
| Captures expression | Yes | Yes |
| Performs symbol substitution | No — returns `expr` verbatim | Yes — replaces bound symbols with their values from `env` |
| Typical context | Top-level (global) code | Inside a function body, to capture what the *caller* passed |

**Primary use case in rpart:** Called inside a function body as `substitute(arg_name)` where `arg_name` is a formal parameter. This captures the expression the *caller* typed for that argument, most commonly a bare variable name. The result is then converted to a character string with `deparse()` to build default filenames, labels, or messages.

---

## 2. Contextual Usage Analysis

There is one usage of `substitute` in the rpart package CSV:

**Location:** `rpart/R/post.rpart.R`, function `post.rpart`, line 3.

The full function signature is:

```r
post.rpart <- function(tree, title.,
    filename = paste(deparse(substitute(tree)), ".ps", sep = ""),
    digits = getOption("digits") - 2, pretty = TRUE,
    use.n = TRUE, horizontal = TRUE, ...)
```

`substitute(tree)` appears in the **default value expression** for the `filename` parameter. When the caller does not supply `filename`, R evaluates this default expression in the context of the function call. At that moment, `substitute(tree)` captures the *unevaluated expression* the caller passed as the `tree` argument.

**Concrete example:**

```r
# Caller writes:
post.rpart(my_fitted_model)

# Inside the default expression:
# substitute(tree)  →  the symbol `my_fitted_model`  (a `name` object)
# deparse(...)      →  the string "my_fitted_model"
# paste(..., ".ps", sep = "")  →  "my_fitted_model.ps"
```

**Data types involved:**
- Input to `substitute`: a formal parameter name (`tree`) — R captures whatever expression the caller supplied.
- The caller's expression is invariably a simple bare variable name (a `name`/symbol object), not a complex call.
- Return type of `substitute(tree)`: a `name` object (mode `"name"`).
- Return type of the full `deparse(substitute(tree))` idiom: a `character` vector of length 1 containing the variable name as a plain string.

**Recurring pattern:** `substitute` never appears in isolation in rpart. It is always nested immediately inside `deparse()` to form the `deparse(substitute(x))` idiom, which is R's idiomatic way to convert a function argument's *name* (as written by the caller) into a string. See also the `deparse` conversion guide at `language_dependency_analysis/conversion_guides/deparse.md` (Pattern B, section 4.2) for a parallel discussion.

---

## 3. Python Conversion Strategy

Python **has no equivalent of `substitute()`**. The fundamental reason is architectural: R's NSE mechanism operates at the level of the language parser — a function can inspect the unevaluated parse tree of its arguments before they are evaluated. Python always evaluates all arguments before entering the function body, so by the time the function receives a value, the originating variable name has been discarded.

The chosen Python conversion strategy depends on how important faithful name recovery is for the specific use case:

| Scenario | Recommended Python approach |
|---|---|
| Default filename/label built from argument name; exact name recovery is nice-to-have | `None` sentinel + `inspect` module for best-effort name lookup |
| Default filename/label; caller is expected to supply it explicitly | `None` sentinel with a fixed fallback string |
| Production use where exact caller-name recovery is critical | Require the caller to pass the name as an explicit string parameter |

For the rpart `post.rpart` use case, the `inspect`-based approach (Option 1 below) best preserves the original behaviour, while the explicit-parameter approach (Option 2) is more robust and Pythonic.

No `numpy`, `scipy`, or `pandas` import is needed — this is a pure string introspection operation.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Building a default filename from an argument's variable name

**Location:** `rpart/R/post.rpart.R`, function `post.rpart`, line 3.

**Original R Context:**

Input type: `tree` is an rpart model object (an R `list` of class `"rpart"`). The `substitute(tree)` call does not inspect the *value* of `tree`; it captures the *expression* the caller typed — in practice always a bare variable name.

Return type of `substitute(tree)`: a `name` object.
Return type of `deparse(substitute(tree))`: a `character` vector of length 1, e.g. `"my_model"`.

```r
# Generalised snippet showing the full default-argument mechanism:
post.rpart <- function(tree, title.,
    filename = paste(deparse(substitute(tree)), ".ps", sep = ""),
    ...)
{
    # If the caller wrote: post.rpart(my_model)
    # then filename defaults to: "my_model.ps"
    ...
}
```

**Python Equivalent — Option 1 (recommended): `inspect`-based name recovery**

```python
import inspect

def post_rpart(tree, title=None, filename=None, digits=None, pretty=True,
               use_n=True, horizontal=True, **kwargs):
    """
    Python equivalent of R's post.rpart().

    When `filename` is not supplied, attempts to recover the caller's
    variable name for `tree` via inspect — mirroring R's
    deparse(substitute(tree)) idiom.
    """
    if filename is None:
        # Walk up one frame to the caller's local scope.
        caller_frame = inspect.currentframe().f_back
        caller_locals = caller_frame.f_locals

        # Find the first local variable in the caller's scope whose
        # identity matches the object passed as `tree`.
        tree_name = next(
            (name for name, val in caller_locals.items() if val is tree),
            "tree"  # fallback when the argument was not a simple bare variable
        )
        filename = f"{tree_name}.ps"

    # ... remainder of the function (plot, save PostScript, etc.)
```

**Python Equivalent — Option 2 (simpler): explicit `None` sentinel with fixed fallback**

```python
def post_rpart(tree, title=None, filename=None, digits=None, pretty=True,
               use_n=True, horizontal=True, **kwargs):
    """
    Python equivalent of R's post.rpart().

    When `filename` is not supplied, falls back to the fixed name "tree.ps".
    Callers that need a custom filename should pass it explicitly.
    """
    if filename is None:
        filename = "tree.ps"

    # ... remainder of the function
```

**Explanation:**

1. **Why `substitute` has no direct Python equivalent.** R's `substitute()` is a *parser-level* primitive — it hooks into the call mechanism before argument evaluation. Python's calling convention evaluates all arguments to values before the callee's body runs, so the originating expression is irretrievably lost.

2. **`inspect.currentframe().f_back.f_locals` (Option 1).** The `inspect` module lets you inspect the calling frame's local variable table at runtime. Iterating over `f_locals.items()` and checking `val is tree` (object identity, not equality) finds the name of the variable the caller used — provided it was a simple bare variable reference. This mirrors `deparse(substitute(tree))` for the common case. It will silently fall back to `"tree"` when the caller passed an expression (e.g. `post_rpart(fit_models[0])`), which is acceptable since R's `deparse()` would produce something like `"fit_models[[1L]]"` rather than a clean filename stem in that situation anyway.

3. **`f"{tree_name}.ps"` vs. `paste(deparse(substitute(tree)), ".ps", sep = "")`.** The f-string is the direct Python equivalent of R's `paste(..., sep = "")`. R's `paste` with `sep = ""` concatenates without a separator, identical to Python's string concatenation or f-string interpolation.

4. **Option 2 trade-off.** Requiring an explicit `filename` is more Pythonic and robust (no frame introspection, no edge cases with expressions or aliased variables), but loses the convenience of the automatic name. For an internal rpart utility function like `post_rpart`, Option 2 is often the right production choice; Option 1 is useful during a faithful translation phase where behavioural parity with R is prioritised.
