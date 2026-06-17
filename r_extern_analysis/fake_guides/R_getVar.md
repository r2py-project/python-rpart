# Fake Header Implementation Guide: `R_getVar`

> **R Interpreter Item.** `R_getVar` (in the form used by rpart) performs a symbol lookup in an R environment. A complete fake is impossible without a running R interpreter because the environment frame chain, the symbol table, and the variable bindings it searches are all managed by the R runtime. For R < 4.5.0, `R_getVar` is not a library function at all — it is a source-level macro that expands to a local compatibility shim (`compat_getVar`) which calls `findVar` or `findVarInFrame`. The fake for `R_getVar` therefore consists of: (a) ensuring that the `#define R_getVar` macro is compiled (by setting `R_VERSION < R_Version(4,5,0)` in `fake_Rversion.hpp`), and (b) providing Python-registered function pointer stubs for `findVar` and `findVarInFrame`, on which `compat_getVar` depends at runtime. This guide documents that structure and provides the complete stub, registration function, and Python-side `ctypes` code.

---

### 1. Overview of `R_getVar` in R API

`R_getVar(SEXP symbol, SEXP rho, Rboolean inherits)` looks up a variable named `symbol` in the R environment `rho`. When `inherits` is `TRUE`, the search walks the parent environment chain (equivalent to `findVar`); when `inherits` is `FALSE`, the search is confined to the immediate frame `rho` (equivalent to `findVarInFrame`). On success it returns the bound `SEXP` value; on failure it signals an error. `R_getVar` as a standalone C API function was introduced in R 4.5.0. In R versions below 4.5.0 — which is the version bracket that the fake build targets — `R_getVar` does not exist as a library symbol. Instead, `rpart_callback.c` defines a local static shim function `compat_getVar` with the same signature and registers it under the name `R_getVar` via a preprocessor macro. Because all three dependencies of `compat_getVar` — `findVar`, `findVarInFrame`, and `install` — require a running R interpreter to function correctly, `R_getVar` is an **R Interpreter Item** (Category E, Invariant 3 applies).

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart_callback.c` | 1–83 | Full file header, `compat_getVar` shim, static globals, `init_rpcallback` body |

**Context window for all four CSV rows (lines 18–72):**

```c
/* rpart_callback.c:18-28 — compat_getVar shim and macro definition */
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

/* rpart_callback.c:30-40 — static module-level variables */
static int ysave;
static int rsave;
static SEXP expr1;
static SEXP expr2;
static SEXP rho;
static double *ydata;
static double *xdata;
static double *wdata;
static int    *ndata;

