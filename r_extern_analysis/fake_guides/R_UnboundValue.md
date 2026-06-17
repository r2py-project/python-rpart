# Fake Header Implementation Guide: `R_UnboundValue`

> **R Interpreter Item (partial).** `R_UnboundValue` is a sentinel SEXP maintained by the R interpreter to signal that a symbol lookup in an environment returned no binding. A fully faithful fake — one that is produced dynamically by the real `findVar`/`findVarInFrame` machinery when a lookup fails — is impossible without a running R interpreter. However, because the sole rpart usage of `R_UnboundValue` is a pointer identity comparison (`val == R_UnboundValue`) inside a compatibility shim (`compat_getVar`) that wraps `findVar`/`findVarInFrame`, and because those lookup functions are themselves Category E items with function-pointer bridges, the fake for `R_UnboundValue` itself reduces to a stable static sentinel SEXP. The pointer bridge requirement is inherited from `findVar`/`findVarInFrame`, not from `R_UnboundValue` directly. This guide documents that reduction, explains the boundary conditions, and provides the complete fake.

---

### 1. Overview of `R_UnboundValue` in R API

`R_UnboundValue` is a permanently allocated `SEXP` of special type `SYMSXP` (or an internal marker type in some R versions), declared in `Rinternals.h` at line 413 as:

```c
LibExtern SEXP  R_UnboundValue;     /* Unbound marker */
```

It appears in the "Special Values" block of `Rinternals.h`, alongside `R_NilValue` and `R_MissingArg`. `LibExtern` expands to `extern` in client translation units that link against `libR.so`; the actual object is allocated inside the R shared library during interpreter initialization. `R_UnboundValue` serves as the sentinel return value from `findVar(sym, env)` and `findVarInFrame(env, sym)` when the symbol `sym` is not bound in the environment `env` (or its parents, for `findVar`). Code that calls these lookup functions checks the result against `R_UnboundValue` to determine whether the lookup succeeded. It is an **R Interpreter Item** in the sense that its counterpart in the real R runtime is produced by the interpreter's environment-variable lookup machinery; however, as a sentinel pointer it can be faked as a static `SEXPREC` without a live interpreter, provided that the `findVar`/`findVarInFrame` function-pointer bridges are also in place.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Context |
|---|---|---|
| `rpart_callback.c` | 1–28 | File header through end of `compat_getVar` compatibility shim |

The single CSV row is `rpart_callback.c:23`. The full 15-line window (lines 8–28) is:

```c
/* rpart_callback.c:18-28 */
/* compatibility shim for R < 4.5.0 */
#if R_VERSION < R_Version(4, 5, 0)
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
  if (val == R_UnboundValue)                                /* line 23 */
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif
```

**Argument and return types at line 23.**

The comparison is:

```c
if (val == R_UnboundValue)
```

where:
- `val` is a local `SEXP` (`SEXPREC *`) that holds the result of either `findVar(sym, rho)` or `findVarInFrame(rho, sym)`.
- `R_UnboundValue` is a `SEXP` (`SEXPREC *`).
- The `==` operator is plain pointer equality. No dereference of `R_UnboundValue` occurs; no accessor (`INTEGER`, `REAL`, `TYPEOF`, `LENGTH`, etc.) is applied to it. Its exact `SEXPREC` field values do not matter at this call site — only its pointer address matters.

**Co-occurring R API items in the context window.**

