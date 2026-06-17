# Fake Header Implementation Guide: `install`

> **R Interpreter Item (best-effort fakeable).** `install` interns a C string as a symbol (`SYMSXP`) in R's global symbol table. In a live R session, the symbol table is a hash structure managed by the R interpreter, and every call to `install(name)` with the same `name` returns the exact same `SEXPREC *` pointer. A complete fake that replicates inter-session identity with a live R interpreter is impossible. However, because `install` is used in rpart exclusively to produce a `SYMSXP` argument for `R_getVar` / `findVarInFrame` — whose only requirement on the symbol is stable identity and a readable `PRINTNAME` — the interning behavior can be replicated faithfully in pure C++ using a `thread_local std::unordered_map<std::string, SEXP>` symbol cache. No Python function pointer is required for the common case. A Python function pointer bridge is provided as an optional alternative for completeness.

---

### 1. Overview of `install` in R API

`install(const char *name)` (declared in `Rinternals.h` as `SEXP Rf_install(const char *)`, aliased as `#define install Rf_install`) looks up `name` in R's global symbol table; if the symbol already exists it returns a pointer to the existing `SYMSXP` node, otherwise it creates a new node, inserts it into the table, and returns it. The returned `SEXP` has type `SYMSXP` (tag value `1`), and its print-name slot holds a `CHARSXP` node whose data buffer contains the null-terminated symbol name. Crucially, `install` is an **idempotent interning function**: calling `install("yback")` twice must return the same pointer both times. In rpart, `install` is used exclusively inside `init_rpcallback` (lines 59, 62, 65, 68) to produce the symbol argument passed to `R_getVar`, which in turn calls `findVarInFrame(rho, sym)` for the environment lookup. Because the symbols produced by `install` are used only as stable dictionary keys (identity-compared against registered SEXP handles), the live interpreter's global symbol table is not required — a per-thread `std::unordered_map` achieves the same interning guarantee within a single build.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart_callback.c` | 1–83 | Full file header, `compat_getVar` shim, static globals, and `init_rpcallback` body |

**Context window for all four CSV rows (lines 44–72).**

```c
/* rpart_callback.c:44-72 */
SEXP
init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;

    rho   = rhox;
    ysave = asInteger(ny);
    rsave = asInteger(nr);
    expr1 = expr1x;
    expr2 = expr2x;

    stemp = R_getVar(install("yback"), rho, FALSE);   /* line 59 */
    ydata = REAL(stemp);

    stemp = R_getVar(install("wback"), rho, FALSE);   /* line 62 */
    wdata = REAL(stemp);

    stemp = R_getVar(install("xback"), rho, FALSE);   /* line 65 */
    xdata = REAL(stemp);

    stemp = R_getVar(install("nback"), rho, FALSE);   /* line 68 */
    ndata = INTEGER(stemp);

    return R_NilValue;
}
```

**C types of arguments and return values.**

| Expression | Input type | Return type | Notes |
|---|---|---|---|
| `install("yback")` | `const char *` (string literal) | `SEXP` (SYMSXP) | Sole argument is always a string literal at every call site |
| `install("wback")` | `const char *` | `SEXP` (SYMSXP) | Same pattern |
| `install("xback")` | `const char *` | `SEXP` (SYMSXP) | Same pattern |
| `install("nback")` | `const char *` | `SEXP` (SYMSXP) | Same pattern |

The return value is immediately passed as the first argument to `R_getVar(sym, rho, FALSE)`, which expands (via the `#define R_getVar` macro at `rpart_callback.c:27`) to `compat_getVar(sym, rho, FALSE)`. Inside `compat_getVar`, `sym` is used in:
1. `findVarInFrame(rho, sym)` — as the lookup key; the fake `findVarInFrame` stub compares `sym` by pointer identity against registered handles.
2. `CHAR(PRINTNAME(sym))` — on the error path when `val == R_UnboundValue`; reads `sym->data` as a `CHARSXP` child to extract the symbol name string.

**Co-occurring R API items in context windows.**

