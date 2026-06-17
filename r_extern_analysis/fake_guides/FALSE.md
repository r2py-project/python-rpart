# Fake Header Implementation Guide: `FALSE`

---

### 1. Overview of `FALSE` in R API

`FALSE` is one of the two named enumerator constants of the `Rboolean` enum, defined in `R_ext/Boolean.h` (included transitively by `R.h` and `Rinternals.h`). Its integer value is `0`. The real header always `#undef FALSE` before the enum declaration so that any prior macro definition (e.g., from `<stdbool.h>` or `<cstdbool>`) is replaced by the enumerator. `FALSE` is used wherever R's C API requires a boolean `false` argument — most prominently as the `inherits` flag of `R_getVar`/`findVar`-family functions, and as a boolean configuration argument to `R_useDynamicSymbols`. It is not a macro in the compiled program; it is an enumerator of type `Rboolean` with value `0`.

---

### 2. Contextual Usage Analysis

**Source files and lines examined.**

| File | Line | Context |
|---|---|---|
| `init.c` | 26 | `R_useDynamicSymbols(dll, FALSE);` |
| `rpart_callback.c` | 59 | `stemp = R_getVar(install("yback"), rho, FALSE);` |
| `rpart_callback.c` | 62 | `stemp = R_getVar(install("wback"), rho, FALSE);` |
| `rpart_callback.c` | 65 | `stemp = R_getVar(install("xback"), rho, FALSE);` |
| `rpart_callback.c` | 68 | `stemp = R_getVar(install("nback"), rho, FALSE);` |

**Full context around `init.c:26`.**

```c
/* init.c:22-30 */
void
R_init_rpart(DllInfo * dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

`R_useDynamicSymbols` is declared in `R_ext/Rdynload.h` as:

```c
Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value);
```

`FALSE` is passed as the second argument of type `Rboolean`. In the standalone fake build `R_useDynamicSymbols` is a no-op; `FALSE` merely needs to be an integer-compatible constant so the call compiles.

**Full context around `rpart_callback.c:59-68`.**

```c
/* rpart_callback.c:17-32 */
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

/* rpart_callback.c:47-71 (init_rpcallback) */
SEXP
init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;
    rho = rhox;
    ysave = asInteger(ny);
    rsave = asInteger(nr);
    expr1 = expr1x;
    expr2 = expr2x;

    stemp = R_getVar(install("yback"), rho, FALSE);
    ydata = REAL(stemp);

    stemp = R_getVar(install("wback"), rho, FALSE);
    wdata = REAL(stemp);

    stemp = R_getVar(install("xback"), rho, FALSE);
    xdata = REAL(stemp);

    stemp = R_getVar(install("nback"), rho, FALSE);
    ndata = INTEGER(stemp);

    return R_NilValue;
}
```

`FALSE` is the third argument (`inherits`) of `R_getVar` / `compat_getVar`, whose declared type is `Rboolean`. Passing `FALSE` (value `0`) means "do not search enclosing environments; look only in the immediate frame `rho`."

**C types of arguments and return values.**

- In `R_useDynamicSymbols(dll, FALSE)`: `FALSE` is the second argument of declared type `Rboolean`. The function returns `Rboolean` (ignored at the call site).
- In `R_getVar(install("yback"), rho, FALSE)`: `FALSE` is the third argument of declared type `Rboolean`. The function returns `SEXP`.
- In both positions `FALSE` is consumed as an integer-valued boolean flag. No arithmetic is performed on it; it is used only in boolean tests or passed opaquely.

**Co-occurring R API items.**

- `Rboolean` — the enum type of which `FALSE` is a member. Already documented in `Rboolean.md`.
- `TRUE` — the complementary enumerator (`= 1`) used on `init.c:28` with `R_forceSymbols`. Defined in the same enum as `FALSE`.
- `DllInfo` — the first argument of `R_useDynamicSymbols`. Documented in `DllInfo.md`.
- `R_useDynamicSymbols`, `R_forceSymbols`, `R_registerRoutines` — no-op registration functions; consume `FALSE`/`TRUE` but do nothing in the fake build.
- `R_getVar`, `install`, `findVar`, `findVarInFrame` — R Interpreter Items (Category E). `FALSE` is passed to these functions but the functions themselves require separate fake treatment.
- `SEXP`, `REAL`, `INTEGER`, `asInteger` — SEXP accessors co-occurring in the same function body.

**Distinct usage patterns.**

There are two distinct usage patterns in the CSV:

1. **No-op registration argument** (`init.c:26`) — `FALSE` is passed to `R_useDynamicSymbols`, a library-initialisation function that is a complete no-op in the standalone fake build. The constant only needs to exist and be integer-compatible.
2. **Boolean inherits flag to R_getVar** (`rpart_callback.c:59, 62, 65, 68`) — `FALSE` is passed as the `Rboolean inherits` parameter of `R_getVar` / `compat_getVar`. The value controls which branch of a ternary expression is taken inside the shim (`findVarInFrame` is chosen when `inherits` is `FALSE`). Both `findVar` and `findVarInFrame` are R Interpreter Items.

Both patterns share the same fake strategy: define `FALSE` as enumerator `0` of the `Rboolean` enum. No separate fake mechanism is required per pattern; the difference is purely in the caller's behaviour.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`FALSE` is an enumerator constant. It carries no runtime logic, manages no memory, calls no interpreter function, issues no error or warning, and allocates nothing. The entire fake consists of ensuring that `FALSE` is defined as integer value `0` in a form that is type-compatible with `Rboolean`.

**Chosen mechanism.**

The `Rboolean.md` guide already establishes the canonical fake definition on the GCC/Linux platform (where `HAVE_ENUM_BASE_TYPE` is not defined):

```cpp
#undef FALSE
#undef TRUE
typedef enum { FALSE = 0, TRUE = 1 } Rboolean;
```

`FALSE` is therefore an enumerator of the `Rboolean` enum with value `0`. This guide for `FALSE` does not introduce a new definition; it documents `FALSE` as a named constant that is produced as a side effect of the `Rboolean` enum declaration in `fake_Boolean.hpp`.

The `#undef FALSE` directive before the enum is essential: without it, if a translation unit has already included `<stdbool.h>` or `<cstdbool>`, `FALSE` will be a macro expanding to `0`, and the enum member declaration `FALSE = 0` will be ill-formed (a macro name cannot be re-used as an enumerator name within the same expansion). After `#undef`, `FALSE` is reclaimed as an enumerator name.

