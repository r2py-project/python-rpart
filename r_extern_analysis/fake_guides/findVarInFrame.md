# Fake Header Implementation Guide: `findVarInFrame`

> **R Interpreter Item.** `findVarInFrame` (i.e., `Rf_findVarInFrame`) requires a running R interpreter to function. It searches for a symbol binding in a single environment frame without walking parent frames, consulting R's internal environment frame structure and symbol table. Neither the environment frame data structure nor the symbol table exists outside of an initialized R runtime. In the fake build, `findVarInFrame` is implemented as a function pointer that Python registers via `ctypes.CFUNCTYPE` before invoking any `.Call` function that exercises the user-defined splitting code path (`method=4`). `findVarInFrame` **is reached at runtime** in rpart (unlike its sibling `findVar`, which is never reached), so registration of the Python callback is mandatory for the `method=4` path to function.

---

### 1. Overview of `findVarInFrame` in R API

`Rf_findVarInFrame(SEXP rho, SEXP sym)` — aliased as `findVarInFrame` via `#define findVarInFrame Rf_findVarInFrame` at `Rinternals.h` line 940 — takes an R environment object `rho` (`ENVSXP`, the frame to search) and a symbol object `sym` (`SYMSXP`, produced by `install(name)`) and returns the `SEXP` value that `sym` is bound to in the **immediate frame** `rho` only, without walking the parent environment chain. If the symbol is not found in `rho`, `findVarInFrame` returns the global sentinel `R_UnboundValue`. The function is declared in `~/.conda/envs/r-to-python/lib/R/include/Rinternals.h` at line 534 as:

```c
SEXP Rf_findVarInFrame(SEXP, SEXP);
```

Note the argument order: `rho` (environment) first, `sym` (symbol) second. This is the **reverse** of `findVar(sym, rho)` (symbol first, environment second). The distinction is load-bearing at the call site in `rpart_callback.c:22`.

`findVarInFrame` is the frame-local counterpart to `findVar`: while `findVar` walks the entire parent chain until it reaches `R_EmptyEnv`, `findVarInFrame` restricts its search to the single frame `rho`. Both functions require R's internal environment frame linked list and symbol table hash structure to be fully initialized. This makes `findVarInFrame` an **R Interpreter Item**: a complete standalone fake is impossible.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart_callback.c` | 7–37 | Full header section, `compat_getVar` shim and macro, static globals |

**Context window for the CSV row (line 22).**

The single CSV row is at `rpart_callback.c:22`, inside the compatibility shim `compat_getVar`. The complete window (lines 7–37) is:

```c
/* rpart_callback.c:7-37 */
#include <R.h>
#include <Rinternals.h>
#include <Rversion.h>
/* don't include rpart.h: it conflicts */

#ifdef ENABLE_NLS
#include <libintl.h>
#define _(String) dgettext ("rpart", String)
#else
#define _(String) (String)
#endif

/* compatibility shim for R < 4.5.0 */
#if R_VERSION < R_Version(4, 5, 0)
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);   /* line 22 */
  if (val == R_UnboundValue)
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif

static int ysave;               /* number of columns of y  */
static int rsave;               /* the length of the returned "mean" from the
				 * user's eval routine */
static SEXP expr1;              /* the evaluation expression for splits */
static SEXP expr2;              /* the evaluation expression for values */
static SEXP rho;
```

**C types of arguments and return values.**

| Argument | Declared type | Meaning at call site |
|---|---|---|
| `rho` (first) | `SEXP` | An environment object (`ENVSXP`) — the frame to search; passed in from Python as `rhox` and stored in the static global `rho` by `init_rpcallback` (line 53). Serves as the lookup scope. |
| `sym` (second) | `SEXP` | A symbol object (`SYMSXP`) produced by `install("yback")` etc. at lines 59, 62, 65, 68; carries the interned string name of the variable to look up. |
| return value | `SEXP` | The bound value in the frame `rho`; must be `REALSXP` for `yback`/`wback`/`xback`, `INTSXP` for `nback`; returns `R_UnboundValue` if not found. |

**Call site mechanics and argument order.**

`findVarInFrame` appears as the false branch of the conditional expression at line 22:

```c
SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
```

The argument order difference is critical:
- `findVar(sym, rho)` — symbol first, then environment (matches `Rf_findVar(SEXP, SEXP)` at `Rinternals.h:533`).
- `findVarInFrame(rho, sym)` — environment first, then symbol (matches `Rf_findVarInFrame(SEXP, SEXP)` at `Rinternals.h:534`).

In the rpart source, `inherits` is always `FALSE` at all four `R_getVar` call sites in `init_rpcallback` (lines 59, 62, 65, 68), so `findVarInFrame(rho, sym)` is **always** executed. This makes `findVarInFrame` the critical runtime dependency (as opposed to `findVar`, which is never invoked).

**Downstream usage of the returned SEXP.**