| Item | Line | Role |
|---|---|---|
| `findVar(sym, rho)` | 22 | Looks up `sym` in `rho` and its parent environments; returns `R_UnboundValue` on failure. Category E item. |
| `findVarInFrame(rho, sym)` | 22 | Looks up `sym` in `rho` only (no parent chain walk); returns `R_UnboundValue` on failure. Category E item. |
| `R_UnboundValue` | 23 | Used only as the right-hand side of a `==` pointer comparison with `val`. |
| `error(...)` | 24 | Signals that the variable was not found. In the fake runtime, this throws `RError` (Invariant 1). |
| `CHAR(PRINTNAME(sym))` | 24 | Extracts the symbol name as a C string for the error message. Requires `PRINTNAME` (returns the `CHARSXP` name of a `SYMSXP`) and `CHAR` (returns the `char *` from a `CHARSXP`); both are documented in `SEXP.md`. |
| `R_getVar` macro | 27 | Defined as `compat_getVar(sym, rho, inherits)` for R < 4.5.0. Used in `init_rpcallback()` at lines 59–68 to look up the four `yback`/`wback`/`xback`/`nback` SEXP variables in the callback frame. |
| `R_VERSION` / `R_Version` | 19 | Compile-time version gate. The `compat_getVar` body (including the `R_UnboundValue` comparison) is only compiled when `R_VERSION < R_Version(4, 5, 0)`. The fake `Rversion.h` must define these macros such that this condition is `true`, ensuring `compat_getVar` is compiled and `R_getVar` is defined. |
| `Rboolean` | 20 | Parameter type of `compat_getVar`; the `inherits` argument is `FALSE` in all four call sites. Documented in `Rboolean.md`. |

**Distinct implementation patterns.**

There is exactly one occurrence of `R_UnboundValue` across all rpart source files (`rpart_callback.c:23`). It belongs to a single pattern:

**Pattern: Global sentinel SEXP used as the right-hand side of a pointer equality comparison to detect a failed environment variable lookup.**

The pointer value of `R_UnboundValue` is compared against `val` (the return value of `findVar` / `findVarInFrame`). The comparison is meaningful only if the fake implementations of `findVar` and `findVarInFrame` return the same pointer that `R_UnboundValue` holds when the lookup fails. The entire correctness guarantee therefore rests on a single invariant: the fake `findVar` / `findVarInFrame` stubs must return `R_UnboundValue` (or the identical pointer) when the requested symbol is not registered, and the fake `R_UnboundValue` sentinel must be distinct from every other SEXP pointer that could be returned by those stubs on success.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant (static global sentinel SEXP).**

Although `R_UnboundValue` is technically an R Interpreter Item (its real value is managed by the R engine), its observable contract in the rpart source reduces to a Category A fake: a stable, unique, non-null global `SEXP` pointer that is returned by the `findVar`/`findVarInFrame` stubs on lookup failure and compared with `==` by `compat_getVar`. No interpreter, no environment walk, and no field dereference are exercised by the comparison itself.

**Why a complete fake is technically impossible but practically sufficient.**

A fully faithful fake of `R_UnboundValue` in the real R sense would require:

1. The R interpreter to be running and to have pre-allocated a permanent special-type `SEXPREC` node as the canonical "unbound" marker at startup.
2. `findVar` and `findVarInFrame` to return a pointer equal to `R_UnboundValue` exactly when the symbol is absent.

Neither requirement can be met without `libR.so`. However, the fake runtime can satisfy the observable contract with a static sentinel, because:

- `R_UnboundValue` is never dereferenced in the rpart source. No code reads `val->type`, `val->length`, or `val->data` when `val == R_UnboundValue`. The comparison is always immediately followed by an `error(...)` call or a `return val` — neither path accesses the SEXP's fields.
- The fake `findVar` / `findVarInFrame` stubs (Category E items) are the only code that produces a value that will be compared against `R_UnboundValue`. As long as those stubs return `R_UnboundValue` on failure and return a different SEXP on success, the comparison at line 23 behaves correctly.

**Chosen fake mechanism.**

The real `Rinternals.h` declares `R_UnboundValue` as `LibExtern SEXP R_UnboundValue;` — a variable exported from `libR.so`. In the fake build there is no shared library, so no definition is linked in from outside. The fake must define `R_UnboundValue` as a C++ object with the same type and a suitable value.

Following the exact same pattern established by `R_NilValue` and `R_NamesSymbol` in `SEXP.md` (lines 288–292 of that guide), the fake provides:

```cpp
inline SEXP make_unbound_value() {
    static SEXPREC unbound_rec = { SYMSXP, 0, 0, 0, nullptr };
    return &unbound_rec;
}
static SEXP R_UnboundValue = make_unbound_value();
```

This is already present in `SEXP.md` as part of the canonical `fake_Rinternals.hpp` listing. This guide provides the full rationale and correctness argument that was summarised there.

