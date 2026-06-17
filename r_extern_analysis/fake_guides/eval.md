# Fake Header Implementation Guide: `eval`

> **R Interpreter Item.** `eval` (i.e., `Rf_eval`) requires a running R interpreter to function. It evaluates an R language object (expression or call) in an R environment by traversing R's environment frame chain, dispatching through R's internal evaluation loop, and potentially executing arbitrary R code. None of these mechanisms can be replicated without the R runtime. In the fake build, `eval` is implemented as a function pointer that Python registers via `ctypes.CFUNCTYPE` before invoking any `.Call` function that exercises the user-defined splitting code path (`method=4`).

---

### 1. Overview of `eval` in R API

`Rf_eval(SEXP expr, SEXP rho)` — aliased as `eval` via `#define eval Rf_eval` in `Rinternals.h` line 934 — takes an R language object `expr` (typically `LANGSXP`, an unevaluated function call) and an environment `rho` (`ENVSXP`), and returns the `SEXP` result of evaluating `expr` in `rho`. The function is declared in `~/.conda/envs/r-to-python/lib/R/include/Rinternals.h` at line 531 as:

```c
SEXP Rf_eval(SEXP, SEXP);
```

It is a core component of R's evaluation engine: it drives the interpreter loop, looks up symbols in the environment chain, dispatches S3/S4 method calls, and manages R's promise (`PROMSXP`) evaluation. Every path through `Rf_eval` assumes that R's internal global state — the evaluation stack (`R_EvalDepth`), the garbage collector root set, the symbol table, and the environment chain — is fully initialized. This is an **R Interpreter Item**: a complete fake is impossible.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart_callback.c` | 1–173 | Full file: static globals, `init_rpcallback`, `rpart_callback0`, `rpart_callback1`, `rpart_callback2` |

**Context window for the two CSV rows.**

The two `eval` call sites are in separate callback functions that are invoked internally by rpart's C core when `method=4` (user-defined splits):

```c
/* rpart_callback.c:88-120 — rpart_callback1: the "evaluation" callback */
void
rpart_callback1(int n, double *y[], double *wt, double *z)
{
    int i, j, k;
    SEXP value;
    double *dptr;

    /* Copy response data and weights into the shared back-arrays */
    for (i = 0, k = 0; i < ysave; i++)
        for (j = 0; j < n; j++)
            ydata[k++] = y[j][i];
    for (i = 0; i < n; i++)
        wdata[i] = wt[i];
    ndata[0] = n;

    /* no need to protect as no memory allocation (or error) below */
    value = eval(expr2, rho);         /* line 112 — CSV row 1 */
    if (!isReal(value))
        error(_("return value not a vector"));
    if (LENGTH(value) != (1 + rsave))
        error(_("returned value is the wrong length"));
    dptr = REAL(value);
    for (i = 0; i <= rsave; i++)
        z[i] = dptr[i];
}

/* rpart_callback.c:126-173 — rpart_callback2: the "split-goodness" callback */
void
rpart_callback2(int n, int ncat, double *y[], double *wt,
                double *x, double *good)
{
    int i, j, k;
    SEXP goodness;
    double *dptr;

    for (i = 0, k = 0; i < ysave; i++)
        for (j = 0; j < n; j++)
            ydata[k++] = y[j][i];
    for (i = 0; i < n; i++) {
        wdata[i] = wt[i];
        xdata[i] = x[i];
    }
    ndata[0] = (ncat > 0) ? -n : n;

    /* no need to protect as no memory allocation (or error) below */
    goodness = eval(expr1, rho);      /* line 146 — CSV row 2 */
    if (!isReal(goodness))
        error(_("the expression expr1 did not return a vector!"));
    j = LENGTH(goodness);
    dptr = REAL(goodness);

    if (ncat == 0) {
        if (j != 2 * (n - 1))
            error("the expression expr1 returned a list of %d elements, %d required",
                  j, 2 * (n - 1));
        for (i = 0; i < j; i++)
            good[i] = dptr[i];
    } else {
        good[0] = (j + 1) / 2;
        for (i = 0; i < j; i++)
            good[i + 1] = dptr[i];
    }
}
```