After `compat_getVar` returns `val`, `init_rpcallback` immediately extracts data pointers:

| Call site | Variable sought | Downstream accessor | Static pointer set |
|---|---|---|---|
| Line 59–60 | `"yback"` | `REAL(stemp)` | `ydata` (`double *`) |
| Line 62–63 | `"wback"` | `REAL(stemp)` | `wdata` (`double *`) |
| Line 65–66 | `"xback"` | `REAL(stemp)` | `xdata` (`double *`) |
| Line 68–69 | `"nback"` | `INTEGER(stemp)` | `ndata` (`int *`) |

**Co-occurring R API items in the context window.**

| Item | Line | Role |
|---|---|---|
| `findVar(sym, rho)` | 22 | True branch of the ternary; never reached at runtime (always `inherits=FALSE`); its own Category E stub — documented in `findVar.md` |
| `R_UnboundValue` | 23 | Sentinel SEXP for a failed lookup; compared via pointer equality against `val`; documented in `R_UnboundValue.md` |
| `error(...)` | 24 | Throws `RError` in the fake runtime (Invariant 1) when `val == R_UnboundValue`; documented in `error.md` |
| `CHAR(PRINTNAME(sym))` | 24 | Extracts symbol name string for the error message; requires `PRINTNAME` and `CHAR` from `SEXP.md` |
| `install("yback")` etc. | 59,62,65,68 | Produces the `sym` argument before `compat_getVar` is called; Category E item (`install.md`) |
| `R_VERSION < R_Version(4, 5, 0)` | 19 | Compile-time gate; ensures `compat_getVar` and `#define R_getVar` are compiled; must evaluate to `1` in the fake build |
| `Rboolean inherits` | 20 | Third parameter of `compat_getVar`; documented in `Rboolean.md` |
| `REAL(stemp)`, `INTEGER(stemp)` | 60,63,66,69 | Applied to the SEXP returned through `compat_getVar`; documented in `REAL.md`, `INTEGER.md` |

**Distinct implementation patterns.**

There is exactly one occurrence of `findVarInFrame` in rpart's source:

| Pattern | Location | Description |
|---|---|---|
| P1: Immediate-frame lookup — `findVarInFrame` branch (always reached at runtime) | `rpart_callback.c:22` (false branch) | Called when `inherits=FALSE`; reached by all four `R_getVar` call sites in `init_rpcallback`; the fake stub must be registered by Python before `method=4` callbacks are exercised |

Because `findVarInFrame` is the sole runtime code path through `compat_getVar` for rpart's usage, its Python callback registration is **mandatory** (not optional) for the `method=4` path to work. This distinguishes it from `findVar`, which is present only to satisfy the compiler.

**Relationship to previously generated guides.**

The `findVar.md` guide (already generated) defines the complete `Rf_findVar` and `Rf_findVarInFrame` stubs together, including the `#define findVarInFrame Rf_findVarInFrame` alias and the registration infrastructure, under the rationale that the two functions appear at the same call site and share a registration pattern. The `R_UnboundValue.md` and `R_getVar.md` guides contain abbreviated versions of the same stubs. This guide is the **authoritative specification** for `findVarInFrame` specifically, and is consistent with all those prior stubs. The final `fake_Rinternals.hpp` must contain exactly one definition of `Rf_findVarInFrame`, `g_findVarInFrame_fn`, and `register_findVarInFrame_fn`; the abbreviated versions in `R_UnboundValue.md` and `R_getVar.md` are superseded by the complete version given here.

---

### 3. Fake C++ Implementation Strategy

**Category: E — R Interpreter Item.**

`findVarInFrame` is Category E. A complete standalone fake is impossible for the following reasons:

1. **`rho` is an `ENVSXP`** — an R environment frame whose internal structure (`FRAME()`, a hash table or pairlist of `(symbol, value)` bindings, and `ENCLOS()`, a pointer to the parent frame) is part of R's internal `SEXPREC` memory layout. Accessing and walking this structure requires R's internal field macros (only available inside the R engine behind `USE_RINTERNALS`). There is no public C API to enumerate or look up the bindings of an `ENVSXP` without a running interpreter.

