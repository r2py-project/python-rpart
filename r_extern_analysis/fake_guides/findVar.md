# Fake Header Implementation Guide: `findVar`

> **R Interpreter Item.** `findVar` (i.e., `Rf_findVar`) requires a running R interpreter to function. It traverses an R environment's frame chain, consulting R's internal symbol table and binding records at each level. None of these data structures exist outside of an initialized R runtime. In the fake build, `findVar` is implemented as a function pointer that Python registers via `ctypes.CFUNCTYPE` before invoking any `.Call` function that exercises the user-defined splitting code path (`method=4`).

---

### 1. Overview of `findVar` in R API

`Rf_findVar(SEXP sym, SEXP rho)` — aliased as `findVar` via `#define findVar Rf_findVar` in `Rinternals.h` line 939 — takes an R symbol object `sym` (a `SYMSXP` produced by `install(name)`) and an environment object `rho` (`ENVSXP`), and returns the `SEXP` value that `sym` is bound to by walking `rho` and each of its successive parent environments. If the symbol is not found in any reachable frame, `findVar` returns the global sentinel `R_UnboundValue`. The function is declared in `~/.conda/envs/r-to-python/lib/R/include/Rinternals.h` at line 533 as:

```c
SEXP Rf_findVar(SEXP, SEXP);
```

`findVar` is the inheritance-respecting counterpart to `findVarInFrame`: while `findVarInFrame` restricts its search to the single frame `rho`, `findVar` walks the entire parent chain until it reaches `R_EmptyEnv`. Both functions require the R interpreter's internal environment-frame linked list and symbol-table hash structure to be fully initialized. This makes `findVar` an **R Interpreter Item**: a complete standalone fake is impossible.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart_callback.c` | 1–83 | Full file header, `compat_getVar` shim and macro, static globals, `init_rpcallback` body |

**Context window for the CSV row (line 22).**

The single CSV row is at `rpart_callback.c:22`, inside the compatibility shim `compat_getVar`. The complete 15-line window (lines 7–37) is:

```c
/* rpart_callback.c:7-28 */
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

static int ysave;
static int rsave;
static SEXP expr1;
static SEXP expr2;
static SEXP rho;
```

**C types of arguments and return values.**

| Argument | Declared type | Meaning at call site |
|---|---|---|
| `sym` (first) | `SEXP` | A symbol object (`SYMSXP`) produced by `install("yback")` etc.; carries the interned string name of the variable to look up |
| `rho` (second) | `SEXP` | An environment object (`ENVSXP`) that is the starting frame for the search; passed in from R by `init_rpcallback` (line 53) as the static global `rho` |
| return value | `SEXP` | The bound value in the environment chain; must be `REALSXP` for `yback`/`wback`/`xback` and `INTSXP` for `nback`; returns `R_UnboundValue` if not found |

**Call site mechanics.**

`findVar` appears in the conditional expression:

```c
SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
```

Note the argument order difference:
- `findVar(sym, rho)` — symbol first, then environment.
- `findVarInFrame(rho, sym)` — environment first, then symbol.

This matches the real R API signatures:
- `SEXP Rf_findVar(SEXP sym, SEXP rho)` (sym first)
- `SEXP Rf_findVarInFrame(SEXP rho, SEXP sym)` (rho first)

In the rpart source, `inherits` is always `FALSE` at all four `R_getVar` call sites in `init_rpcallback` (lines 59, 62, 65, 68), meaning `findVarInFrame` is executed and `findVar` is never reached at runtime. However, `findVar` must still compile and link correctly because the compiler evaluates both branches of the ternary expression at compile time.

**Co-occurring R API items in the context window.**