| Item | Location | Role relative to `install` |
|---|---|---|
| `R_getVar(sym, rho, FALSE)` | Lines 59, 62, 65, 68 | Immediately consumes the SEXP returned by `install` |
| `compat_getVar(sym, rho, inherits)` | Lines 20–26 | The macro expansion target; uses `sym` for `findVarInFrame` and `CHAR(PRINTNAME(...))` |
| `findVarInFrame(rho, sym)` | Line 22 | Receives `sym` as a lookup key; requires stable pointer identity |
| `CHAR(PRINTNAME(sym))` | Line 24 | Reads `sym->data` cast to `SEXP` (a `CHARSXP`); requires `sym->data` to be a valid `mkChar` node |
| `R_UnboundValue` | Line 23 | Sentinel comparison; triggers the `CHAR(PRINTNAME(sym))` error path |
| `error(fmt, ...)` | Line 24 | Throws `RError` on variable-not-found; uses the symbol name extracted via `CHAR(PRINTNAME(sym))` |

**Distinct implementation patterns.**

There is exactly one distinct usage pattern across all four CSV rows:

| Pattern | CSV rows | Description |
|---|---|---|
| P1: Intern a string literal as a SYMSXP for use as a variable lookup key | Lines 59, 62, 65, 68 | `install("<name>")` — fixed string literal input, result passed directly to `R_getVar`/`findVarInFrame` |

All four call sites are structurally identical: `install` takes a string literal and returns a SYMSXP. The variable names differ (`"yback"`, `"wback"`, `"xback"`, `"nback"`) but the fake mechanism is the same for all. No separate treatment is required.

---

### 3. Fake C++ Implementation Strategy

**Category: E — R Interpreter Item (best-effort fakeable without a Python function pointer).**

In the real R runtime, `install` depends on R's global symbol table — a hash map allocated and managed by the R interpreter at startup. The exact same `SEXPREC *` pointer must be returned for each distinct name regardless of how many times `install` is called and from how many translation units, because downstream code (including the real `findVarInFrame`) uses pointer identity to match symbols against bindings.

**Why a complete fake is impossible — and why a best-effort fake is sufficient for rpart.**

A complete fake cannot replicate R session-level global state (e.g., symbols created by `install` in rpart would not be recognized by a hypothetically live `findVarInFrame`). However, in the fake build, `findVarInFrame` is also a stub (Category E, documented in `findVarInFrame.md`), and its Python-side implementation uses the same pointer values returned by the fake `install` as lookup keys in `_frame_registry`. As long as:
1. The fake `install` is deterministic: same name => same pointer within a process,
2. The returned SEXP has `type == SYMSXP` and `data` pointing to a valid `CHARSXP` node (so that `CHAR(PRINTNAME(sym))` works on the error path),

the entire `R_getVar` call chain works correctly in the fake build.

**Chosen mechanism: thread-local `std::unordered_map` symbol cache.**

```
thread_local std::unordered_map<std::string, SEXP> gSymbolCache;
```

On the first call to `install("yback")` within a thread, the fake allocates a `CHARSXP` node via `mkChar("yback")` (heap-allocated, `std::malloc`), then allocates a `SEXPREC` with `type=SYMSXP` and `data=charsxp_node`, inserts both into the cache under the key `"yback"`, and returns the `SYMSXP` pointer. On all subsequent calls with `"yback"`, the same pointer is retrieved from the cache and returned — satisfying the idempotency invariant.

The `thread_local` qualifier is consistent with the rest of the fake runtime: `gArenaStack` from `fake_arena.hpp` is also `thread_local`, and each thread's symbol cache is independent (no cross-thread symbol sharing occurs in rpart's single-threaded `.Call` model).

**SYMSXP node layout.**

Each `SYMSXP` node produced by the fake `install` must satisfy:

- `sym->type == SYMSXP` (value `1`)
- `sym->length == 0` (symbols have no element count)
- `sym->nrow == 0`, `sym->ncol == 0`
- `sym->data` points to a `CHARSXP` `SEXPREC` node — i.e., a node with `type==CHARSXP` and `data` holding the `char *` string buffer from `mkChar(name)`

This layout satisfies the `PRINTNAME` accessor (from `PRINTNAME.md`):

