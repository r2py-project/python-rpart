# Conversion Guide: `environment` (R to Python)

---

## 1. Overview of `environment` in R

`environment()` is a base R function that operates on the environment (scope) associated with a function object (closure). It has two distinct forms:

**Getter form — `environment(fun)`**

Returns the environment that is attached to the function `fun`. Every R function carries a reference to the environment in which it was defined; that environment is called its *enclosing environment* or *closure environment*. When `fun` is `NULL` (or omitted), `environment()` returns the *current* evaluation environment — i.e., the frame in which the call itself is being evaluated.

**Assignment form — `environment(fun) <- env`**

Replaces the enclosing environment of `fun` with `env`. Any subsequent name lookups inside `fun` that escape its local frame will search `env` rather than the original defining environment.

Key characteristics:

- **Input (getter):** A function object, a formula, or `NULL`.
- **Input (assignment):** A function object (left-hand side) and an environment object (right-hand side).
- **Return value (getter):** An environment object, or the current environment when called with no argument.
- **Side effect (assignment):** Mutates the enclosing environment of the supplied function in-place.

---

## 2. Contextual Usage Analysis

All five usages appear inside the `rpart` function in `/groups/jli9/Yufei/python-rpart/rpart/R/rpart.R`, lines 69–77.

**Lines 69 and 72 — getter used as an `envir` argument**

```r
init <- if (missing(parms))
    get(paste("rpart", method, sep = "."),
        envir = environment())(Y, offset, , wt)
else
    get(paste("rpart", method, sep = "."),
        envir = environment())(Y, offset, parms, wt)
```

Here `environment()` is called with no argument, so it returns the *current* evaluation frame of `rpart`. That frame is passed to `get()` as the search scope, directing R to look up a symbol such as `"rpart.anova"` starting from the local variables and enclosing scopes of `rpart` itself, rather than from the global environment or an arbitrary namespace. The return value is an environment object used purely as a lookup scope.

**Lines 75–77 — assignment form used to rebind closure environments**

```r
ns <- asNamespace("rpart")
if (!is.null(init$print))   environment(init$print)   <- ns
if (!is.null(init$summary)) environment(init$summary) <- ns
if (!is.null(init$text))    environment(init$text)    <- ns
```

`init` is a list returned by one of the `rpart.<method>` initialisation functions. Its `$print`, `$summary`, and `$text` fields are R function objects (closures). The assignment form replaces each function's enclosing environment with the `"rpart"` package namespace (`ns`). The stated purpose (see the comment on line 73) is to *avoid saving the full execution environment on the fitted model object* — by rebinding the closures to the package namespace, serialisation of the `rpart` result object no longer drags along the large local frame of `rpart`.

**Data types involved:**