/* rpart_callback.c:47-72 — init_rpcallback, the only call site */
SEXP
init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;

    rho   = rhox;
    ysave = asInteger(ny);
    rsave = asInteger(nr);
    expr1 = expr1x;
    expr2 = expr2x;

    stemp = R_getVar(install("yback"), rho, FALSE);  /* line 59 */
    ydata = REAL(stemp);

    stemp = R_getVar(install("wback"), rho, FALSE);  /* line 62 */
    wdata = REAL(stemp);

    stemp = R_getVar(install("xback"), rho, FALSE);  /* line 65 */
    xdata = REAL(stemp);

    stemp = R_getVar(install("nback"), rho, FALSE);  /* line 68 */
    ndata = INTEGER(stemp);

    return R_NilValue;
}
```

**C types of arguments and return values.**

| Argument | Declared type | Meaning at call site |
|---|---|---|
| `sym` (first) | `SEXP` | A symbol SEXP produced by `install("yback")` etc.; holds the interned string name |
| `rho` (second) | `SEXP` | An environment SEXP passed in from Python as `rhox`; the frame in which to search |
| `inherits` (third) | `Rboolean` | Always `FALSE` (value `0`) at all four call sites: search only the immediate frame |
| return value | `SEXP` | A SEXP holding the value of the named variable in `rho`; type varies by variable: `REALSXP` for `yback`/`wback`/`xback`, `INTSXP` for `nback` |

**Return value downstream usage.**

After each `R_getVar` call, `stemp` is immediately accessed via an accessor:

| Line | Variable sought | Downstream accessor | Result stored in |
|---|---|---|---|
| 59–60 | `"yback"` | `REAL(stemp)` | `ydata` (`double *`) |
| 62–63 | `"wback"` | `REAL(stemp)` | `wdata` (`double *`) |
| 65–66 | `"xback"` | `REAL(stemp)` | `xdata` (`double *`) |
| 68–69 | `"nback"` | `INTEGER(stemp)` | `ndata` (`int *`) |

These static pointers (`ydata`, `wdata`, `xdata`, `ndata`) are subsequently used inside `rpart_callback1` and `rpart_callback2` when `method=4` (user-defined splits) is active. The returned SEXPs are `REALSXP` for the first three and `INTSXP` for the fourth; the Python side must supply appropriately typed SEXP handles.

**Co-occurring R API items in the context window.**

| Item | Line | Role |
|---|---|---|
| `findVar(sym, rho)` | 22 | Called when `inherits=TRUE`; not reached at any rpart call site (always `FALSE`) |
| `findVarInFrame(rho, sym)` | 22 | Called when `inherits=FALSE`; reached at all four call sites; Category E |
| `R_UnboundValue` | 23 | Sentinel comparison; `compat_getVar` throws if the lookup returns this sentinel |
| `error(...)` | 24 | Throws `RError` in the fake runtime (Invariant 1) when variable is not found |
| `CHAR(PRINTNAME(sym))` | 24 | Extracts symbol name for the error message; uses fake `PRINTNAME` and `CHAR` from `SEXP.md` |
| `install("yback")` etc. | 59,62,65,68 | Produces the `sym` SEXP argument; Category E item, documented in `install.md` |
| `REAL(stemp)` | 60,63,66 | Extracts `double *` from the returned `REALSXP` SEXP |
| `INTEGER(stemp)` | 69 | Extracts `int *` from the returned `INTSXP` SEXP |
| `asInteger(ny)`, `asInteger(nr)` | 54,55 | Scalar coercions; unrelated to `R_getVar` |
| `R_NilValue` | 71 | Return value of `init_rpcallback`; returned unconditionally |

**Distinct implementation patterns.**

There is exactly one implementation pattern across all four CSV rows:

**Pattern: Variable lookup in an environment frame using `R_getVar` (via `compat_getVar`) with `inherits=FALSE`, followed by immediate SEXP data-pointer extraction.**

All four call sites are structurally identical: `R_getVar(install("<name>"), rho, FALSE)` returns a `SEXP`, and `REAL()` or `INTEGER()` extracts its data pointer. The only variation is the variable name and the downstream accessor (`REAL` vs. `INTEGER`). This variation does not require separate fake treatment — the fake mechanism is the same for all four.

---

### 3. Fake C++ Implementation Strategy

**Category: E — R Interpreter Item.**

`R_getVar` requires a running R environment for two reasons: (1) the `install("<name>")` call that produces its first argument interns the string in R's global symbol table, and (2) the `findVarInFrame(rho, sym)` call that does the actual lookup traverses R's environment frame structure. Neither operation can be replicated without R's internal data structures.

**Why `R_getVar` itself does not need a function pointer stub.**

For R < 4.5.0, `R_getVar` is not a library function — it is defined by `rpart_callback.c` itself as the preprocessor macro:

```c
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
```

This macro, along with the `compat_getVar` static function, is compiled as part of `rpart_callback.c` when `R_VERSION < R_Version(4, 5, 0)`. The fake build forces this condition to be true via `fake_Rversion.hpp` (documented in `R_VERSION.md` and `R_Version.md`), so `R_getVar` is always resolved to `compat_getVar` at the preprocessor stage — before the linker is involved. No separate function pointer stub is needed for `R_getVar` itself.

**Where the function pointer stubs are needed.**

The function pointer bridges are required for the two items that `compat_getVar` calls at runtime:

1. `findVarInFrame(rho, sym)` — called when `inherits=FALSE`, which is always the case at the four `R_getVar` call sites in rpart. This is a Category E item with its own stub (`g_findVarInFrame_fn`), as established in `R_UnboundValue.md`.
2. `install("yback")` etc. — called to produce the `sym` argument before `compat_getVar` is entered. This is a Category E item with its own stub, documented in `install.md`.

`findVar(sym, rho)` (the `inherits=TRUE` branch) is never reached at the rpart call sites but must still resolve to a stub to allow compilation. Its stub (`g_findVar_fn`) is established in `R_UnboundValue.md`.

**The complete call chain for `R_getVar(install("yback"), rho, FALSE)`:**

```
R_getVar("yback", rho, FALSE)                         [macro, expands under R_VERSION < 4.5.0]
  -> compat_getVar(install("yback"), rho, FALSE)       [static C function in rpart_callback.c]
       -> install("yback")  [evaluated before call]    [Category E stub: g_install_fn]
       -> findVarInFrame(rho, sym)                     [Category E stub: g_findVarInFrame_fn]
       -> if (val == R_UnboundValue)                   [sentinel check; SEXP pointer equality]
            -> error("variable '%s' not found", ...)   [throws RError via Invariant 1]
       -> return val                                   [the SEXP looked up by Python side]
