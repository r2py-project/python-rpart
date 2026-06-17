# Fake Header Implementation Guide: `R_useDynamicSymbols`

---

### 1. Overview of `R_useDynamicSymbols` in R API

`R_useDynamicSymbols` is a C function declared in `R_ext/Rdynload.h` (line 85) with signature:

```c
Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value);
```

It is a library-registration function called inside `R_init_<pkg>` — the shared-library constructor that R's dynamic loader invokes when a package is loaded via `dyn.load()`. When called with `value = FALSE`, it instructs R's symbol resolver to forbid ad-hoc name-based symbol lookup (i.e., `.Call("rpart", ...)` where the string `"rpart"` is resolved dynamically at call time from the package's full exported symbol table). Paired with `R_forceSymbols(dll, TRUE)`, this enforces that all entry points must have been pre-registered via `R_registerRoutines`. The function returns the previous dynamic-lookup state (`Rboolean`), which is typically discarded. In the standalone fake build there is no R dynamic loader, no R symbol table, and `R_init_rpart` is never invoked; consequently `R_useDynamicSymbols` is a complete no-op.

---

### 2. Contextual Usage Analysis

**Source file examined:** `/groups/jli9/Yufei/python-rpart/rpart/src/init.c`, lines 1–30 (entire file).

**Full context window.**

```c
/* init.c — complete file */
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
    R_useDynamicSymbols(dll, FALSE);        /* <-- subject of this guide */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

**Argument and return types at the call site (`init.c:26`).**

| Position | Expression | Declared type |
|---|---|---|
| First argument | `dll` | `DllInfo *` — opaque handle passed from `R_init_rpart`'s parameter |
| Second argument | `FALSE` | `Rboolean` — the enumerator `FALSE = 0` |
| Return value | (discarded) | `Rboolean` — the previous dynamic-symbol-lookup state; never used |

**Co-occurring R API items.**

- `DllInfo` — the opaque handle type for `dll`. Faked as `typedef struct DllInfo_fake DllInfo; struct DllInfo_fake { int _unused; };` in `fake_Rdynload.hpp` (established by `DllInfo.md`).
- `Rboolean`, `FALSE` — the argument type and value. Faked as `typedef enum { FALSE = 0, TRUE = 1 } Rboolean;` in `fake_Boolean.hpp` (established by `Rboolean.md` and `FALSE.md`).
- `R_registerRoutines` — the preceding companion registration call in the same function body (`init.c:25`). Already a no-op stub in `fake_Rdynload.hpp` (established by `R_registerRoutines.md`).
- `R_forceSymbols` — the following companion registration call in the same function body (`init.c:28`), gated by a version guard. Already a no-op stub in `fake_Rdynload.hpp` (established by `R_forceSymbols.md`).
- `R_VERSION`, `R_Version` — preprocessor macros from `<Rversion.h>` that gate whether `R_forceSymbols` is compiled. Established by `R_VERSION.md` in `fake_Rversion.hpp`.
- `R_CallMethodDef`, `DL_FUNC` — types used in the `CallEntries` table in the same translation unit (`init.c:12–19`).
- `SEXP` — the concrete parameter and return type of every function pointer in `CallEntries`. In scope from `rpart.h` (included at `init.c:1`) before `R_ext/Rdynload.h` is included at `init.c:2`.

**Distinct usage patterns.**

There is exactly one usage pattern in the rpart source: `R_useDynamicSymbols(dll, FALSE)` as the second library-registration call inside `R_init_rpart`, immediately after `R_registerRoutines` and before the version-gated `R_forceSymbols`. The return value is discarded. No other call site exists in the rpart source tree. This single pattern requires one fake strategy: a no-op `static inline` stub with the correct two-argument signature that returns `FALSE` to represent the prior state "dynamic lookup was previously permitted."

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant** (registration function variant).

`R_useDynamicSymbols` is a loader-configuration function whose sole effect is to toggle a flag inside R's dynamic linker — infrastructure that is entirely absent in the standalone fake build. It does not allocate memory, does not throw errors, and does not require interpreter state. Its entire observable behaviour is captured by doing nothing.

**Chosen mechanism.**

`R_useDynamicSymbols` is already present as a no-op stub in `fake_Rdynload.hpp`, which was established by `DL_FUNC.md`, refined by `DllInfo.md`, and cross-referenced by `R_registerRoutines.md`, `R_forceSymbols.md`, and `FALSE.md`. This guide documents the rationale for that stub with precision, confirms its two-argument signature against the authoritative header (`R_ext/Rdynload.h` line 85), and establishes it as the canonical entry point for this named external item.

The authoritative declaration from `R_ext/Rdynload.h` line 85:

```c
Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value);
```

The fake stub reproduces this signature exactly, discards both arguments via `(void)` casts to suppress `-Wall -Wextra` unused-parameter warnings, and returns `FALSE` (value `0`). Returning `FALSE` is the most accurate plausible value: it represents "dynamic lookup was previously not restricted," which is what the first call to `R_useDynamicSymbols` would return in a freshly loaded real package.

**Why the return value is `FALSE`.**

The real `R_useDynamicSymbols` returns the previous value of the dynamic-lookup flag for the `DllInfo`. On a freshly loaded library, the default is `TRUE` (dynamic lookup enabled), so the first call `R_useDynamicSymbols(dll, FALSE)` would return `TRUE`. However, the rpart call site at `init.c:26` discards the return value entirely, so any `Rboolean` return is correct. `FALSE` (value `0`) is chosen for consistency with the companion stubs `R_forceSymbols` and the convention adopted in `fake_Rdynload.hpp` by the pre-existing guides.

**Position of `R_useDynamicSymbols` within `fake_Rdynload.hpp`.**

`R_useDynamicSymbols` depends on two types being defined before its signature can be parsed: `DllInfo` and `Rboolean`. Within `fake_Rdynload.hpp`, the required declaration order is:

1. `Rboolean` enum (from `R_ext/Boolean.h` inline block)
2. `DL_FUNC` typedef
3. `R_NativePrimitiveArgType` typedef
4. `R_CMethodDef` struct and `R_FortranMethodDef` typedef
5. `R_CallMethodDef` struct and `R_ExternalMethodDef` typedef
6. `DllInfo` typedef + struct (C-compatible two-step form)
7. `R_registerRoutines` stub (depends on 1–6)
8. **`R_useDynamicSymbols` stub** (depends on 1–6; positioned after `R_registerRoutines` to mirror the call order in `R_init_rpart`)
9. `R_forceSymbols` stub

This ordering is established by the prior guides and must not be changed.

**`#define` aliases that must be preserved.**