| Item | Line | Role |
|---|---|---|
| `findVarInFrame(rho, sym)` | 22 | The false branch of the ternary; called when `inherits=FALSE` (always true at rpart call sites); Category E item |
| `R_UnboundValue` | 23 | Sentinel SEXP for a failed lookup; compared via pointer equality against `val`; documented in `R_UnboundValue.md` |
| `error(...)` | 24 | Throws `RError` in the fake runtime (Invariant 1) when `val == R_UnboundValue`; documented in `error.md` |
| `CHAR(PRINTNAME(sym))` | 24 | Extracts symbol name for the error message; requires `PRINTNAME` and `CHAR` from `SEXP.md` / `CHAR.md` / `PRINTNAME.md` |
| `install("yback")` etc. | 59,62,65,68 | Produces the `sym` argument before `compat_getVar` is called; Category E item (symtable intern) |
| `R_VERSION < R_Version(4, 5, 0)` | 19 | Compile-time gate; forces `compat_getVar` and its `#define R_getVar` macro to be compiled; must evaluate to `1` in the fake build |
| `Rboolean inherits` | 20 | Third parameter of `compat_getVar`; documented in `Rboolean.md` |
| `REAL(stemp)`, `INTEGER(stemp)` | 60,63,66,69 | Applied to the SEXP returned through `compat_getVar`; documented in `REAL.md`, `INTEGER.md` |

**Distinct implementation patterns.**

There is exactly one occurrence of `findVar` in rpart's source:

| Pattern | Location | Description |
|---|---|---|
| P1: Conditional lookup — `findVar` branch (never reached at runtime) | `rpart_callback.c:22` (true branch) | Called only when `inherits=TRUE`; not reached by any rpart call site but must compile and link |

Because `findVar` is never actually called at runtime (the `inherits=FALSE` always takes the `findVarInFrame` branch), the fake stub for `findVar` needs only to compile cleanly and satisfy the linker. However, the stub must also correctly throw `RError` if it is somehow invoked without a registered Python callback, to avoid silent undefined behavior.

---

### 3. Fake C++ Implementation Strategy

**Category: E — R Interpreter Item.**

`findVar` is Category E. A complete standalone fake is impossible for the following reasons:

1. **`sym` is a `SYMSXP`** — an R symbol object whose string name was interned by `install()` into R's global symbol hash table. The `SYMSXP` node is a pointer into R's heap; its `PRINTNAME` field points to a `CHARSXP` node in R's string pool. Neither the symbol table nor the string pool exists in the fake runtime.

2. **`rho` is an `ENVSXP`** — an R environment frame that is linked into a parent chain via R's internal `SEXP_RHO_PARENT` field. Walking the chain in `findVar` means following these `ENVSXP` pointers, consulting R's `FRAME()` (a hash table or pairlist of variable bindings) at each level. These data structures are part of R's internal `SEXPREC` memory layout that is not exposed through the public API and cannot be constructed without a live interpreter.

3. **Symbol table identity** — `findVar` depends on the invariant that `install("yback")` called at one location returns the exact same `SEXP` pointer as `install("yback")` called at any other location (symbol interning). Without R's global symbol table to enforce this invariant, there is no canonical address for the symbol, and pointer-equality comparison inside `compat_getVar` would be unreliable.

**Why a function pointer bridge achieves best-effort Python interop.**

The `findVar` call site is inside the static helper `compat_getVar`, which is only compiled when `R_VERSION < R_Version(4, 5, 0)` (enforced by `fake_Rversion.hpp`). At runtime, `compat_getVar` is only called from `init_rpcallback` (lines 59–68) as part of the `method=4` setup path. `findVar` itself is never reached because `inherits` is always `FALSE`, but `findVarInFrame` is called and follows the same pattern.

The fake provides a function pointer stub for `findVar` so that:
1. The binary links cleanly (the `findVar` symbol is resolved).
2. If `findVar` is ever invoked with a registered callback, it delegates to Python.
3. If `findVar` is invoked without a registered callback (e.g., if `inherits=TRUE` were passed), it throws `RError` rather than crashing silently.

The function pointer type is:
```cpp
typedef SEXP (*findVar_fn_t)(SEXP sym, SEXP rho);
```

Python registers a Python function as the callback via `ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)` and calls `register_findVar_fn` before invoking `init_rpcallback_wrapper`. The Python callback implements the variable lookup using a Python-managed `dict` keyed by `(rho_ptr, sym_ptr)`.

**The `#define` aliases that must be preserved.**

The real `Rinternals.h` lines 939–940 define:

```c
#define findVar          Rf_findVar
#define findVarInFrame   Rf_findVarInFrame
```

Both aliases must be reproduced in the fake header so that `findVar(sym, rho)` and `findVarInFrame(rho, sym)` at `rpart_callback.c:22` expand to `Rf_findVar(sym, rho)` and `Rf_findVarInFrame(rho, sym)` respectively — the same expansion performed by the real `Rinternals.h`. The original source file `rpart_callback.c` is not modified.

