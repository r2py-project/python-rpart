# Fake Header Implementation Guide: `R_VERSION`

---

### 1. Overview of `R_VERSION` in R API

`R_VERSION` is a preprocessor integer constant defined in `Rversion.h`. It encodes the version of the R installation as a single composite integer using the formula `(major * 65536) + (minor * 256) + (patch)`. The companion macro `R_Version(v, p, s)` expands to the same formula so that source code can write readable version comparisons such as `R_VERSION >= R_Version(2, 16, 0)` or `R_VERSION < R_Version(4, 5, 0)`. In the installed R header at `~/.conda/envs/r-to-python/lib/R/include/Rversion.h`, `R_VERSION` is defined as the literal integer `263427` (corresponding to R 4.5.3: `4*65536 + 5*256 + 3`). In the standalone fake build — where `libR.so` is absent — `R_VERSION` and `R_Version` are pure preprocessor constructs that influence which code paths are compiled at C preprocessing time; they have no runtime existence.

---

### 2. Contextual Usage Analysis

**Source files and lines examined.**

| File | Line | Context |
|---|---|---|
| `init.c` | 27 | `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` |
| `rpart_callback.c` | 19 | `#if R_VERSION < R_Version(4, 5, 0)` |

**Full context window — `init.c` lines 12–30.**

```c
static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart",           (DL_FUNC) &rpart,           11},
    {"xpred",           (DL_FUNC) &xpred,           15},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,        2},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,      12},
    {NULL, NULL, 0}
};

#include <Rversion.h>
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

The `#if defined(R_VERSION)` guard first checks that the macro is defined at all (a safety net for very old R installs), then requires the encoded version to be at least `R_Version(2, 16, 0)` (i.e., R 2.16.0). If the condition is true, `R_forceSymbols(dll, TRUE)` is called; otherwise that call is silently omitted. In the fake build, `R_forceSymbols` is a no-op, so the guard's only observable effect is whether the call is compiled. The standalone build must make the guard evaluate to true so that the enclosed `R_forceSymbols` call is present and compiles (even though it does nothing at runtime).

**Full context window — `rpart_callback.c` lines 1–28.**

```c
#include <stddef.h>
#include <R.h>
#include <Rinternals.h>
#include <Rversion.h>

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
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
  if (val == R_UnboundValue)
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif
```

Here `R_VERSION < R_Version(4, 5, 0)` guards a compatibility shim for the `R_getVar` function, which was introduced as a native R API function in R 4.5.0. When the condition is true, `compat_getVar` is compiled and `R_getVar` is `#define`d to call it. When the condition is false, the preprocessor assumes the native `R_getVar` from `libR.so` will be available at link time — which it is not in the standalone fake build.

**C types of arguments and return values.**

`R_VERSION` and `R_Version(v, p, s)` are preprocessor macros that expand to integer constant expressions. They are consumed exclusively in `#if` / `#elif` preprocessor directives; they have no C type and produce no runtime value. The comparison operators `>=` and `<` are applied to these integer expressions by the preprocessor, not by the C compiler.

**Co-occurring R API items.**

- `R_Version(v, p, s)` — always appears alongside `R_VERSION`; it is defined in the same `Rversion.h` header and must be faked together with `R_VERSION`.
- `R_forceSymbols` (`init.c:28`) — the call compiled only when `R_VERSION >= R_Version(2, 16, 0)`. In the fake build this is a no-op; see `DllInfo.md`.
- `R_useDynamicSymbols`, `R_registerRoutines` — no-op registration functions in the same function body.
- `DllInfo` — parameter type of `R_init_rpart`; documented in `DllInfo.md`.
- `FALSE`, `TRUE` — boolean constants passed to `R_useDynamicSymbols` and `R_forceSymbols`; documented in `FALSE.md` and `Rboolean.md`.
- `compat_getVar`, `findVar`, `findVarInFrame`, `R_getVar`, `install` — compiled only when `R_VERSION < R_Version(4, 5, 0)`; `findVar`, `findVarInFrame`, `install`, and `R_getVar` are R Interpreter Items.
- `Rboolean`, `SEXP`, `R_UnboundValue`, `error`, `CHAR`, `PRINTNAME` — also compiled inside the `rpart_callback.c` block guarded by `R_VERSION`.

**Distinct implementation patterns.**

There are two distinct preprocessor patterns:

1. **Feature-presence guard** (`init.c:27`): `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)`. Encloses a no-op registration call. The fake must define `R_VERSION` such that this guard evaluates to true, so the enclosed call is compiled and the translation unit has no undefined-reference to `R_forceSymbols` at link time (where `R_forceSymbols` is provided as a no-op stub).