The function-local `static` ensures that the `SEXPREC` is allocated exactly once, before first use, regardless of static initialization order across translation units. Every translation unit that includes `fake_Rinternals.hpp` gets its own module-level `static SEXP R_UnboundValue` variable, but all of them point to the same `SEXPREC` object because `make_unbound_value()` returns a pointer to the same function-local static.

**Uniqueness guarantee.**

The sentinel is unique by construction:
- `R_UnboundValue` points to `unbound_rec` (a specific `SEXPREC` in the BSS segment).
- `R_NilValue` points to `nil_rec` (a different `SEXPREC`, established by `make_nil_value()`).
- `R_NamesSymbol` points to `sym` (a different `SEXPREC`, established by `make_names_symbol()`).
- Any `SEXP` produced by `allocVector`, `allocMatrix`, or `mkChar` is heap-allocated via `std::malloc` and therefore has a different address from all of the above function-statics.

Since `std::malloc` never returns the address of a function-local static, and since each `make_*` function has its own distinct local static, all global sentinel SEXPs are mutually non-equal. A fake `findVar` stub that returns `R_UnboundValue` on failure and a freshly allocated `allocVector` result on success will never produce a false equality with the sentinel.

**The `findVar`/`findVarInFrame` bridge requirement.**

`R_UnboundValue` itself requires no function-pointer bridge. However, the correctness of the `compat_getVar` function that uses it depends entirely on the `findVar` and `findVarInFrame` stubs behaving correctly. Specifically:

- If the `findVar` / `findVarInFrame` stubs are not yet registered (Python has not called the registration function), those stubs should throw `RError("findVar: Python callback not registered")` rather than returning `R_UnboundValue` or a garbage pointer.
- If Python registers the stubs, they must return `R_UnboundValue` when the symbol is absent and a valid `SEXP` otherwise.
- The `error(...)` call at line 24 (triggered when `val == R_UnboundValue`) throws `RError` (Invariant 1), which propagates up through `compat_getVar`, through `R_getVar`, through `init_rpcallback`, and is caught at the `.Call` boundary wrapper.

**The `R_VERSION < R_Version(4, 5, 0)` compile guard.**

The entire `compat_getVar` body — including the `R_UnboundValue` comparison — is gated by a preprocessor condition. For the fake build, `fake_Rversion.hpp` must define `R_VERSION` and `R_Version(major, minor, patch)` such that the condition evaluates to true (i.e., the fake version is below 4.5.0). This ensures that `compat_getVar` is compiled and `R_getVar` is defined as a macro. If the condition were false, `R_UnboundValue` would not appear in the compiled translation unit at all, and the `R_getVar(...)` calls at lines 59–68 of `rpart_callback.c` would be unresolved.

**`#define` aliases that must be preserved.**

The real `Rinternals.h` declares `R_UnboundValue` as a `LibExtern` variable with no `#define` alias. The variable name `R_UnboundValue` is used directly in the source, not through a macro. No alias is required. The `error` macro alias (`#define error Rf_error` from `R_ext/Error.h`) must be present for line 24 (`error(_("variable '%s' not found"), ...)`) to compile; that alias is documented in the `error`/`Rf_error` fake guide.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): triggered at line 24, not by `R_UnboundValue` itself. When `val == R_UnboundValue`, the code calls `error(...)` which expands to `Rf_error(...)` which must throw `RError`. The `R_UnboundValue` sentinel itself does not trigger Invariant 1.
- Invariant 2 (arena memory): not triggered. `R_UnboundValue` is a function-static `SEXPREC` (BSS segment). No arena allocation occurs.
- Invariant 3 (R Interpreter Items): partially applicable. `R_UnboundValue` technically requires an interpreter for its real value. However, because it is only used as a sentinel in a pointer comparison — and because the fake `findVar`/`findVarInFrame` stubs are designed to return this exact sentinel on failure — the static sentinel fully satisfies the observable contract without a function-pointer bridge on `R_UnboundValue` itself. The function-pointer bridge requirement belongs to `findVar` and `findVarInFrame`, not to `R_UnboundValue`.

---

### 4. Fake Implementation Examples

#### Pattern: Global Sentinel SEXP for Pointer Equality Comparison in `compat_getVar`

