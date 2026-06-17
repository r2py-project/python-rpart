# Fake Header Implementation Guide: `TRUE`

---

### 1. Overview of `TRUE` in R API

`TRUE` is one of the two named enumerator constants of the `Rboolean` enum, defined in `R_ext/Boolean.h` (included transitively by `R.h` and `Rinternals.h`). Its integer value is `1`. The real header always `#undef TRUE` before the enum declaration so that any prior macro definition (e.g., from `<stdbool.h>` or `<cstdbool>`) is replaced by the enumerator. `TRUE` is used wherever R's C API requires a boolean `true` argument — in rpart specifically as a configuration argument to `R_forceSymbols`, which instructs R's dynamic loader to require that callers use the registered symbol table rather than looking up symbols by name at runtime. It is not a macro in the compiled program; it is an enumerator of type `Rboolean` with value `1`.

---

### 2. Contextual Usage Analysis

**Source files and lines examined.**

| File | Line | Context |
|---|---|---|
| `init.c` | 28 | `R_forceSymbols(dll, TRUE);` |

**Full context window (`init.c`, lines 1–30).**

```c
#include "rpart.h"
#include "R_ext/Rdynload.h"
#include "node.h"
#include "rpartproto.h"

SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x);
SEXP rpartexp2(SEXP dtimes, SEXP seps);
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
        SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
        SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2);

static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart", (DL_FUNC) &rpart, 11},
    {"xpred", (DL_FUNC) &xpred, 15},
    {"rpartexp2", (DL_FUNC) &rpartexp2, 2},
    {"pred_rpart", (DL_FUNC) &pred_rpart, 12},
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

`R_forceSymbols` is declared in `R_ext/Rdynload.h` as:

```c
Rboolean R_forceSymbols(DllInfo *info, Rboolean value);
```

`TRUE` is passed as the second argument of type `Rboolean`. The call at line 28 is guarded by `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)`. In the standalone fake build `R_forceSymbols` is a no-op; `TRUE` merely needs to be an integer-compatible constant of type `Rboolean` so the call compiles.

**C types of arguments and return values.**

- In `R_forceSymbols(dll, TRUE)`: `TRUE` is the second argument of declared type `Rboolean`. The function returns `Rboolean` (ignored at the call site).
- `TRUE` is consumed as an integer-valued boolean flag. No arithmetic is performed on it; it is passed opaquely to a no-op stub.

**Co-occurring R API items.**

- `Rboolean` — the enum type of which `TRUE` is a member. Documented in `Rboolean.md`; its fake definition is `typedef enum { FALSE = 0, TRUE = 1 } Rboolean;` in `fake_Boolean.hpp`.
- `FALSE` — the complementary enumerator (`= 0`) used on `init.c:26` with `R_useDynamicSymbols`. Defined in the same enum as `TRUE`. Documented in `FALSE.md`.
- `DllInfo` — the first argument of `R_forceSymbols`. Documented in `DllInfo.md`; faked as `typedef struct DllInfo_fake DllInfo;`.
- `R_registerRoutines`, `R_useDynamicSymbols`, `R_forceSymbols` — no-op registration functions in `fake_Rdynload.hpp` (established by `DllInfo.md`). All three consume `DllInfo *` and `Rboolean` but do nothing in the fake build.
- `R_VERSION`, `R_Version` — preprocessor macros from `<Rversion.h>` that gate the `R_forceSymbols` call. For `TRUE` to be compiled at all, the fake `Rversion.h` must define `R_VERSION` as a value `>= R_Version(2, 16, 0)`.
- `DL_FUNC`, `R_CallMethodDef` — used in the `CallEntries` table in the same translation unit; documented in `DL_FUNC.md` and `R_CallMethodDef.md`.

**Distinct usage patterns.**

There is exactly one usage pattern in the CSV:

1. **No-op registration argument** (`init.c:28`) — `TRUE` is passed to `R_forceSymbols`, a library-initialisation function that is a complete no-op in the standalone fake build. The constant only needs to exist and be of type `Rboolean` so the call expression is well-typed.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`TRUE` is an enumerator constant. It carries no runtime logic, manages no memory, calls no interpreter function, issues no error or warning, and allocates nothing. The entire fake consists of ensuring that `TRUE` is defined as integer value `1` in a form that is type-compatible with `Rboolean`.

**Chosen mechanism.**

The `Rboolean.md` guide establishes the canonical fake definition on the GCC/Linux platform (where `HAVE_ENUM_BASE_TYPE` is not defined, as confirmed by `Rconfig.h`). That definition, already present in `fake_Boolean.hpp`, is:

```cpp
#undef FALSE
#undef TRUE
typedef enum { FALSE = 0, TRUE = 1 } Rboolean;
```

`TRUE` is therefore an enumerator of the `Rboolean` enum with value `1`. This guide for `TRUE` does not introduce a new definition; it documents `TRUE` as a named constant produced as a side effect of the `Rboolean` enum declaration in `fake_Boolean.hpp`. The `FALSE.md` guide established the same pattern for the complementary constant; this guide is entirely symmetric.

The authoritative `R_ext/Boolean.h` (confirmed at `/users/ycai9/.conda/envs/r-to-python/lib/R/include/R_ext/Boolean.h`, lines 32–72) uses:

```c
#undef FALSE
#undef TRUE
/* ... (compiler detection for HAVE_ENUM_BASE_TYPE) ... */
typedef enum { FALSE = 0, TRUE } Rboolean;   // non-HAVE_ENUM_BASE_TYPE branch
```

Note that the original header writes `TRUE` without `= 1` in the enum body; the value is implicitly the successor of `FALSE = 0`, which is `1`. The fake may write `TRUE = 1` explicitly for clarity — both are equivalent.

**Interaction with `<stdbool.h>` and C++ `bool`.**

In C++, `true` (lowercase) is a keyword of type `bool`. The name `TRUE` (uppercase) has no built-in meaning; it is always user- or library-defined. The real `R_ext/Boolean.h` issues `#undef TRUE` before the enum declaration to remove any prior macro definition (e.g., from `<stdbool.h>` which defines `TRUE` as `1` in some C standard library implementations). After `#undef`, the enum member `TRUE = 1` is the only definition visible. This is already handled by the `#undef TRUE` in `fake_Boolean.hpp` established by `Rboolean.md` and cross-referenced by `FALSE.md`.