**C types of arguments and return values.**

| Argument | Declared type | Meaning at call site |
|---|---|---|
| `expr` (first) | `SEXP` | A language object (`LANGSXP`) stored in the static globals `expr2` (line 112) and `expr1` (line 146). These were received from R and stored by `init_rpcallback` at lines 56–57. |
| `rho` (second) | `SEXP` | An environment object (`ENVSXP`) stored in the static global `rho`. Received from R by `init_rpcallback` at line 53. |
| return value | `SEXP` | Stored in `SEXP value` (line 112) and `SEXP goodness` (line 146). Both are immediately tested with `isReal()` and accessed via `REAL()` and `LENGTH()`. Both must be `REALSXP` vectors. |

**Return value downstream usage.**

| Call site | Return stored in | Accessor applied | Result used for |
|---|---|---|---|
| `rpart_callback1`, line 112 | `SEXP value` | `isReal(value)`, `LENGTH(value)`, `REAL(value)` | Writes `value[0..rsave]` into `z[]` (the deviance/mean output array) |
| `rpart_callback2`, line 146 | `SEXP goodness` | `isReal(goodness)`, `LENGTH(goodness)`, `REAL(goodness)` | Writes into `good[]` (the split-goodness output array) |

**Co-occurring R API items in context windows.**

| Item | Line | Role |
|---|---|---|
| `isReal(value)` | 113, 147 | Checks that the returned SEXP is `REALSXP`; defined as an inline predicate in `fake_Rinternals.hpp` |
| `LENGTH(value)` | 115, 149 | Reads the element count of the returned SEXP; inline accessor in `fake_Rinternals.hpp` |
| `REAL(value)` | 117, 150 | Extracts `double *` from the returned SEXP; inline accessor in `fake_Rinternals.hpp` |
| `error(...)` | 114, 116, 148, 158 | Throws `RError` in the fake runtime (Invariant 1); documented in `error.md` |
| `PROTECT` / `UNPROTECT` | not present at these call sites | The source comment explicitly notes: "no need to protect as no memory allocation (or error) below" — eval() is assumed to return a pre-existing SEXP that is already protected in the R frame |
| Static globals `expr1`, `expr2`, `rho` | 33–35 | Declared as `SEXP`; set by `init_rpcallback` (lines 53–57); consumed here by `eval` |

**Distinct implementation patterns.**

Both call sites share a structurally identical pattern — `eval(expr, rho)` returns a `SEXP` that is immediately validated as a `REALSXP` and read via `REAL()`. The only variation is which expression and which output array are involved:

| Pattern | CSV rows | Description |
|---|---|---|
| P1: Evaluate `expr2` in `rho`, write deviance/mean into `z[]` | `rpart_callback.c:112` | Called by rpart's evaluation function hook; result must be length `1 + rsave` |
| P2: Evaluate `expr1` in `rho`, write split-goodness into `good[]` | `rpart_callback.c:146` | Called by rpart's split function hook; result length depends on `ncat` |

Both patterns share the same fake strategy: a single `eval` function pointer stub with one global `g_eval_fn` pointer. The two call sites are distinguished solely by their `expr` argument (`expr2` vs. `expr1`) — the fake stub handles both uniformly.

---

### 3. Fake C++ Implementation Strategy

**Category: E — R Interpreter Item.**

`eval` is Category E. A complete fake is impossible for the following reasons:

1. **`expr` is a `LANGSXP`** — an R call object that encodes the function to call and the unevaluated argument list. Evaluating it requires R's full dispatch mechanism: symbol lookup in the environment chain, S3/S4 dispatch, primitive/closure execution, and recursive evaluation of sub-expressions.

2. **`rho` is an `ENVSXP`** — an R environment frame that must be linked to a parent environment chain. The evaluation of `expr` may look up any number of symbols across the chain, call arbitrary R functions, and modify bindings. None of this is representable as a static C++ struct.

3. **Side effects during evaluation** — R's `eval` may trigger garbage collection, resize the R stack, call back into compiled code, and interact with R's condition-handling system. All of these require an initialized R runtime.

