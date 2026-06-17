# Fake Header Implementation Guide: `R_forceSymbols`

---

### 1. Overview of `R_forceSymbols` in R API

`R_forceSymbols` is a C function declared in `R_ext/Rdynload.h` (line 86) with signature:

```c
Rboolean R_forceSymbols(DllInfo *info, Rboolean value);
```

It is a library-registration function called inside `R_init_<pkg>` — the shared-library constructor that R's dynamic loader invokes when a package is loaded via `dyn.load()`. When called with `value = TRUE`, it instructs R's symbol resolver to forbid ad-hoc name-based symbol lookup (i.e., `.Call("rpart", ...)` where the string `"rpart"` is resolved at call time) and to require instead that callers use the pre-registered table of entry points established by `R_registerRoutines`. Its return value is the previous enforcement state (`Rboolean`), and is typically discarded. In the standalone fake build there is no R dynamic loader, no R symbol table, and `R_init_rpart` is never invoked; consequently `R_forceSymbols` is a complete no-op.

---

### 2. Contextual Usage Analysis

**Source file examined:** `/groups/jli9/Yufei/python-rpart/rpart/src/init.c`, lines 1–30 (entire file).

**Full context window.**

```c
/* init.c — lines 1–30 (complete file) */
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

**Argument and return types at the call site (`init.c:28`).**

| Position | Expression | Declared type |
|---|---|---|
| First argument | `dll` | `DllInfo *` — opaque handle passed from `R_init_rpart`'s parameter |
| Second argument | `TRUE` | `Rboolean` — the enumerator `TRUE = 1` |
| Return value | (discarded) | `Rboolean` — the previous enforcement state; never used |

**Preprocessor gate.** The call is enclosed by:

```c
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
```

This means the call is only compiled when the fake `Rversion.h` defines `R_VERSION` at or above R 2.16.0. As established by `R_VERSION.md`, the fake defines `R_VERSION = R_Version(4, 4, 0) = 263168`, which satisfies the condition.

**Co-occurring R API items.**

- `DllInfo` — the opaque handle type for `dll`. Faked as `typedef struct DllInfo_fake DllInfo; struct DllInfo_fake { int _unused; };` in `fake_Rdynload.hpp` (established by `DllInfo.md`).
- `Rboolean`, `TRUE` — the argument type and value. Faked as `typedef enum { FALSE = 0, TRUE = 1 } Rboolean;` in `fake_Boolean.hpp` (established by `Rboolean.md`; cross-referenced by `TRUE.md`).
- `R_registerRoutines`, `R_useDynamicSymbols` — the two companion registration calls in the same function body. Both are already present as no-op stubs in `fake_Rdynload.hpp`.
- `R_VERSION`, `R_Version` — preprocessor macros that gate whether `R_forceSymbols` is compiled at all. Established by `R_VERSION.md` in `fake_Rversion.hpp`.
- `R_CallMethodDef`, `DL_FUNC` — types used in the `CallEntries` table in the same translation unit. Established by `R_CallMethodDef.md` and `DL_FUNC.md`.

**Distinct usage patterns.**

There is exactly one usage pattern in the rpart source: `R_forceSymbols(dll, TRUE)` as a library-registration call inside `R_init_rpart`, gated by a preprocessor version guard. The return value is discarded. No other call site exists. This single pattern requires one fake strategy: a no-op inline stub with the correct signature.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function** does not apply. **Category: D — Error, Warning, or Print Function** does not apply. **Category: E — R Interpreter Item** does not apply.

**Classification: Category A — Type or Enum Constant** (registration function variant).

`R_forceSymbols` is a registration function whose sole effect is to configure R's dynamic loader — infrastructure that is entirely absent in the standalone fake build. It does not allocate memory, does not throw errors, and does not require interpreter state. Its behaviour is completely captured by doing nothing. The fake is an `inline` no-op stub that accepts the correct argument types, discards both arguments, and returns `FALSE` (a plausible "previous state was not enforced" value matching what the real function would return on first call).

**Chosen mechanism.**

`R_forceSymbols` is already present as a no-op stub in `fake_Rdynload.hpp`, established by `DllInfo.md` (lines 206–210 of that guide's code block) and retained by `R_CallMethodDef.md`. This guide documents the rationale for that stub with precision, confirms its signature against the authoritative header (`R_ext/Rdynload.h` line 86), and establishes it as the canonical entry point for this item.

The authoritative declaration from `R_ext/Rdynload.h` line 86:

```c
Rboolean R_forceSymbols(DllInfo *info, Rboolean value);
```

The fake stub reproduces this signature exactly and adds `(void)` casts to suppress `-Wall -Wextra` unused-parameter warnings.

**Preprocessor gate interaction.**

`R_forceSymbols` is compiled into `init.c` only when `R_VERSION >= R_Version(2, 16, 0)`. The fake `Rversion.h` must define `R_VERSION` such that this condition is true, or the stub will never be reached by the compiler (and an undefined-reference link error would result if somehow the gate were bypassed). As confirmed by `R_VERSION.md`, the fake value `R_Version(4, 4, 0) = 263168` satisfies the condition.

**`#define` aliases that must be preserved.**