2. **`sym` is a `SYMSXP`** with an interned identity — `install("yback")` called at one location must return the exact same `SEXP` pointer as `install("yback")` called at any other location (R's symbol interning invariant). Without R's global symbol table to enforce this invariant, pointer-equality matching of symbols against frame bindings would be unreliable.

3. **Frame binding representation** — in R's internal layout, each frame binding is a pairlist node (`LISTSXP`) where the `TAG` field holds the symbol SEXP and the `CAR` field holds the bound value. Walking the frame means following a linked list of such nodes and comparing `TAG(node) == sym`. This structure requires the R engine's internal `SEXPREC` layout, which is hidden behind `USE_RINTERNALS` and not available to client code.

**Why a function pointer bridge achieves best-effort Python interop.**

`findVarInFrame` is called from `compat_getVar`, which is compiled only when `R_VERSION < R_Version(4, 5, 0)`. At runtime, `compat_getVar` is called by `init_rpcallback` (lines 59–68) as the mechanism for resolving the four shared back-array SEXPs (`yback`, `wback`, `xback`, `nback`) that the callback functions read during tree fitting. Python can substitute its own lookup implementation because:

1. The set of variable names queried is static and known: always `"yback"`, `"wback"`, `"xback"`, `"nback"`.
2. Python already owns the numpy arrays that back these SEXPs; it can construct fake SEXPREC nodes for them before the call.
3. The `rho` SEXP handle is constructed on the Python side (as an opaque `make_env_sexp()` placeholder) and serves as the lookup key in a Python `dict`.
4. The `sym` SEXP handles are produced by the fake `install()` stub, which is also Python-registered and memoized — ensuring the same pointer is returned for the same name string every time.

The function pointer type is:
```cpp
typedef SEXP (*findVarInFrame_fn_t)(SEXP rho, SEXP sym);
```

Note the argument order: `rho` first, `sym` second, matching `Rf_findVarInFrame(SEXP, SEXP)` at `Rinternals.h:534` and the call site `findVarInFrame(rho, sym)` at `rpart_callback.c:22`.

Python registers a Python function as the callback via `ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)` and calls `register_findVarInFrame_fn` before invoking `init_rpcallback_wrapper`. The Python callback implements the variable lookup using a Python-managed `dict` keyed by `(rho_ptr, sym_ptr)`.

**Relationship to `findVar` stub and the `#define` aliases.**

The real `Rinternals.h` lines 939–940 define:

```c
#define findVar          Rf_findVar
#define findVarInFrame   Rf_findVarInFrame
```

Both aliases must be reproduced in the fake header so that `findVar(sym, rho)` and `findVarInFrame(rho, sym)` at `rpart_callback.c:22` expand to `Rf_findVar(sym, rho)` and `Rf_findVarInFrame(rho, sym)` respectively — the same expansion performed by the real `Rinternals.h`. The original source file `rpart_callback.c` is not modified.

The `findVar.md` guide already establishes `g_findVar_fn`, `Rf_findVar`, `register_findVar_fn`, and `#define findVar Rf_findVar`. This guide establishes the parallel `findVarInFrame` infrastructure. Both must appear in `fake_Rinternals.hpp`; neither can be omitted, because both names appear in the same expression at line 22.

**Which code paths require this item and which do not.**

- `findVarInFrame` **is reached at runtime** on the `method=4` (user-defined splits) code path, specifically during `init_rpcallback` (lines 59–68). All four `R_getVar(install("..."), rho, FALSE)` calls expand to `compat_getVar(sym, rho, FALSE)` which unconditionally calls `findVarInFrame(rho, sym)`.
- Python **must** register `register_findVarInFrame_fn` before calling `init_rpcallback_wrapper` with user-defined method data; failure to do so causes `Rf_findVarInFrame` to throw `RError("findVarInFrame: Python callback not registered")`, which propagates to the `.Call` boundary.
- `findVar` (the `inherits=TRUE` branch) is **never reached** at runtime by any rpart call site; its stub is required only to compile and link cleanly.
- All standard rpart fitting methods (anova, poisson, class, exp) never call `init_rpcallback` and therefore never trigger either `findVarInFrame` or `findVar`. For those paths, neither stub needs to be registered.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): The `findVarInFrame` stub throws `RError` when called without a registered Python callback. The `compat_getVar` function also calls `error(...)` at line 24 when `val == R_UnboundValue`; that call throws `RError` (documented in `error.md`). The `.Call`-boundary wrapper for `init_rpcallback` must catch `RError`.
- Invariant 2 (arena memory): Not triggered by `findVarInFrame` itself. No memory allocation occurs inside `findVarInFrame`; it returns a pointer to an existing binding (in the fake, a heap-allocated SEXPREC constructed by the Python side). The `ArenaFrame` guard at the `.Call` boundary is required by the surrounding `init_rpcallback_wrapper`.
- Invariant 3 (R Interpreter Items): Fully applicable. This entire guide is the Invariant 3 treatment for `findVarInFrame`.

---

### 4. Fake Implementation Examples

#### Pattern: Immediate-Frame Symbol Lookup — `findVarInFrame` Branch (Always Reached at Runtime)

- **Locations:** `rpart_callback.c:22` (false branch of `inherits ? findVar(sym, rho) : findVarInFrame(rho, sym)`)

- **Original R API Usage:**

```c
/* rpart_callback.c:19-28 — compat_getVar shim, compiled when R_VERSION < 4.5.0 */
#if R_VERSION < R_Version(4, 5, 0)
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
  if (val == R_UnboundValue)
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif

/* rpart_callback.c:59-69 — init_rpcallback, all four call sites */
stemp = R_getVar(install("yback"), rho, FALSE);   /* expands: compat_getVar -> findVarInFrame */
ydata = REAL(stemp);

stemp = R_getVar(install("wback"), rho, FALSE);
wdata = REAL(stemp);

stemp = R_getVar(install("xback"), rho, FALSE);
xdata = REAL(stemp);

stemp = R_getVar(install("nback"), rho, FALSE);
ndata = INTEGER(stemp);
```

