# Fake Header Implementation Guide: `DllInfo`

---

### 1. Overview of `DllInfo` in R API

`DllInfo` is an opaque C struct type defined in `R_ext/Rdynload.h` via the forward declaration `typedef struct _DllInfo DllInfo;`. Its internal layout is private to `libR.so` and never exposed to package code. In R's C API, `DllInfo` serves as a handle representing a loaded shared library: R's dynamic loader passes a pointer to a `DllInfo` instance as the sole argument to the library initialisation function `R_init_<pkg>`, which package authors implement to register callable entry points with R's symbol table via `R_registerRoutines`, `R_useDynamicSymbols`, and `R_forceSymbols`. Package code never dereferences or allocates a `DllInfo` object; it only forwards the pointer to these registration functions.

---

### 2. Contextual Usage Analysis

**Source file examined:** `/groups/jli9/Yufei/python-rpart/rpart/src/init.c`, lines 1–30 (entire file).

**Argument and return types observed.**

`DllInfo` appears in exactly one position in the rpart source: as the parameter type of the initialisation function at line 23:

```c
void R_init_rpart(DllInfo * dll)
```

The pointer `dll` is then passed unchanged to three registration functions:

```c
R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
R_useDynamicSymbols(dll, FALSE);
R_forceSymbols(dll, TRUE);           // guarded by #if R_VERSION >= 2.16.0
```

`DllInfo *` is therefore used purely as a pass-through argument. The pointer is never dereferenced, its fields are never read, and no memory is allocated through it.

**Co-occurring R API items.**

- `R_CallMethodDef` — the struct whose array (`CallEntries`) is passed as the third argument to `R_registerRoutines`. Contains a `DL_FUNC` field (a cast-to generic function pointer). Previously documented in `DL_FUNC.md`.
- `DL_FUNC` — the generic function pointer typedef used inside `R_CallMethodDef`. Already faked in `DL_FUNC.md`; `fake_Rdynload.hpp` established there covers `DllInfo` as `struct DllInfo {}`. The present guide supersedes that inline stub with a precise rationale.
- `R_registerRoutines`, `R_useDynamicSymbols`, `R_forceSymbols` — the three registration functions that consume `DllInfo *`. All three are no-ops in the standalone build.
- `Rboolean`, `FALSE`, `TRUE` — used as arguments to the registration functions.
- `R_VERSION`, `R_Version` — preprocessor macros from `<Rversion.h>` that gate the `R_forceSymbols` call. In the standalone build the `<Rversion.h>` fake must supply a version value; if the version is set to `>= 2.16.0`, `R_forceSymbols` will be called and must also be a no-op.

**Distinct usage patterns.**

There is exactly one usage pattern: `DllInfo *` as the parameter of `R_init_rpart`, forwarded unchanged to three no-op registration functions. No other pattern exists in the rpart source.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`DllInfo` is an opaque struct. The real `Rdynload.h` declares it as `typedef struct _DllInfo DllInfo;` — a forward declaration. The package source never dereferences the pointer, so the internal layout of `struct _DllInfo` is completely irrelevant. In the standalone build:

- `DllInfo` is defined as an empty struct: `struct DllInfo {};`. This satisfies the forward declaration semantics: `DllInfo *` is a well-formed pointer type, pointer arithmetic and null comparison work, and any code that takes or passes `DllInfo *` compiles without change.
- Because the real header uses `typedef struct _DllInfo DllInfo`, the fake must either replicate this two-step form or define the struct directly as `struct DllInfo` and add `typedef struct DllInfo DllInfo;` for C compatibility. Since `init.c` is compiled as C (not C++), the fake header must be C-compatible inside the typedef; the C++ `struct DllInfo {};` idiom is acceptable only when the fake header is included from a C++ translation unit. To support both C and C++ compilation, the canonical form is:

```c
typedef struct DllInfo_fake DllInfo;
struct DllInfo_fake { int _unused; };
```

- `R_init_rpart` is never called in the standalone build. R's dynamic loader is not present, so the initialisation protocol (passing a real `DllInfo *`) never runs. The function still compiles and its symbol is present in the shared object; it is simply dead code at runtime.
- `R_registerRoutines`, `R_useDynamicSymbols`, and `R_forceSymbols` are faked as inline no-op functions returning plausible values.

**`#define` aliases that must be preserved.**

