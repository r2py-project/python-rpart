# Fake Header Implementation Guide: `Rboolean`

---

### 1. Overview of `Rboolean` in R API

`Rboolean` is R's dedicated boolean type, defined in `R_ext/Boolean.h` (included transitively by `R.h`). It is a C `enum` with exactly two named members: `FALSE = 0` and `TRUE = 1`. The enum has no `NA_LOGICAL` member — R's tri-valued logical NA is represented separately via `INT_MIN` in the `LGLSXP` vector storage layer and is not part of `Rboolean`. When the C compiler supports enum base-type specification (`HAVE_ENUM_BASE_TYPE`, a Clang/C23 extension), the authoritative header spells it `typedef enum :int { FALSE = 0, TRUE } Rboolean`, guaranteeing that the underlying integer type is exactly `int`. On compilers that lack this extension (including the GCC/Linux platform where this project runs, where `HAVE_ENUM_BASE_TYPE` is not defined per `Rconfig.h`), the header falls back to `typedef enum { FALSE = 0, TRUE } Rboolean`. In practice `Rboolean` is used wherever R's C API requires an explicit boolean argument (e.g., the `inherits` flag of `findVar`-family functions and `R_getVar`), providing a self-documenting alternative to passing a raw `int`.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `rpart_callback.c` | 20 | `static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)` |

**Full context window (lines 1–30 of `rpart_callback.c`):**

```c
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

And the call sites inside `init_rpcallback` (lines 59–69):

```c
stemp = R_getVar(install("yback"), rho, FALSE);
stemp = R_getVar(install("wback"), rho, FALSE);
stemp = R_getVar(install("xback"), rho, FALSE);
stemp = R_getVar(install("nback"), rho, FALSE);
```

**C types of arguments and return values.**

- `Rboolean inherits` is the third parameter of `compat_getVar`. Its declared type is `Rboolean`.
- Inside the function body it is used in a boolean context (`inherits ? ... : ...`), so any type that is implicitly convertible to `int` (or that participates in C boolean evaluation) is acceptable.
- At every call site the literal `FALSE` is passed. `FALSE` is a macro defined by `R_ext/Boolean.h` as `0` after first `#undef`-ing any pre-existing definition. In standard C (and C++) the constant `0` is implicitly convertible to any integer or enum type; `Rboolean` accepts it without a cast.

**Co-occurring R API items.**

- `SEXP`, `R_UnboundValue` — appear in the same function as parameters and a sentinel comparison value.
- `findVar(sym, rho)` and `findVarInFrame(rho, sym)` — the two branches selected by the `Rboolean` flag; both are R Interpreter Items (Category E) that require a running R environment.
- `error(...)`, `CHAR(...)`, `PRINTNAME(...)` — error formatting and symbol-name extraction.
- `install(...)` — symbol interning; also an R Interpreter Item.
- `R_getVar` — the macro alias that replaces `compat_getVar` for R >= 4.5.0.

**Distinct usage patterns.**

There is exactly one usage pattern in the CSV:

1. **Parameter type declaration** — `Rboolean` is used as the type of a formal parameter `inherits` in the signature of a static shim function. The value passed at every call site is the named constant `FALSE` (i.e., `0`). The parameter is consumed only in a ternary boolean test; no arithmetic is performed on it.

No other patterns (e.g., `Rboolean` as a local variable, as a struct field, or tested against `TRUE` by name) appear in the CSV dataset.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`Rboolean` is a pure type definition. It carries no runtime logic, manages no memory, and calls no interpreter. The entire fake consists of reproducing the type and its two named constants so that the original source compiles unmodified.

**Chosen mechanism.**

On the target Linux/GCC platform, `HAVE_ENUM_BASE_TYPE` is not defined (confirmed by `Rconfig.h` line 33: `/* #undef HAVE_ENUM_BASE_TYPE */`). The authoritative header therefore uses the plain form:

```c
typedef enum { FALSE = 0, TRUE } Rboolean;
```

The fake header replicates this exactly. In a C++ compilation unit (`extern "C"` is not needed for a typedef), `typedef enum { FALSE = 0, TRUE } Rboolean` is valid C++11 and later: anonymous enums are permitted, and the enumerators `FALSE` and `TRUE` are placed in enclosing scope as `int`-valued constants.

**Interaction with `bool` and `<stdbool.h>`.**

The real `R_ext/Boolean.h` always `#undef FALSE` and `#undef TRUE` before defining the enum, removing any prior macro definitions (such as those from `<stdbool.h>`). The fake must do the same to avoid conflicts when compiled in a translation unit that has already included `<stdbool.h>` or `<cstdbool>`. After the `#undef` directives, `FALSE` and `TRUE` are enumerator constants (not macros), which is exactly what the original source uses at the `R_getVar(install("yback"), rho, FALSE)` call sites.

**`#define` aliases that must be preserved.**

`R_ext/Boolean.h` does not introduce any `#define` aliases for `Rboolean` itself. The constants `FALSE` and `TRUE` are enum members, not macros, after the `#undef` directives run. No additional `#define` wrappers are required.

**Invariant applicability.**