```cpp
inline SEXP PRINTNAME(SEXP s) {
    if (s && s->type == SYMSXP && s->data)
        return static_cast<SEXP>(s->data);  // returns the CHARSXP child
    return s;
}
```

And `CHAR(PRINTNAME(sym))` then correctly returns the null-terminated name string via `R_CHAR`.

**Memory lifetime.**

Symbol nodes (both the `SYMSXP` and its `CHARSXP` child) are heap-allocated once per unique name per thread. They are stored in `gSymbolCache` indefinitely for the lifetime of the thread. They are **not** arena-managed (arena memory is freed at `ArenaFrame` destruction at the `.Call` boundary — symbols must survive across `.Call` calls because `findVarInFrame` needs to match them to the Python-registered handles). They are also **not** freed by `free_sexp` unless the caller explicitly clears the cache.

A `clear_symbol_cache()` function is provided for cleanup between independent test runs.

**Optional Python function pointer alternative.**

For symmetry with the other Category E stubs (`findVar`, `findVarInFrame`) and to support an alternative implementation where Python fully controls symbol creation, a `g_install_fn` function pointer bridge is also provided. When `g_install_fn` is registered, it takes precedence over the built-in hash-map implementation. When it is not registered (the common case), the built-in hash-map is used. This means the stub never throws `RError` under normal operation.

**`#define` aliases that must be preserved.**

The real `Rinternals.h` declares:

```c
SEXP Rf_install(const char *);
#ifndef R_NO_REMAP
#define install  Rf_install
#endif
```

The fake header must define both `Rf_install` (the canonical function name) and the `#define install Rf_install` alias so that the original source file `rpart_callback.c` (which uses `install(...)` without the `Rf_` prefix) compiles without modification.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): triggered on the error path in `compat_getVar`. The `install` fake itself does not call `error`; if `std::malloc` fails inside `mkChar` or the symbol allocator, it throws `RError("install: out of memory")`. This propagates to the `.Call` boundary wrapper for `init_rpcallback`, which catches it.
- Invariant 2 (arena memory): not applicable. Symbol nodes are heap-allocated (they must persist beyond the `ArenaFrame` boundary) and stored in a thread-local map. The arena is not involved.
- Invariant 3 (R Interpreter Items): partially applicable. The interning behavior of `install` is fully replicated by the hash-map fake. The aspect that cannot be replicated is cross-session symbol identity with a live R interpreter — but since both `install` and `findVarInFrame` are faked consistently, this limitation is irrelevant for the rpart standalone build.

---

### 4. Fake Implementation Examples

#### Pattern: Intern a String Literal as a SYMSXP for Variable Lookup

- **Locations:** `rpart_callback.c:59`, `rpart_callback.c:62`, `rpart_callback.c:65`, `rpart_callback.c:68`

- **Original R API Usage:**

