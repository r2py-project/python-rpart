# Conversion Guide: `on.exit` in R

## 1. Overview of `on.exit` in R

`on.exit` registers an expression to be evaluated when the enclosing function exits, regardless of whether the exit is normal (return) or caused by an error. It is R's idiomatic mechanism for guaranteed cleanup of side effects, analogous to a `finally` block in other languages.

**Signature:**
```r
on.exit(expr = NULL, add = FALSE, after = TRUE)
```

Key behaviours:
- The registered expression runs when the surrounding function scope exits — whether by a normal `return`, an unhandled condition, or a `stop()` call.
- `add = TRUE` appends the expression to any previously registered exit handler instead of replacing it.
- `after = TRUE` (the default) queues the new expression to run after any previously registered handlers.
- Calling `on.exit()` with no arguments cancels previously registered exit expressions.

Typical inputs: any valid R expression, most commonly a function call that reverses a side effect (close a device, restore graphics parameters, close a file sink).

Typical outputs: none — `on.exit` is used purely for its side effect of scheduling cleanup.

---

## 2. Contextual Usage Analysis

Across all four call sites in the rpart source, `on.exit` is used to guarantee resource cleanup for two classes of side effects:

**Graphics device / parameter management** (`post.rpart.R`, `roc.rpart.R`)

| Location | Registered expression | Trigger condition |
|---|---|---|
| `post.rpart`, line 10 | `dev.off()` | A PostScript device was opened with `postscript()` |
| `post.rpart`, line 13 | `invisible(par(oldpar))` | Graphics parameters were changed with `par(mar = ...)` |
| `roc.rpart`, line 60 | `par(o.par)` | Graphics parameters were changed with `par(pty = "s")` |

In all three cases the pattern is identical: a state-mutating call returns the previous state (e.g., `oldpar <- par(...)`) or opens a resource (e.g., `postscript()`), and `on.exit` is immediately called to schedule reversal.

**Text sink management** (`summary.rpart.R`)

| Location | Registered expression | Trigger condition |
|---|---|---|
| `summary.rpart`, line 11 | `sink()` | Output was redirected to a file with `sink(file)` |

`sink()` with no arguments closes the most recently opened text diversion, restoring output to the console.

Recurring pattern across all usages: `on.exit` is called immediately after the side-effecting operation, not at the end of the function. This ensures the cleanup is registered even if subsequent code raises an error.

---

## 3. Python Conversion Strategy

Python provides two native constructs that directly replace `on.exit`:

1. **`try / finally` blocks** — the `finally` clause runs unconditionally when the `try` block exits, whether normally or via an exception. This is the most direct semantic equivalent.
2. **Context managers (`with` statements)** — for resources that already implement `__enter__` / `__exit__` (e.g., file objects, `matplotlib` backends), a `with` block is the idiomatic Python pattern.

For `matplotlib` graphics parameter management (equivalent to R's `par()`), the `matplotlib.rcParams` context can be temporarily overridden using `matplotlib.rc_context()`. For output redirection (equivalent to R's `sink()`), Python's `contextlib.redirect_stdout` or manual `sys.stdout` reassignment inside a `try/finally` block is appropriate.

There is no single Python function that directly maps to `on.exit`. The translation must be structural: wrap the body of the R function in a `try/finally` block (or a `with` block where a context manager is available), placing the cleanup in `finally`.

---

## 4. Step-by-Step Conversion Examples

### 4.1 Closing a graphics device on exit

**Locations:** `post.rpart.R` — function `post.rpart`, line 10

**Original R Context:**

```r
# Return type of postscript(): NULL (side effect: opens a PS file device)
# Return type of dev.off(): integer device number (side effect: closes current device)
if (filename != "") {
    postscript(file = filename, horizontal = horizontal, ...)
    par(mar = c(2,2,4,2) + 0.1)
    on.exit(dev.off())
}
# ... plotting code ...
```

`dev.off()` takes no arguments in this context and closes the most recently opened graphics device. The expression registered with `on.exit` receives no inputs and produces no meaningful return value; it is called solely for the side effect of flushing and closing the PostScript file.

**Python Equivalent:**

```python
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.backends.backend_pdf as pdf_backend

def post_rpart(tree, title_=None, filename=None, digits=None,
               pretty=True, use_n=True, horizontal=True):
    if filename:
        fig, ax = plt.subplots()
        try:
            # configure margins equivalent to par(mar = c(2,2,4,2) + 0.1)
            fig.subplots_adjust(left=0.1, right=0.9, bottom=0.1, top=0.8)
            # ... plotting logic ...
            fig.savefig(filename)
        finally:
            plt.close(fig)   # equivalent to dev.off()
    else:
        # handled in section 4.2
        ...
```

**Explanation:**
- `plt.close(fig)` in the `finally` block is the direct equivalent of `dev.off()`: it releases the figure/device regardless of whether the plotting code raises an exception.
- Python's `matplotlib` does not have a global "current device" concept in the same way R does; the `fig` object is captured in the local scope and closed explicitly.

---

### 4.2 Restoring graphics parameters on exit