`R_ext/Rdynload.h` defines no preprocessor aliases for `R_forceSymbols`. The function name is used directly at the call site. No `#define` aliases are needed in the fake header.

**Invariant applicability.**

- Invariant 1 (C++ error/warning style): not triggered. `R_forceSymbols` does not call `Rf_error`, `Rf_warning`, or any error mechanism.
- Invariant 2 (arena memory): not triggered. `R_forceSymbols` does not allocate or free any memory, heap or arena.
- Invariant 3 (R Interpreter Items): not triggered. `R_forceSymbols` does not require a running R interpreter; it is a loader-configuration function with no interpreter interaction.

**Relationship to existing guides.**

`DllInfo.md` already includes the `R_forceSymbols` no-op stub in `fake_Rdynload.hpp`. `R_CallMethodDef.md` confirms the same stub. `TRUE.md` documents that `TRUE` (the argument value) is defined by `fake_Boolean.hpp`. `R_VERSION.md` confirms the preprocessor gate. The present guide does not introduce a new file; it adds precise documentation for `R_forceSymbols` as a named external item and confirms that the stub already present in `fake_Rdynload.hpp` is correct and complete.

---

### 4. Fake Implementation Examples

#### Pattern: No-op Library Registration Call Gated by Version Preprocessor Guard

- **Locations:** `init.c:28`

- **Original R API Usage:**