**Why a function pointer bridge achieves best-effort Python interop.**

The two functions `rpart_callback1` and `rpart_callback2` are C-linkage callbacks registered in `func_table.h` under the user-defined split method slot. Python cannot call them directly via ctypes in the way it calls entry-point wrappers — they are invoked by rpart's internal tree-fitting loop deep inside `rpart.c`. However, the expressions `expr1` and `expr2` were passed in from the R side as pre-built `LANGSXP` objects that represent closures or calls over the shared back-arrays (`yback`, `wback`, etc.).

In the fake runtime, Python replaces the entire evaluation with a C function pointer:

```
SEXP g_eval_fn(SEXP expr, SEXP rho) -> SEXP
```

When `eval(expr2, rho)` fires inside `rpart_callback1`, the stub calls `g_eval_fn(expr2, rho)`. The Python callback identifies which expression is being evaluated (by comparing the `expr` pointer against the known `expr1`/`expr2` handles), reads the current values from the back-arrays (already populated by the C code just before the `eval` call), computes the deviance/mean or split-goodness using pure Python/numpy logic, builds a fake `REALSXP` SEXP from the result, and returns its pointer. The fake C code then reads `REAL(value)` to extract the data.

This approach means Python provides the evaluation logic entirely, supplanting the R interpreter. The `expr` and `rho` handles serve as opaque dispatch keys rather than as actual R objects.

**The `eval` function pointer stub.**

```cpp
// In fake_Rinternals.hpp, after the SEXPREC/SEXP typedef and RError definition:

typedef SEXP (*eval_fn_t)(SEXP expr, SEXP rho);
static eval_fn_t g_eval_fn = nullptr;

extern "C" void register_eval_fn(eval_fn_t fn) {
    g_eval_fn = fn;
}

inline SEXP Rf_eval(SEXP expr, SEXP rho) {
    if (!g_eval_fn)
        throw RError(
            "eval: Python callback not registered. "
            "User-defined splits (method=4) require registration "
            "via register_eval_fn() before calling rpart() with method=4.");
    return g_eval_fn(expr, rho);
}

#define eval Rf_eval
```

**`#define` alias that must be preserved.**

The real `Rinternals.h` at line 934 defines:

```c
#define eval Rf_eval
```

This alias must be reproduced in the fake header so that `eval(expr2, rho)` at `rpart_callback.c:112` and `eval(expr1, rho)` at `rpart_callback.c:146` compile without modification. All call sites in rpart use the short-form `eval`, never `Rf_eval` directly.

**Which code paths require this item and which do not.**

`eval` is only invoked on the `method=4` (user-defined splits) code path in rpart. Specifically:

- `rpart_callback1` and `rpart_callback2` are registered as function pointer callbacks in `func_table.h` at the slot for `method=4` (the user-supplied splitting method). The rpart tree-fitting loop in `rpart.c` only calls these callbacks when `method=4` is selected.
- `rpart_callback0` (line 79–83) reads `rsave` and never calls `eval`. It is safe without the stub.
- `init_rpcallback` (lines 47–72) sets up the back-array pointers but does not call `eval` itself. However, it calls `R_getVar(install("yback"), rho, FALSE)` which requires the `install` and `findVarInFrame` stubs documented in `R_getVar.md`.

**All standard rpart fitting methods** (anova, poisson, class, exp — `method` values 1–4 in the default enum) use the built-in evaluation functions in `func_table.h` and never call `eval`. For all standard use cases, the `eval` stub is never invoked.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): The `eval` stub throws `RError` when called without a registered Python callback. Additionally, `rpart_callback1` and `rpart_callback2` call `error(...)` immediately after `eval()` to validate the result — those `error` calls also throw `RError` (documented in `error.md`). The `.Call`-boundary wrapper for any top-level function in the call chain must catch `RError`.
- Invariant 2 (arena memory): Not triggered by `eval` itself. The comment at `rpart_callback.c:111` confirms: "no need to protect as no memory allocation (or error) below" — indicating that `eval` in the real R runtime returns an already-protected SEXP and does not allocate additional arena memory. In the fake runtime, the SEXP returned by `g_eval_fn` is heap-allocated by Python and is not arena-managed.
- Invariant 3 (R Interpreter Items): fully applicable; this entire guide is the Invariant 3 treatment for `eval`.