```

**The `compat_getVar` function compiles unmodified** because:
- `SEXP`, `Rboolean`, `FALSE` are defined by `fake_Boolean.hpp` and `fake_Rinternals.hpp`.
- `findVar`, `findVarInFrame` are inline stubs in `fake_Rinternals.hpp`.
- `R_UnboundValue` is a static sentinel `SEXP` in `fake_Rinternals.hpp`.
- `error(...)` expands to `Rf_error(...)` which throws `RError` (Invariant 1).
- `CHAR`, `PRINTNAME` are inline functions in `fake_Rinternals.hpp`.

**The `R_getVar` function pointer stub itself.**

For documentation completeness and to support a possible future R >= 4.5.0 build path (where `R_getVar` would be a real library function rather than a macro), the fake header provides an optional `R_getVar` function pointer stub. This stub is **not used by the current rpart code** under the forced `R_VERSION < 4.5.0` build, but it is shown here to satisfy the guide structure and to document the semantics precisely.

**`#define` aliases that must be preserved.**

The macro `#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)` is defined in the original source file `rpart_callback.c` (line 27), not in any R header. It does not need to appear in the fake header. The fake header must, however, ensure that all names the macro expansion depends on (`findVar`, `findVarInFrame`, `R_UnboundValue`, `error`, `CHAR`, `PRINTNAME`, `Rboolean`, `FALSE`) are defined — which they are, by the headers already established in previous guides.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): triggered at `rpart_callback.c:24` — the `error(...)` call inside `compat_getVar` when `val == R_UnboundValue`. In the fake build, `error` expands to `Rf_error`, which formats the message with `vsnprintf` and throws `RError`. The `.Call` boundary wrapper for `init_rpcallback` must catch `RError`.
- Invariant 2 (arena memory): not directly triggered by `R_getVar` / `compat_getVar`. The `init_rpcallback` entry point does not allocate arena memory itself, but it is compiled in the same translation unit as callback functions that may. An `ArenaFrame` guard is required at the entry of `init_rpcallback`'s `.Call` wrapper as a precautionary standard measure.
- Invariant 3 (R Interpreter Items): fully applicable. `compat_getVar` calls `findVarInFrame` (and potentially `findVar`), which are Category E items. The `install` calls before `compat_getVar` are also Category E. Python must register both `g_findVarInFrame_fn` and `g_install_fn` before calling `init_rpcallback`.

---

### 4. Fake Implementation Examples

#### Pattern: Variable Lookup in Environment Frame via `compat_getVar` (all four call sites)

- **Locations:** `rpart_callback.c:59`, `rpart_callback.c:62`, `rpart_callback.c:65`, `rpart_callback.c:68`

- **Original R API Usage:**