**Interaction with `<stdbool.h>` and C++ `bool`.**

In C++, `false` (lowercase) is a keyword of type `bool`. The name `FALSE` (uppercase) has no built-in meaning; it is always user- or library-defined. After `#undef FALSE`, the enum member `FALSE = 0` is the only definition visible. An `int` value `0` passed where a `Rboolean` is expected is accepted by C++ compilers because integer constant `0` is implicitly convertible to any enumeration type (the special "null pointer constant / zero integer" rule for enum initialisation).

**`#define` aliases that must be preserved.**

`R_ext/Boolean.h` introduces no `#define` aliases for `FALSE` beyond the `#undef` that removes prior definitions. After the enum declaration, `FALSE` is an enumerator, not a macro. No additional `#define` wrapper is required.

**Invariant applicability.**

- Invariant 1 (C++ error/warning style): not triggered by `FALSE` itself. The surrounding `compat_getVar` function calls `error(...)` — that is covered by the `Rf_error` / `error` guide.
- Invariant 2 (arena memory): not triggered. `FALSE` is a scalar constant; no allocation occurs.
- Invariant 3 (R Interpreter Items): not triggered by `FALSE` itself. The functions to which `FALSE` is passed (`R_getVar`, `findVar`, `findVarInFrame`) are R Interpreter Items, but `FALSE`'s own definition requires no interpreter.

---

### 4. Fake Implementation Examples

#### Pattern: No-op Registration Argument

- **Locations:** `init.c:26`

- **Original R API Usage:**

```c
/* init.c:25-29 */
R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
```

- **C++ Fake Implementation:**

```cpp
// fake_Boolean.hpp  (excerpt)
// Provides FALSE, TRUE, and Rboolean for the standalone build.
// This file is included by the master fake header (fake_R.hpp) and
// replaces R_ext/Boolean.h in the shadow include tree.

#pragma once
#ifndef FAKE_BOOLEAN_H
#define FAKE_BOOLEAN_H

// Remove any prior macro definitions (e.g. from <stdbool.h>).
#undef FALSE
#undef TRUE

// Rboolean: R's two-valued boolean enum.
// FALSE=0, TRUE=1.  Enumerators are placed in enclosing scope.
typedef enum { FALSE = 0, TRUE = 1 } Rboolean;

#endif // FAKE_BOOLEAN_H

// fake_Rdynload.hpp  (excerpt — the relevant no-op stubs)
// R_useDynamicSymbols and R_forceSymbols are no-ops in the
// standalone build; they exist only to let init.c compile.

#pragma once
#ifndef FAKE_RDYNLOAD_H
#define FAKE_RDYNLOAD_H

#include "fake_Boolean.hpp"
// DllInfo and R_CallMethodDef provided by fake_Rdynload.hpp
// (already documented in DllInfo.md and R_CallMethodDef.md).

struct DllInfo {};  // opaque; only ever used as DllInfo *

inline Rboolean R_useDynamicSymbols(DllInfo * /*info*/, Rboolean /*value*/) {
    return FALSE;  // no-op; return value is never used in init.c
}

inline Rboolean R_forceSymbols(DllInfo * /*info*/, Rboolean /*value*/) {
    return FALSE;  // no-op
}

#endif // FAKE_RDYNLOAD_H
```