---

### 4. Fake Implementation Examples

#### Pattern P1: Evaluate `expr2` for Deviance/Mean Output (`rpart_callback1`)

- **Locations:** `rpart_callback.c:112`

- **Original R API Usage:**

```c
/* rpart_callback.c:88-120 */
void
rpart_callback1(int n, double *y[], double *wt, double *z)
{
    int i, j, k;
    SEXP value;
    double *dptr;

    /* Populate shared back-arrays before eval */
    for (i = 0, k = 0; i < ysave; i++)
        for (j = 0; j < n; j++)
            ydata[k++] = y[j][i];
    for (i = 0; i < n; i++)
        wdata[i] = wt[i];
    ndata[0] = n;

    /* no need to protect as no memory allocation (or error) below */
    value = eval(expr2, rho);
    if (!isReal(value))
        error(_("return value not a vector"));
    if (LENGTH(value) != (1 + rsave))
        error(_("returned value is the wrong length"));
    dptr = REAL(value);
    for (i = 0; i <= rsave; i++)
        z[i] = dptr[i];
}
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// Additions for eval support — placed after the SEXPREC/SEXP typedef block,
// after the RError definition (from error.md / fake_error.hpp), and after the
// REAL / isReal / LENGTH inline accessors.
//
// This stub applies equally to both CSV call sites (lines 112 and 146).

// -----------------------------------------------------------------------
// eval / Rf_eval — R Interpreter Item (Category E, Invariant 3).
//
// eval(SEXP expr, SEXP rho) evaluates an R expression in an environment.
// In the fake runtime this is implemented as a Python-registered function
// pointer.  If the pointer has not been registered, the stub throws RError,
// which unwinds through rpart_callback1 / rpart_callback2 to the nearest
// .Call boundary wrapper.
//
// Registration function: register_eval_fn(eval_fn_t fn)
// Must be called by Python (via ctypes) before any invocation of rpart()
// with method=4.
// -----------------------------------------------------------------------
typedef SEXP (*eval_fn_t)(SEXP expr, SEXP rho);
static eval_fn_t g_eval_fn = nullptr;

extern "C" void register_eval_fn(eval_fn_t fn) {
    g_eval_fn = fn;
}

inline SEXP Rf_eval(SEXP expr, SEXP rho) {
    if (!g_eval_fn)
        throw RError(
            "eval: Python callback not registered. "
            "User-defined splits (method=4) require registration "
            "via register_eval_fn() before calling rpart() with method=4.");
    return g_eval_fn(expr, rho);
}

// Preserve the #define alias from real Rinternals.h:934.
// rpart_callback.c uses eval(expr2, rho) not Rf_eval(expr2, rho).
#define eval Rf_eval

// -----------------------------------------------------------------------
// .Call boundary wrapper for rpart() — the outermost C-linkage function
// that Python calls via ctypes when fitting a tree.
//
// rpart_callback1 is not called directly from Python; it is invoked by
// rpart()'s internal fitting loop.  Therefore the ArenaFrame and try/catch
// must be at the rpart() entry point, not at rpart_callback1 itself.
//
// If g_eval_fn is not registered and method=4 is used, Rf_eval throws
// RError.  The exception unwinds through:
//   rpart_callback1  -> rpart's internal C fitting loop  -> rpart()
//   -> rpart_wrapper (here)  -> caught by catch(const RError &e)
// -----------------------------------------------------------------------
extern "C" SEXP rpart_wrapper(
        SEXP ncat2, SEXP method2, SEXP opt2,
        SEXP parms2, SEXP xvals2, SEXP xgrp2,
        SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2)
{
    ArenaFrame _frame;   // Invariant 2: push arena frame; freed on exit
    try {
        return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                     ymat2, xmat2, wt2, ny2, cost2);
    } catch (const RError &e) {
        // Invariant 1: translate C++ exception to a Python-readable message.
        // set_python_error stores the message in thread-local storage so
        // Python can retrieve it after the call returns nullptr.
        set_python_error(e.what());
        return nullptr;   // signals failure to the Python caller
    }
}
```