**Relationship to `R_getVar.md`.**

`R_getVar.md` documents the complete call chain for the four `R_getVar(install("..."), rho, FALSE)` call sites in `init_rpcallback` and already contains abbreviated `findVar` and `findVarInFrame` stubs. The stubs in this guide are the authoritative, complete versions. The final `fake_Rinternals.hpp` must include only one copy of each stub; the abbreviated version from `R_getVar.md` should be removed in favor of the complete versions defined here.

**Which code paths require this item and which do not.**

- `findVar` (the `inherits=TRUE` branch of `compat_getVar`) is **never reached** by any rpart call in any standard method (anova, poisson, class, exp — methods 1–4 in the built-in sense). All four `R_getVar` calls in `init_rpcallback` pass `inherits=FALSE`, always taking the `findVarInFrame` branch.
- `findVarInFrame` **is reached** when `method=4` (user-defined splits) is active, specifically during `init_rpcallback` (lines 59–68). Python must register a `findVarInFrame` callback before calling `init_rpcallback_wrapper` with user-defined method data.
- All standard rpart fitting methods (anova, poisson, class, exp) never call `init_rpcallback` and therefore never trigger either `findVar` or `findVarInFrame`.
- The `findVar` stub must be registered (or at minimum compiled and linked) for the binary to be valid; if `inherits=TRUE` is ever passed at runtime and the pointer is null, the stub throws `RError`.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): The `findVar` stub throws `RError` when called without a registered Python callback. The `compat_getVar` function also calls `error(...)` at line 24 when `val == R_UnboundValue`, which throws `RError` (documented in `error.md`). The `.Call`-boundary wrapper for any entry point that eventually calls `init_rpcallback` must catch `RError`.
- Invariant 2 (arena memory): Not triggered by `findVar` itself. No memory allocation occurs inside `findVar`; it returns a pointer to an existing binding in the environment frame.
- Invariant 3 (R Interpreter Items): Fully applicable. This entire guide is the Invariant 3 treatment for `findVar`.

---

### 4. Fake Implementation Examples

#### Pattern: Conditional Environment Lookup — `findVar` Branch (Compile-and-Link Target)

