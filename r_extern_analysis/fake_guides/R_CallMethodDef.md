# Fake Header Implementation Guide: `R_CallMethodDef`

---

### 1. Overview of `R_CallMethodDef` in R API

`R_CallMethodDef` is a C struct defined in `R_ext/Rdynload.h` (line 62–66) that describes a single `.Call`-callable entry point in a compiled R package. Each instance holds three fields: a string name (the R-visible symbol), a `DL_FUNC` generic function pointer (the address of the C function), and an integer argument count. Package authors build a NULL-sentinel-terminated static array of `R_CallMethodDef` and pass it to `R_registerRoutines` inside the library initialiser `R_init_<pkg>` so that R's dynamic loader can resolve `.Call("name", ...)` to the correct C function at runtime. `R_CallMethodDef` is a pure data-layout type: it carries no behaviour and requires no interpreter state.

---

### 2. Contextual Usage Analysis

**Source file examined:** `/groups/jli9/Yufei/python-rpart/rpart/src/init.c`, lines 1–30 (entire file).

**Argument and return types observed.**

`R_CallMethodDef` appears exclusively as the element type of the `static const` array `CallEntries` declared at line 12. Each of the five non-sentinel entries is a compound literal of the form:

```c
{"symbol_name", (DL_FUNC) &c_function, numArgs}
```

where the three fields map to:
- `const char *name` — string literal (e.g., `"rpart"`, `"xpred"`).
- `DL_FUNC fun` — address of a concrete SEXP-typed function cast to the generic function pointer type `void *(*)(void)`. The five functions and their argument counts are: `init_rpcallback` (5), `rpart` (11), `xpred` (15), `rpartexp2` (2), `pred_rpart` (12).
- `int numArgs` — the number of `SEXP` arguments the function expects at the `.Call` boundary.

The sentinel element `{NULL, NULL, 0}` terminates the array. This requires `DL_FUNC` to be a pointer type (so that `NULL` is a valid initialiser for the `fun` field), which the typedef `void *(*DL_FUNC)(void)` satisfies.

**Co-occurring R API items.**

- `DL_FUNC` — the `fun` field type inside `R_CallMethodDef`; already faked in `DL_FUNC.md` as `typedef void * (*DL_FUNC)(void)`.
- `DllInfo` — the opaque handle parameter of `R_registerRoutines`; already faked in `DllInfo.md` as `typedef struct DllInfo_fake DllInfo; struct DllInfo_fake { int _unused; };`.
- `R_registerRoutines` — the function that receives the `CallEntries` array as its third argument; declared and faked as a no-op in `fake_Rdynload.hpp` (established by `DL_FUNC.md` and refined by `DllInfo.md`).
- `R_useDynamicSymbols`, `R_forceSymbols` — companion registration functions also faked as no-ops in `fake_Rdynload.hpp`.
- `Rboolean`, `FALSE`, `TRUE` — used as arguments to `R_useDynamicSymbols` and `R_forceSymbols`; faked as `typedef enum { FALSE = 0, TRUE = 1 } Rboolean;` in `fake_Rdynload.hpp`.
- `SEXP` — the concrete parameter and return type of every function pointer registered via `R_CallMethodDef`. Required before `init.c` compiles; provided by the `SEXP` fake guide via `rpart.h` → `Rinternals.h` include chain.

**Distinct usage patterns.**

There is exactly one usage pattern across the entire rpart source: constructing a NULL-terminated `static const R_CallMethodDef[]` array of `.Call` entry-point descriptors and passing it to `R_registerRoutines`. All six array elements (five function entries plus the NULL sentinel) are structurally identical compound initialisers and require the same fake strategy.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`R_CallMethodDef` is a plain data struct. The fake reproduces the three-field layout from the real `Rdynload.h` (lines 62–66) verbatim:

```c
typedef struct {
    const char *name;
    DL_FUNC     fun;
    int         numArgs;
} R_CallMethodDef;
```

This definition is already present in the `fake_Rdynload.hpp` header established by `DL_FUNC.md` (line 143–147 of that guide's code block) and retained verbatim in the revised version from `DllInfo.md` (lines 150–154 of that guide's code block). The present guide adds the precise rationale and integration notes that were absent from those earlier treatments.

**Fake mechanism and why it satisfies the invariants.**

Because `R_CallMethodDef` is a pure data type:

- The struct definition compiles in both C and C++ without modification.
- The compound initialisers in `init.c` (`{"name", (DL_FUNC) &fn, n}`) compile unchanged because the three field types (`const char *`, `DL_FUNC`, `int`) are exactly preserved.
- The NULL sentinel `{NULL, NULL, 0}` compiles correctly because `DL_FUNC` is `void *(*)(void)` — a pointer type for which `NULL` is a valid initialiser in C99 and C++11.
- `R_registerRoutines` is a no-op; it receives the `CallEntries` pointer but does nothing with it. No R symbol table exists in the standalone build, so the registration data is never needed at runtime.
- `R_init_rpart` (the function that constructs and passes `CallEntries`) is the R shared-library constructor invoked by R's `dyn.load()` mechanism. In the standalone Python build, `dyn.load()` is never called, so `R_init_rpart` is dead code at runtime. It still compiles and links; its symbol is simply unreachable.

**Invariant applicability.**

- Invariant 1 (error/warning style): not triggered. `R_CallMethodDef` and the registration functions produce no errors or warnings.
- Invariant 2 (arena memory): not triggered. The `CallEntries` array is `static const` on the program's data segment. No heap or arena allocation is involved anywhere in `init.c`.
- Invariant 3 (interpreter items): not triggered. `R_CallMethodDef` does not require a running R interpreter; it is a passive data struct.

**`#define` aliases that must be preserved.**

`Rdynload.h` defines no preprocessor aliases for `R_CallMethodDef` itself. The aliases `FALSE` and `TRUE` (from `R_ext/Boolean.h`, included by `Rdynload.h`) are already replicated in `fake_Rdynload.hpp`. No additional aliases are required for `R_CallMethodDef`.

**Relationship to existing guides.**

The `DL_FUNC.md` guide established `fake_Rdynload.hpp` and already contains the `R_CallMethodDef` struct definition. The `DllInfo.md` guide refined that header with a C-compatible `DllInfo` typedef and `extern "C"` guards. The present guide does not introduce a new file; it documents the rationale for `R_CallMethodDef` specifically and confirms that the definition already present in `fake_Rdynload.hpp` is correct and complete.

---

### 4. Fake Implementation Examples

#### Pattern: NULL-terminated static array of `.Call` entry-point descriptors

- **Locations:** `init.c:12` (the array declaration spanning lines 12–19, covering all five function entries at lines 13–17 and the NULL sentinel at line 18)

- **Original R API Usage:**

```c
/* init.c — lines 1–30, original */
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

- **C++ Fake Implementation:**

The definition of `R_CallMethodDef` lives in `fake_Rdynload.hpp`, which was established by `DL_FUNC.md` and refined by `DllInfo.md`. The struct definition to include in that header is reproduced below for completeness, alongside all companion declarations that must be present for `init.c` to compile:

```cpp
// fake_Rdynload.hpp
// Drop-in replacement for R_ext/Rdynload.h.
// Provides DL_FUNC, R_CallMethodDef, DllInfo, and all registration
// functions as no-ops so that init.c compiles without libR.so.
//
// Compatible with both C and C++ compilation units.

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
 * DL_FUNC
 * Real definition (Rdynload.h line 39):
 *   typedef void * (*DL_FUNC)(void);
 * Reproduced verbatim.  The cast (DL_FUNC) &some_sexp_function is valid in
 * C99 and C++11 even though the concrete type differs; the pointer is never
 * called through DL_FUNC in the standalone build.
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
 *   typedef struct {
 *       const char *name;
 *       DL_FUNC     fun;
 *       int         numArgs;
 *   } R_CallMethodDef;
 *
 * Reproduced verbatim.  Three-field layout matches exactly:
 *   - name    : const char *   — R-visible symbol string
 *   - fun     : DL_FUNC        — generic function pointer; NULL is valid
 *                                because DL_FUNC is a pointer type
 *   - numArgs : int            — expected SEXP argument count at .Call boundary
 *
 * The NULL sentinel {NULL, NULL, 0} at the end of CallEntries[] compiles
 * correctly because NULL is a valid initialiser for both const char * and
 * DL_FUNC (which is void *(*)(void), a pointer type).
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
 * The internal layout of struct _DllInfo is private to libR.so.
 * Package code only holds and forwards the pointer; it never dereferences it.
 *
 * C-compatible two-step form required because init.c is compiled as plain C:
 * in C, a struct body must contain at least one member.
 * -------------------------------------------------------------------------*/
typedef struct DllInfo_fake DllInfo;
struct DllInfo_fake { int _unused; };