- **Arena / Memory Notes:** Not applicable. `FALSE` is a scalar constant; no allocation or deallocation occurs.

- **Explanation:**

  `R_useDynamicSymbols(dll, FALSE)` passes `FALSE` as the `Rboolean value` second parameter. The function's purpose — telling R's loader whether to resolve symbols dynamically — is meaningless in the standalone build. The fake implements it as an `inline` no-op returning `FALSE`. The return value is discarded at the call site. The only requirement on `FALSE` is that it is an integer-compatible constant of type `Rboolean` so the call expression is well-typed; the enum definition in `fake_Boolean.hpp` satisfies this. The original `init.c` is not modified.

---

#### Pattern: Boolean Inherits Flag to R_getVar

- **Locations:** `rpart_callback.c:59`, `rpart_callback.c:62`, `rpart_callback.c:65`, `rpart_callback.c:68`

- **Original R API Usage:**

```c
/* rpart_callback.c:17-32 — compatibility shim */
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

/* rpart_callback.c:59-68 — call sites */
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
// fake_Boolean.hpp — same definition as Pattern 1 above.
// No additional definition is needed for FALSE itself.
// The caller-side (R_getVar / compat_getVar) fake is shown below.

// fake_rpart_callback_interp.hpp
// R_getVar, install, findVar, findVarInFrame are R Interpreter Items.
// They are handled by their own guides (install.md, R_getVar.md, etc.).
// FALSE's role here is limited to being an argument of type Rboolean=0.
//
// For completeness, the compat_getVar shim as it will appear when
// R_VERSION is faked below 4.5.0:

// In the fake build, R_VERSION is set (in fake_Rversion.hpp) to a value
// less than R_Version(4, 5, 0).  This causes the preprocessor to compile
// compat_getVar, which uses FALSE in a boolean test:
//
//   SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
//
// When FALSE (== 0) is passed, inherits evaluates to false, so
// findVarInFrame is selected.  Both findVar and findVarInFrame must be
// provided by their own fake stubs (Category E — R Interpreter Items).
//
// The type check: FALSE is enumerator 0 of Rboolean; the parameter type
// is Rboolean.  C++ accepts the implicit conversion from integer constant
// 0 to any enum type.  No cast is required in the original source.

// Boundary wrapper at the .Call entry point (init_rpcallback):
// The surrounding function is a Category E context — it calls install()
// and R_getVar().  The ArenaFrame guard should still be declared at
// entry to cover any arena-based allocations made by helpers called
// within the same invocation.

extern "C" SEXP init_rpcallback_entry(SEXP rhox, SEXP ny, SEXP nr,
                                       SEXP expr1x, SEXP expr2x)
{
    ArenaFrame frame;  // Invariant 2: free arena allocations on exit
    try {
        return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
    } catch (const RError &e) {
        // Invariant 1: translate C++ exception back to Python error
        // (set a Python exception flag via the ctypes glue layer)
        last_rerror_message = e.what();
        return nullptr;
    }
}
```

- **Python Interop Notes:**

  The functions called with `FALSE` in `rpart_callback.c` are R Interpreter Items (`R_getVar`, `install`, `findVar`, `findVarInFrame`). `FALSE` itself is just an integer flag. From Python's perspective, `FALSE` appears only as the C integer `0` inside arguments passed to those interpreter stubs. No Python-side registration is required for `FALSE`. Registration is required for `install` and `R_getVar`/`findVar`/`findVarInFrame` separately (see those guides).

  The Python-side boundary wrapper uses ctypes to call `init_rpcallback_entry`. If the C++ layer sets `last_rerror_message`, the Python wrapper raises a `RuntimeError`:

  ```python
  import ctypes

  lib = ctypes.CDLL("/path/to/fake_rpart.so")

  # Prototype for the .Call-compatible entry point
  lib.init_rpcallback_entry.restype  = ctypes.c_void_p   # SEXP = pointer
  lib.init_rpcallback_entry.argtypes = [
      ctypes.c_void_p,  # rhox   (SEXP)
      ctypes.c_void_p,  # ny     (SEXP)
      ctypes.c_void_p,  # nr     (SEXP)
      ctypes.c_void_p,  # expr1x (SEXP)
      ctypes.c_void_p,  # expr2x (SEXP)
  ]

  # FALSE == 0 is passed purely within the C layer; Python never
  # supplies it directly.  init_rpcallback_entry does not expose
  # the inherits flag to Python callers.
  ```