```c
/* rpart_callback.c:59-69 */
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
// fake_Rinternals.hpp  (additions for install support)
//
// This block must appear AFTER:
//   - struct SEXPREC and typedef SEXPREC *SEXP         (from SEXP.md)
//   - #define SYMSXP 1  and  #define CHARSXP 9        (from SEXP.md / INTSXP.md)
//   - inline SEXP mkChar(const char *str) { ... }      (from SEXP.md)
//   - inline SEXP PRINTNAME(SEXP s) { ... }            (from SEXP.md / PRINTNAME.md)
//   - struct RError and Rf_error() / #define error     (from error.md / SEXP.md)
//
// And BEFORE any translation unit that includes rpart_callback.c is compiled,
// because rpart_callback.c uses install(...) at lines 59, 62, 65, 68.

#include <string>
#include <unordered_map>

// -----------------------------------------------------------------------
// Thread-local symbol cache — maps string names to interned SYMSXP nodes.
//
// Each distinct name receives exactly one SYMSXP node per thread.
// Subsequent calls to install(name) for the same name return the same
// SEXPREC* pointer, satisfying the idempotency invariant that downstream
// code (findVarInFrame, PRINTNAME) depends on.
//
// Symbol nodes and their CHARSXP children are heap-allocated once and
// stored here for the lifetime of the thread.  They are NOT arena-managed:
// the ArenaFrame at the .Call boundary must not free them.
//
// To release all symbol memory between independent test runs, call
// clear_symbol_cache() from Python.
// -----------------------------------------------------------------------
inline thread_local std::unordered_map<std::string, SEXP> gSymbolCache;

inline void clear_symbol_cache() {
    for (auto &kv : gSymbolCache) {
        SEXP sym = kv.second;
        if (sym) {
            // Free the CHARSXP child stored in sym->data, then the SYMSXP node.
            SEXP charnode = static_cast<SEXP>(sym->data);
            if (charnode) {
                std::free(charnode->data);   // the char* string buffer
                std::free(charnode);         // the CHARSXP SEXPREC node
            }
            std::free(sym);                  // the SYMSXP SEXPREC node
        }
    }
    gSymbolCache.clear();
}

// -----------------------------------------------------------------------
// Optional Python function pointer bridge (alternative to the built-in
// hash-map).  When g_install_fn is non-null, it takes precedence.
// When it is null (the default), the built-in hash-map is used.
//
// Python registers this only if it needs to control symbol allocation
// (e.g., to reuse SEXP handles from a live R session).
// -----------------------------------------------------------------------
typedef SEXP (*install_fn_t)(const char *name);
static install_fn_t g_install_fn = nullptr;

extern "C" void register_install_fn(install_fn_t fn) {
    g_install_fn = fn;
}

// -----------------------------------------------------------------------
// Rf_install / install — the canonical fake implementation.
//
// Lookup order:
//   1. If g_install_fn is registered, delegate to it.
//   2. Otherwise, look up name in gSymbolCache.
//      a. Cache hit  -> return the existing SYMSXP pointer.
//      b. Cache miss -> allocate a new CHARSXP (via mkChar) and a new
//                       SYMSXP node, insert into cache, return the pointer.
//
// On std::malloc failure in mkChar or the SYMSXP allocator, RError is
// thrown.  This propagates to the .Call boundary wrapper and is caught
// by the try/catch, which stores the message for Python to retrieve.
// -----------------------------------------------------------------------
inline SEXP Rf_install(const char *name) {
    // Path 1: Python-registered function pointer bridge.
    if (g_install_fn)
        return g_install_fn(name);

    // Path 2: built-in hash-map symbol cache.
    std::string key(name);
    auto it = gSymbolCache.find(key);
    if (it != gSymbolCache.end())
        return it->second;   // Cache hit: return existing SYMSXP pointer.

    // Cache miss: allocate a new symbol node.
    //
    // Step A: Create the CHARSXP child node that carries the name string.
    //         mkChar(name) allocates a SEXPREC with type=CHARSXP and
    //         data pointing to a heap-allocated null-terminated string.
    //         (mkChar is defined in SEXP.md / fake_Rinternals.hpp.)
    SEXP charnode = mkChar(name);  // throws RError on OOM

    // Step B: Allocate the SYMSXP node.
    SEXPREC *sym = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!sym) {
        // Avoid leaking the charnode if the SYMSXP allocation fails.
        std::free(charnode->data);
        std::free(charnode);
        throw RError("install: out of memory (SYMSXP node)");
    }

    // Step C: Populate the SYMSXP fields.
    //   type   = SYMSXP (1)       — identifies this as a symbol node
    //   length = 0                — symbols have no element count
    //   nrow   = 0, ncol = 0      — not a matrix
    //   data   = charnode         — PRINTNAME reads this as the CHARSXP child
    sym->type   = SYMSXP;
    sym->length = 0;
    sym->nrow   = 0;
    sym->ncol   = 0;
    sym->data   = charnode;   // PRINTNAME(sym) returns static_cast<SEXP>(sym->data)

    // Step D: Insert into the cache and return.
    gSymbolCache[key] = sym;
    return sym;
}

// Preserve the #define alias from Rinternals.h so that rpart_callback.c
// compiles unchanged — it calls install(...) without the Rf_ prefix.
#define install Rf_install

// -----------------------------------------------------------------------
// .Call boundary wrapper for init_rpcallback.
//
// init_rpcallback is the only .Call entry point in rpart_callback.c.
// It calls R_getVar(install(...), rho, FALSE) at lines 59, 62, 65, 68.
//
// The ArenaFrame guard (Invariant 2) is a standard precautionary measure
// for .Call wrappers, even though init_rpcallback itself does not perform
// arena allocations.  rpart_callback1 and rpart_callback2 (called later
// on the method=4 code path) do use arena memory; their wrappers also
// need ArenaFrame guards.
//
// The try/catch translates RError into a Python-readable error message
// (Invariant 1).  RError can be thrown by:
//   - install(): std::malloc failure during symbol allocation (rare)
//   - findVarInFrame(): when g_findVarInFrame_fn is not registered
//   - error() inside compat_getVar: when R_UnboundValue is returned
// -----------------------------------------------------------------------
extern "C" SEXP init_rpcallback_wrapper(
        SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    ArenaFrame _frame;    // Invariant 2: free arena allocations on exit
    try {
        return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
    } catch (const RError &e) {
        // Invariant 1: translate C++ exception to a Python-readable message.
        set_python_error(e.what());
        return nullptr;   // signals failure; Python checks for nullptr
    }
}
```