- Invariant 1 (C++ error/warning style): not directly triggered by `Rboolean`. The `error(...)` call inside `compat_getVar` does involve `Rf_error`, which must throw `RError` — but that is documented in the `error` / `Rf_error` guide, not here.
- Invariant 2 (arena memory): not triggered. `Rboolean` is a scalar type; no allocation occurs.
- Invariant 3 (R Interpreter Items): not triggered by `Rboolean` itself. The function that accepts a `Rboolean` parameter (`compat_getVar`) is a shim around `findVar` and `findVarInFrame`, which are R Interpreter Items, but `Rboolean`'s type definition requires no interpreter.

---

### 4. Fake Implementation Examples

#### Pattern: Boolean Flag Parameter in Compatibility Shim

- **Locations:** `rpart_callback.c:20`

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

/* Call site (rpart_callback.c:59) */
stemp = R_getVar(install("yback"), rho, FALSE);
```

- **C++ Fake Implementation:**

```cpp
// fake_Boolean.hpp
// Drop-in replacement for R_ext/Boolean.h.
// Mirrors the authoritative definition on GCC/Linux platforms where
// HAVE_ENUM_BASE_TYPE is not defined (Rconfig.h line 33).
//
// Include this header before any rpart source file that includes R.h
// or R_ext/Boolean.h.  The master fake header (fake_R.hpp) includes
// this file; do not include it twice.

#pragma once
#ifndef FAKE_BOOLEAN_H
#define FAKE_BOOLEAN_H

// Remove any pre-existing macro definitions of FALSE and TRUE
// (e.g. from <stdbool.h> or <cstdbool>) so that the enum members
// below become the authoritative definitions, exactly as the real
// R_ext/Boolean.h does.
#undef FALSE
#undef TRUE

// Rboolean: R's two-valued boolean type.
// Enumerators FALSE=0 and TRUE=1 are placed in enclosing (file/global)
// scope, matching the behaviour of the original C definition.
// The underlying type is implicitly int in both C and C++.
typedef enum { FALSE = 0, TRUE = 1 } Rboolean;

#endif // FAKE_BOOLEAN_H
```

- **Arena / Memory Notes:** Not applicable. `Rboolean` is a scalar type; it participates in no allocation or deallocation.

- **Explanation:**

  The fake reproduces the non-`HAVE_ENUM_BASE_TYPE` branch of the real `R_ext/Boolean.h` verbatim. The two `#undef` directives ensure that `FALSE` and `TRUE` are enum enumerators rather than integer macros from `<stdbool.h>`, exactly matching the contract of the real header. The enumerator values `FALSE = 0` and `TRUE = 1` are implicitly convertible to `int` in C++, so the ternary expression `inherits ? findVar(...) : findVarInFrame(...)` in `compat_getVar` compiles without any cast or warning.

  At the call sites (`R_getVar(install("yback"), rho, FALSE)`), the macro `R_getVar` expands to `compat_getVar(sym, rho, FALSE)`, and `FALSE` resolves to the enumerator `(Rboolean)0`. The compiler accepts this without an explicit cast because integer constant `0` is special-cased in C++ as implicitly convertible to any enum type (as an enumerator whose value is zero). This matches the behaviour under the real R headers.

  The original source file is not modified in any way. The fake header is injected through the shadow include tree (see Integration Requirements below), so `#include <R_ext/Boolean.h>` in `rpart_callback.c` (transitively via `R.h`) resolves to `fake_Boolean.hpp` instead of the real system header.

  Note that `compat_getVar` is compiled only when `R_VERSION < R_Version(4, 5, 0)`. In the fake build, `R_VERSION` and `R_Version` must be defined (typically as constants in `fake_Rversion.hpp`) such that this condition evaluates to `1` (true) so that the shim is compiled and the `R_getVar` macro is defined. If `R_VERSION >= R_Version(4, 5, 0)` is faked instead, the native `R_getVar` from `R_ext/Memory.h` would be used, but that function is not available without `libR.so`. The safer approach is to force `R_VERSION` below `4.5.0` in the fake build so that `compat_getVar` is always compiled.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP` / `SEXPREC` (established in `INTSXP.md` and `REALSXP.md`) | The `SEXPREC` struct and `SEXP` typedef are required because `compat_getVar` takes `SEXP sym` and `SEXP rho` parameters and returns `SEXP`. `Rboolean` itself has no dependency on `SEXPREC`, but any translation unit that includes `fake_Boolean.hpp` alongside `fake_Rinternals.hpp` must see `SEXPREC` first. |
| `fake_arena.hpp` | Not required by `Rboolean` directly. Required by the surrounding `.Call` entry points that use `R_alloc` / `ALLOC` scratch memory (see `INTSXP.md` Invariant 2 discussion). Included here for completeness since `rpart_callback.c` is compiled in the same build. |
| `error` / `Rf_error` (not yet generated — requires a `Rf_error.md` or `error.md` guide) | `compat_getVar` calls `error(...)` on the "not found" path. In the fake build, `error` must be aliased to `Rf_error`, which must throw `RError` (Invariant 1). The `Rboolean` type itself does not call `error`; the dependency is at the function level in `rpart_callback.c`. |
| `Rversion.h` / `fake_Rversion.hpp` (not yet generated) | The `#if R_VERSION < R_Version(4, 5, 0)` preprocessor guard that wraps `compat_getVar` — and therefore the only use of `Rboolean` in rpart — depends on `R_VERSION` and `R_Version(major, minor, patch)` being defined. A fake `Rversion.h` must define these constants such that the compatibility shim is compiled (i.e., `R_VERSION` is set to a value less than `R_Version(4, 5, 0)`). Without this, `Rboolean` may never appear in a compiled translation unit. |