```c
/* init.c:22-30 — original */
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
// fake_Rdynload.hpp
// Drop-in replacement for R_ext/Rdynload.h.
// Provides DL_FUNC, R_CallMethodDef, DllInfo, and all registration
// functions as no-ops so that init.c compiles without libR.so.
//
// Compatible with both C and C++ compilation units.
//
// R_forceSymbols stub: confirmed against real declaration at
//   R_ext/Rdynload.h line 86:
//     Rboolean R_forceSymbols(DllInfo *info, Rboolean value);

#pragma once
#ifndef FAKE_R_EXT_RDYNLOAD_H
#define FAKE_R_EXT_RDYNLOAD_H

#include <stddef.h>  /* NULL */

/* -------------------------------------------------------------------------
 * Rboolean — replicated from R_ext/Boolean.h (included by real Rdynload.h)
 * -------------------------------------------------------------------------*/
#ifndef FAKE_R_BOOLEAN_H
#define FAKE_R_BOOLEAN_H
#undef FALSE
#undef TRUE
typedef enum { FALSE = 0, TRUE = 1 } Rboolean;
#endif /* FAKE_R_BOOLEAN_H */

/* -------------------------------------------------------------------------
 * DL_FUNC — generic function pointer
 * Real definition (Rdynload.h line 39):
 *   typedef void * (*DL_FUNC)(void);
 * -------------------------------------------------------------------------*/
typedef void * (*DL_FUNC)(void);

/* -------------------------------------------------------------------------
 * Supporting types
 * -------------------------------------------------------------------------*/
typedef unsigned int R_NativePrimitiveArgType;

#define SINGLESXP 302

typedef struct {
    const char               *name;
    DL_FUNC                   fun;
    int                       numArgs;
    R_NativePrimitiveArgType *types;
} R_CMethodDef;

typedef R_CMethodDef R_FortranMethodDef;

typedef struct {
    const char *name;
    DL_FUNC     fun;
    int         numArgs;
} R_CallMethodDef;

typedef R_CallMethodDef R_ExternalMethodDef;

/* -------------------------------------------------------------------------
 * DllInfo — opaque handle for a loaded shared library.
 * Real declaration (Rdynload.h line 71):
 *   typedef struct _DllInfo DllInfo;
 * C-compatible two-step form required because init.c is compiled as
 * plain C (struct body must have at least one member in C).
 * -------------------------------------------------------------------------*/
typedef struct DllInfo_fake DllInfo;
struct DllInfo_fake { int _unused; };

/* -------------------------------------------------------------------------
 * Registration functions — all no-ops in the standalone build.
 *
 * R_forceSymbols: real declaration at R_ext/Rdynload.h line 86:
 *   Rboolean R_forceSymbols(DllInfo *info, Rboolean value);
 *
 * Purpose in real R: when value == TRUE, instructs R's dynamic loader to
 * reject ad-hoc name-based .Call("symbol") lookups and require callers to
 * use the pre-registered table set up by R_registerRoutines.
 *
 * In the standalone fake build: R's dynamic loader is absent; R_init_rpart
 * is never invoked by a loader; the function has nothing to configure.
 * The stub accepts both arguments, discards them via (void) casts, and
 * returns FALSE (representing "symbol forcing was previously not active"),
 * which matches the plausible first-call return value of the real function.
 * The return value is discarded at the call site in init.c.
 *
 * The call site is guarded by:
 *   #if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
 * With fake_Rversion.hpp defining R_VERSION = R_Version(4, 4, 0) = 263168,
 * the condition is 263168 >= 131584 = true, so the stub is compiled and
 * must be present to avoid an undefined-reference link error.
 * -------------------------------------------------------------------------*/
#ifdef __cplusplus
extern "C" {
#endif

static inline int R_registerRoutines(
        DllInfo * info,
        const R_CMethodDef        * const croutines,
        const R_CallMethodDef     * const callRoutines,
        const R_FortranMethodDef  * const fortranRoutines,
        const R_ExternalMethodDef * const externalRoutines)
{
    (void)info; (void)croutines; (void)callRoutines;
    (void)fortranRoutines; (void)externalRoutines;
    return 1;   /* real function returns 1 on success */
}

static inline Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value)
{
    (void)info; (void)value;
    return FALSE;
}

/* R_forceSymbols — primary subject of this guide.
 * Signature matches R_ext/Rdynload.h line 86 exactly.
 * Returns FALSE (prior state: not enforced) which is safe because
 * the return value is discarded at init.c:28.                        */
static inline Rboolean R_forceSymbols(DllInfo *info, Rboolean value)
{
    (void)info;   /* DllInfo * — opaque, never dereferenced */
    (void)value;  /* TRUE received here; has no effect in fake build  */
    return FALSE;
}

/* Not API — stubs for completeness */
static inline DllInfo *R_getDllInfo(const char *name)
{
    (void)name;
    return (DllInfo *)0;
}
static inline DllInfo *R_getEmbeddingDllInfo(void)
{
    return (DllInfo *)0;
}

/* Cross-package callable registration — not used by rpart */
static inline void R_RegisterCCallable(const char *pkg,
                                       const char *name,
                                       DL_FUNC     fptr)
{
    (void)pkg; (void)name; (void)fptr;
}
static inline DL_FUNC R_GetCCallable(const char *pkg, const char *name)
{
    (void)pkg; (void)name;
    return (DL_FUNC)0;
}

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* FAKE_R_EXT_RDYNLOAD_H */
```

- **Arena / Memory Notes:** Not applicable. `R_forceSymbols` neither allocates nor frees any memory. The `DllInfo *` pointer is passed opaquely without any arena or heap interaction. No `ArenaFrame` guard is relevant to this item or to any code in `init.c`.