`R_ext/Rdynload.h` defines no preprocessor aliases for `R_useDynamicSymbols`. The function name is used directly at the call site. No `#define` aliases are needed in the fake header.

**Invariant applicability.**

- Invariant 1 (C++ error/warning style): not triggered. `R_useDynamicSymbols` does not call `Rf_error`, `Rf_warning`, or any error mechanism in either the real or fake implementation.
- Invariant 2 (arena memory): not triggered. `R_useDynamicSymbols` does not allocate or free any memory, heap or arena.
- Invariant 3 (R Interpreter Items): not triggered. `R_useDynamicSymbols` does not require a running R interpreter; it is a dynamic-loader configuration function with no interpreter interaction.

**Relationship to existing guides.**

`DllInfo.md` (lines 200–204 of the code block) already contains the `R_useDynamicSymbols` no-op stub in `fake_Rdynload.hpp`. `R_CallMethodDef.md`, `R_registerRoutines.md`, `R_forceSymbols.md`, and `FALSE.md` all reproduce and confirm that stub. The present guide does not introduce a new file; it documents `R_useDynamicSymbols` as a named external item in its own right, confirms the existing stub is correct and complete, and provides the precise rationale for each design decision.

---

### 4. Fake Implementation Examples

#### Pattern: No-Op Library Registration Call Disabling Dynamic Symbol Lookup

- **Locations:** `init.c:26`

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

The stub for `R_useDynamicSymbols` lives in `fake_Rdynload.hpp`, which is the drop-in replacement for `R_ext/Rdynload.h`. The complete canonical header is reproduced below; `R_useDynamicSymbols` is the primary subject.

