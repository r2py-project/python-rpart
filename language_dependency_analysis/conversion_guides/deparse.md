# Conversion Guide: `deparse` (R to Python)

---

## 1. Overview of `deparse` in R

`deparse()` converts an unevaluated R expression object (a language object) into a character string that is the textual source-code representation of that object. It is, conceptually, the inverse of `parse()`.

**Signature:**
```r
deparse(expr, width.cutoff = 60L, backtick = mode(expr) %in% c("call", "expression", "(", "function"),
        control = c("keepNA", "keepInteger", "niceNames", "showAttributes"), nlines = -1L)
```

**Key parameters:**
- `expr`: Any R object — most commonly a language object (a `call`, a `symbol`/`name`, or an expression). In the rpart usages, this is always a `call` or a `name` extracted from a stored call object (`$call`).
- `width.cutoff`: A lower-bound on the number of bytes per output line before a line break is inserted (default 60).
- `nlines`: Maximum number of output lines; `-1` means unlimited.

**Return value:** A character vector. For simple symbols and short calls it is a length-1 character vector containing the plain source-code string, e.g. `"rpart"`, `"predict"`, or `"my_tree"`.

**Typical use cases:**
- Converting a stored function-call object to a human-readable string for comparison or display.
- Converting a `substitute()`-captured symbol to a string (e.g. to build a default filename from an argument name).

---

## 2. Contextual Usage Analysis

There are two distinct usage patterns across the three CSV rows:

### Pattern A — Inspecting the head of a stored call object (`oc[[1L]]`)

Locations: `model.frame.rpart.R`, function `model.frame.rpart`, lines 6 and 14.

`formula$call` is the unevaluated call that was used to construct the rpart model (e.g. `rpart(Species ~ ., data = iris)`). In R, `[[1L]]` on a call object retrieves the *function name* as a `name`/`symbol` object. `deparse()` converts that symbol to a plain string such as `"rpart"`, `"predict"`, or `"rpart::rpart"`.

- Line 6 uses the string for a prefix check (`substring(..., 1L, 7L) == "predict"`).
- Line 14 uses the string for a membership check (`. %in% c("rpart", "rpart::rpart", "rpart:::rpart")`).

The input to `deparse` is always a `name`/`symbol` object (a single identifier), so the output is always a length-1 character vector.

### Pattern B — Converting a `substitute()`-captured argument name to a string

Location: `post.rpart.R`, function `post.rpart`, line 3.

`substitute(tree)` captures the *unevaluated expression* that the caller passed as the `tree` argument — in practice a bare variable name such as `my_model`. `deparse()` then converts that symbol to the string `"my_model"`, which is used to build the default PostScript filename: `"my_model.ps"`.

The input is always a `name`/`symbol`, and the output is a length-1 character vector containing the variable name as a string.

**Recurring pattern across all usages:** `deparse` is applied exclusively to `name`/`symbol` objects (never to complex nested calls), so its output is always a single, short, whitespace-free string. No multi-line deparsing concerns arise.

---

## 3. Python Conversion Strategy

Because all three usages produce a plain string from an already-known Python object (a string, function reference, or variable name), there is no single universal Python library equivalent to `deparse`. Instead, the conversion is context-dependent:

| R idiom | Python equivalent |
|---|---|
| `deparse(oc[[1L]])` where `oc` is a stored call and `oc[[1L]]` is its function name | The function name is already stored as a plain Python string in an equivalent call-record structure; access it directly. |
| `deparse(substitute(x))` to get an argument's name as a string | Python has no `substitute()`, so the caller must pass the name explicitly, or use introspection via the `inspect` module. |

No `numpy`, `scipy`, or `pandas` import is needed — these usages are pure string/introspection operations.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Pattern A — Checking the function name of a stored call (lines 6 and 14)

**Locations:** `rpart/R/model.frame.rpart.R`, function `model.frame.rpart`, lines 6 and 14.

**Original R Context:**

In R, an rpart model object stores the originating call as `model$call`. Indexing a `call` object with `[[1L]]` yields the function-name `name` object; `deparse()` converts it to a string.

```r
# oc is a language object: the stored call, e.g. quote(rpart(y ~ x, data = df))
# oc[[1L]] is the symbol `rpart`
# deparse(oc[[1L]]) returns the string "rpart"

# Line 6: prefix check
if (substring(deparse(oc[[1L]]), 1L, 7L) == "predict") { ... }

# Line 14: membership check
while (!deparse(oc[[1L]]) %in% c("rpart", "rpart::rpart", "rpart:::rpart"))
    oc <- eval(oc[[2L]])$call
```