- **Explanation:**

  The call `R_forceSymbols(dll, TRUE)` at `init.c:28` becomes reachable at the compilation stage only when the preprocessor evaluates `defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` as true. With `fake_Rversion.hpp` providing `R_VERSION = R_Version(4, 4, 0) = 263168` and `R_Version(2, 16, 0) = 131584`, the condition is `263168 >= 131584`, which is true. The compiler therefore includes the call in the translation unit.

  Because the stub `R_forceSymbols` is declared `static inline` in `fake_Rdynload.hpp`, the compiler resolves the call directly to the no-op body and optimises it away entirely. No external symbol lookup occurs at link time and `libR.so` is not needed.

  The `(void)info;` and `(void)value;` casts suppress `-Wall -Wextra` unused-parameter warnings without modifying `init.c`. The `static inline` qualifier prevents multiple-definition errors when `fake_Rdynload.hpp` is included by more than one translation unit.

  `R_init_rpart` is the R shared-library constructor invoked by R's `dyn.load()` mechanism. In the standalone Python build, `dyn.load()` is never called, so `R_init_rpart` — including its `R_forceSymbols` call — is dead code at runtime. The function still compiles and its symbol is present in the shared object, which is harmless.

  The original `init.c` is not modified in any way. `fake_Rdynload.hpp` is injected through the shadow include tree so that `#include "R_ext/Rdynload.h"` at `init.c:2` resolves to the fake header instead of the real one.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `DllInfo.md` / `fake_Rdynload.hpp` | Provides `typedef struct DllInfo_fake DllInfo; struct DllInfo_fake { int _unused; };`. `R_forceSymbols` takes `DllInfo *` as its first argument; `DllInfo` must be defined before the stub appears. `DllInfo.md` established the C-compatible two-step form and the containing header `fake_Rdynload.hpp`. The `R_forceSymbols` stub is defined in that same file; this guide documents it as a named external item and confirms the existing stub is correct. |
| `Rboolean.md` / `FALSE.md` / `TRUE.md` / `fake_Boolean.hpp` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean;`. `R_forceSymbols` returns `Rboolean` and takes `Rboolean value` as its second argument; `Rboolean` must be defined before the stub's signature can be resolved. `fake_Rdynload.hpp` self-contains this definition under the `FAKE_R_BOOLEAN_H` guard at the top of the file, mirroring the real `Rdynload.h` which includes `R_ext/Boolean.h` at line 35. |
| `R_VERSION.md` / `fake_Rversion.hpp` | Provides `#define R_VERSION R_Version(4, 4, 0)` and `#define R_Version(v,p,s) (((v)*65536)+((p)*256)+(s))`. The preprocessor gate `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` at `init.c:27` must evaluate to true for the `R_forceSymbols` call to be compiled into the translation unit. With `R_Version(4, 4, 0) = 263168 >= R_Version(2, 16, 0) = 131584`, the condition is satisfied. Without this, `R_forceSymbols` is a preprocessor dead branch and the stub is irrelevant for `init.c`. |
| `DL_FUNC.md` / `R_CallMethodDef.md` | Provide `typedef void * (*DL_FUNC)(void)` and the `R_CallMethodDef` struct. These are defined earlier in `fake_Rdynload.hpp` and must appear before `R_forceSymbols` in the same header. The `R_registerRoutines` companion stub takes `const R_CallMethodDef * const` as a parameter; `R_CallMethodDef` must therefore be defined before `R_registerRoutines`, which in turn must precede `R_forceSymbols` in the file. |
| `SEXP.md` / `Rinternals.h` fake | Provides the `SEXPREC` struct and `SEXP` typedef. `init.c` includes `rpart.h` (line 1) before `R_ext/Rdynload.h` (line 2), so `SEXP` is already in scope when `fake_Rdynload.hpp` is processed. The `DL_FUNC` casts in `CallEntries[]` reference `SEXP`-typed concrete function pointers; `SEXP` must be defined in the same translation unit. `R_forceSymbols` itself does not reference `SEXP`, but it is compiled in the same translation unit that does. |