At runtime in rpart, `inherits` is always `FALSE` (all four `R_getVar` call sites pass `FALSE`), so `findVarInFrame(rho, sym)` is **always** executed. The `findVar(sym, rho)` true branch is never reached.

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// Additions for findVarInFrame / findVar support.
// These definitions must appear AFTER:
//   - SEXPREC / SEXP typedef (from SEXP.md)
//   - RError definition (from error.md)
//   - R_UnboundValue sentinel SEXP (from R_UnboundValue.md)
//   - Rboolean / FALSE definitions (from Rboolean.md / FALSE.md)
//
// Relationship to existing guides:
//   - findVar.md establishes Rf_findVar and #define findVar Rf_findVar;
//     these are reproduced here for completeness as both appear at the
//     same call site. The final fake_Rinternals.hpp must consolidate
//     to exactly ONE definition of each stub.
//   - R_UnboundValue.md and R_getVar.md contain abbreviated versions
//     of these stubs; the versions below are authoritative and supersede
//     the abbreviated forms.

// -----------------------------------------------------------------------
// findVarInFrame / Rf_findVarInFrame — R Interpreter Item (Category E, Invariant 3).
//
// Rf_findVarInFrame(SEXP rho, SEXP sym) searches ONLY the immediate frame
// rho for a binding of sym.  No parent chain walk.
// Returns R_UnboundValue if sym is not bound in rho.
//
// ARGUMENT ORDER: rho first, sym second.
// This matches Rinternals.h:534 declaration:
//   SEXP Rf_findVarInFrame(SEXP, SEXP);
// and the alias at Rinternals.h:940:
//   #define findVarInFrame Rf_findVarInFrame
// The call site at rpart_callback.c:22 uses: findVarInFrame(rho, sym).
//
// RUNTIME STATUS: findVarInFrame IS called at runtime.  All four
// R_getVar(install("..."), rho, FALSE) calls in init_rpcallback expand
// to compat_getVar(..., FALSE) which unconditionally calls findVarInFrame.
// Python MUST register this callback before init_rpcallback_wrapper is
// called with method=4 data.
//
// Registration function: register_findVarInFrame_fn(findVarInFrame_fn_t fn)
// -----------------------------------------------------------------------
typedef SEXP (*findVarInFrame_fn_t)(SEXP rho, SEXP sym);
static findVarInFrame_fn_t g_findVarInFrame_fn = nullptr;

extern "C" void register_findVarInFrame_fn(findVarInFrame_fn_t fn) {
    g_findVarInFrame_fn = fn;
}

inline SEXP Rf_findVarInFrame(SEXP rho, SEXP sym) {
    if (!g_findVarInFrame_fn)
        throw RError(
            "findVarInFrame: Python callback not registered. "
            "init_rpcallback() requires registration via "
            "register_findVarInFrame_fn() before calling any "
            "function that exercises the method=4 user-defined "
            "splits path.");
    return g_findVarInFrame_fn(rho, sym);
}

// Preserve the #define alias from real Rinternals.h:940.
// compat_getVar in rpart_callback.c uses findVarInFrame(rho, sym)
// not Rf_findVarInFrame(rho, sym).
#define findVarInFrame Rf_findVarInFrame

// -----------------------------------------------------------------------
// findVar / Rf_findVar — R Interpreter Item (Category E, Invariant 3).
//
// Rf_findVar(SEXP sym, SEXP rho) searches rho AND all parent environments.
// ARGUMENT ORDER: sym first, rho second — the reverse of findVarInFrame.
//
// RUNTIME STATUS: findVar is NEVER called at runtime in rpart because
// compat_getVar's 'inherits' argument is always FALSE (taking the
// findVarInFrame branch).  This stub exists solely to:
//   1. Satisfy the linker (the symbol must resolve).
//   2. Provide a safe, debuggable failure if inherits=TRUE were ever passed.
//   3. Allow Python to register a real implementation for future use.
//
// Registration function: register_findVar_fn(findVar_fn_t fn)
// -----------------------------------------------------------------------
typedef SEXP (*findVar_fn_t)(SEXP sym, SEXP rho);
static findVar_fn_t g_findVar_fn = nullptr;

extern "C" void register_findVar_fn(findVar_fn_t fn) {
    g_findVar_fn = fn;
}

inline SEXP Rf_findVar(SEXP sym, SEXP rho) {
    if (!g_findVar_fn)
        throw RError(
            "findVar: Python callback not registered. "
            "findVar (inherits=TRUE path) is not reached by standard rpart "
            "methods. If using method=4 with inherits=TRUE, "
            "register a callback via register_findVar_fn() first.");
    return g_findVar_fn(sym, rho);
}