- **Python Interop Notes:**

  Python must register a callback for `eval` before calling `rpart()` with `method=4`. The callback receives two opaque SEXP pointers — `expr` (the expression) and `rho` (the environment) — and must return a heap-allocated `REALSXP` SEXP whose `data` field contains the `double` result array and whose `length` field is set correctly.

  The `expr` pointer serves as a dispatch key: Python compares it to the stored `expr1`/`expr2` handles (which were passed to `init_rpcallback_wrapper` and stored in the C static globals) to determine which computation to perform. The back-arrays (`ydata`, `wdata`, `xdata`, `ndata`) are already populated by the C code inside `rpart_callback1` / `rpart_callback2` just before `eval` is called, so the Python callback can read the current node's observation data directly from the numpy buffers it registered via `make_real_sexp` / `make_int_sexp`.

  ```python
  import ctypes
  import numpy as np

  # Load the shared library built from the fake-header rpart source.
  lib = ctypes.CDLL("./librpart_fake.so")

  # SEXP is an opaque pointer in Python.
  SEXP = ctypes.c_void_p

  # ----------------------------------------------------------------
  # Define the eval callback function type.
  # Signature: SEXP eval_fn(SEXP expr, SEXP rho)
  # ----------------------------------------------------------------
  EvalFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)

  # ----------------------------------------------------------------
  # Retrieve the expr1 / expr2 SEXP handles that were passed to
  # init_rpcallback_wrapper and stored in the C static globals.
  # These are needed so the Python callback can dispatch on expr.
  #
  # In a real integration, these handles are whatever c_void_p values
  # Python passed as the expr1x and expr2x arguments.  The callback
  # compares the received expr pointer against these values.
  # ----------------------------------------------------------------

  # These are set when init_rpcallback_wrapper is called:
  _expr1_handle: int = 0   # opaque SEXP ptr for expr1
  _expr2_handle: int = 0   # opaque SEXP ptr for expr2

  # Back-array numpy buffers registered before init_rpcallback_wrapper:
  # (these are the buffers that ydata/wdata/xdata/ndata point into)
  _yback: np.ndarray   # shape (n_obs * ysave,) float64
  _wback: np.ndarray   # shape (n_obs,) float64
  _xback: np.ndarray   # shape (n_obs,) float64  (current split variable)
  _nback: np.ndarray   # shape (1,) int32 — set to current n by C code

  # Helper: allocate a REALSXP SEXP from a numpy float64 array.
  lib.make_real_sexp.restype  = SEXP
  lib.make_real_sexp.argtypes = [ctypes.c_void_p, ctypes.c_int]

  def make_result_sexp(arr: np.ndarray) -> int:
      """Wrap a 1-D float64 numpy array as a fake REALSXP SEXP."""
      arr = np.ascontiguousarray(arr, dtype=np.float64)
      # Keep arr alive by storing in a module-level list; the C code will
      # read the data pointer immediately after eval() returns.
      _eval_result_buffer.append(arr)
      return lib.make_real_sexp(arr.ctypes.data_as(ctypes.c_void_p), arr.size)

  _eval_result_buffer: list = []   # prevent GC until C is done reading

  # ----------------------------------------------------------------
  # The eval callback itself.
  #
  # For expr2 (rpart_callback1): compute deviance and mean for the
  # current node.  Return a REALSXP of length (1 + rsave).
  #   result[0]         = total deviance for the node
  #   result[1..rsave]  = mean response value(s)
  #
  # For expr1 (rpart_callback2): compute split goodness scores.
  # Return a REALSXP whose length depends on ncat:
  #   ncat == 0: length = 2*(n-1) — one goodness score and one direction
  #              per potential split point for a continuous variable
  #   ncat >  0: length = 2*ncategories_present - 1
  #
  # The Python implementation below is a template.  Replace the body
  # of each branch with the actual user-defined split logic.
  # ----------------------------------------------------------------
  def py_eval(expr_ptr: int, rho_ptr: int) -> int:
      n = int(_nback[0]) if _nback[0] > 0 else -int(_nback[0])
      # nback[0] is negative when ncat > 0 (categorical variable)

      if expr_ptr == _expr2_handle:
          # rpart_callback1: compute deviance + mean for current node.
          # y: shape (ysave, n) — response matrix for n observations
          y = _yback[:n].copy()      # adjust slice per actual ysave/n layout
          w = _wback[:n]

          # --- USER-DEFINED EVALUATION LOGIC HERE ---
          # Example for a single continuous response (ysave=1, rsave=1):
          total_wt  = np.sum(w)
          wmean     = np.sum(w * y) / total_wt
          wdeviance = np.sum(w * (y - wmean) ** 2)
          result = np.array([wdeviance, wmean], dtype=np.float64)
          # length must equal 1 + rsave
          return make_result_sexp(result)

      elif expr_ptr == _expr1_handle:
          # rpart_callback2: compute split-goodness for each split point.
          # nback[0] positive => continuous variable (ncat==0)
          # nback[0] negative => categorical variable (ncat>0)
          y = _yback[:n].copy()
          w = _wback[:n]
          x = _xback[:n]

          # --- USER-DEFINED SPLIT GOODNESS LOGIC HERE ---
          # Example for a continuous variable (ncat == 0):
          # For each of the n-1 possible split points, compute a goodness
          # score and a direction indicator.
          good   = np.zeros(n - 1, dtype=np.float64)
          direct = np.zeros(n - 1, dtype=np.float64)
          # ... (fill good[] and direct[] based on x, y, w) ...
          result = np.empty(2 * (n - 1), dtype=np.float64)
          result[0::2] = good
          result[1::2] = direct
          return make_result_sexp(result)

      else:
          # Unknown expression — should not happen in a correct integration.
          raise RuntimeError(
              f"py_eval called with unrecognized expr ptr {expr_ptr:#x}. "
              "Did you forget to record expr1/expr2 handles from "
              "init_rpcallback_wrapper?")

  _eval_cb = EvalFnType(py_eval)

  # ----------------------------------------------------------------
  # Register the eval callback with the C library.
  # Must be done before calling rpart_wrapper with method=4.
  # ----------------------------------------------------------------
  lib.register_eval_fn.restype  = None
  lib.register_eval_fn.argtypes = [EvalFnType]
  lib.register_eval_fn(_eval_cb)

  # ----------------------------------------------------------------
  # Example: call rpart_wrapper with method=4.
  # (Assumes init_rpcallback_wrapper has already been called and
  # the install/findVarInFrame stubs have been registered per R_getVar.md.)
  # ----------------------------------------------------------------
  lib.rpart_wrapper.restype  = SEXP
  lib.rpart_wrapper.argtypes = [SEXP] * 11   # 11 SEXP parameters

  lib.get_last_rerror_message.restype  = ctypes.c_char_p
  lib.get_last_rerror_message.argtypes = []

  result_sexp = lib.rpart_wrapper(
      # ... construct all 11 SEXP arguments (ncat2, method2, opt2, ...) ...
  )

  msg = lib.get_last_rerror_message()
  if msg:
      raise RuntimeError(f"rpart failed: {msg.decode()}")
  ```