```c
/* rpart_callback.c:18-28 — compat_getVar shim, compiled when R_VERSION < 4.5.0 */
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

/* rpart_callback.c:59-69 — all four call sites in init_rpcallback */
stemp = R_getVar(install("yback"), rho, FALSE);
ydata = REAL(stemp);

stemp = R_getVar(install("wback"), rho, FALSE);
wdata = REAL(stemp);

stemp = R_getVar(install("xback"), rho, FALSE);
xdata = REAL(stemp);

stemp = R_getVar(install("nback"), rho, FALSE);
ndata = INTEGER(stemp);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (additions for R_getVar support)
// These stubs must be added AFTER the SEXPREC/SEXP typedef block,
// AFTER the RError definition (from error.md / fake_Rinternals.hpp),
// and AFTER the R_UnboundValue sentinel definition.
//
// The R_getVar macro itself is defined in rpart_callback.c:27 and
// does not need to appear in the fake header.  The fake header only
// needs to supply the items that compat_getVar depends on at runtime.

// -----------------------------------------------------------------------
// install — R Interpreter Item (Category E).
//
// install(const char *name) interns a C string as an R symbol SEXP
// (SYMSXP).  In the real R runtime, it looks up or creates an entry in
// the global symbol table.  In the fake, it is a Python-registered
// function pointer that returns a stable SEXP handle for each name.
//
// The stub below follows the same pattern as findVar / findVarInFrame
// established in R_UnboundValue.md.  It is shown here because install()
// is evaluated before compat_getVar is entered — it produces the sym
// argument that compat_getVar receives.
// -----------------------------------------------------------------------
typedef SEXP (*install_fn_t)(const char *name);
static install_fn_t g_install_fn = nullptr;

extern "C" void register_install_fn(install_fn_t fn) {
    g_install_fn = fn;
}

inline SEXP install(const char *name) {
    if (!g_install_fn)
        throw RError("install: Python callback not registered. "
                     "init_rpcallback() and user-defined splits (method=4) "
                     "require registration via register_install_fn().");
    return g_install_fn(name);
}
#define Rf_install install

// -----------------------------------------------------------------------
// findVar — R Interpreter Item (Category E).
//
// findVar(SEXP sym, SEXP rho) searches rho and its parent chain.
// Not reached by any rpart call site (inherits is always FALSE),
// but must compile.  Stub identical to the one in R_UnboundValue.md.
// -----------------------------------------------------------------------
typedef SEXP (*findVar_fn_t)(SEXP sym, SEXP rho);
static findVar_fn_t g_findVar_fn = nullptr;

extern "C" void register_findVar_fn(findVar_fn_t fn) {
    g_findVar_fn = fn;
}

inline SEXP findVar(SEXP sym, SEXP rho) {
    if (!g_findVar_fn)
        throw RError("findVar: Python callback not registered. "
                     "User-defined splits (method=4) and init_rpcallback() "
                     "require registration via register_findVar_fn().");
    return g_findVar_fn(sym, rho);
}
#define Rf_findVar findVar

// -----------------------------------------------------------------------
// findVarInFrame — R Interpreter Item (Category E).
//
// findVarInFrame(SEXP rho, SEXP sym) searches only the immediate frame.
// Called when inherits=FALSE — which is always the case for the four
// R_getVar calls in init_rpcallback.
// Stub identical to the one in R_UnboundValue.md.
// -----------------------------------------------------------------------
typedef SEXP (*findVarInFrame_fn_t)(SEXP rho, SEXP sym);
static findVarInFrame_fn_t g_findVarInFrame_fn = nullptr;

extern "C" void register_findVarInFrame_fn(findVarInFrame_fn_t fn) {
    g_findVarInFrame_fn = fn;
}

inline SEXP findVarInFrame(SEXP rho, SEXP sym) {
    if (!g_findVarInFrame_fn)
        throw RError("findVarInFrame: Python callback not registered. "
                     "init_rpcallback() requires registration via "
                     "register_findVarInFrame_fn().");
    return g_findVarInFrame_fn(rho, sym);
}
#define Rf_findVarInFrame findVarInFrame

// -----------------------------------------------------------------------
// R_getVar (optional stub for R >= 4.5.0 compatibility path).
//
// In the current fake build, R_VERSION is forced below R_Version(4,5,0),
// so the macro #define R_getVar(...) compat_getVar(...) in rpart_callback.c
// is always active and this stub is NEVER called.  It is provided here
// for documentation purposes and for a future build that does not force
// the version gate.
//
// If the version gate were NOT forced and R >= 4.5.0 were simulated,
// R_getVar would need to be a real symbol.  Its implementation would
// delegate directly to findVarInFrame / findVar per the inherits flag,
// matching the semantics of compat_getVar exactly.
// -----------------------------------------------------------------------
typedef SEXP (*R_getVar_fn_t)(SEXP sym, SEXP rho, Rboolean inherits);
static R_getVar_fn_t g_R_getVar_fn = nullptr;

extern "C" void register_R_getVar_fn(R_getVar_fn_t fn) {
    g_R_getVar_fn = fn;
}

// NOTE: This inline function is intentionally NOT defined when
// R_VERSION < R_Version(4,5,0), because in that case the macro
// #define R_getVar(...) compat_getVar(...) in rpart_callback.c takes
// precedence and the function below would be shadowed / cause a
// redefinition conflict with the macro.
//
// To enable this stub for a >= 4.5.0 path, wrap it in:
//   #if R_VERSION >= R_Version(4, 5, 0)
//   inline SEXP R_getVar(SEXP sym, SEXP rho, Rboolean inherits) {
//       if (!g_R_getVar_fn) {
//           // Fall back to the findVar / findVarInFrame stubs.
//           SEXP val = inherits ? findVar(sym, rho)
//                               : findVarInFrame(rho, sym);
//           if (val == R_UnboundValue)
//               throw RError("R_getVar: variable not found");
//           return val;
//       }
//       return g_R_getVar_fn(sym, rho, inherits);
//   }
//   #endif

// -----------------------------------------------------------------------
// .Call boundary wrapper for init_rpcallback.
//
// This wrapper is the outermost C-linkage function callable from Python
// via ctypes.  It pushes an ArenaFrame (Invariant 2), calls the original
// init_rpcallback(), and catches RError (Invariant 1).
//
// Note: init_rpcallback itself does not perform arena allocations, but
// other functions in the same translation unit (rpart_callback1,
// rpart_callback2) do.  The ArenaFrame is placed here as a standard
// guard for the entire callback subsystem.
// -----------------------------------------------------------------------
extern "C" SEXP init_rpcallback_wrapper(
        SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    ArenaFrame _frame;    // Invariant 2: free arena allocations on exit
    try {
        return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
    } catch (const RError &e) {
        // Invariant 1: translate C++ exception to a Python-readable error.
        // set_python_error stores the message where the Python glue can
        // retrieve it after the call returns nullptr.
        set_python_error(e.what());
        return nullptr;   // signals failure; Python checks for nullptr
    }
}
```