- **Locations:** `rpart_callback.c:22` (true branch of `inherits ? findVar(sym, rho) : findVarInFrame(rho, sym)`)

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
```

At runtime in rpart, `inherits` is always `FALSE` (all `R_getVar` call sites in `init_rpcallback` pass `FALSE`), so `findVarInFrame(rho, sym)` is always called and `findVar(sym, rho)` is never invoked. The stub must nonetheless compile and link, and must behave correctly if ever called.

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// Additions for findVar / findVarInFrame support.
// These definitions must appear AFTER:
//   - SEXPREC / SEXP typedef (from SEXP.md)
//   - RError definition (from error.md)
//   - R_UnboundValue sentinel SEXP (from R_UnboundValue.md)
//   - Rboolean / FALSE definitions (from Rboolean.md / FALSE.md)

// -----------------------------------------------------------------------
// findVar / Rf_findVar — R Interpreter Item (Category E, Invariant 3).
//
// Rf_findVar(SEXP sym, SEXP rho) searches rho and all parent environments
// for the symbol sym.  Returns R_UnboundValue if not found.
//
// In the fake runtime, this is implemented as a Python-registered function
// pointer.  If the pointer has not been registered and findVar is called,
// the stub throws RError.
//
// NOTE: In rpart's source, findVar is NEVER called at runtime because
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
            "methods; if you are using method=4 with inherits=TRUE, "
            "register a callback via register_findVar_fn() first.");
    return g_findVar_fn(sym, rho);
}

// Preserve the #define alias from real Rinternals.h:939.
// compat_getVar in rpart_callback.c uses findVar(sym, rho) not Rf_findVar.
#define findVar Rf_findVar

// -----------------------------------------------------------------------
// findVarInFrame / Rf_findVarInFrame — R Interpreter Item (Category E, Invariant 3).
//
// Rf_findVarInFrame(SEXP rho, SEXP sym) searches ONLY the immediate frame
// rho (no parent chain walk).  Returns R_UnboundValue if not found.
//
// Note the argument ORDER: rho first, sym second — the reverse of findVar.
// This matches the real Rinternals.h:534 declaration:
//   SEXP Rf_findVarInFrame(SEXP, SEXP);
// and the alias at line 940:
//   #define findVarInFrame Rf_findVarInFrame
//
// In the fake runtime, this is implemented as a Python-registered function
// pointer.  findVarInFrame IS called at runtime: every R_getVar(install(name),
// rho, FALSE) call in init_rpcallback resolves to compat_getVar which calls
// findVarInFrame(rho, sym).  Python MUST register this callback before
// init_rpcallback_wrapper is called with method=4 data.
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
            "register_findVarInFrame_fn() before calling any function "
            "that exercises the method=4 user-defined splits path.");
    return g_findVarInFrame_fn(rho, sym);
}

// Preserve the #define alias from real Rinternals.h:940.
#define findVarInFrame Rf_findVarInFrame

// -----------------------------------------------------------------------
// .Call boundary wrapper for init_rpcallback.
//
// This is the outermost C-linkage entry point that Python calls via ctypes.
// It pushes an ArenaFrame (Invariant 2), calls init_rpcallback(), and
// catches RError (Invariant 1).
//
// If g_findVarInFrame_fn is not registered and method=4 is used,
// Rf_findVarInFrame throws RError.  The exception unwinds through:
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

  `findVar` does not allocate any memory. It returns a pointer to an existing `SEXP` binding inside R's environment frame. In the fake runtime, the SEXP returned by `g_findVar_fn` (or `g_findVarInFrame_fn`) is a heap-allocated `SEXPREC` constructed on the Python side via `make_real_sexp` or `make_int_sexp`. It is not arena-managed; its lifetime is tied to the numpy arrays that back the `SEXPREC::data` pointer. The static pointers `ydata`, `wdata`, `xdata`, `ndata` in `rpart_callback.c` (lines 38–40) are set to point into these numpy buffers and remain valid as long as Python keeps the numpy arrays alive.

  The `ArenaFrame _frame` in `init_rpcallback_wrapper` is present as a standard Invariant 2 guard for the entire callback subsystem. `init_rpcallback` itself does not allocate arena memory, but other functions in the same translation unit (`rpart_callback1`, `rpart_callback2`) may do so in future or in extended configurations.

- **Python Interop Notes:**

  Python must register two callbacks before calling `init_rpcallback_wrapper`:
  1. `register_install_fn` — maps a C string name to a stable opaque SEXP handle (documented in `install.md`).
  2. `register_findVarInFrame_fn` — looks up a `(rho_ptr, sym_ptr)` pair in a Python-managed frame registry and returns the associated SEXP.
  3. `register_findVar_fn` — optional for rpart (never reached), but must not be left null if there is any chance of `inherits=TRUE` being passed. A conservative implementation that always returns `R_UnboundValue` is safe for rpart.

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
  # ----------------------------------------------------------------
  _symbol_handles: dict = {}   # {name_str: int pointer value}
  _symbol_nodes:   dict = {}   # keep live so GC doesn't collect the backing bytes

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
  # Argument order: rho first, sym second (matches Rinternals.h:534).
  #
  # Python maintains a nested registry:
  #   _frame_registry[rho_ptr][sym_ptr] = sexp_value_ptr
  #
  # Before calling init_rpcallback_wrapper, Python populates this
  # registry with the four "back" array variables.
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
      This triggers error("variable '...' not found") in compat_getVar.
      """
      frame = _frame_registry.get(rho, {})
      val = frame.get(sym)
      if val is None:
          return R_UNBOUND
      return val

  _findVarInFrame_cb = FindVarInFrameFnType(py_findVarInFrame)

  lib.register_findVarInFrame_fn.restype  = None
  lib.register_findVarInFrame_fn.argtypes = [FindVarInFrameFnType]
  lib.register_findVarInFrame_fn(_findVarInFrame_cb)

  # ----------------------------------------------------------------
  # Step 3: Register the findVar() stub.
  #
  # findVar(sym, rho) walks rho and all parent environments.
  # Argument order: sym first, rho second (matches Rinternals.h:533).
  #
  # This branch is NEVER reached by rpart (inherits is always FALSE),
  # but must be registered to avoid a null-pointer throw if conditions
  # change.  A conservative implementation that always returns
  # R_UnboundValue is safe for rpart's usage pattern.
  # ----------------------------------------------------------------
  FindVarFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)

  def py_findVar(sym: int, rho: int) -> int:
      """Walk rho's parent chain looking for sym.
      For rpart, this path is never reached (inherits=FALSE always).
      Returns R_UnboundValue conservatively.
      To implement correctly: walk _frame_registry entries chained
      by a parent pointer registered separately.
      """
      # Direct frame lookup as a minimal fallback:
      frame = _frame_registry.get(rho, {})
      val = frame.get(sym)
      if val is not None:
          return val
      return R_UNBOUND   # "not found" in any known frame

  _findVar_cb = FindVarFnType(py_findVar)

  lib.register_findVar_fn.restype  = None
  lib.register_findVar_fn.argtypes = [FindVarFnType]
  lib.register_findVar_fn(_findVar_cb)

  # ----------------------------------------------------------------
  # Step 4: Populate the frame registry with the four "back" arrays.
  #
  # Python creates four numpy arrays (yback, wback, xback, nback),
  # wraps each as a fake SEXPREC via a helper, and registers the
  # (rho_handle, sym_handle) -> SEXP mapping.
  # ----------------------------------------------------------------
  n_obs  = 100
  n_resp = 1

  yback_arr = np.zeros(n_obs * n_resp, dtype=np.float64)
  wback_arr = np.ones(n_obs,           dtype=np.float64)
  xback_arr = np.zeros(n_obs,          dtype=np.float64)
  nback_arr = np.array([n_resp],       dtype=np.int32)

  # make_real_sexp / make_int_sexp: build a fake SEXPREC wrapping a buffer.
  # (Provided by the fake header build infrastructure.)
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
  lib.make_env_sexp.restype  = SEXP
  lib.make_env_sexp.argtypes = []
  rho_handle = lib.make_env_sexp()

  # Use py_install to produce the same stable sym handles that the C code
  # will receive when it calls install("yback") etc.
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

  ny_arr = np.array([n_resp], dtype=np.int32)
  nr_arr = np.array([n_resp], dtype=np.int32)
  sexp_ny = lib.make_int_sexp(ny_arr.ctypes.data_as(ctypes.c_void_p), 1)
  sexp_nr = lib.make_int_sexp(nr_arr.ctypes.data_as(ctypes.c_void_p), 1)

  # expr1 and expr2 are R language objects (LANGSXP); in the fake they are
  # opaque SEXP handles forwarded to eval().  Pass None (nullptr) if the
  # eval() callback is not registered (i.e., init-only without callbacks).
  result = lib.init_rpcallback_wrapper(
      rho_handle,   # rhox:   the environment frame SEXP
      sexp_ny,      # ny:     number of response columns (scalar integer SEXP)
      sexp_nr,      # nr:     length of user eval return vector (scalar integer SEXP)
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

  The fake defines `g_findVar_fn` as a `static` global function pointer of type `findVar_fn_t` (i.e., `SEXP(*)(SEXP, SEXP)` with symbol first, environment second). The inline `Rf_findVar` stub checks the pointer and either delegates to the Python callback or throws `RError`. The `#define findVar Rf_findVar` alias ensures that `findVar(sym, rho)` at line 22 expands to `Rf_findVar(sym, rho)` — the same expansion as the real `Rinternals.h:939`. The original source file `rpart_callback.c` is not modified.

  The parallel `findVarInFrame` stub uses type `findVarInFrame_fn_t` (i.e., `SEXP(*)(SEXP, SEXP)` with environment first, symbol second — note the reversed argument order relative to `findVar`). This correctly models `Rf_findVarInFrame(SEXP rho, SEXP sym)` as declared at `Rinternals.h:534`. The `#define findVarInFrame Rf_findVarInFrame` alias at `Rinternals.h:940` is also reproduced.

  The correctness of the lookup depends on a single invariant: whenever the C code calls `install("yback")` to produce a `sym` argument, it must receive the same pointer that was used as the key in `_frame_registry`. This is guaranteed because `py_install` is memoized — `py_install(b"yback")` called during registry population and `py_install(b"yback")` called later by the `g_install_fn` stub from inside `init_rpcallback` both return the same `int` address. The `_symbol_nodes` dict keeps the backing `c_char` allocation alive so the pointer remains valid.

  The `g_findVar_fn` and `g_findVarInFrame_fn` variables are declared `static` within the header. For a multi-translation-unit build, they must be promoted to external linkage (declared `extern` in the header and defined once in a `.cpp` file) to avoid ODR violations. Alternatively, placing all stub definitions in a single `.cpp` translation unit avoids this issue entirely.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct (`type`, `length`, `nrow`, `ncol`, `data`) and `typedef SEXPREC *SEXP`. The `findVar_fn_t` and `findVarInFrame_fn_t` typedefs and the `Rf_findVar` / `Rf_findVarInFrame` stubs all have `SEXP` parameter and return types. Must be compiled before `findVar` / `findVarInFrame` stubs are defined. |