- **Locations:** `rpart_callback.c:23`

- **Original R API Usage:**

```c
/* rpart_callback.c:18-28 */
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

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — R_UnboundValue sentinel)
// This definition must appear AFTER the SEXPREC struct and SEXP typedef,
// and AFTER the SYMSXP constant (#define SYMSXP 1), all of which are
// established earlier in fake_Rinternals.hpp (see SEXP.md).
// It must also appear AFTER the R_NilValue definition, so that the
// ordering in the file is: R_NilValue, then R_UnboundValue.

// -----------------------------------------------------------------------
// R_UnboundValue — the "unbound symbol" sentinel.
//
// Real declaration in Rinternals.h line 413:
//   LibExtern SEXP  R_UnboundValue;     /* Unbound marker */
//
// LibExtern expands to `extern` when linking against libR.so.
// In the fake build there is no libR.so, so the variable must be DEFINED
// (not merely declared) in the fake header.
//
// The fake provides a function-static SEXPREC of type SYMSXP.
// The pointer is stable and unique: make_unbound_value() returns the
// address of the same static object on every call, and that object is
// distinct from nil_rec (R_NilValue) and from any heap allocation.
//
// Observable properties:
//   R_UnboundValue != nullptr             (safe to hold in a SEXP variable)
//   R_UnboundValue != R_NilValue          (distinct from the nil sentinel)
//   R_UnboundValue != any allocVector()   (heap allocations differ)
//   TYPEOF(R_UnboundValue) == SYMSXP (1)  (consistent with a symbol node)
//
// The pointer value of R_UnboundValue is only ever used in:
//   if (val == R_UnboundValue)            (rpart_callback.c:23)
// No accessor (INTEGER, REAL, CHAR, LENGTH, etc.) is applied to it.
// -----------------------------------------------------------------------
inline SEXP make_unbound_value() {
    static SEXPREC unbound_rec = { SYMSXP, 0, 0, 0, nullptr };
    return &unbound_rec;
}
static SEXP R_UnboundValue = make_unbound_value();

// -----------------------------------------------------------------------
// fake findVar / findVarInFrame stubs (Category E — R Interpreter Items).
//
// These stubs are the counterpart to R_UnboundValue: they must return
// R_UnboundValue when the requested symbol is absent, and a valid SEXP
// when it is present.  They are driven by Python-side function pointers
// (see the findVar and findVarInFrame fake guides).
//
// Abbreviated stubs (full versions are in the findVar / findVarInFrame
// fake guides):

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

typedef SEXP (*findVarInFrame_fn_t)(SEXP rho, SEXP sym);
static findVarInFrame_fn_t g_findVarInFrame_fn = nullptr;

extern "C" void register_findVarInFrame_fn(findVarInFrame_fn_t fn) {
    g_findVarInFrame_fn = fn;
}

inline SEXP findVarInFrame(SEXP rho, SEXP sym) {
    if (!g_findVarInFrame_fn)
        throw RError("findVarInFrame: Python callback not registered. "
                     "User-defined splits (method=4) and init_rpcallback() "
                     "require registration via register_findVarInFrame_fn().");
    return g_findVarInFrame_fn(rho, sym);
}
#define Rf_findVarInFrame findVarInFrame

// -----------------------------------------------------------------------
// .Call boundary wrapper for init_rpcallback — shows how R_UnboundValue
// participates in the call chain.
//
// Call chain for init_rpcallback() lines 59-68:
//   R_getVar("yback", rho, FALSE)
//     -> compat_getVar(sym, rho, FALSE)       [compat shim, R < 4.5.0]
//       -> findVarInFrame(rho, sym)            [Category E stub]
//       -> if (val == R_UnboundValue)          [sentinel comparison]
//         -> error("variable '%s' not found")  [throws RError, Invariant 1]
//
// The ArenaFrame guard at the wrapper level catches arena cleanup.
// The try/catch catches RError from both the findVarInFrame stub
// (unregistered pointer) and the error() call (variable not found).
//
//   extern "C" SEXP init_rpcallback_wrapper(
//           SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x) {
//       ArenaFrame _frame;
//       try {
//           return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
// -----------------------------------------------------------------------
```