- **Python Interop Notes:**

  The `init_rpcallback` function is only needed when `method=4` (user-defined splits) is passed to `rpart()`. All standard methods (anova, poisson, class, exp) use built-in evaluation functions in `func_table.h` and never call `init_rpcallback`. For standard use cases, none of the stubs below need to be registered.

  For user-defined splits, Python must register three callbacks before calling `init_rpcallback_wrapper`:

  1. `register_install_fn` — maps a symbol name string to a stable SEXP handle.
  2. `register_findVarInFrame_fn` — looks up a SEXP symbol handle in a Python-managed variable registry keyed by the environment SEXP handle.
  3. `register_findVar_fn` — same as `findVarInFrame` but with parent-chain walk (not reached by rpart, but required for the stub to compile without error if called).

  The `rho` SEXP passed to `init_rpcallback_wrapper` is constructed on the Python side as an opaque handle (a `c_void_p` pointing to a fake `SEXPREC`) and serves as the lookup key that `py_findVarInFrame` uses to dispatch into the Python variable registry.

  ```python
  import ctypes

  # Load the shared library built from the fake-header rpart source.
  lib = ctypes.CDLL("./librpart_fake.so")

  # SEXP is an opaque pointer in Python.
  SEXP = ctypes.c_void_p

  # ----------------------------------------------------------------
  # Step 1: Register the install() stub.
  #
  # install(name) interns a C string as a symbol SEXP.
  # Python maintains a string->c_void_p dict so that the same name
  # always returns the same pointer address.
  # ----------------------------------------------------------------
  _symbol_handles: dict = {}  # {name_str: c_void_p address}

  InstallFnType = ctypes.CFUNCTYPE(SEXP, ctypes.c_char_p)

  def py_install(name_bytes: bytes) -> int:
      name = name_bytes.decode()
      if name not in _symbol_handles:
          # Allocate a tiny fake SEXPREC to serve as a stable symbol handle.
          # In practice, a simple Python integer key is sufficient because
          # the pointer is only used for identity comparisons.
          node = (ctypes.c_char * 1)()           # 1-byte placeholder
          _symbol_handles[name] = ctypes.cast(node, ctypes.c_void_p).value
          _symbol_nodes[name] = node             # keep alive
      return _symbol_handles[name]

  _symbol_nodes: dict = {}   # keep nodes alive so GC doesn't collect them
  _install_cb = InstallFnType(py_install)

  lib.register_install_fn.restype  = None
  lib.register_install_fn.argtypes = [InstallFnType]
  lib.register_install_fn(_install_cb)

  # ----------------------------------------------------------------
  # Step 2: Register the findVarInFrame() stub.
  #
  # findVarInFrame(rho, sym) looks up sym in the frame rho.
  # The Python side maintains a nested registry:
  #   _frame_registry[rho_ptr][sym_ptr] = sexp_value_ptr
  #
  # Before calling init_rpcallback_wrapper, Python populates
  # _frame_registry with the four "back" variables.
  # ----------------------------------------------------------------

  # Retrieve R_UnboundValue sentinel so we can return it on failure.
  lib.get_R_UnboundValue.restype  = SEXP
  lib.get_R_UnboundValue.argtypes = []
  R_UNBOUND = lib.get_R_UnboundValue()

  _frame_registry: dict = {}  # {rho_ptr: {sym_ptr: val_ptr}}

  FindVarInFrameFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)

  def py_findVarInFrame(rho: int, sym: int) -> int:
      """
      Look up sym in the frame keyed by rho.
      Return R_UnboundValue sentinel if not found.
      """
      frame = _frame_registry.get(rho, {})
      val = frame.get(sym)
      if val is None:
          return R_UNBOUND   # triggers error() in compat_getVar
      return val

  _findVarInFrame_cb = FindVarInFrameFnType(py_findVarInFrame)

  lib.register_findVarInFrame_fn.restype  = None
  lib.register_findVarInFrame_fn.argtypes = [FindVarInFrameFnType]
  lib.register_findVarInFrame_fn(_findVarInFrame_cb)

  # ----------------------------------------------------------------
  # Step 3: Register the findVar() stub (inherits=TRUE path).
  # Not reached by rpart call sites, but must not crash if called.
  # A minimal implementation that always returns R_UnboundValue.
  # ----------------------------------------------------------------
  FindVarFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)

  def py_findVar(sym: int, rho: int) -> int:
      return R_UNBOUND   # conservative: always "not found"

  _findVar_cb = FindVarFnType(py_findVar)

  lib.register_findVar_fn.restype  = None
  lib.register_findVar_fn.argtypes = [FindVarFnType]
  lib.register_findVar_fn(_findVar_cb)

  # ----------------------------------------------------------------
  # Step 4: Populate the frame registry with the four "back" arrays.
  #
  # Python creates four numpy arrays (yback, wback, xback, nback),
  # wraps each as a fake SEXPREC via a helper, and registers the
  # symbol->SEXP mapping under the rho handle.
  # ----------------------------------------------------------------
  import numpy as np

  # Example data (adapt to your problem dimensions):
  n_obs   = 100
  n_resp  = 1
  yback_arr = np.zeros((n_obs * n_resp,), dtype=np.float64)
  wback_arr = np.ones(n_obs, dtype=np.float64)
  xback_arr = np.zeros((n_obs, 10), dtype=np.float64, order='F')
  nback_arr = np.array([n_resp], dtype=np.int32)

  # make_sexp_from_numpy: build a fake SEXPREC pointing into the numpy buffer.
  # (Implementation assumed available from the fake header build infrastructure.)
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

  # The rho SEXP handle is whatever pointer Python passed as rhox.
  # Here it is created as a dummy SEXPREC (ENVSXP type) that serves
  # only as a dict key.
  lib.make_env_sexp.restype  = SEXP
  lib.make_env_sexp.argtypes = []
  rho_handle = lib.make_env_sexp()

  # Populate the frame registry for rho_handle.
  _frame_registry[rho_handle] = {
      py_install(b"yback"): sexp_y,
      py_install(b"wback"): sexp_w,
      py_install(b"xback"): sexp_x,
      py_install(b"nback"): sexp_n,
  }

  # ----------------------------------------------------------------
  # Step 5: Call init_rpcallback_wrapper.
  # ----------------------------------------------------------------
  lib.init_rpcallback_wrapper.restype  = SEXP
  lib.init_rpcallback_wrapper.argtypes = [SEXP, SEXP, SEXP, SEXP, SEXP]

  # ny and nr are scalar integer SEXPs.
  ny_arr = np.array([n_resp], dtype=np.int32)
  nr_arr = np.array([n_resp], dtype=np.int32)
  sexp_ny = lib.make_int_sexp(ny_arr.ctypes.data_as(ctypes.c_void_p), 1)
  sexp_nr = lib.make_int_sexp(nr_arr.ctypes.data_as(ctypes.c_void_p), 1)

  # expr1 and expr2 are R language objects; in the fake they are opaque
  # SEXP handles passed through to eval() stubs.  Use nullptr if the
  # eval() stub is not registered (standard methods only).
  result = lib.init_rpcallback_wrapper(
      rho_handle,   # rhox:   the environment frame
      sexp_ny,      # ny:     number of response columns
      sexp_nr,      # nr:     length of user's eval return vector
      None,         # expr1x: R expression for splits (opaque; nullptr OK)
      None,         # expr2x: R expression for values (opaque; nullptr OK)
  )

  # Check for error.
  lib.get_last_rerror_message.restype  = ctypes.c_char_p
  lib.get_last_rerror_message.argtypes = []
  msg = lib.get_last_rerror_message()
  if msg:
      raise RuntimeError(f"init_rpcallback failed: {msg.decode()}")
  ```

