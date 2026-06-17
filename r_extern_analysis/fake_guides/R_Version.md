# Fake Header Implementation Guide: `R_Version`

---

### 1. Overview of `R_Version` in R API

`R_Version(v, p, s)` is a preprocessor macro defined in `Rversion.h` that encodes an R version triple — major (`v`), minor (`p`), and patch (`s`) — into a single composite integer using the formula `((v) * 65536) + ((p) * 256) + (s)`. Its sole purpose is to produce a comparable integer literal at preprocessing time so that source code can write readable version comparisons against the companion constant `R_VERSION`, e.g. `R_VERSION >= R_Version(2, 16, 0)` or `R_VERSION < R_Version(4, 5, 0)`. It is not a runtime function: it takes no arguments at the C level, returns no value, allocates no memory, and has no observable behaviour outside of `#if` / `#elif` preprocessor directives.

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

The `#if defined(R_VERSION)` guard first tests that the constant is defined at all (a safety net for very old R installs), then uses `R_Version(2, 16, 0)` to produce the integer `131584` for comparison. If true, `R_forceSymbols(dll, TRUE)` is compiled; otherwise it is omitted. In the fake build, `R_forceSymbols` is a no-op stub, so the guard's only meaningful effect is whether that call is present in the translation unit.

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

Here `R_Version(4, 5, 0)` produces `263424`. The comparison `R_VERSION < 263424` guards a compatibility shim that provides `compat_getVar` and the `R_getVar` macro when the installed R predates the native `R_getVar` API function (added in R 4.5.0).

**C types of arguments and return values.**

`R_Version(v, p, s)` is a pure preprocessor macro. Its three operands are integer literals provided at preprocessing time; the expansion is an integer constant expression. The macro has no C type signature, no return type, and produces no runtime value. The comparison operators `>=` and `<` applied to it are evaluated entirely by the C preprocessor, not by the compiler.

**Co-occurring R API items.**

- `R_VERSION` — always appears alongside `R_Version`; it is the left-hand operand in every comparison. Fully documented in `R_VERSION.md` (see Integration Requirements).
- `R_forceSymbols` (`init.c:28`) — compiled when `R_VERSION >= R_Version(2, 16, 0)` is true; a no-op stub in `fake_Rdynload.hpp` (see `DllInfo.md`).
- `compat_getVar`, `findVar`, `findVarInFrame`, `R_UnboundValue`, `error`, `CHAR`, `PRINTNAME`, `Rboolean`, `SEXP` — all compiled into `rpart_callback.c` when `R_VERSION < R_Version(4, 5, 0)` is true. Each is covered by its own fake guide.

**Distinct implementation patterns.**

Both CSV rows use `R_Version` in a preprocessor comparison against `R_VERSION`. They share one fake strategy — define `R_Version(v, p, s)` as a `#define` formula macro — and differ only in the threshold values supplied as arguments:

1. `R_Version(2, 16, 0)` = `131584` in `init.c:27` (lower bound, feature-presence guard).
2. `R_Version(4, 5, 0)` = `263424` in `rpart_callback.c:19` (upper bound, backward-compatibility shim guard).

Both are covered by a single fake definition; no separate treatment per pattern is required for `R_Version` itself.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant** (compile-time macro variant).

`R_Version` is a preprocessor macro that produces an integer constant expression. It falls into Category A because it is a pure compile-time construct with no runtime behaviour, no memory interaction, no error/warning mechanism, and no interpreter dependency. The entire fake consists of a single `#define` directive.

**Chosen mechanism.**

```cpp
#define R_Version(v, p, s)  (((v) * 65536) + ((p) * 256) + (s))
```

This is identical to the real `Rversion.h` definition. The macro is self-contained: it requires no helper types, no arena, and no exception handling. Any integer arguments produce a deterministic integer constant expression that the preprocessor can evaluate.

**Relationship to `R_VERSION` (established in `R_VERSION.md`).**

`R_Version` and `R_VERSION` are inseparable: `R_Version` is the formula and `R_VERSION` is the specific value produced by applying that formula to the installed R version. The `R_VERSION.md` guide (already generated) documents both macros together and establishes the faked value `R_VERSION = R_Version(4, 4, 0) = 263168`. That value simultaneously satisfies both guards in the CSV:

- `defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)`: `263168 >= 131584` — true.
- `R_VERSION < R_Version(4, 5, 0)`: `263168 < 263424` — true.

The `R_Version.md` guide (this document) focuses exclusively on the formula macro. The `R_VERSION.md` guide focuses on the specific constant. Both macros must be defined in the same fake header file, `fake_Rversion.hpp`, so that any `#include <Rversion.h>` in the package source resolves both at once.

**`#define` aliases and supplementary macros.**

The real `Rversion.h` also defines `R_NICK`, `R_MAJOR`, `R_MINOR`, `R_STATUS`, `R_YEAR`, `R_MONTH`, `R_DAY`, and `R_SVN_REVISION`. None appear in the rpart CSV dataset, but they are included in `fake_Rversion.hpp` with R 4.4.0 placeholder values to prevent compile errors from transitively included headers. See `R_VERSION.md` for the full list.

**Invariant applicability.**

- Invariant 1 (C++ error/warning style): not triggered. `R_Version` is a preprocessor formula; it issues no errors or warnings.
- Invariant 2 (arena memory): not triggered. `R_Version` allocates nothing.
- Invariant 3 (R Interpreter Items): not triggered by `R_Version` itself. However, the code compiled when `R_VERSION < R_Version(4, 5, 0)` is true calls `findVar`, `findVarInFrame`, and `error`, which are R Interpreter Items or Category D items handled in their own guides.

---

### 4. Fake Implementation Examples