- **Arena / Memory Notes:**

  `eval` itself does not allocate arena memory. The source comment at `rpart_callback.c:111` explicitly states: "no need to protect as no memory allocation (or error) below" — in the real R runtime, `eval` returns a reference to an existing SEXP that is already on R's protection stack; no new R heap nodes are allocated. In the fake runtime, the SEXP returned by `g_eval_fn` is heap-allocated by `make_real_sexp` inside the Python callback. Its `data` pointer aliases into the numpy array stored in `_eval_result_buffer`. This SEXP is not arena-managed and is not freed by `ArenaFrame` destruction. Its lifetime is tied to the numpy array. In practice, the C code at `rpart_callback1:117-119` reads `REAL(value)` immediately and copies the values into `z[]` before returning — so the SEXP and its buffer need only survive until `rpart_callback1` (or `rpart_callback2`) returns. A single-element `_eval_result_buffer` list (cleared between calls) is sufficient to manage this lifetime.

- **Explanation:**

  The fake defines `g_eval_fn` as a `static` global function pointer of type `eval_fn_t` (i.e., `SEXP(*)(SEXP, SEXP)`). The inline `Rf_eval` stub checks the pointer and either delegates to the Python callback or throws `RError`. The `#define eval Rf_eval` alias ensures that `eval(expr2, rho)` at line 112 and `eval(expr1, rho)` at line 146 expand to `Rf_eval(expr2, rho)` and `Rf_eval(expr1, rho)` respectively — the same expansion performed by the real `Rinternals.h`. The original source file `rpart_callback.c` is not modified.

  The `g_eval_fn` variable is declared `static` within the header file. Because `fake_Rinternals.hpp` uses `#pragma once` / the `#ifndef FAKE_RINTERNALS_H` guard, it is included exactly once per translation unit in a non-LTO build. For a multi-TU build that links `rpart_callback.c` and other files together, `g_eval_fn` must be promoted to a single definition with external linkage (declared `extern eval_fn_t g_eval_fn;` in the header and defined once in a `.cpp` file) to avoid ODR violations. Alternatively, placing all definitions in a single `.cpp` translation unit avoids this issue entirely.