- **Arena / Memory Notes:**

  Symbol nodes (both `SYMSXP` and their `CHARSXP` children) are **heap-allocated** via `std::malloc` inside `mkChar` and the `Rf_install` allocator. They are **not** arena-managed. The reason is lifetime: symbol nodes must survive across `.Call` boundary crossings because the `findVarInFrame` stub (documented in `findVarInFrame.md`) uses the SEXP pointer returned by `install` as a key in the Python-side `_frame_registry` dictionary. If symbol nodes were placed in the arena, they would be freed by `ArenaFrame` at the end of `init_rpcallback_wrapper`, invalidating the `_frame_registry` keys before any subsequent `R_getVar` lookups during the actual rpart computation.

  The `ArenaFrame _frame` guard in `init_rpcallback_wrapper` only frees arena allocations made by `R_alloc` / `ALLOC` within the call. Since `init_rpcallback` itself makes no arena allocations, the guard is a zero-cost formality for this specific wrapper.

  If `std::malloc` fails inside `mkChar` or the `SYMSXP` allocator, `RError` is thrown. The `.Call` boundary `try/catch` in `init_rpcallback_wrapper` catches it, stores the message via `set_python_error`, and returns `nullptr` to the Python caller.

- **Python Interop Notes:**

  For the standard rpart use case (methods anova, poisson, class, exp), `init_rpcallback` is never called, and neither `install` nor `findVarInFrame` stubs are invoked. The symbol cache remains empty.

  For the user-defined splits code path (`method=4`), Python must call `init_rpcallback_wrapper` before `rpart` is called. The `install` fake requires no Python registration — it works out of the box using the built-in hash-map. However, `findVarInFrame` (called inside `compat_getVar`) **does** require Python registration. Python must:

  1. Register `findVarInFrame` before calling `init_rpcallback_wrapper`.
  2. Populate `_frame_registry` using the same pointer values that `Rf_install` will produce, so that the lookup succeeds.

  The `py_install` helper below shows how to obtain the pointer values the C++ fake will produce, so that Python can pre-populate the registry consistently:

  ```python
  import ctypes

  # Load the shared library built from the fake-header rpart source.
  lib = ctypes.CDLL("./librpart_fake.so")

  SEXP = ctypes.c_void_p

  # ----------------------------------------------------------------
  # install: use the built-in C++ hash-map (no registration needed).
  #
  # To discover the pointer value that the C++ fake assign to a given
  # name (so that Python can populate _frame_registry with matching
  # keys), call install() directly from Python via a thin C wrapper:
  #
  #   extern "C" SEXP call_install(const char *name) {
  #       return Rf_install(name);
  #   }
  #
  # This wrapper must be compiled into the shared library.
  # ----------------------------------------------------------------
  lib.call_install.restype  = SEXP
  lib.call_install.argtypes = [ctypes.c_char_p]

  sym_yback = lib.call_install(b"yback")
  sym_wback = lib.call_install(b"wback")
  sym_xback = lib.call_install(b"xback")
  sym_nback = lib.call_install(b"nback")

  # ----------------------------------------------------------------
  # Alternatively, register a Python-controlled install() callback.
  # Use this if you need to ensure that the SEXP handles returned by
  # install() in C++ match handles you have created on the Python side
  # (e.g., when interoperating with a live R session via rpy2).
  # ----------------------------------------------------------------
  _symbol_nodes: dict = {}  # keep ctypes structures alive (prevent GC)
  _symbol_handles: dict = {}  # name -> integer pointer value

  InstallFnType = ctypes.CFUNCTYPE(SEXP, ctypes.c_char_p)

  def py_install(name_bytes: bytes) -> int:
      name = name_bytes.decode()
      if name not in _symbol_handles:
          # Allocate a 1-byte ctypes object as a stable pointer target.
          node = (ctypes.c_char * 1)()
          _symbol_nodes[name] = node      # keep alive
          _symbol_handles[name] = ctypes.cast(node, ctypes.c_void_p).value
      return _symbol_handles[name]

  _install_cb = InstallFnType(py_install)

  lib.register_install_fn.restype  = None
  lib.register_install_fn.argtypes = [InstallFnType]
  # Uncomment to use the Python-controlled path instead of the built-in cache:
  # lib.register_install_fn(_install_cb)

  # ----------------------------------------------------------------
  # Populate _frame_registry using the symbol pointer values from above,
  # then register findVarInFrame (as documented in findVarInFrame.md).
  # ----------------------------------------------------------------
  import numpy as np

  n_obs = 100
  n_resp = 1
  yback_arr = np.zeros(n_obs * n_resp, dtype=np.float64)
  wback_arr = np.ones(n_obs, dtype=np.float64)
  xback_arr = np.zeros((n_obs, 10), dtype=np.float64, order='F')
  nback_arr = np.array([n_resp], dtype=np.int32)

  lib.make_real_sexp.restype  = SEXP
  lib.make_real_sexp.argtypes = [ctypes.c_void_p, ctypes.c_int]
  lib.make_int_sexp.restype   = SEXP
  lib.make_int_sexp.argtypes  = [ctypes.c_void_p, ctypes.c_int]

  sexp_y = lib.make_real_sexp(yback_arr.ctypes.data_as(ctypes.c_void_p), yback_arr.size)
  sexp_w = lib.make_real_sexp(wback_arr.ctypes.data_as(ctypes.c_void_p), wback_arr.size)
  sexp_x = lib.make_real_sexp(xback_arr.ctypes.data_as(ctypes.c_void_p), xback_arr.size)
  sexp_n = lib.make_int_sexp(nback_arr.ctypes.data_as(ctypes.c_void_p), nback_arr.size)

  lib.make_env_sexp.restype  = SEXP
  lib.make_env_sexp.argtypes = []
  rho_handle = lib.make_env_sexp()

  # _frame_registry maps rho_ptr -> {sym_ptr -> val_ptr}
  # The sym_ptr keys must match the values returned by the C++ Rf_install.
  _frame_registry = {
      rho_handle: {
          sym_yback: sexp_y,
          sym_wback: sexp_w,
          sym_xback: sexp_x,
          sym_nback: sexp_n,
      }
  }

  # Retrieve R_UnboundValue sentinel for use in py_findVarInFrame.
  lib.get_R_UnboundValue.restype  = SEXP
  lib.get_R_UnboundValue.argtypes = []
  R_UNBOUND = lib.get_R_UnboundValue()

  FindVarInFrameFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)

  def py_findVarInFrame(rho: int, sym: int) -> int:
      frame = _frame_registry.get(rho, {})
      val = frame.get(sym)
      return val if val is not None else R_UNBOUND

  _findVarInFrame_cb = FindVarInFrameFnType(py_findVarInFrame)
  lib.register_findVarInFrame_fn.restype  = None
  lib.register_findVarInFrame_fn.argtypes = [FindVarInFrameFnType]
  lib.register_findVarInFrame_fn(_findVarInFrame_cb)

  # Call init_rpcallback_wrapper.
  lib.init_rpcallback_wrapper.restype  = SEXP
  lib.init_rpcallback_wrapper.argtypes = [SEXP, SEXP, SEXP, SEXP, SEXP]

  ny_arr = np.array([n_resp], dtype=np.int32)
  nr_arr = np.array([n_resp], dtype=np.int32)
  sexp_ny = lib.make_int_sexp(ny_arr.ctypes.data_as(ctypes.c_void_p), 1)
  sexp_nr = lib.make_int_sexp(nr_arr.ctypes.data_as(ctypes.c_void_p), 1)

  result = lib.init_rpcallback_wrapper(
      rho_handle, sexp_ny, sexp_nr,
      None,   # expr1x: opaque; pass nullptr for standard methods
      None,   # expr2x: opaque; pass nullptr for standard methods
  )

  lib.get_last_rerror_message.restype  = ctypes.c_char_p
  lib.get_last_rerror_message.argtypes = []
  msg = lib.get_last_rerror_message()
  if msg:
      raise RuntimeError(f"init_rpcallback failed: {msg.decode()}")
  ```

  **Which code paths require `install`.**

  `install` is called only inside `init_rpcallback` (lines 59, 62, 65, 68 of `rpart_callback.c`). This function is only invoked when `method=4` (user-defined splits) is active in rpart. All standard rpart methods (anova, poisson, class, exp — methods 1–4 using the built-in `func_table`) never call `init_rpcallback` and therefore never invoke `install` at runtime. The fake `install` using the built-in hash-map is always compiled into the shared library (because the source file always includes `fake_Rinternals.hpp`) but its runtime code is never executed for the standard use case.