- **Explanation:**

  At each of the four call sites, the macro `R_getVar(install("yback"), rho, FALSE)` expands (under the `#if R_VERSION < R_Version(4, 5, 0)` guard) to `compat_getVar(install("yback"), rho, FALSE)`. The argument `FALSE` is enumerator `0` of `Rboolean`, passed as the `Rboolean inherits` parameter. Inside `compat_getVar`, the ternary `inherits ? findVar(...) : findVarInFrame(...)` evaluates the enum value in boolean context: `0` is falsy, so `findVarInFrame` is chosen. This semantics — "search only the immediate frame, not enclosing environments" — is preserved in the fake build once `findVarInFrame` is implemented as a Python-registered stub.

  The fake `FALSE` requires no change to the original source. `fake_Boolean.hpp` provides the `#undef FALSE` / enum definition so that the enumerator is in scope at the point where `rpart_callback.c` uses it. The original source file is not modified; the shadow include tree resolves `#include <R_ext/Boolean.h>` to `fake_Boolean.hpp`.

  The `#if R_VERSION < R_Version(4, 5, 0)` preprocessor guard is critical: it determines whether `compat_getVar` is compiled. In the fake build, `fake_Rversion.hpp` must define `R_VERSION` to a value below `R_Version(4, 5, 0)` so that the shim (and the `R_getVar` macro) is always compiled. If `R_VERSION` were faked as `>= 4.5.0`, the native `R_getVar` from `libR.so` would be expected, which is unavailable in the standalone build.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `Rboolean.md` | Provides the `typedef enum { FALSE = 0, TRUE = 1 } Rboolean;` declaration in `fake_Boolean.hpp`. `FALSE` is an enumerator of this enum; `fake_Boolean.hpp` must be included before any source file that uses `FALSE`. This guide does not introduce a new header — it reuses `fake_Boolean.hpp` from `Rboolean.md`. |
| `DllInfo.md` | Provides `struct DllInfo {}` required so that `R_useDynamicSymbols(DllInfo *, Rboolean)` compiles at `init.c:26`. |
| `R_CallMethodDef.md` | Provides the `R_CallMethodDef` struct and `R_registerRoutines` no-op required by `init.c` (same translation unit as the `FALSE` usage at line 26). |
| `DL_FUNC.md` | Provides the `DL_FUNC` typedef used inside `R_CallMethodDef`. |
| `SEXP.md` / `INTSXP.md` / `REALSXP.md` | Provide the `SEXPREC` struct and `SEXP` typedef. `compat_getVar` and `init_rpcallback` operate on `SEXP` values alongside `FALSE`. |
| `fake_Rversion.hpp` (not yet generated) | Must define `R_VERSION` and the `R_Version(major, minor, patch)` macro such that `R_VERSION < R_Version(4, 5, 0)` is true. This causes `compat_getVar` to be compiled and the `R_getVar` macro to be defined — the code path that uses `FALSE` as the `inherits` flag. |
| `install.md` (not yet generated — Category E) | `install("yback")` etc. are passed as the first argument to `R_getVar`. `install` is an R Interpreter Item and requires a Python-registered function pointer stub. |
| `R_getVar.md` / `findVar.md` / `findVarInFrame.md` (not yet generated — Category E) | These R Interpreter Items are the functions to which `FALSE` is the `inherits` flag. Their stubs must be implemented before `init_rpcallback` can be called successfully from Python. |
| `error.md` / `Rf_error.md` (not yet generated — Category D) | `compat_getVar` calls `error(...)` on the "variable not found" path. Per Invariant 1, `error` must throw `RError`. The `fake_Boolean.hpp` file itself does not call `error`, but the translation unit that includes it (`rpart_callback.c`) does. |
| `fake_arena.hpp` | Required by the top-level `.Call` entry points in the same translation unit (`init_rpcallback`). Per Invariant 2, `ArenaFrame frame;` must be declared at entry of each `.Call` function to ensure arena cleanup on exit. `FALSE` itself does not allocate, but the guard is mandatory in the surrounding function. |