**`#define` aliases that must be preserved.**

`R_ext/Boolean.h` introduces no `#define` aliases for `TRUE` beyond the `#undef` that removes prior definitions. After the enum declaration, `TRUE` is an enumerator, not a macro. No additional `#define` wrapper is required.

**Preprocessor gate dependency.**

The only usage of `TRUE` in rpart is inside:

```c
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
```

For this line to be compiled, `fake_Rversion.hpp` must define `R_VERSION` as a value satisfying `R_VERSION >= R_Version(2, 16, 0)`. The `DllInfo.md` guide recommends `R_VERSION = R_Version(4, 3, 0)`, which satisfies this condition. The `R_forceSymbols` stub is a no-op, so the call is safe regardless.

**Invariant applicability.**

- Invariant 1 (C++ error/warning style): not triggered by `TRUE` itself. No error or warning mechanism is involved.
- Invariant 2 (arena memory): not triggered. `TRUE` is a scalar constant; no allocation occurs.
- Invariant 3 (R Interpreter Items): not triggered. `R_forceSymbols` is a no-op registration function, not an interpreter item. `TRUE` itself requires no interpreter.

---

### 4. Fake Implementation Examples

#### Pattern: No-op Registration Argument

- **Locations:** `init.c:28`

- **Original R API Usage:**

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

- **C++ Fake Implementation:**

```cpp
// fake_Boolean.hpp
// Drop-in replacement for R_ext/Boolean.h.
// Mirrors the authoritative definition on GCC/Linux platforms where
// HAVE_ENUM_BASE_TYPE is not defined (Rconfig.h line 33).
//
// Established by Rboolean.md; referenced without modification by
// FALSE.md and this guide (TRUE.md).  Do not redefine separately.

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
// FALSE=0 and TRUE=1 are enumerators placed in enclosing (file/global)
// scope, matching the behaviour of the original C definition.
// The underlying type is implicitly int in both C and C++.
typedef enum { FALSE = 0, TRUE = 1 } Rboolean;

#endif // FAKE_BOOLEAN_H


// fake_Rdynload.hpp  (excerpt — the relevant no-op stub for R_forceSymbols)
// R_forceSymbols is a no-op in the standalone build; it exists only to
// let init.c compile.  The full fake_Rdynload.hpp is documented in DllInfo.md.

// Rboolean and DllInfo must already be defined before this point.
// (fake_Boolean.hpp provides Rboolean; DllInfo_fake typedef provides DllInfo.)

static inline Rboolean R_forceSymbols(DllInfo * info, Rboolean value)
{
    (void)info;   // suppress unused-parameter warning
    (void)value;  // TRUE is received here but has no effect
    return FALSE; // real function returns the previous value; FALSE is safe
}
```