---

#### Pattern P2: Evaluate `expr1` for Split-Goodness Output (`rpart_callback2`)

- **Locations:** `rpart_callback.c:146`

- **Original R API Usage:**

```c
/* rpart_callback.c:126-173 */
void
rpart_callback2(int n, int ncat, double *y[], double *wt,
                double *x, double *good)
{
    int i, j, k;
    SEXP goodness;
    double *dptr;

    /* Populate back-arrays: y, w, x for current node */
    for (i = 0, k = 0; i < ysave; i++)
        for (j = 0; j < n; j++)
            ydata[k++] = y[j][i];
    for (i = 0; i < n; i++) {
        wdata[i] = wt[i];
        xdata[i] = x[i];
    }
    ndata[0] = (ncat > 0) ? -n : n;
        /* the negative serves as a marker for rpart.R */

    /* no need to protect as no memory allocation (or error) below */
    goodness = eval(expr1, rho);
    if (!isReal(goodness))
        error(_("the expression expr1 did not return a vector!"));
    j = LENGTH(goodness);
    dptr = REAL(goodness);

    if (ncat == 0) {
        if (j != 2 * (n - 1))
            error("the expression expr1 returned a list of %d elements, %d required",
                  j, 2 * (n - 1));
        for (i = 0; i < j; i++)
            good[i] = dptr[i];
    } else {
        good[0] = (j + 1) / 2;
        for (i = 0; i < j; i++)
            good[i + 1] = dptr[i];
    }
}
```

- **C++ Fake Implementation:**