Input type: `name` (R language symbol).
Return type: `str` of length 1 (e.g. `"rpart"`, `"predict.rpart"`).

**Python Equivalent:**

In the Python translation of rpart, the stored call equivalent is a plain Python dict (or object) that records the function name as a string. There is no language object to deparse — the name is already a string.

```python
# Assume `oc` is a dict representing the stored call, e.g.:
# oc = {"func": "rpart", "formula": ..., "data": ..., "subset": ..., "method": ...}

# Line 6 equivalent: prefix check
func_name = oc["func"]  # already a plain Python string, no deparse needed
if func_name[:7] == "predict":
    ...

# Line 14 equivalent: membership check
while oc["func"] not in {"rpart", "rpart::rpart", "rpart:::rpart"}:
    oc = eval_call(oc["args"][0]).call  # traverse the call chain
```

**Explanation:**
- R's `deparse(oc[[1L]])` extracts and stringifies the function-name symbol from a language object. In Python the equivalent call record stores the function name as a plain `str` from the outset, so no conversion step is needed.
- R's `substring(s, 1L, 7L)` uses 1-based, inclusive indices. The Python equivalent is the slice `s[:7]` (0-based, exclusive end).
- R's `%in%` operator maps to Python's `in` operator (or `not in` for the negated form). Using a `set` literal (`{...}`) instead of a `list` is idiomatic and slightly faster for membership tests.

---

### 4.2 Pattern B — Building a default filename from an argument's name (line 3)

**Location:** `rpart/R/post.rpart.R`, function `post.rpart`, line 3.

**Original R Context:**

`substitute(tree)` captures the unevaluated symbol that the caller passed as the `tree` argument (e.g. if the caller wrote `post.rpart(my_model)`, `substitute(tree)` yields the symbol `my_model`). `deparse()` converts that symbol to the string `"my_model"`, which becomes the stem of the default PostScript filename.

```r
post.rpart <- function(tree, title.,
    filename = paste(deparse(substitute(tree)), ".ps", sep = ""),
    ...)
{
    # If called as post.rpart(my_model), filename defaults to "my_model.ps"
    ...
}
```

Input type: `name` produced by `substitute()` — captures the caller's expression.
Return type: `str` of length 1 (the variable name as written by the caller).

**Python Equivalent:**

Python has no `substitute()` mechanism. The standard Pythonic approach is to require the caller to supply the name explicitly when a default derived from the argument name is needed, or to use the `inspect` module to retrieve it from the call stack as a best-effort approximation.

**Option 1 (recommended): explicit `filename` parameter with `None` sentinel**

```python
import inspect

def post_rpart(tree, title=None, filename=None, digits=None, pretty=True,
               use_n=True, horizontal=True, **kwargs):
    if filename is None:
        # Attempt to recover the caller's variable name via inspect
        frame = inspect.currentframe().f_back
        # find the name of the variable passed as `tree` in the caller's locals
        caller_locals = frame.f_locals
        tree_name = next(
            (name for name, val in caller_locals.items() if val is tree),
            "tree"  # fallback if the argument was not a simple variable reference
        )
        filename = f"{tree_name}.ps"
    ...
```

**Option 2 (simpler): caller passes the name explicitly**

```python
def post_rpart(tree, title=None, filename=None, digits=None, pretty=True,
               use_n=True, horizontal=True, **kwargs):
    if filename is None:
        filename = "tree.ps"  # fixed fallback; caller supplies filename= when needed
    ...
```

**Explanation:**
- R's `substitute()` is a non-standard evaluation (NSE) mechanism that operates at parse time inside the function body. Python has no equivalent; it evaluates all arguments before the function body executes.
- `inspect.currentframe().f_back.f_locals` lets you inspect the calling frame's local variables at runtime, but it only reliably recovers the name when the caller passed a simple bare variable (not an expression). This mirrors `deparse(substitute(...))` for the common case.
- The `f"{tree_name}.ps"` f-string is the direct equivalent of R's `paste(deparse(substitute(tree)), ".ps", sep = "")`.
- Option 1 is preferred when faithful name recovery is important (e.g. for user-facing output filenames). Option 2 is preferred when the filename parameter is almost always supplied explicitly by the caller.