// Preserve the #define alias from real Rinternals.h:939.
// compat_getVar in rpart_callback.c uses findVar(sym, rho)
// not Rf_findVar(sym, rho).
#define findVar Rf_findVar

// -----------------------------------------------------------------------
// get_R_UnboundValue accessor — needed by Python to obtain the sentinel
// pointer so that py_findVarInFrame can return it on lookup failure.
// The C++ side and the Python side must share the same pointer address.
// -----------------------------------------------------------------------
extern "C" SEXP get_R_UnboundValue() { return R_UnboundValue; }

// -----------------------------------------------------------------------
// .Call boundary wrapper for init_rpcallback.
//
// This is the outermost C-linkage entry point that Python calls via ctypes.
// It pushes an ArenaFrame (Invariant 2), calls init_rpcallback(), and
// catches RError (Invariant 1).
//
// Call chain for init_rpcallback lines 59-69 when method=4:
//   R_getVar("yback", rho, FALSE)        [macro -> compat_getVar]
//     -> compat_getVar(sym, rho, FALSE)  [static C fn]
//       -> findVarInFrame(rho, sym)      [-> Rf_findVarInFrame -> g_findVarInFrame_fn]
//       -> if (val == R_UnboundValue)    [sentinel pointer comparison]
//         -> error("variable '%s'...")   [throws RError, Invariant 1]
//       -> return val                   [SEXP for yback/wback/xback/nback]
//     -> REAL(val) / INTEGER(val)       [data pointer extraction]
//
// If g_findVarInFrame_fn is not registered, Rf_findVarInFrame throws RError.
// The exception unwinds through:
//   compat_getVar -> init_rpcallback -> init_rpcallback_wrapper
//   -> caught by catch(const RError &e)
// -----------------------------------------------------------------------
extern "C" SEXP init_rpcallback_wrapper(
        SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    ArenaFrame _frame;    // Invariant 2: push arena frame; freed on exit
    try {
        return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
    } catch (const RError &e) {
        // Invariant 1: translate C++ exception to a Python-readable message.
        // set_python_error stores the message in thread-local storage so
        // Python can retrieve it after the call returns nullptr.
        set_python_error(e.what());
        return nullptr;   // signals failure to the Python caller
    }
}
```

- **Arena / Memory Notes:**

  `findVarInFrame` does not allocate any memory. It returns a pointer to an existing `SEXP` binding. In the fake runtime, the SEXP returned by `g_findVarInFrame_fn` is a heap-allocated `SEXPREC` constructed on the Python side via `make_real_sexp` or `make_int_sexp`. It is not arena-managed; its lifetime is tied to the numpy arrays that back the `SEXPREC::data` pointer. The static pointers `ydata`, `wdata`, `xdata`, `ndata` in `rpart_callback.c` (lines 37–40) are set to point directly into these numpy buffers and remain valid as long as Python keeps the arrays alive.

  The `ArenaFrame _frame` in `init_rpcallback_wrapper` is present as the standard Invariant 2 guard. `init_rpcallback` itself does not allocate arena memory, but other functions in the same translation unit (`rpart_callback1`, `rpart_callback2`) may, and the `ArenaFrame` stack discipline ensures correct cleanup if those callbacks are invoked in the same thread context.

- **Python Interop Notes:**

  Python must register at minimum one callback — `register_findVarInFrame_fn` — before calling `init_rpcallback_wrapper` when `method=4` is active. The `register_findVar_fn` registration is optional for rpart (the branch is never taken), but should be registered as a safe conservative stub to prevent crashes if conditions change.

  The correctness of the entire lookup depends on a single identity invariant: the `sym` pointer that the C code receives from its `install("yback")` call must be the same pointer that Python used as the key in `_frame_registry`. This is guaranteed because both sides use the same `py_install` memoization function.

  ```python
  import ctypes
  import numpy as np

  # Load the shared library built from the fake-header rpart source.
  lib = ctypes.CDLL("./librpart_fake.so")

  # SEXP is an opaque pointer in Python.
  SEXP = ctypes.c_void_p

  # ----------------------------------------------------------------
  # Step 1: Register the install() stub.
  #
  # install(name) interns a C string as a symbol SEXP.
  # Python maintains a str->c_void_p dict so the same name always
  # returns the same stable pointer address (symbol interning invariant).
  # The sym pointer produced here is used as a key in _frame_registry
  # and is the same pointer the C code receives when it calls
  # install("yback") from within init_rpcallback.
  # ----------------------------------------------------------------
  _symbol_handles: dict = {}   # {name_str: int pointer value}
  _symbol_nodes:   dict = {}   # keep live so GC does not collect backing bytes

  InstallFnType = ctypes.CFUNCTYPE(SEXP, ctypes.c_char_p)

  def py_install(name_bytes: bytes) -> int:
      name = name_bytes.decode()
      if name not in _symbol_handles:
          node = (ctypes.c_char * 1)()   # 1-byte placeholder; address is the handle
          _symbol_nodes[name]   = node
          _symbol_handles[name] = ctypes.cast(node, ctypes.c_void_p).value
      return _symbol_handles[name]

  _install_cb = InstallFnType(py_install)

  lib.register_install_fn.restype  = None
  lib.register_install_fn.argtypes = [InstallFnType]
  lib.register_install_fn(_install_cb)

  # ----------------------------------------------------------------
  # Step 2: Register the findVarInFrame() stub.
  #
  # findVarInFrame(rho, sym) looks up sym in the single frame rho.
  # Argument order: rho first, sym second
  #   (matches Rinternals.h:534 and rpart_callback.c:22).
  #
  # Python maintains a nested registry:
  #   _frame_registry[rho_ptr][sym_ptr] = sexp_value_ptr
  #
  # This registry must be populated with the four "back" array
  # variables before init_rpcallback_wrapper is called.
  # ----------------------------------------------------------------

  # Retrieve R_UnboundValue sentinel pointer so we can return it on miss.
  lib.get_R_UnboundValue.restype  = SEXP
  lib.get_R_UnboundValue.argtypes = []
  R_UNBOUND = lib.get_R_UnboundValue()

  _frame_registry: dict = {}   # {rho_ptr: {sym_ptr: sexp_ptr}}

  FindVarInFrameFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)

  def py_findVarInFrame(rho: int, sym: int) -> int:
      """Look up sym in the frame keyed by rho.
      Returns R_UnboundValue if the (rho, sym) pair is not registered.
      This triggers error("variable '...' not found") in compat_getVar,
      which throws RError and propagates to init_rpcallback_wrapper.
      """
      frame = _frame_registry.get(rho, {})
      val = frame.get(sym)
      if val is None:
          return R_UNBOUND   # == R_UnboundValue on the C side
      return val

  _findVarInFrame_cb = FindVarInFrameFnType(py_findVarInFrame)

  lib.register_findVarInFrame_fn.restype  = None
  lib.register_findVarInFrame_fn.argtypes = [FindVarInFrameFnType]
  lib.register_findVarInFrame_fn(_findVarInFrame_cb)

  # ----------------------------------------------------------------
  # Step 3: Register the findVar() stub (inherits=TRUE path).
  #
  # findVar(sym, rho) walks rho and all parent environments.
  # Argument order: sym first, rho second
  #   (matches Rinternals.h:533 — note reversal from findVarInFrame).
  #
  # This branch is NEVER reached by rpart (inherits is always FALSE).
  # A conservative implementation that always returns R_UnboundValue
  # is safe; it triggers error() in compat_getVar if ever called.
  # ----------------------------------------------------------------
  FindVarFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)

  def py_findVar(sym: int, rho: int) -> int:
      """Walk rho parent chain for sym.
      For rpart, this path is never reached (inherits=FALSE always).
      Minimal fallback: check only the direct frame, then return R_UnboundValue.
      """
      frame = _frame_registry.get(rho, {})
      val = frame.get(sym)
      if val is not None:
          return val
      return R_UNBOUND   # "not found" — triggers error() in compat_getVar

  _findVar_cb = FindVarFnType(py_findVar)

  lib.register_findVar_fn.restype  = None
  lib.register_findVar_fn.argtypes = [FindVarFnType]
  lib.register_findVar_fn(_findVar_cb)

  # ----------------------------------------------------------------
  # Step 4: Populate the frame registry with the four "back" arrays.
  #
  # Python creates four numpy arrays (yback, wback, xback, nback),
  # wraps each as a fake SEXPREC via make_real_sexp / make_int_sexp,
  # and registers the (rho_handle, sym_handle) -> SEXP mapping.
  #
  # The data pointers stored in these SEXPs alias directly into the
  # numpy buffers; the C code reads ydata, wdata, xdata, ndata
  # (set by REAL(stemp) / INTEGER(stemp) in init_rpcallback) for the
  # duration of the rpart() call.  The numpy arrays must remain live.
  # ----------------------------------------------------------------
  n_obs  = 100
  n_resp = 1

  yback_arr = np.zeros(n_obs * n_resp, dtype=np.float64)
  wback_arr = np.ones(n_obs,           dtype=np.float64)
  xback_arr = np.zeros(n_obs,          dtype=np.float64)
  nback_arr = np.array([n_resp],       dtype=np.int32)

  # make_real_sexp / make_int_sexp: build a fake SEXPREC whose data
  # pointer aliases the supplied numpy buffer (no copy).
  lib.make_real_sexp.restype  = SEXP
  lib.make_real_sexp.argtypes = [ctypes.c_void_p, ctypes.c_int]
  lib.make_int_sexp.restype   = SEXP
  lib.make_int_sexp.argtypes  = [ctypes.c_void_p, ctypes.c_int]

  sexp_y = lib.make_real_sexp(yback_arr.ctypes.data_as(ctypes.c_void_p),
                               yback_arr.size)
  sexp_w = lib.make_real_sexp(wback_arr.ctypes.data_as(ctypes.c_void_p),
                               wback_arr.size)
  sexp_x = lib.make_real_sexp(xback_arr.ctypes.data_as(ctypes.c_void_p),
                               xback_arr.size)
  sexp_n = lib.make_int_sexp(nback_arr.ctypes.data_as(ctypes.c_void_p),
                              nback_arr.size)

  # Create a dummy ENVSXP handle as the rho key.
  # This same handle must be passed as rhox to init_rpcallback_wrapper
  # so that py_findVarInFrame can find it in _frame_registry.
  lib.make_env_sexp.restype  = SEXP
  lib.make_env_sexp.argtypes = []
  rho_handle = lib.make_env_sexp()

  # Use py_install to produce the same stable sym handles that the C code
  # receives when it calls install("yback") etc. inside init_rpcallback.
  _frame_registry[rho_handle] = {
      py_install(b"yback"): sexp_y,
      py_install(b"wback"): sexp_w,
      py_install(b"xback"): sexp_x,
      py_install(b"nback"): sexp_n,
  }

  # ----------------------------------------------------------------
  # Step 5: Call init_rpcallback_wrapper.
  #
  # rhox must be rho_handle — the same pointer used as the key in
  # _frame_registry — so that py_findVarInFrame dispatches correctly.
  # ----------------------------------------------------------------
  lib.init_rpcallback_wrapper.restype  = SEXP
  lib.init_rpcallback_wrapper.argtypes = [SEXP, SEXP, SEXP, SEXP, SEXP]

  ny_arr  = np.array([n_resp], dtype=np.int32)
  nr_arr  = np.array([n_resp], dtype=np.int32)
  sexp_ny = lib.make_int_sexp(ny_arr.ctypes.data_as(ctypes.c_void_p), 1)
  sexp_nr = lib.make_int_sexp(nr_arr.ctypes.data_as(ctypes.c_void_p), 1)

  # expr1 and expr2 are R language objects (LANGSXP); in the fake they
  # are opaque SEXP handles forwarded to eval(). Pass None (nullptr) if
  # the eval() callback is not registered (init-only without callbacks).
  result = lib.init_rpcallback_wrapper(
      rho_handle,   # rhox:   must match the key used in _frame_registry
      sexp_ny,      # ny:     number of response columns (scalar INTSXP)
      sexp_nr,      # nr:     length of user eval return vector (scalar INTSXP)
      None,         # expr1x: R split expression (opaque; None OK if eval not registered)
      None,         # expr2x: R value expression (opaque; None OK if eval not registered)
  )

  # Check for error.
  lib.get_last_rerror_message.restype  = ctypes.c_char_p
  lib.get_last_rerror_message.argtypes = []
  msg = lib.get_last_rerror_message()
  if msg:
      raise RuntimeError(f"init_rpcallback failed: {msg.decode()}")
  ```

- **Explanation:**

  The fake defines `g_findVarInFrame_fn` as a `static` global function pointer of type `findVarInFrame_fn_t` (i.e., `SEXP(*)(SEXP, SEXP)` with `rho` first, `sym` second). The inline `Rf_findVarInFrame` stub checks the pointer and either delegates to the Python callback or throws `RError`. The `#define findVarInFrame Rf_findVarInFrame` alias ensures that `findVarInFrame(rho, sym)` at line 22 expands to `Rf_findVarInFrame(rho, sym)` — the same expansion as the real `Rinternals.h:940`. The original source file `rpart_callback.c` is not modified.

  The parallel `findVar` stub uses type `findVar_fn_t` (i.e., `SEXP(*)(SEXP, SEXP)` with `sym` first, `rho` second — note the reversed argument order relative to `findVarInFrame`). This correctly models `Rf_findVar(SEXP sym, SEXP rho)` as declared at `Rinternals.h:533`. The `#define findVar Rf_findVar` alias at `Rinternals.h:939` is also reproduced.

  The correctness of the lookup depends on a single invariant: whenever the C code calls `install("yback")` to produce a `sym` argument, it must receive the same pointer that was used as the key in `_frame_registry`. This is guaranteed because `py_install` is memoized — `py_install(b"yback")` called during registry population and `py_install(b"yback")` called later by `g_install_fn` from inside `init_rpcallback` both return the same `int` address. The `_symbol_nodes` dict keeps the backing `c_char` allocation alive so the pointer remains valid.

  The `g_findVarInFrame_fn` variable is declared `static` within the header. For a multi-translation-unit build, it must be promoted to external linkage (declared `extern` in the header and defined once in a `.cpp` file) to avoid ODR violations. Alternatively, placing all stub definitions in a single `.cpp` translation unit avoids this issue entirely.

  The `get_R_UnboundValue()` C-linkage accessor is required so that Python can read the sentinel's address via `lib.get_R_UnboundValue()` and use it as the failure return value from `py_findVarInFrame`. Without this accessor, Python has no way to know what pointer value represents "not found" on the C side. This accessor is also referenced in `R_UnboundValue.md` and `findVar.md`; the final header must provide exactly one definition.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct (`type`, `length`, `nrow`, `ncol`, `data`) and `typedef SEXPREC *SEXP`. The `findVarInFrame_fn_t` and `findVar_fn_t` typedefs and the `Rf_findVarInFrame` / `Rf_findVar` stubs all have `SEXP` parameter and return types. Must be compiled before `findVarInFrame` / `findVar` stubs are defined. `SEXP.md` also establishes the complete `fake_Rinternals.hpp` listing including `PRINTNAME`, `CHAR`, `REAL`, `INTEGER`, and `R_UnboundValue` — all used in the call chain around `findVarInFrame`. |