- **Arena / Memory Notes:**

  `R_getVar` / `compat_getVar` does not allocate any memory. The `SEXP val` variable inside `compat_getVar` receives a pointer returned by `findVarInFrame`, which on the fake Python side is a pointer to a fake SEXPREC constructed by `make_real_sexp` or `make_int_sexp` above. That SEXPREC is heap-allocated (via `std::malloc`) by the Python-side helper functions and is not arena-managed. Its lifetime is tied to the numpy arrays (`yback_arr`, etc.) supplied by Python; the data pointer stored in `sexp->data` aliases directly into the numpy buffer and must not be freed while `ydata`, `wdata`, `xdata`, or `ndata` are in use by the rpart callback functions.

  The `ArenaFrame _frame` guard in `init_rpcallback_wrapper` is a precautionary standard measure; no arena allocation occurs inside `init_rpcallback` itself. Arena cleanup is relevant for subsequent callback invocations (`rpart_callback1`, `rpart_callback2`) that may allocate scratch memory via `R_alloc` / `ALLOC` — those wrappers also need `ArenaFrame` guards.

- **Explanation:**

  The fake does not need to define `R_getVar` as a function. Under the fake build's version constraint (`R_VERSION < R_Version(4, 5, 0)`, enforced by `fake_Rversion.hpp`), the macro `#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)` defined at `rpart_callback.c:27` takes effect at the preprocessor stage and redirects every `R_getVar(...)` call to `compat_getVar(...)`. The fake header's job is only to supply the items that `compat_getVar` itself references: `findVar`, `findVarInFrame`, `R_UnboundValue`, `error`, `CHAR`, `PRINTNAME`, `Rboolean`, `FALSE` — all of which are already established by previously generated guides.

  The original `rpart_callback.c` source file is not modified in any way. The shadow include tree resolves `#include <Rinternals.h>` to `fake_Rinternals.hpp`, which provides all the required definitions. `compat_getVar` compiles as a standard static C function calling the fake inline stubs. At runtime, each `R_getVar(install("yback"), rho, FALSE)` call evaluates as:
  1. `g_install_fn("yback")` returns a stable SEXP handle for the symbol.
  2. `g_findVarInFrame_fn(rho, sym)` looks up that handle in the Python-managed `_frame_registry` and returns the associated SEXP.
  3. `compat_getVar` checks `val == R_UnboundValue` (false if the symbol was found) and returns `val`.
  4. `REAL(val)` or `INTEGER(val)` extracts the data pointer from the returned SEXP into the static `ydata`/`wdata`/`xdata`/`ndata` pointers.

  The only code paths that cannot be exercised without the registered stubs are those inside `init_rpcallback` (lines 59–69) and the downstream `rpart_callback1` / `rpart_callback2` functions — all of which are guarded by the `method=4` branch in the rpart R layer. Standard tree fitting (methods anova, poisson, class, exp) never calls `init_rpcallback` and therefore never triggers any of the interpreter stubs.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct (`type`, `length`, `nrow`, `ncol`, `data`) and `typedef SEXPREC *SEXP`. Required because `compat_getVar` takes `SEXP sym`, `SEXP rho` parameters and returns `SEXP`; the `install`, `findVar`, `findVarInFrame` stubs all have `SEXP` parameter and return types. `SEXP.md` also establishes `SYMSXP`, `REAL`, `INTEGER`, `CHAR`, `PRINTNAME`, `R_NilValue`, `R_UnboundValue`, and the complete `fake_Rinternals.hpp` listing. |