The real `Rdynload.h` defines no preprocessor aliases for `DllInfo`. The aliases `FALSE` and `TRUE` come from `R_ext/Boolean.h` (included by `Rdynload.h`) and are already replicated in the `fake_Rdynload.hpp` introduced by `DL_FUNC.md`. No additional aliases are required.

**Invariant applicability.**

- Invariant 1 (error/warning style): not triggered. `DllInfo` and the registration functions do not generate errors or warnings.
- Invariant 2 (arena memory): not triggered. No memory is allocated through `DllInfo` or the registration functions.
- Invariant 3 (interpreter items): not triggered. `DllInfo` does not require a running R interpreter; R's loader is simply absent and `R_init_rpart` is never called.

**Relationship to existing `DL_FUNC.md` guide.**

The `DL_FUNC.md` guide already contains an inline stub `struct DllInfo {};` at line 157 of `fake_Rdynload.hpp`. This guide provides the precise rationale and the C-compatible two-step form. Both definitions are functionally equivalent for C++ compilation. For a build that compiles `init.c` as C (not C++), the C-compatible form in this guide must be used instead of the bare C++ `struct DllInfo {};`.

---

### 4. Fake Implementation Examples

#### Pattern: `DllInfo *` as parameter of `R_init_rpart`, forwarded to no-op registration functions

- **Locations:** `init.c:23`

- **Original R API Usage:**