| `error.md` | Provides the `RError` exception class (`struct RError : public std::runtime_error`) and the `Rf_error` / `error` throwing implementation (Invariant 1). Required because: (a) the `Rf_findVar` and `Rf_findVarInFrame` stubs throw `RError` when the callback is null, and (b) `compat_getVar` at `rpart_callback.c:24` calls `error(...)` which must expand to `Rf_error(...)` throwing `RError`. `RError` must be defined before the `findVar` stubs are parsed. |
| `R_UnboundValue.md` | Provides the static `R_UnboundValue` sentinel `SEXP` (a stable pointer distinct from any valid binding). The Python-side `py_findVarInFrame` and `py_findVar` callbacks return `R_UnboundValue` when the symbol is not found; `compat_getVar` compares `val == R_UnboundValue` at line 23 to detect the failure condition. Pointer identity between the C-side `R_UnboundValue` and the Python-obtained sentinel (via `lib.get_R_UnboundValue()`) must be guaranteed; this is provided by `R_UnboundValue.md`'s `get_R_UnboundValue` accessor. |
| `Rboolean.md` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean` in `fake_Boolean.hpp`. Required because `compat_getVar` (the function that calls `findVar` / `findVarInFrame`) has `Rboolean inherits` as its third parameter. Must be included before `fake_Rinternals.hpp` is parsed. |
| `FALSE.md` | Establishes that `FALSE` is enumerator `0` of `Rboolean`. All four `R_getVar` call sites in `init_rpcallback` pass `FALSE` as the `inherits` argument; `compat_getVar` uses `inherits` in the boolean ternary at line 22 to dispatch between `findVar` and `findVarInFrame`. |
| `R_getVar.md` | Documents the complete call chain for the four `R_getVar(install("..."), rho, FALSE)` call sites in `init_rpcallback`. Contains abbreviated `findVar` / `findVarInFrame` stubs that are superseded by the complete versions in this guide. The final `fake_Rinternals.hpp` must consolidate to a single definition of each stub. `R_getVar.md` also establishes the `install` stub (`g_install_fn`, `register_install_fn`, `install(const char *)`), which is required because `install("yback")` etc. produce the `sym` argument that `findVarInFrame` receives. |
| `CHAR.md` | Provides the `CHAR(SEXP x)` inline function that extracts `const char *` from a `CHARSXP`. Required because `compat_getVar` at line 24 calls `CHAR(PRINTNAME(sym))` for the error message when a variable is not found. |
| `PRINTNAME.md` | Provides the `PRINTNAME(SEXP x)` inline function that returns the `CHARSXP` name field of a `SYMSXP`. Required alongside `CHAR.md` for the same `rpart_callback.c:24` error message. |
| `R_VERSION.md` / `R_Version.md` / `fake_Rversion.hpp` | Must define `R_VERSION` as a compile-time integer constant and `R_Version(major, minor, patch)` as a macro such that `R_VERSION < R_Version(4, 5, 0)` evaluates to `1` (true) at preprocessing time. Without this, the `#if` guard at `rpart_callback.c:19` suppresses `compat_getVar` and the `#define R_getVar` macro, leaving both `findVar` and `findVarInFrame` absent from the call graph and leaving `init_rpcallback` with unresolved `R_getVar` identifiers. |
| `fake_arena.hpp` | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, `arena_calloc`. Required by `init_rpcallback_wrapper` for the `ArenaFrame _frame` RAII guard (Invariant 2). Not used by `findVar`, `findVarInFrame`, or `compat_getVar` directly. |