2. **Backward-compatibility shim guard** (`rpart_callback.c:19`): `#if R_VERSION < R_Version(4, 5, 0)`. Encloses the `compat_getVar` shim and the `R_getVar` macro. The fake must define `R_VERSION` such that this guard evaluates to true, ensuring the shim is always compiled. If the guard were false, the preprocessor would expect the native `R_getVar` symbol from `libR.so`, which is absent in the standalone build.

Both patterns require the same underlying fake: a fixed compile-time integer for `R_VERSION` and the `R_Version(v, p, s)` formula macro. The two patterns impose contradictory-seeming constraints — pattern 1 wants `R_VERSION >= R_Version(2, 16, 0)`, pattern 2 wants `R_VERSION < R_Version(4, 5, 0)` — which are simultaneously satisfiable by any version in the range `[R_Version(2, 16, 0), R_Version(4, 5, 0))`. The natural choice is `R_Version(4, 4, 0)` (i.e., R 4.4.0, encoded as `263168`), which satisfies both guards and is close to the actual installed R version.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant** (macro constant variant).

`R_VERSION` and `R_Version` are preprocessor macros, not C types or enum values, but they fall into Category A because they are compile-time constants consumed exclusively by the preprocessor. They carry no runtime behaviour, manage no memory, call no interpreter, and issue no errors or warnings. The entire fake consists of two `#define` directives.

**Chosen mechanism.**

Define `R_VERSION` as the integer literal `263168` (corresponding to R 4.4.0: `4*65536 + 4*256 + 0`) and define `R_Version(v, p, s)` with the same encoding formula as the real header. The value `263168` simultaneously satisfies both guards present in the CSV:

- `defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)`: `263168 >= 131584` — true. `R_forceSymbols` call is compiled (and is a no-op).
- `R_VERSION < R_Version(4, 5, 0)`: `263168 < 263424` — true. `compat_getVar` shim is compiled and `R_getVar` macro is defined; the native `R_getVar` symbol from `libR.so` is not required.

Any integer in the half-open range `[R_Version(2, 16, 0), R_Version(4, 5, 0))` = `[131584, 263424)` satisfies both guards. R 4.4.0 (`263168`) is chosen because it is the most recent version that satisfies both constraints and is close to the actual installed R version (`4.5.3` = `263427`), minimising the risk of activating unintended `#if R_VERSION ...` guards elsewhere in the source tree.

**`#define` aliases and supplementary macros that must be preserved.**

The real `Rversion.h` also defines several supplementary macros (`R_NICK`, `R_MAJOR`, `R_MINOR`, `R_STATUS`, `R_YEAR`, `R_MONTH`, `R_DAY`, `R_SVN_REVISION`). None of these appear in the rpart CSV dataset, but they may be referenced by transitively included headers or by code paths not covered by the CSV. They should be included in `fake_Rversion.hpp` with plausible placeholder values to prevent compile errors from any `#include <Rversion.h>` elsewhere in the build.

**Invariant applicability.**

- Invariant 1 (C++ error/warning style): not triggered. `R_VERSION` is a preprocessor constant; it issues no errors or warnings.
- Invariant 2 (arena memory): not triggered. `R_VERSION` allocates nothing.
- Invariant 3 (R Interpreter Items): not triggered by `R_VERSION` itself. However, the code path that `R_VERSION < R_Version(4, 5, 0)` compiles (i.e., `compat_getVar`) calls `findVar`, `findVarInFrame`, `install`, and `error` — all of which are handled in their own guides.

---

### 4. Fake Implementation Examples

#### Pattern: Feature-Presence Guard (Compile No-Op Registration Call)

- **Locations:** `init.c:27`

- **Original R API Usage:**

```c
/* init.c:22-30 */
#include <Rversion.h>
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

- **C++ Fake Implementation:**

```cpp
// fake_Rversion.hpp
// Drop-in replacement for Rversion.h.
// Defines R_VERSION as a compile-time integer that satisfies all
// preprocessor guards found in rpart/src/*.c without requiring libR.so.
//
// Chosen value: R 4.4.0  =>  4*65536 + 4*256 + 0  =  263168
//   * >= R_Version(2, 16, 0) = 131584  =>  true  (R_forceSymbols path compiled)
//   *  < R_Version(4, 5, 0)  = 263424  =>  true  (compat_getVar path compiled)

#pragma once
#ifndef FAKE_RVERSION_H
#define FAKE_RVERSION_H

// Core version encoding formula — identical to the real Rversion.h.
#define R_Version(v, p, s)  (((v) * 65536) + ((p) * 256) + (s))

// Faked R version: 4.4.0
#define R_VERSION           R_Version(4, 4, 0)   /* 263168 */