| Expression | Type |
|---|---|
| `environment()` (no arg) | Returns `environment` object (current frame) |
| `environment(init$print)` | Returns `environment` object (the closure's enclosing env) |
| `environment(init$print) <- ns` | Mutates the closure's enclosing env; no return value consumed |
| `ns` (`asNamespace("rpart")`) | `environment` object (a package namespace) |
| `init$print`, `init$summary`, `init$text` | `function` objects (closures) or `NULL` |

**Recurring pattern:** Both usage groups serve environment-manipulation purposes that are intrinsic to R's object model. There is no scalar/vector arithmetic involved; all operands are first-class R environment and function objects.

---

## 3. Python Conversion Strategy

R's `environment` concept maps onto Python's built-in object model rather than onto any numerical library like `numpy` or `scipy`. The relevant Python primitives are:

| R concept | Python equivalent |
|---|---|
| Environment object | `dict` or a module object / `types.ModuleType` |
| Current evaluation environment | `locals()` / `globals()` (read-only snapshots) or explicit `dict` scopes |
| Closure's enclosing environment | `func.__globals__` (the global scope the function was compiled against) or cells in `func.__closure__` |
| `environment(fun) <- ns` | Rebinding `func.__globals__` is not supported natively; the closest idiom is recreating the function with `types.FunctionType` pointing at a new globals dict |
| `asNamespace("rpart")` | Importing the Python package/module: `import rpart; module = rpart` |
| `get("rpart.anova", envir=environment())` | `locals()["rpart_anova"]` or simply referencing the name directly if it is in scope |

Because all usages are about *scope manipulation* rather than numerical computation, `numpy`/`scipy`/`pandas` are not relevant here.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Getter — obtaining the current scope for dynamic lookup (lines 69, 72)

**Locations:** `rpart/R/rpart.R`, function `rpart`, lines 67–72.

**Original R context**

```r
# method is a string such as "anova", "poisson", "class", or "exp".
# get() looks up "rpart.anova" (etc.) starting from the current frame.
init <- if (missing(parms))
    get(paste("rpart", method, sep = "."),
        envir = environment())(Y, offset, , wt)
else
    get(paste("rpart", method, sep = "."),
        envir = environment())(Y, offset, parms, wt)
```

- `environment()` returns the current frame so `get()` can find local or package-level symbols.
- The result of `get(...)` is a function, which is immediately called.

**Python equivalent**

```python
import importlib
import sys

# In Python the equivalent of get("rpart.anova", envir=environment()) is a
# straightforward dictionary lookup in the local or module namespace.

# Option A — look up within the current module's global namespace
# (mirrors the R behaviour when the symbol is defined at package scope)
method_func_name = f"rpart_{method}"   # e.g. "rpart_anova"
method_func = globals()[method_func_name]

# Call the resolved function (parms may be None to signal "missing")
if parms is None:
    init = method_func(Y, offset, None, wt)
else:
    init = method_func(Y, offset, parms, wt)
```

**Explanation**

- `paste("rpart", method, sep=".")` becomes an f-string `f"rpart_{method}"` (dots in Python identifiers are replaced by underscores).
- `get(..., envir=environment())` — looking up a name in the current R frame — becomes `globals()[method_func_name]` when the target functions live at module scope, or `locals()[method_func_name]` for truly local symbols. In practice, since `rpart_anova` etc. are module-level functions, `globals()` is the correct choice.
- The empty positional argument (`,`) in `(Y, offset, , wt)` is not valid Python syntax; pass `None` explicitly as a sentinel for "missing parms".
- No import of `numpy` or any numerical library is needed; this is pure name resolution.

---

### 4.2 Assignment form — rebinding a closure's enclosing environment to a namespace (lines 75–77)

**Locations:** `rpart/R/rpart.R`, function `rpart`, lines 74–77.

**Original R context**

```r
# ns is the "rpart" package namespace (an environment object).
ns <- asNamespace("rpart")

# init$print, init$summary, init$text are function objects returned by
# the rpart.<method> initialiser.  They may be NULL.
if (!is.null(init$print))   environment(init$print)   <- ns
if (!is.null(init$summary)) environment(init$summary) <- ns
if (!is.null(init$text))    environment(init$text)    <- ns
```

The assignment strips each closure's reference to the large local frame of `rpart` and replaces it with the lean package namespace, preventing that frame from being serialised into the fitted model object.

**Python equivalent**

```python
import types
import sys

# Retrieve the rpart module (equivalent of asNamespace("rpart"))
rpart_module_globals = vars(sys.modules[__name__])
# or, if calling from outside the package:
# import rpart as _rpart_mod
# rpart_module_globals = vars(_rpart_mod)

def rebind_closure_globals(func, new_globals: dict):
    """
    Return a copy of `func` whose __globals__ dict is replaced with
    `new_globals`.  This mirrors R's  environment(func) <- ns  idiom.
    Python functions' __globals__ cannot be reassigned in-place, so a
    new function object must be constructed.
    """
    return types.FunctionType(
        func.__code__,
        new_globals,
        func.__name__,
        func.__defaults__,
        func.__closure__,
    )

# Apply only when the field is not None (mirrors R's !is.null check)
if init.get("print") is not None:
    init["print"] = rebind_closure_globals(init["print"], rpart_module_globals)

if init.get("summary") is not None:
    init["summary"] = rebind_closure_globals(init["summary"], rpart_module_globals)

if init.get("text") is not None:
    init["text"] = rebind_closure_globals(init["text"], rpart_module_globals)
```

**Explanation**

- **`asNamespace("rpart")` → `vars(sys.modules[__name__])`** — `asNamespace` retrieves the package namespace environment; `vars(module)` returns an equivalent writable dict of all names defined in a Python module. `sys.modules[__name__]` is the currently executing module, which is the package-level analogue.
- **`environment(fun) <- ns` → `rebind_closure_globals(fun, new_globals)`** — Python function objects expose `__globals__` as a read-only attribute; the underlying dict can be mutated but the attribute itself cannot be reassigned. The idiomatic workaround is to construct a new `types.FunctionType` from the same `__code__` object but with a different globals dict. This achieves the same effect: future name lookups inside the function that escape its local frame will now search `new_globals` rather than the original compilation-time globals.
- **`!is.null(init$print)` → `init.get("print") is not None`** — R's `NULL` maps to Python's `None`; the `if not None` guard mirrors `!is.null`.
- **Serialisation motivation** — Python's `pickle` serialises a function by recording its qualified name, not its closure variables, so the memory-saving motivation is less acute than in R. Nevertheless, explicitly rebinding globals to a lean module dict is still a valid technique for controlling which names a function can reach at runtime.
- **No `numpy`/`scipy`** — This conversion involves no numeric computation whatsoever. The only imports needed are `types` and `sys`, both from the Python standard library.