| `R_UnboundValue.md` | Provides the `make_unbound_value()` + `static SEXP R_UnboundValue` sentinel and the abbreviated `findVar` / `findVarInFrame` function pointer stubs (`g_findVar_fn`, `g_findVarInFrame_fn`, `register_findVar_fn`, `register_findVarInFrame_fn`). The `R_getVar` guide's stubs are consistent with and supersede the abbreviated versions from `R_UnboundValue.md`; in the final `fake_Rinternals.hpp` only one copy of each stub should be present. The sentinel `R_UnboundValue` is used by `compat_getVar` at `rpart_callback.c:23` and must be defined before `compat_getVar` compiles. |
| `Rboolean.md` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean` in `fake_Boolean.hpp`. Required because `compat_getVar` (the expansion of `R_getVar`) has `Rboolean inherits` as its third parameter. Must be included before `fake_Rinternals.hpp` is parsed by the compiler (or embedded within it). |
| `FALSE.md` | Establishes that `FALSE` is enumerator `0` of `Rboolean`, defined in `fake_Boolean.hpp` after `#undef FALSE`. All four `R_getVar` call sites in `init_rpcallback` pass `FALSE` as the `inherits` argument; `compat_getVar` uses it in a boolean ternary expression. No separate definition beyond `Rboolean.md` / `FALSE.md` is needed. |
| `error.md` | Provides the `RError` exception class (`struct RError : public std::runtime_error`) and the `Rf_error` / `error` throwing implementation (Invariant 1). Required because `compat_getVar` calls `error(_("variable '%s' not found"), ...)` at `rpart_callback.c:24` when `val == R_UnboundValue`. The `#define error Rf_error` alias from `R_ext/Error.h` must be preserved in the fake header. |
| `install.md` (not yet generated — Category E) | Must provide the `g_install_fn` global pointer, the `register_install_fn` C-linkage registration function, and the `install(const char *)` inline stub. `install("yback")` etc. are evaluated before `compat_getVar` is entered; they produce the `sym` SEXP argument. The stub shown in Section 4 of this guide is authoritative until `install.md` is generated; the final fake header must use exactly one definition. |
| `findVar.md` (not yet generated — Category E) | Must provide the full `g_findVar_fn`, `register_findVar_fn`, and `findVar` inline stub. The abbreviated version in `R_UnboundValue.md` and the version in this guide are consistent; the final fake header must consolidate to a single definition. |
| `findVarInFrame.md` (not yet generated — Category E) | Must provide the full `g_findVarInFrame_fn`, `register_findVarInFrame_fn`, and `findVarInFrame` inline stub. Same consolidation note as `findVar.md`. |
| `R_VERSION.md` / `R_Version.md` / `fake_Rversion.hpp` | Must define `R_VERSION` as a compile-time integer constant and `R_Version(major, minor, patch)` as a macro such that `R_VERSION < R_Version(4, 5, 0)` evaluates to `1` (true). Without this, the `#if` guard at `rpart_callback.c:19` suppresses `compat_getVar` and the `R_getVar` macro definition, leaving all four call sites in `init_rpcallback` as unresolved identifiers. |
| `fake_arena.hpp` | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, `arena_calloc`. Required by `init_rpcallback_wrapper` for the `ArenaFrame _frame` RAII guard (Invariant 2). Not used by `R_getVar` / `compat_getVar` directly. |