| `error.md` | Provides the `RError` exception class (`struct RError : public std::runtime_error`) and the `Rf_error` / `error` throwing implementation (Invariant 1). Required because: (a) the `Rf_findVarInFrame` stub throws `RError` when the callback is null, and (b) `compat_getVar` at `rpart_callback.c:24` calls `error(...)` which expands to `Rf_error(...)` throwing `RError` when `val == R_UnboundValue`. `RError` must be defined before the `findVarInFrame` stubs are parsed. |
| `R_UnboundValue.md` | Provides the static `R_UnboundValue` sentinel `SEXP` (a stable pointer distinct from any valid binding) and the `make_unbound_value()` function. The Python-side `py_findVarInFrame` callback returns `R_UnboundValue` when the symbol is not found; `compat_getVar` compares `val == R_UnboundValue` at line 23 to detect the failure condition. Pointer identity between the C-side `R_UnboundValue` and the Python-obtained sentinel (via `lib.get_R_UnboundValue()`) is guaranteed by the `get_R_UnboundValue` accessor also established in this guide. |
| `findVar.md` | Provides the `Rf_findVar` stub, `g_findVar_fn`, `register_findVar_fn`, and `#define findVar Rf_findVar`. `findVar` and `findVarInFrame` appear in the same ternary expression at `rpart_callback.c:22`; both must be defined. `findVar.md` is the authoritative specification for `findVar`; this guide is the authoritative specification for `findVarInFrame`. The final `fake_Rinternals.hpp` must consolidate to a single definition of each stub, using the versions from their respective authoritative guides. |
| `R_getVar.md` | Documents the complete call chain for the four `R_getVar(install("..."), rho, FALSE)` call sites in `init_rpcallback` and contains abbreviated `findVar` / `findVarInFrame` stubs that are superseded by the complete versions in this guide and `findVar.md`. `R_getVar.md` also establishes the `install` stub (`g_install_fn`, `register_install_fn`, `install(const char *)`), which is required because `install("yback")` etc. produce the `sym` argument that `findVarInFrame` receives. |
| `Rboolean.md` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean` in `fake_Boolean.hpp`. Required because `compat_getVar` (the function that calls `findVarInFrame`) has `Rboolean inherits` as its third parameter. Must be included before `fake_Rinternals.hpp` is parsed. |
| `FALSE.md` | Establishes that `FALSE` is enumerator `0` of `Rboolean`. All four `R_getVar` call sites in `init_rpcallback` pass `FALSE` as `inherits`; `compat_getVar` uses it in the boolean ternary at line 22 to dispatch to `findVarInFrame`. |
| `CHAR.md` | Provides the `CHAR(SEXP x)` inline function extracting `const char *` from a `CHARSXP`. Required because `compat_getVar` at line 24 calls `CHAR(PRINTNAME(sym))` for the error message when a variable is not found. |
| `PRINTNAME.md` | Provides the `PRINTNAME(SEXP x)` inline function returning the `CHARSXP` name field of a `SYMSXP`. Required alongside `CHAR.md` for the same `rpart_callback.c:24` error message. |
| `R_VERSION.md` / `R_Version.md` / `fake_Rversion.hpp` | Must define `R_VERSION` as a compile-time integer constant and `R_Version(major, minor, patch)` as a macro such that `R_VERSION < R_Version(4, 5, 0)` evaluates to `1` (true) at preprocessing time. Without this, the `#if` guard at `rpart_callback.c:19` suppresses `compat_getVar` and the `#define R_getVar` macro, leaving both `findVar` and `findVarInFrame` absent from the call graph and leaving `init_rpcallback` with unresolved `R_getVar` identifiers. |
| `fake_arena.hpp` | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, `arena_calloc`. Required by `init_rpcallback_wrapper` for the `ArenaFrame _frame` RAII guard (Invariant 2). Not used by `findVarInFrame`, `findVar`, or `compat_getVar` directly. |