// Supplementary macros — present in the real Rversion.h; included here
// to prevent compile errors from any transitively included header or
// code path that references them.  Values match R 4.4.0 placeholders.
#define R_NICK          "Pile of Leaves"
#define R_MAJOR         "4"
#define R_MINOR         "4.0"
#define R_STATUS        ""
#define R_YEAR          "2024"
#define R_MONTH         "04"
#define R_DAY           "24"
#define R_SVN_REVISION  86474

#endif // FAKE_RVERSION_H
```

The no-op stubs required by the compiled `R_forceSymbols` call live in `fake_Rdynload.hpp` (established in `DllInfo.md`):

```cpp
// fake_Rdynload.hpp (excerpt — already documented in DllInfo.md)
#include "fake_Boolean.hpp"

struct DllInfo {};

inline void R_registerRoutines(DllInfo *, const void *, const void *,
                                const void *, const void *) {}
inline Rboolean R_useDynamicSymbols(DllInfo *, Rboolean) { return FALSE; }
inline Rboolean R_forceSymbols(DllInfo *, Rboolean)      { return FALSE; }
```

- **Arena / Memory Notes:** Not applicable. This pattern is a pure preprocessor guard; no allocation occurs.

- **Explanation:**

  When the preprocessor processes `init.c`, it evaluates `defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)`. With `fake_Rversion.hpp` providing `R_VERSION = 263168` and `R_Version(2, 16, 0) = 131584`, the condition is `263168 >= 131584`, which is true. The preprocessor therefore retains the `R_forceSymbols(dll, TRUE)` call in the translation unit. Because `R_forceSymbols` is defined as an `inline` no-op stub in `fake_Rdynload.hpp`, the call compiles and links without `libR.so`. The original `init.c` is not modified.

---

#### Pattern: Backward-Compatibility Shim Guard (Compile `compat_getVar` and `R_getVar` Macro)

- **Locations:** `rpart_callback.c:19`

- **Original R API Usage:**

```c
/* rpart_callback.c:8-28 */
#include <Rversion.h>

/* compatibility shim for R < 4.5.0 */
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
// fake_Rversion.hpp — same definition as Pattern 1 above.
// R_VERSION = 263168 (R 4.4.0) satisfies R_VERSION < R_Version(4, 5, 0)
// = 263168 < 263424 => true.
// The preprocessor therefore compiles compat_getVar and defines the
// R_getVar macro.  No second header file is needed.

// Downstream stubs required because compat_getVar is now compiled:
//
// 1. findVar / findVarInFrame / install — R Interpreter Items (Category E).
//    These must be provided as function-pointer stubs that Python registers
//    via ctypes before calling init_rpcallback.  See the respective guides.
//
// 2. error() — Category D.  compat_getVar calls error(...) on the
//    "not found" path.  Must throw RError (Invariant 1).
//
// 3. R_UnboundValue, CHAR, PRINTNAME — covered by their own guides.
//
// The .Call boundary wrapper for init_rpcallback illustrates how
// Invariants 1 and 2 interact with the code path enabled by R_VERSION:

#include "fake_Rversion.hpp"    // provides R_VERSION, R_Version
#include "fake_Boolean.hpp"     // provides Rboolean, FALSE, TRUE
#include "fake_Rinternals.hpp"  // provides SEXP, SEXPREC, etc.
#include "fake_arena.hpp"       // provides ArenaFrame, gArenaStack

// RError — project-wide C++ exception type for R errors (Invariant 1).
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

// Thread-local storage for the last RError message,
// readable by the Python ctypes glue layer.
inline thread_local const char *last_rerror_message = nullptr;

// .Call boundary wrapper for init_rpcallback.
// Declared extern "C" so Python's ctypes can find the symbol by name.
extern "C" SEXP init_rpcallback_entry(SEXP rhox, SEXP ny, SEXP nr,
                                       SEXP expr1x, SEXP expr2x)
{
    ArenaFrame frame;   // Invariant 2: pushes a new arena frame;
                        // popped (all frame memory freed) on scope exit.
    try {
        return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
    } catch (const RError &e) {
        // Invariant 1: translate C++ exception to a Python-visible flag.
        last_rerror_message = e.what();
        return nullptr;
    }
}
```

The corresponding Python-side glue reads the error flag after each call:

```python
import ctypes

lib = ctypes.CDLL("/path/to/fake_rpart.so")

# Retrieve the thread-local error message pointer.
lib.last_rerror_message.restype = ctypes.c_char_p

# Prototype for the .Call-compatible entry point.
lib.init_rpcallback_entry.restype  = ctypes.c_void_p   # SEXP = pointer
lib.init_rpcallback_entry.argtypes = [
    ctypes.c_void_p,  # rhox   (SEXP)
    ctypes.c_void_p,  # ny     (SEXP)
    ctypes.c_void_p,  # nr     (SEXP)
    ctypes.c_void_p,  # expr1x (SEXP)
    ctypes.c_void_p,  # expr2x (SEXP)
]