**Locations:** `post.rpart.R` — function `post.rpart`, line 13; `roc.rpart.R` — function `roc.rpart`, line 60

**Original R Context (`post.rpart`):**

```r
# par() with arguments: returns named list of previous values (scalars/vectors),
# sets new values as side effect.
# par() with a saved list: restores previous values, returns invisibly.
oldpar <- par(mar = c(2,2,4,2) + 0.1)
on.exit(invisible(par(oldpar)))
# ... plotting code ...
```

**Original R Context (`roc.rpart`):**

```r
o.par <- par(pty = "s")
on.exit(par(o.par))
# ... plotting code ...
```

Both usages follow the same pattern: `par()` returns the previous parameter values as a named list, and the exit handler re-applies that saved list to restore state.

**Python Equivalent:**

```python
import matplotlib
import matplotlib.pyplot as plt

def post_rpart_no_file(tree, ...):
    # Use rc_context to temporarily override rcParams, restoring them on exit
    with matplotlib.rc_context():
        # set margins equivalent to par(mar = c(2,2,4,2) + 0.1)
        plt.rcParams['figure.subplot.left']   = 0.10
        plt.rcParams['figure.subplot.right']  = 0.90
        plt.rcParams['figure.subplot.bottom'] = 0.10
        plt.rcParams['figure.subplot.top']    = 0.80
        # ... plotting logic ...
```

```python
def roc_rpart(obj, plot_ok=True, x_orient=1):
    # ...computation...
    if plot_ok:
        # "pty = 's'" forces a square plot area
        old_aspect = plt.rcParams.get('figure.subplot.left')  # save relevant param
        with matplotlib.rc_context({'axes.aspect': 'equal'}):
            # ... ROC plot logic ...
            pass
        # rc_context restores previous params automatically on __exit__
```

For more explicit save/restore without `rc_context`:

```python
import matplotlib.pyplot as plt

def roc_rpart_explicit(obj, plot_ok=True, x_orient=1):
    if plot_ok:
        saved_params = {
            'axes.aspect': plt.rcParams.get('axes.aspect', 'auto')
        }
        try:
            plt.rcParams['axes.aspect'] = 'equal'   # equivalent to par(pty="s")
            # ... plotting logic ...
        finally:
            plt.rcParams.update(saved_params)        # equivalent to par(o.par)
```

**Explanation:**
- `matplotlib.rc_context()` is a context manager that snapshots `rcParams` on entry and restores them on exit, exactly mirroring the R `par()` save-and-restore idiom.
- When a context manager is not convenient, the explicit `try/finally` with a saved dict mirrors the R pattern directly: save before, restore in `finally`.
- R's `pty = "s"` (square plot area) maps to `plt.rcParams['axes.aspect'] = 'equal'` or `ax.set_aspect('equal')` in matplotlib.
- R's `mar` (margin in lines) maps approximately to `fig.subplots_adjust()` or `plt.tight_layout()` with padding arguments.

---

### 4.3 Closing a text output sink on exit

**Locations:** `summary.rpart.R` — function `summary.rpart`, line 11

**Original R Context:**

```r
# sink(file): redirects all subsequent cat()/print() output to `file` (side effect).
# sink() with no arguments: pops the most recent output diversion, returning None.
if (!missing(file)) {
    sink(file)
    on.exit(sink())
}
# ... cat() / print() calls whose output goes to `file` ...
```

`sink(file)` redirects `stdout` to a file connection. `sink()` with no arguments closes the diversion and restores `stdout`. No return value is meaningful; both calls are used for side effects only.

**Python Equivalent:**

```python
import sys
import contextlib

def summary_rpart(obj, cp=0, digits=None, file=None):
    if file is not None:
        with open(file, 'w') as f:
            with contextlib.redirect_stdout(f):
                # all print() / sys.stdout.write() calls go to file
                _summary_rpart_body(obj, cp=cp, digits=digits)
    else:
        _summary_rpart_body(obj, cp=cp, digits=digits)
```

Alternatively, using `try/finally` for explicit control:

```python
import sys

def summary_rpart(obj, cp=0, digits=None, file=None):
    if file is not None:
        f = open(file, 'w')
        old_stdout = sys.stdout
        sys.stdout = f
        try:
            _summary_rpart_body(obj, cp=cp, digits=digits)
        finally:
            sys.stdout = old_stdout   # equivalent to sink()
            f.close()
    else:
        _summary_rpart_body(obj, cp=cp, digits=digits)
```

**Explanation:**
- `contextlib.redirect_stdout(f)` is the idiomatic Python equivalent of the R `sink(file)` / `on.exit(sink())` pair. It captures `sys.stdout` for the duration of the `with` block and restores it unconditionally on exit, matching the guaranteed cleanup semantics of `on.exit`.
- The explicit `try/finally` version makes the save-and-restore structure visible and is useful when the context manager form is not available or when the sink must span multiple functions.
- Unlike R's `sink()`, Python's `redirect_stdout` does not apply to C-level `stdout` writes (e.g., from extension modules); for those, OS-level redirection via `os.dup2` would be required, but that is not needed for pure Python `print()` / `sys.stdout` usage that mirrors R's `cat()` / `print()`.