- **Python Interop Notes:**

  `R_UnboundValue` itself requires no Python-side registration. It is a C++-side sentinel. However, the `findVar` and `findVarInFrame` stubs that *produce* a value to be compared against `R_UnboundValue` are Category E items that Python must register. The Python registration snippet for `findVarInFrame` (the path taken by `compat_getVar` when `inherits=FALSE`, which is the case for all four `R_getVar` calls in `init_rpcallback`) is:

  ```python
  import ctypes

  # Load the shared library built from the fake-header rpart source.
  lib = ctypes.CDLL("./librpart_fake.so")

  # SEXP is an opaque pointer in Python; use c_void_p.
  SEXP = ctypes.c_void_p

  # Python-side implementation of findVarInFrame.
  # rho:  SEXP representing the environment frame (passed in from Python
  #       as a ctypes c_void_p handle to a fake SEXPREC).
  # sym:  SEXP representing the symbol being looked up (produced by install()).
  # Returns: a SEXP handle, or the R_UnboundValue sentinel on failure.

  # Retrieve the R_UnboundValue sentinel pointer from the fake library.
  # The sentinel is a module-level static in the fake header; Python reads
  # it via a small exported accessor function (add to fake_Rinternals.hpp):
  #
  #   extern "C" SEXP get_R_UnboundValue() { return R_UnboundValue; }
  #
  lib.get_R_UnboundValue.restype  = SEXP
  lib.get_R_UnboundValue.argtypes = []
  R_UNBOUND = lib.get_R_UnboundValue()

  # The Python symbol registry: maps symbol-SEXP pointer -> value-SEXP pointer.
  # Populated before each .Call invocation by the Python glue layer.
  _symbol_registry: dict = {}  # {sym_ptr: val_ptr}

  FindVarInFrameFnType = ctypes.CFUNCTYPE(SEXP, SEXP, SEXP)

  def py_findVarInFrame(rho: int, sym: int) -> int:
      """
      Look up sym in rho.  Return the registered value SEXP, or
      R_UnboundValue if sym is absent from the registry.
      """
      val = _symbol_registry.get(sym)
      if val is None:
          return R_UNBOUND   # == R_UnboundValue on the C side
      return val

  _findVarInFrame_cb = FindVarInFrameFnType(py_findVarInFrame)

  lib.register_findVarInFrame_fn.restype  = None
  lib.register_findVarInFrame_fn.argtypes = [FindVarInFrameFnType]
  lib.register_findVarInFrame_fn(_findVarInFrame_cb)
  ```

  The key invariant: `py_findVarInFrame` returns `R_UNBOUND` (the integer address of the `R_UnboundValue` sentinel obtained via `get_R_UnboundValue()`) when the symbol is absent. On the C side, `findVarInFrame` returns this pointer, and `compat_getVar` compares it with `R_UnboundValue` using `==`. Because both sides hold the same pointer (the address of `unbound_rec`), the comparison evaluates to `true` and `error(...)` is called.

  The `init_rpcallback` call path (lines 59–68 of `rpart_callback.c`) is only active when `method=4` (user-defined splits) is passed to `rpart()`. Standard methods (anova, poisson, class, exp) use built-in evaluation functions and never invoke `init_rpcallback`. For all standard use cases, the `findVar`/`findVarInFrame` stubs are never called and `R_UnboundValue` is never compared against anything.

- **Arena / Memory Notes:**

  `R_UnboundValue` is a function-static `SEXPREC` allocated in the BSS segment at program startup. It is not heap-allocated, not arena-allocated, and never freed. The `make_unbound_value()` function uses a function-local `static` to guarantee that the `SEXPREC` is initialized exactly once, process-wide, the first time the function is called during static initialization. The `ArenaFrame _frame` at the `.Call` boundary does not interact with `R_UnboundValue` in any way.