def call_init_rpcallback(rhox, ny, nr, expr1x, expr2x):
    result = lib.init_rpcallback_entry(rhox, ny, nr, expr1x, expr2x)
    if result is None:
        msg = lib.last_rerror_message
        raise RuntimeError(msg.decode() if msg else "unknown RError")
    return result
```

- **Arena / Memory Notes:** `R_VERSION` itself allocates nothing. However, because the condition `R_VERSION < R_Version(4, 5, 0)` is true in the fake build, `compat_getVar` and its callers are compiled. Within `init_rpcallback` (the `.Call` entry point), the `ArenaFrame` guard at the boundary wrapper (`init_rpcallback_entry`) ensures that any arena-based allocations made by callees (e.g., from `R_alloc`-using helpers) are freed when the frame exits. This is required by Invariant 2 regardless of whether `compat_getVar` itself allocates arena memory.

- **Explanation:**

  With `R_VERSION = 263168` (R 4.4.0), the preprocessor evaluates `R_VERSION < R_Version(4, 5, 0)` as `263168 < 263424`, which is true. The `compat_getVar` function definition and the `#define R_getVar(...)` alias are therefore compiled into every translation unit that includes `fake_Rversion.hpp`.

  This is the critical design decision: if `R_VERSION` were faked as `>= R_Version(4, 5, 0)` (e.g., matching the installed R 4.5.3 = `263427`), the preprocessor would skip `compat_getVar` and the `R_getVar` macro. The code would then expect the native `R_getVar` symbol from `libR.so` — which is not available in the standalone build — causing an undefined-reference link error. By keeping `R_VERSION` below `4.5.0`, the fake build always compiles the self-contained shim, bypassing the need for the native symbol.

  The original `rpart_callback.c` is not modified. The shadow include tree redirects `#include <Rversion.h>` to `fake_Rversion.hpp`, which supplies `R_VERSION` and `R_Version` as pure preprocessor constants.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `Rboolean.md` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean` in `fake_Boolean.hpp`. Required because `compat_getVar` (compiled when `R_VERSION < R_Version(4, 5, 0)`) declares a `Rboolean inherits` parameter. `fake_Rversion.hpp` must be included before or alongside `fake_Boolean.hpp`. |
| `FALSE.md` | Provides the `FALSE` enumerator constant passed as the `inherits` argument at all four `R_getVar` call sites in `init_rpcallback`. |
| `SEXP.md` / `INTSXP.md` / `REALSXP.md` | Provide the `SEXPREC` struct and `SEXP` typedef. `compat_getVar` and `init_rpcallback` operate on `SEXP` values. |
| `DllInfo.md` | Provides `struct DllInfo {}` and the `R_forceSymbols` no-op stub. `R_forceSymbols` is compiled into `init.c` because `R_VERSION >= R_Version(2, 16, 0)` is true with the faked value. |
| `R_CallMethodDef.md` | Provides the `R_CallMethodDef` struct and `R_registerRoutines` no-op. Same translation unit (`init.c`) as the `R_VERSION` usage at line 27. |
| `DL_FUNC.md` | Provides the `DL_FUNC` typedef used inside the `CallEntries` table in `init.c`. |
| `R_UnboundValue.md` | Provides the `R_UnboundValue` sentinel SEXP used in `compat_getVar`'s "not found" check. Required when `R_VERSION < R_Version(4, 5, 0)` is true (always in the fake build). |
| `Rboolean.md` (also listed above) | `R_useDynamicSymbols(dll, FALSE)` at `init.c:26` requires `Rboolean` and `FALSE` to be defined before `R_init_rpart` is compiled. |
| `error.md` / `Rf_error.md` (not yet generated — Category D) | `compat_getVar` calls `error(...)` on the "variable not found" path. Per Invariant 1, `error` must be aliased to `Rf_error`, which must `throw RError(msg)`. This guide must be generated before the build can execute the error path inside `compat_getVar`. |
| `findVar.md` / `findVarInFrame.md` (not yet generated — Category E) | `compat_getVar` calls `findVar` or `findVarInFrame` depending on the `inherits` flag. Both are R Interpreter Items requiring Python-registered function pointer stubs. The code path that calls them (`init_rpcallback` with user-defined splits, method=4) remains unavailable until the stubs are registered. |
| `install.md` (not yet generated — Category E) | `R_getVar(install("yback"), rho, FALSE)` etc. call `install(name)` to intern a symbol name. `install` is an R Interpreter Item requiring a Python-registered function pointer stub. |
| `fake_arena.hpp` | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, `arena_calloc`. Required by the `.Call` boundary wrapper (`init_rpcallback_entry`) to satisfy Invariant 2. `R_VERSION` itself does not allocate, but the surrounding `.Call` function must declare `ArenaFrame frame` at entry. |