```cpp
// fake_Rdynload.hpp
// Drop-in replacement for R_ext/Rdynload.h.
// Provides DL_FUNC, R_CallMethodDef, DllInfo, and all registration
// functions as no-ops so that init.c compiles without libR.so.
//
// Compatible with both C and C++ compilation units.
//
// R_useDynamicSymbols stub: confirmed against real declaration at
//   R_ext/Rdynload.h line 85:
//     Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value);

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

/* -------------------------------------------------------------------------
 * R_CallMethodDef
 * Real definition (Rdynload.h lines 62-66):
 *   typedef struct { const char *name; DL_FUNC fun; int numArgs; } R_CallMethodDef;
 * Three-field layout must match exactly so that CallEntries[] compound
 * initialisers compile without change.
 * -------------------------------------------------------------------------*/
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
 * In the real libR.so these functions configure R's dynamic loader:
 *   R_registerRoutines   — populates R's internal symbol table
 *   R_useDynamicSymbols  — controls whether .Call("name") dynamic lookup
 *                          is permitted (FALSE disables it)
 *   R_forceSymbols       — requires callers to use the pre-registered table
 *
 * In the standalone fake build:
 *   - R's dynamic loader is absent; R_init_rpart is never invoked.
 *   - All three functions are dead code at runtime.
 *   - They exist solely to satisfy the linker and allow init.c to compile
 *     and link without modification.
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
    (void)info;
    (void)croutines;
    (void)callRoutines;
    (void)fortranRoutines;
    (void)externalRoutines;
    return 1;   /* real function returns 1 on success */
}

/* R_useDynamicSymbols — primary subject of this guide.
 *
 * Signature confirmed against R_ext/Rdynload.h line 85:
 *   Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value);
 *
 * Purpose in real R: when value == FALSE, disables the ability to call
 * package C functions via .Call("symbol_name_string") dynamic lookup.
 * Only pre-registered entry points (registered by R_registerRoutines)
 * remain callable.  This is a security/robustness measure.
 *
 * In the standalone fake build: R's dynamic loader is absent; there is
 * no symbol table to configure.  The function has nothing to do.
 * The stub accepts both arguments, discards them via (void) casts, and
 * returns FALSE (representing "dynamic lookup was previously not
 * restricted").  The return value is discarded at init.c:26.
 *
 * (void) casts suppress -Wall -Wextra unused-parameter warnings without
 * requiring any modification to init.c.                                 */
static inline Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value)
{
    (void)info;   /* DllInfo * — opaque, never dereferenced */
    (void)value;  /* FALSE received here; has no effect in fake build    */
    return FALSE;
}

/* R_forceSymbols — companion call at init.c:28, gated by R_VERSION.
 * Signature confirmed against R_ext/Rdynload.h line 86:
 *   Rboolean R_forceSymbols(DllInfo *info, Rboolean value);
 * No-op in the fake build.  See R_forceSymbols.md for full rationale.  */
static inline Rboolean R_forceSymbols(DllInfo *info, Rboolean value)
{
    (void)info;
    (void)value;
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

- **Arena / Memory Notes:** Not applicable. `R_useDynamicSymbols` neither allocates nor frees any memory. The `DllInfo *` pointer is passed opaquely and immediately discarded. No `ArenaFrame` guard is relevant to `R_useDynamicSymbols` or to any code path in `init.c`.

- **Explanation:**

  The sole mechanical change required to compile `init.c` without `libR.so` is to place `fake_Rdynload.hpp` on the compiler include path such that `#include "R_ext/Rdynload.h"` at `init.c:2` resolves to the fake header. The standard approach is to create a shadow include directory (e.g., `fake_include/`) containing a subdirectory `R_ext/` with a file named `Rdynload.h` whose content is, or `#include`s, `fake_Rdynload.hpp`. Adding `-I fake_include/` before the real R include path on the compiler command line causes the fake to shadow the real header.

  `R_useDynamicSymbols` is declared `static inline` in `fake_Rdynload.hpp`. The compiler resolves the call at `init.c:26` directly to the no-op body and optimises it away entirely. No external symbol reference is emitted and `libR.so` is not needed at link time for this symbol.

  `R_init_rpart` is the R shared-library constructor invoked by R's `dyn.load()` mechanism. In the standalone Python build, `dyn.load()` is never called. Consequently `R_init_rpart` — including its `R_useDynamicSymbols(dll, FALSE)` call — is dead code at runtime. The function still compiles and its symbol is present in the shared object, which is harmless. Python calls the five rpart entry points directly by their C function symbols (e.g., `lib.rpart(...)` via ctypes), bypassing R's loader and symbol table entirely. The dynamic-lookup restriction that `R_useDynamicSymbols(dll, FALSE)` would have enforced in a live R process is therefore irrelevant to the standalone build.

  The `(void)info;` and `(void)value;` casts inside the stub suppress `-Wall -Wextra` unused-parameter warnings without requiring any modification to `init.c`. The `static inline` qualifier prevents multiple-definition link errors when `fake_Rdynload.hpp` is included by more than one translation unit in the same link step.

  The `R_useDynamicSymbols` call is not guarded by any preprocessor version condition (unlike `R_forceSymbols` at `init.c:28`). It is always compiled. The stub must therefore always be present in `fake_Rdynload.hpp`; it cannot be conditionally omitted based on any version value in `fake_Rversion.hpp`.

  The original `init.c` is not modified in any way.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `DllInfo.md` / `fake_Rdynload.hpp` | Provides `typedef struct DllInfo_fake DllInfo; struct DllInfo_fake { int _unused; };`. `R_useDynamicSymbols` takes `DllInfo *` as its first argument; `DllInfo` must be defined before the stub's signature can be parsed. `DllInfo.md` established the C-compatible two-step form required because `init.c` is compiled as plain C. The `R_useDynamicSymbols` stub is already present in `fake_Rdynload.hpp` as established by that guide; the present guide confirms the stub and documents it as a named item. |