- **Explanation:**

  The fake adds the following to `fake_Rinternals.hpp`:

  1. `make_unbound_value()` + `static SEXP R_UnboundValue` — replaces the `LibExtern SEXP R_UnboundValue;` declaration from the real `Rinternals.h`. The `LibExtern` expansion to `extern` would cause a link-time undefined-symbol error when building without `libR.so`; the static definition eliminates that error by providing a BSS-segment `SEXPREC` as the variable's value.

  2. `findVar` and `findVarInFrame` function-pointer stubs, along with their `register_*` functions callable from Python. These are the items that actually produce a value to compare against `R_UnboundValue`; they are the true Category E items in this call chain. Their complete specifications belong to the `findVar` and `findVarInFrame` fake guides, but abbreviated versions are shown here because they are the only consumers of the `R_UnboundValue` sentinel within rpart source.

  3. An exported accessor `get_R_UnboundValue()` (not shown in the main snippet above but required for correct Python interop) so that Python can read the sentinel's address and use it as the failure return value from its `py_findVarInFrame` callback.

  The original `rpart_callback.c` source compiles without modification because:
  - `R_UnboundValue` resolves to a valid `SEXP` expression (a `SEXPREC *` module-level static).
  - The `==` comparison `val == R_UnboundValue` is a well-formed pointer equality expression between two `SEXP` values.
  - `findVar` and `findVarInFrame` resolve to the inline stub functions defined in `fake_Rinternals.hpp`.
  - The `#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)` macro at line 27 is compiled because `fake_Rversion.hpp` sets `R_VERSION < R_Version(4, 5, 0)` to true.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct (`type`, `length`, `nrow`, `ncol`, `data` fields) and the `SEXP` typedef (`typedef SEXPREC *SEXP`). Both are required for `static SEXPREC unbound_rec = { SYMSXP, 0, 0, 0, nullptr };` to be a valid aggregate initializer and for `static SEXP R_UnboundValue` to have the correct type. The `SYMSXP` constant (`#define SYMSXP 1`) from the SEXPTYPE block is required for the initializer. `SEXP.md` also contains the canonical `fake_Rinternals.hpp` listing which already includes `make_unbound_value()` and `static SEXP R_UnboundValue` at lines 288–292. |
| `R_NilValue.md` | Establishes the `make_nil_value()` + `static SEXP R_NilValue` pattern that `R_UnboundValue` follows exactly. `R_NilValue` must be defined before `R_UnboundValue` in `fake_Rinternals.hpp` (both appear in the same section). The `R_NilValue` guide also documents the `error_return` macro which depends on `R_NilValue` and `Rf_error`; those are co-located in the same header. |
| `Rboolean.md` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean`. Required because `compat_getVar` (the function containing the `R_UnboundValue` comparison) has `Rboolean inherits` as its third parameter. `Rboolean` must be defined before `compat_getVar` is compiled. |
| `fake_Rversion.hpp` (not yet generated) | Must define `R_VERSION` and `R_Version(major, minor, patch)` such that `R_VERSION < R_Version(4, 5, 0)` evaluates to `true`. Without this, `compat_getVar` is not compiled, `R_getVar` is not defined, and the `R_UnboundValue` comparison at line 23 is never reached. |
| `findVar` / `findVarInFrame` fake guides (not yet generated — Category E) | `findVar` and `findVarInFrame` produce the `val` that is compared against `R_UnboundValue`. Their stubs must return `R_UnboundValue` on failure. The `R_UnboundValue` sentinel defined here is a prerequisite for those stubs — the stubs must reference `R_UnboundValue` in their failure return paths. |
| `install` fake guide (not yet generated — Category E) | `install("yback")` etc. at `rpart_callback.c:59–68` produces the `sym` argument passed to `compat_getVar` (via `R_getVar`). The `install` stub must return a stable unique SEXP for each string so that the `_symbol_registry` lookup in `py_findVarInFrame` can match it by pointer. |
| `fake_arena.hpp` | Required by the `init_rpcallback_wrapper` `.Call` boundary for the `ArenaFrame` RAII guard. `R_UnboundValue` itself has no arena dependency. |
| `error` / `Rf_error` fake guide (Category D) | The `error(...)` call at `rpart_callback.c:24` (the branch taken when `val == R_UnboundValue`) must throw `RError` (Invariant 1). The `#define error Rf_error` alias from `R_ext/Error.h` and the `Rf_error` throwing implementation must be present in `fake_Rinternals.hpp`. |