```c
/* init.c — lines 21–30, original */
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
// fake_Rdynload.hpp
// Drop-in replacement for R_ext/Rdynload.h.
// Provides DllInfo, DL_FUNC, R_CallMethodDef, and all registration
// functions as no-ops so that init.c compiles without libR.so.
//
// Compatible with both C and C++ compilation units.

#pragma once
#ifndef FAKE_R_EXT_RDYNLOAD_H
#define FAKE_R_EXT_RDYNLOAD_H

#include <stddef.h>   /* NULL */

/* -------------------------------------------------------------------------
 * Rboolean — replicated from R_ext/Boolean.h (pulled in by real Rdynload.h)
 * -------------------------------------------------------------------------*/
#ifndef FAKE_R_BOOLEAN_H
#define FAKE_R_BOOLEAN_H
#undef FALSE
#undef TRUE
typedef enum { FALSE = 0, TRUE = 1 } Rboolean;
#endif /* FAKE_R_BOOLEAN_H */

/* -------------------------------------------------------------------------
 * DL_FUNC — generic function pointer (typedef void * (*DL_FUNC)(void))
 * Reproduced verbatim from the real Rdynload.h line 39.
 * -------------------------------------------------------------------------*/
typedef void * (*DL_FUNC)(void);

/* -------------------------------------------------------------------------
 * Supporting types
 * -------------------------------------------------------------------------*/
typedef unsigned int R_NativePrimitiveArgType;

#define SINGLESXP 302

typedef struct {
    const char                *name;
    DL_FUNC                    fun;
    int                        numArgs;
    R_NativePrimitiveArgType  *types;
} R_CMethodDef;

typedef R_CMethodDef R_FortranMethodDef;

typedef struct {
    const char *name;
    DL_FUNC     fun;
    int         numArgs;
} R_CallMethodDef;

typedef R_CallMethodDef R_ExternalMethodDef;

/* -------------------------------------------------------------------------
 * DllInfo — opaque handle representing a loaded shared library.
 *
 * Real declaration in Rdynload.h:   typedef struct _DllInfo DllInfo;
 * The internal layout of struct _DllInfo lives entirely inside libR.so
 * and is never exposed to package code.  Package code only ever holds a
 * DllInfo * and forwards it to registration functions — it never reads or
 * writes any field.
 *
 * Fake strategy: define an empty-body struct under a unique tag name to
 * avoid collisions with any residual forward declaration, then typedef it
 * to DllInfo.  The C-compatible two-step form (typedef + tag) is used so
 * that this header compiles correctly when init.c is compiled as plain C.
 * -------------------------------------------------------------------------*/
typedef struct DllInfo_fake DllInfo;
struct DllInfo_fake { int _unused; };

/* -------------------------------------------------------------------------
 * Registration functions — all no-ops in the standalone build.
 *
 * In the real libR.so these functions update R's internal symbol table so
 * that .Call("rpart", ...) can resolve to the C function rpart().  In the
 * standalone build there is no R symbol table and the functions are never
 * invoked by R's loader, so they exist solely to satisfy the linker and to
 * allow init.c to compile and link without modification.
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

static inline Rboolean R_useDynamicSymbols(DllInfo * info, Rboolean value)
{
    (void)info; (void)value;
    return FALSE;
}

static inline Rboolean R_forceSymbols(DllInfo * info, Rboolean value)
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

- **Arena / Memory Notes:** Not applicable. `DllInfo` is never allocated, freed, or touched by any memory management function. The `R_CallMethodDef` table (`CallEntries`) is a `static const` array on the program's data segment — no heap or arena involvement.

- **Explanation:**

  The only mechanical change is that `R_ext/Rdynload.h` must be shadowed by `fake_Rdynload.hpp` in the compiler's include search path. Because `init.c` uses the angle-bracket form `#include "R_ext/Rdynload.h"` (relative to the R include tree), the build system must place a directory on the `-I` path that contains `R_ext/Rdynload.h` as a file, pointing to `fake_Rdynload.hpp`. A common approach is to create a shadow directory `fake_include/R_ext/` and place a copy or symlink of `fake_Rdynload.hpp` there as `Rdynload.h`.

  The C-compatible two-step typedef (`typedef struct DllInfo_fake DllInfo; struct DllInfo_fake { int _unused; };`) is required because `init.c` is a plain C file, not C++. In C, `struct Foo {}` is not valid syntax; the struct body must contain at least one member. The `int _unused` member satisfies this while adding negligible overhead (the struct is never allocated).

  `R_init_rpart` is the shared-library constructor invoked by R's `dyn.load()` mechanism. In the standalone Python build, `dyn.load()` is never called, so `R_init_rpart` is dead code. It still compiles and its symbol is visible in the shared object, which is harmless.

  The `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` guard at line 27 of `init.c` requires `<Rversion.h>` to be faked as well. If the fake `Rversion.h` defines `R_VERSION` as a value greater than or equal to `R_Version(2, 16, 0)` (which is `0x020a0000` in the real header's encoding), then `R_forceSymbols` will be called by `R_init_rpart`. Because `R_forceSymbols` is a no-op in the fake, this path is safe regardless of the version value chosen.

  The `(void)param;` casts inside each registration function suppress unused-parameter warnings under `-Wall -Wextra` without requiring any change to `init.c`.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `DL_FUNC.md` / `fake_Rdynload.hpp` | `DL_FUNC` typedef and `R_CallMethodDef` struct must be defined before `DllInfo` appears in the same translation unit. `fake_Rdynload.hpp` (introduced by `DL_FUNC.md`) already contains an inline `DllInfo` stub (`struct DllInfo {};`). The present guide replaces that stub with the C-compatible two-step form. Only one of the two definitions should be active in the final header; the `DL_FUNC.md` inline stub must be removed or guarded so it does not conflict with the `DllInfo_fake` typedef here. |
| `Rboolean` / `R_ext/Boolean.h` fake | The `Rboolean` enum (values `FALSE = 0`, `TRUE = 1`) must be defined before `fake_Rdynload.hpp` because `R_useDynamicSymbols` and `R_forceSymbols` use `Rboolean` in their signatures. `fake_Rdynload.hpp` self-contains this definition under the `FAKE_R_BOOLEAN_H` guard; a separate `Boolean.h` fake is only required if `Rboolean` also appears independently in other headers compiled into the same translation unit. |
| `SEXP` / `Rinternals.h` fake | The concrete function pointer types cast to `DL_FUNC` in `init.c` (e.g., `SEXP (*)(SEXP, SEXP, ...)`) reference `SEXP`. `init.c` includes `rpart.h` before `R_ext/Rdynload.h`, so `SEXP` is already in scope when `fake_Rdynload.hpp` is processed. The `SEXP` guide — providing the `SEXPREC` struct and the `SEXP` typedef — must be compiled (or its header included) before `fake_Rdynload.hpp` in any translation unit that includes both. |
| `Rversion.h` fake | `init.c` includes `<Rversion.h>` at line 21 to gate `R_forceSymbols`. The fake `Rversion.h` must define `R_VERSION` and the `R_Version(major, minor, patch)` macro. Since `R_forceSymbols` is a no-op, any version value is acceptable; defining `R_VERSION` as `R_Version(4, 3, 0)` is recommended to enable the `R_forceSymbols` path (which is then silently discarded). |