| `Rboolean.md` / `FALSE.md` / `fake_Boolean.hpp` | Provides `typedef enum { FALSE = 0, TRUE = 1 } Rboolean;`. `R_useDynamicSymbols` returns `Rboolean` and takes `Rboolean value` as its second argument; `Rboolean` must be defined before the stub's signature can be resolved. `fake_Rdynload.hpp` self-contains this definition under the `FAKE_R_BOOLEAN_H` guard at the top of the file, mirroring the real `Rdynload.h` which includes `R_ext/Boolean.h` at line 35. |
| `R_registerRoutines.md` / `fake_Rdynload.hpp` | The `R_registerRoutines` stub must appear before `R_useDynamicSymbols` in `fake_Rdynload.hpp` (both to mirror the call order in `R_init_rpart` and because `R_registerRoutines` depends on the supporting structs `R_CMethodDef`, `R_CallMethodDef`, and `DllInfo` that are defined earlier in the same file). The ordering constraint established by `R_registerRoutines.md` must be respected. |
| `R_forceSymbols.md` / `fake_Rdynload.hpp` | The `R_forceSymbols` stub must appear after `R_useDynamicSymbols` in `fake_Rdynload.hpp`. Both stubs share the same two-argument `(DllInfo *, Rboolean)` signature; their relative order within the file is a stylistic choice that mirrors the order of calls in `R_init_rpart`. |
| `DL_FUNC.md` / `R_CallMethodDef.md` | Provide `typedef void * (*DL_FUNC)(void)` and the `R_CallMethodDef` struct. These must appear before `R_registerRoutines` (and therefore before `R_useDynamicSymbols`) in `fake_Rdynload.hpp` because `R_registerRoutines`'s signature references them. |
| `R_VERSION.md` / `fake_Rversion.hpp` | Provides `#define R_VERSION R_Version(4, 4, 0)` and the `R_Version(v,p,s)` macro. This is required so that the `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` gate at `init.c:27` evaluates to true and `R_forceSymbols` (the stub that follows `R_useDynamicSymbols` in `fake_Rdynload.hpp`) is compiled. Without `fake_Rversion.hpp`, the gate defaults to false and `R_forceSymbols` becomes a preprocessor dead branch — the stub would be unused but must still be present to avoid a link error if the gate were ever enabled. `R_useDynamicSymbols` itself is not gated and does not require `fake_Rversion.hpp` directly. |
| `SEXP.md` / `Rinternals.h` fake | Provides the `SEXPREC` struct and `SEXP` typedef. `init.c` includes `rpart.h` at line 1 (before `R_ext/Rdynload.h` at line 2), so `SEXP` is already in scope when `fake_Rdynload.hpp` is processed. `R_useDynamicSymbols` itself does not reference `SEXP` in its own signature, but the `DL_FUNC` casts in the `CallEntries` array in the same translation unit do. |