#### Pattern: Compile-time version comparison using R_Version macro

- **Locations:** `init.c:27`, `rpart_callback.c:19`

- **Original R API Usage:**

```c
/* init.c:27 */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif

/* rpart_callback.c:19 */
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
// fake_Rversion.hpp
// Drop-in replacement for <Rversion.h>.
// Defines R_Version and R_VERSION as pure preprocessor constants so that
// rpart/src/*.c compile and link without libR.so.
//
// Design constraints satisfied simultaneously:
//   init.c:27        requires  R_VERSION >= R_Version(2, 16, 0) = 131584  => TRUE
//   rpart_callback.c:19  requires  R_VERSION <  R_Version(4, 5, 0) = 263424  => TRUE
//
// Chosen faked version: R 4.4.0  =>  R_Version(4, 4, 0) = 263168
//   263168 >= 131584  =>  true   (R_forceSymbols call compiled)
//   263168  < 263424  =>  true   (compat_getVar shim compiled; native R_getVar not needed)

#pragma once
#ifndef FAKE_RVERSION_H
#define FAKE_RVERSION_H

// Version encoding formula — identical to the real Rversion.h.
// Encodes a (major, minor, patch) triple as a single integer:
//   major * 65536 + minor * 256 + patch
#define R_Version(v, p, s)  (((v) * 65536) + ((p) * 256) + (s))

// Faked R version constant: R 4.4.0 = 263168.
// Established in R_VERSION.md; reproduced here for completeness.
#define R_VERSION           R_Version(4, 4, 0)   /* 263168 */

// Supplementary macros from the real Rversion.h.
// Present here to prevent compile errors from transitively included headers.
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

- **Explanation:**

  The preprocessor resolves `R_Version(2, 16, 0)` to `((2)*65536 + (16)*256 + (0))` = `131584` and `R_Version(4, 5, 0)` to `((4)*65536 + (5)*256 + (0))` = `263424`. With `R_VERSION` defined as `263168`:

  - In `init.c`: `defined(R_VERSION)` is true (the macro exists), and `263168 >= 131584` is true. The preprocessor retains `R_forceSymbols(dll, TRUE)` in the translation unit. Because `R_forceSymbols` is a no-op inline stub in `fake_Rdynload.hpp` (documented in `DllInfo.md`), the call compiles and links without `libR.so`.

  - In `rpart_callback.c`: `263168 < 263424` is true. The `compat_getVar` function definition and the `#define R_getVar(...)` alias are compiled into the translation unit. The native `R_getVar` symbol from `libR.so` is never referenced, avoiding an undefined-reference link error.

  Neither `init.c` nor `rpart_callback.c` is modified. The shadow include tree redirects `#include <Rversion.h>` to `fake_Rversion.hpp`, supplying both `R_Version` and `R_VERSION` as pure preprocessor constants.

  The three parentheses pairs in `(((v) * 65536) + ((p) * 256) + (s))` follow the standard defensive `#define` style: each operand is parenthesised individually to prevent operator-precedence surprises if a macro argument is itself an expression (e.g. `R_Version(MAJOR, MINOR, PATCH)` where the identifiers expand to arithmetic expressions).

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `R_VERSION.md` | Provides the companion constant `#define R_VERSION R_Version(4, 4, 0)` in `fake_Rversion.hpp`. `R_Version` is the encoding formula; `R_VERSION` is the specific value produced by that formula. Both live in the same header file. `R_VERSION.md` must be consulted to confirm the faked value (263168) before `fake_Rversion.hpp` is written, because changing `R_VERSION` would alter which preprocessor branches are compiled across all rpart source files. |
| `DllInfo.md` | Provides the `R_forceSymbols` no-op stub in `fake_Rdynload.hpp`. `R_forceSymbols` is compiled into `init.c` because `R_VERSION >= R_Version(2, 16, 0)` evaluates to true with the faked value. Without the stub, the translation unit would have an undefined reference at link time. |
| `Rboolean.md` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean` in `fake_Boolean.hpp`. Required because `compat_getVar` (compiled when `R_VERSION < R_Version(4, 5, 0)`) declares a `Rboolean inherits` parameter. |
| `SEXP.md` | Provides the `SEXPREC` struct and `SEXP` typedef. `compat_getVar` and all callers in `rpart_callback.c` operate on `SEXP` values. |
| `R_UnboundValue.md` | Provides the `R_UnboundValue` sentinel SEXP used in `compat_getVar`'s "variable not found" check, compiled because `R_VERSION < R_Version(4, 5, 0)` is true. |
| `error.md` / `Rf_error.md` (Category D — not yet generated at time of writing) | `compat_getVar` calls `error(...)` on the "variable not found" path. Per Invariant 1, `error` must be aliased to `Rf_error`, which must `throw RError(msg)`. This guide must be generated before the build can execute the error path inside `compat_getVar`. |
| `findVar.md` / `findVarInFrame.md` (Category E — not yet generated at time of writing) | `compat_getVar` calls `findVar` or `findVarInFrame` depending on the `inherits` flag. Both are R Interpreter Items requiring Python-registered function pointer stubs. The code path that calls them (user-defined splits, method=4 in rpart) remains unavailable until those stubs are registered from Python. |
| `install.md` (Category E — not yet generated at time of writing) | Call sites in `rpart_callback.c` that use `R_getVar(install("yback"), rho, FALSE)` etc. require `install(name)` to intern a symbol name. `install` is an R Interpreter Item requiring its own function pointer stub. |
| `fake_arena.hpp` | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, `arena_calloc`. Required by the `.Call` boundary wrapper for `init_rpcallback` to satisfy Invariant 2. `R_Version` itself allocates nothing, but the surrounding `.Call` function must declare `ArenaFrame frame` at entry. |