The same `g_eval_fn` stub defined in Pattern P1 handles this call site. No additional C++ code is required. The `eval(expr1, rho)` call at line 146 expands via `#define eval Rf_eval` to `Rf_eval(expr1, rho)`, which invokes `g_eval_fn(expr1, rho)`. The Python callback distinguishes this call from the Pattern P1 call by comparing `expr_ptr` against `_expr1_handle` (as shown in the `py_eval` function in Pattern P1's Python snippet).

The key behavioral difference from Pattern P1:

- The expression argument is `expr1` (not `expr2`).
- The `ndata[0]` encoding: positive `n` means continuous split variable (`ncat == 0`), negative `n` means categorical (`ncat > 0`). The Python callback reads `_nback[0]` to determine which layout to produce.
- The required result length: `2*(n-1)` for continuous splits, `(2*ncategories_present - 1)` for categorical splits.
- The result is written into `good[]` (a caller-supplied `double *` array) rather than `z[]`.

```cpp
// No additional C++ stub needed beyond the one shown in Pattern P1.
// The same register_eval_fn / g_eval_fn / Rf_eval / #define eval Rf_eval
// block in fake_Rinternals.hpp covers both rpart_callback.c:112 and
// rpart_callback.c:146.
//
// For reference, the call chain for rpart_callback2:
//
//   rpart's internal split loop
//     -> rpart_callback2(n, ncat, y, wt, x, good)   [callback via func_table]
//          -> ndata[0] = (ncat > 0) ? -n : n         [C code, no fake needed]
//          -> goodness = eval(expr1, rho)             [Rf_eval stub]
//               -> g_eval_fn(expr1, rho)              [Python py_eval callback]
//               <- returns REALSXP of length 2*(n-1) or 2*ncats-1
//          -> isReal(goodness)                        [inline in fake_Rinternals.hpp]
//          -> LENGTH(goodness)                        [inline in fake_Rinternals.hpp]
//          -> REAL(goodness)                          [inline in fake_Rinternals.hpp]
//          -> copies data into good[]                 [C code, no fake needed]
```

- **Arena / Memory Notes:** Same as Pattern P1. The SEXP returned by `g_eval_fn` is heap-allocated by the Python callback and read immediately by `REAL(goodness)`. No arena interaction occurs.

- **Python Interop Notes:** The Python dispatch logic for Pattern P2 is included in the `py_eval` function shown under Pattern P1 (the `elif expr_ptr == _expr1_handle:` branch). No additional Python registration is required — a single `register_eval_fn(_eval_cb)` call covers both patterns.

- **Explanation:**

  The structural symmetry between `rpart_callback1` (line 112) and `rpart_callback2` (line 146) is complete: both call `eval(exprN, rho)`, validate with `isReal`, check `LENGTH`, and read with `REAL`. The fake handles them with a single stub and a single Python registration. The `expr` argument (`expr1` vs. `expr2`) acts as the sole dispatch key in the Python callback. The C code in `rpart_callback.c` is not modified in any way; the fake header's `#define eval Rf_eval` alias is sufficient for both call sites to resolve to the same stub.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct (`type`, `length`, `nrow`, `ncol`, `data`) and `typedef SEXPREC *SEXP`. Both the `eval_fn_t` typedef and the `Rf_eval` stub have `SEXP` parameter and return types. `SEXP.md` also establishes `REALSXP`, `isReal`, `REAL`, and `LENGTH` — all used immediately after `eval()` returns at lines 113–117 and 147–150. Must be compiled before `fake_eval.hpp` (or the `eval` stub block in `fake_Rinternals.hpp`). |
| `error.md` | Provides the `RError` exception class (`struct RError : public std::runtime_error`) and the `Rf_error` / `error` throwing implementation. Required because `rpart_callback1` and `rpart_callback2` call `error(...)` immediately after `eval()` to validate the return type and length. `RError` must be defined before `Rf_eval` is defined, since `Rf_eval` throws `RError` when `g_eval_fn` is null. |
| `R_getVar.md` | Documents the `install`, `findVar`, and `findVarInFrame` function pointer stubs, which must be registered before `init_rpcallback_wrapper` is called. `init_rpcallback` stores the `expr1`, `expr2`, and `rho` SEXP handles that are later passed to `eval` — so `R_getVar.md`'s stubs must be active before the `eval` stub is needed. |
| `PROTECT.md` | Documents that `PROTECT` and `UNPROTECT` are no-ops in the fake runtime. Relevant context: `rpart_callback.c:111` explicitly notes that no `PROTECT` is needed around the `eval` call; in the fake runtime this is automatically satisfied because `PROTECT` is an identity no-op anyway. |
| `fake_arena.hpp` | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, `arena_calloc`. Required by `rpart_wrapper` (the `.Call`-boundary entry point for `rpart()`) for the `ArenaFrame _frame` RAII guard (Invariant 2). Not used by `eval` or `rpart_callback1`/`rpart_callback2` directly, since those functions do not perform arena allocations. |
| `R_VERSION.md` / `R_Version.md` / `fake_Rversion.hpp` | Must define `R_VERSION < R_Version(4, 5, 0)` as true so that the `compat_getVar` / `R_getVar` macro block in `rpart_callback.c:19-28` is compiled. Without this, `R_getVar` is unresolved at lines 59–68, which blocks `init_rpcallback` from running and therefore blocks the `expr1`/`expr2`/`rho` static globals from being set — making any subsequent `eval` call operate on null/garbage SEXPs. |