- **Explanation:**

  The fake header defines `Rf_install` as a C++ `inline` function and provides the `#define install Rf_install` alias. Every occurrence of `install(...)` in `rpart_callback.c` expands to `Rf_install(...)` — the original source file compiles without any modification.

  The built-in hash-map (`gSymbolCache`) handles the four string literals `"yback"`, `"wback"`, `"xback"`, `"nback"` transparently. On the first call to `init_rpcallback`, each of these names is interned once: a `CHARSXP` node is created via `mkChar(name)` (which heap-allocates both the `SEXPREC` node and the `char *` string buffer), then a `SYMSXP` node is allocated with `sym->data = charnode`, and both are stored in `gSymbolCache`. On subsequent calls (e.g., if `init_rpcallback` is called again for a second fitting), the cache returns the same pointer — the pointer identity invariant is satisfied without any Python coordination.

  The `PRINTNAME` accessor (from `PRINTNAME.md`) is satisfied because `sym->type == SYMSXP && sym->data != nullptr`. `PRINTNAME(sym)` returns `static_cast<SEXP>(sym->data)` — the `CHARSXP` child node. `CHAR(charnode)` then returns `static_cast<const char *>(charnode->data)`, which is the original name string (e.g., `"yback"`). This ensures the error path `error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)))` inside `compat_getVar` produces a readable error message when `findVarInFrame` returns `R_UnboundValue`.

  The `findVarInFrame` stub (from `findVarInFrame.md`) uses the pointer returned by `Rf_install` as the lookup key in `_frame_registry`. Because the same pointer is returned on every call, the registry lookup succeeds on the very first `R_getVar` call in `init_rpcallback`, and `ydata`, `wdata`, `xdata`, `ndata` are set to the data pointers of the numpy-backed SEXP handles registered by Python.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct (`type`, `length`, `nrow`, `ncol`, `data` fields) and `typedef SEXPREC *SEXP`. `Rf_install` allocates `SEXPREC` nodes via `std::malloc` and sets all five fields. `SEXP.md` also provides `mkChar(const char *)` — used inside `Rf_install` to create the `CHARSXP` child node — and `RError` — thrown on `std::malloc` failure. Also provides `#define SYMSXP 1` and the `PRINTNAME` and `R_CHAR` inline functions that consume the `SYMSXP` nodes produced here. |