- **Arena / Memory Notes:** Not applicable. `TRUE` is a scalar constant; no allocation or deallocation occurs. `R_forceSymbols` does not allocate memory in the real or fake implementation.

- **Explanation:**

  `R_forceSymbols(dll, TRUE)` passes `TRUE` as the `Rboolean value` second parameter. The function's purpose — instructing R's dynamic loader to forbid symbol lookup by name and require use of the registered table — is meaningless in the standalone build because R's dynamic loader is not present. The fake implements `R_forceSymbols` as an `inline` no-op returning `FALSE` (the prior-value semantics of the real function; the return value is discarded at the call site in `init.c`).

  The only requirement on `TRUE` is that it is an integer-compatible constant of type `Rboolean` so the call expression `R_forceSymbols(dll, TRUE)` is well-typed. The enum definition in `fake_Boolean.hpp` satisfies this: `TRUE` is enumerator `1` of `Rboolean`, which is implicitly convertible in a `Rboolean`-typed argument position.

  The `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` guard requires that the fake `Rversion.h` define `R_VERSION` as a value at or above `R_Version(2, 16, 0)` (e.g., `R_Version(4, 3, 0)` as recommended in `DllInfo.md`). Without this, the entire line 28 — the only usage of `TRUE` in rpart — is silently dead code at the preprocessor stage.

  The original `init.c` is not modified in any way. `fake_Boolean.hpp` is injected through the shadow include tree so that `#include "R_ext/Rdynload.h"` (which in the real R headers includes `R_ext/Boolean.h` transitively) resolves to the fake counterparts instead.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `Rboolean.md` | Provides the `typedef enum { FALSE = 0, TRUE = 1 } Rboolean;` declaration in `fake_Boolean.hpp`. `TRUE` is an enumerator of this enum; `fake_Boolean.hpp` must be included before any source file that uses `TRUE`. This guide does not introduce a new header — it reuses `fake_Boolean.hpp` from `Rboolean.md`. Must be compiled first. |
| `FALSE.md` | Establishes that `FALSE` and `TRUE` share the same enum declaration in `fake_Boolean.hpp` and must not be split across separate definitions. The `FALSE.md` guide documents the complete `fake_Boolean.hpp` content; `TRUE.md` is consistent with and depends on that established definition. |
| `DllInfo.md` | Provides `typedef struct DllInfo_fake DllInfo;` and the no-op `R_forceSymbols` stub in `fake_Rdynload.hpp`. `R_forceSymbols(DllInfo *, Rboolean)` is the sole consumer of `TRUE` in rpart; without the `DllInfo` and `R_forceSymbols` fake, the call site at `init.c:28` will not compile. |
| `DL_FUNC.md` and `R_CallMethodDef.md` | Provide `DL_FUNC` typedef and `R_CallMethodDef` struct needed by the `CallEntries` table in the same translation unit (`init.c`). These are included via `fake_Rdynload.hpp`. |
| `R_VERSION.md` / `fake_Rversion.hpp` | Must define `R_VERSION >= R_Version(2, 16, 0)` so that the `#if` guard at `init.c:27` evaluates to true and the `R_forceSymbols(dll, TRUE)` call is actually compiled. If `R_VERSION` is faked below `2.16.0`, `TRUE` is a preprocessor dead branch and is never seen by the C compiler, making the `fake_Boolean.hpp` definition irrelevant for this specific usage. The `DllInfo.md` guide recommends `R_Version(4, 3, 0)`. |
| `SEXP.md` / `INTSXP.md` / `REALSXP.md` | Provide the `SEXPREC` struct and `SEXP` typedef. `init.c` includes `rpart.h` (which brings in `SEXP`) before `R_ext/Rdynload.h`, so `SEXP` must be defined prior to the `DL_FUNC` casts in `CallEntries`. `TRUE` itself has no direct dependency on `SEXP`, but the translation unit does. |