/* -------------------------------------------------------------------------
 * Registration functions — all no-ops in the standalone build.
 * In the real libR.so these populate R's internal symbol table so that
 * .Call("rpart", ...) resolves to the C function rpart().  In the standalone
 * build there is no symbol table; these functions exist solely to let init.c
 * compile and link without modification.
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

static inline Rboolean R_forceSymbols(DllInfo *info, Rboolean value)
{
    (void)info; (void)value;
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

- **Arena / Memory Notes:** Not applicable. `R_CallMethodDef` and the `CallEntries` array are `static const` on the program's data segment. The registration functions are no-ops that do not allocate any heap or arena memory. No `ArenaFrame` guard is needed anywhere in `init.c`.

- **Explanation:**

  The sole mechanical change required to compile `init.c` without `libR.so` is to place `fake_Rdynload.hpp` on the compiler include path such that `#include "R_ext/Rdynload.h"` resolves to it. The standard approach is to create a shadow include directory (e.g., `fake_include/`) containing a subdirectory `R_ext/` with a file named `Rdynload.h` whose content is `fake_Rdynload.hpp`. Adding `-I fake_include/` before the real R include path on the compiler command line causes the fake to shadow the real header.

  The struct layout of `R_CallMethodDef` is reproduced from `Rdynload.h` lines 62–66 without change. All compound initialisers in `CallEntries[]` — including the NULL sentinel `{NULL, NULL, 0}` — compile without modification because:
  1. `DL_FUNC` is `void *(*)(void)`, a pointer type, so `NULL` is a valid `fun` initialiser.
  2. `const char *` also accepts `NULL` as a `name` initialiser.
  3. `0` is a valid `int` initialiser for `numArgs`.

  The cross-function-pointer cast `(DL_FUNC) &rpart` is valid under both C99 §6.3.2.3 and C++11 [expr.reinterpret.cast] as long as the pointer is not called through the mismatched type. In the standalone build, `R_registerRoutines` is a no-op and `R_init_rpart` is dead code, so no call ever occurs through a `DL_FUNC` value.

  The `(void)param;` casts in each registration function suppress `-Wall -Wextra` unused-parameter warnings without requiring any modification to `init.c`.

  The `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` preprocessor guard at `init.c` line 27 requires `<Rversion.h>` to be faked with appropriate `R_VERSION` and `R_Version` definitions. Because `R_forceSymbols` is a no-op in the fake, any version value is safe; setting `R_VERSION` to encode version 4.3.0 is recommended so that the `R_forceSymbols` call site is active (and then silently discarded).

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `DL_FUNC.md` / `fake_Rdynload.hpp` | `DL_FUNC` typedef (`typedef void * (*DL_FUNC)(void)`) must be defined before `R_CallMethodDef` because the `fun` field of `R_CallMethodDef` has type `DL_FUNC`. `fake_Rdynload.hpp` already defines both in the correct order; the present guide does not add a new file but confirms the ordering within that header. |
| `DllInfo.md` / `fake_Rdynload.hpp` | `DllInfo` typedef must be defined before `R_registerRoutines` (which takes `DllInfo *`). `DllInfo.md` established the C-compatible two-step form `typedef struct DllInfo_fake DllInfo; struct DllInfo_fake { int _unused; };`. The `R_CallMethodDef` definition must appear after `DL_FUNC` and before or alongside `DllInfo` in `fake_Rdynload.hpp`; the order given in this guide's code block is correct. |
| `Rboolean` / `R_ext/Boolean.h` fake | `Rboolean` enum must be defined before `R_useDynamicSymbols` and `R_forceSymbols` (both of which use `Rboolean` in their signatures). `fake_Rdynload.hpp` self-contains this definition under the `FAKE_R_BOOLEAN_H` guard at the top of the file, before `R_CallMethodDef` is reached. |
| `SEXP` / `Rinternals.h` fake | The concrete function types cast to `DL_FUNC` in `CallEntries[]` (e.g., `SEXP (*)(SEXP, SEXP, ...)`) reference `SEXP`. `init.c` includes `rpart.h` at line 1 before `R_ext/Rdynload.h` at line 2, so `SEXP` is already in scope when the `R_CallMethodDef` struct is first used. The `SEXP` fake guide (providing `SEXPREC` and the `SEXP` typedef) must be compiled, or its header included, before `init.c` is processed. |
| `Rversion.h` fake | `init.c` line 21 includes `<Rversion.h>` to gate `R_forceSymbols`. The fake must define `R_VERSION` and the `R_Version(major, minor, patch)` macro. Any version value is safe because `R_forceSymbols` is a no-op; `R_Version(4, 3, 0)` is recommended. |