| `INTSXP.md` | Provides `#define SYMSXP 1` and `#define CHARSXP 9` within the `SEXPTYPE` constant block. Both constants are set in the nodes allocated by `Rf_install`: `sym->type = SYMSXP` and (inside `mkChar`) `charnode->type = CHARSXP`. Must be visible when `fake_Rinternals.hpp` is compiled. |
| `PRINTNAME.md` | Provides the `PRINTNAME(SEXP s)` inline accessor that reads `sym->data` and casts it to `SEXP`. `PRINTNAME` is called inside `compat_getVar` at `rpart_callback.c:24` with a `SYMSXP` produced by `install`. For `PRINTNAME` to return a non-null `CHARSXP`, the `install` fake must set `sym->data = charnode` (a `CHARSXP` allocated by `mkChar`). This guide's implementation satisfies that contract. |
| `CHAR.md` | Provides `R_CHAR(SEXP s)` and `#define CHAR(x) R_CHAR(x)`. `CHAR(PRINTNAME(sym))` is called at `rpart_callback.c:24` with the `SYMSXP` from `install`. For this to return the symbol name string, both `PRINTNAME` (above) and `R_CHAR` must operate on correctly structured fake nodes — which this guide ensures. |
| `error.md` | Provides `struct RError : public std::runtime_error`, `Rf_error(const char *fmt, ...)` (variadic, throws `RError`), and `#define error Rf_error`. Required because `compat_getVar` (the expansion of `R_getVar` at lines 59–68) calls `error(...)` when `val == R_UnboundValue`. The `RError` type is also thrown by `Rf_install` on allocation failure. |
| `findVarInFrame.md` | Provides the `g_findVarInFrame_fn` pointer, `register_findVarInFrame_fn`, and the `findVarInFrame` inline stub. At runtime, `install` produces the `sym` argument that `findVarInFrame` receives as its second parameter. The correctness of the `findVarInFrame` lookup depends on pointer identity of the `sym` SEXP — guaranteed by the `gSymbolCache` cache in this guide. The `findVarInFrame` stub must be defined before `compat_getVar` is compiled. |
| `findVar.md` | Provides the `g_findVar_fn` pointer, `register_findVar_fn`, and the `findVar` inline stub. The `inherits=TRUE` branch of `compat_getVar` (line 22) calls `findVar(sym, rho)`. Although this branch is never reached at the rpart call sites (all four pass `inherits=FALSE`), the stub must compile. `findVar` receives the same `sym` SEXP produced by `install` and also depends on its pointer identity. |
| `R_getVar.md` | Documents the `compat_getVar` / `R_getVar` shim structure and the complete call chain `R_getVar(install(...), rho, FALSE)`. The `install` guide is a prerequisite for `R_getVar.md` because the `sym` argument passed to `compat_getVar` is always the return value of `install`. The `R_getVar.md` guide's abbreviated `install` stub (shown in its Section 4) is superseded by the authoritative definition in this guide; the final `fake_Rinternals.hpp` must use exactly one definition. |
| `R_UnboundValue.md` | Provides the `make_unbound_value()` + `static SEXP R_UnboundValue` sentinel. Used by `compat_getVar` at `rpart_callback.c:23`: `if (val == R_UnboundValue)`. The error path that calls `CHAR(PRINTNAME(sym))` is only reached when `findVarInFrame` returns this sentinel. |
| `Rboolean.md` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean`. Required because `compat_getVar` (the expansion target of the `R_getVar` macro) has `Rboolean inherits` as its third parameter, and all four `R_getVar` call sites pass `FALSE`. |
| `R_VERSION.md` / `fake_Rversion.hpp` | Provides the `R_VERSION` integer constant and `R_Version(major, minor, patch)` macro such that `R_VERSION < R_Version(4, 5, 0)` evaluates to true. This causes the `compat_getVar` shim and `#define R_getVar` to be compiled, which is required for `install` usage at lines 59–68 (those lines use `R_getVar`, not `install` directly). Without this, the preprocessor skips `compat_getVar` entirely and `R_getVar` is undefined. |
| `fake_arena.hpp` | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, `arena_calloc`. Required by `init_rpcallback_wrapper` for the `ArenaFrame _frame` RAII guard (Invariant 2). Not used by `Rf_install` directly. |
