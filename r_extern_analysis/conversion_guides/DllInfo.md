# Conversion Guide: `DllInfo`

---

## 1. Overview of `DllInfo` in R API

`DllInfo` is an opaque struct type defined in `R_ext/Rdynload.h` as `typedef struct _DllInfo DllInfo`. Its internal layout is private to R's dynamic loading subsystem; package code never inspects its fields directly. It serves as a handle to a loaded shared object (.so / .dll) and is the mandatory first argument to `R_registerRoutines`, `R_useDynamicSymbols`, and `R_forceSymbols`. R automatically constructs a `DllInfo` instance for each loaded package and passes a pointer to it into the package's `R_init_<pkgname>` hook at load time, making that hook the single entry point for all native symbol registration.

---

## 2. Contextual Usage Analysis

### Source window: `rpart/src/init.c`, lines 8–30

The entire `init.c` file is 31 lines. The `DllInfo *` pointer appears exactly once — as the parameter of `R_init_rpart` — and is then forwarded to three registration calls. No arithmetic, dereferencing, or field access is ever performed on it; it is purely an opaque token passed through.

```
Line 23:  void R_init_rpart(DllInfo * dll)
Line 25:      R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
Line 26:      R_useDynamicSymbols(dll, FALSE);
Line 28:      R_forceSymbols(dll, TRUE);
```

**Types involved:**

| Item | Role |
|---|---|
| `DllInfo *dll` | Opaque handle to the rpart shared library, injected by R |
| `R_CallMethodDef CallEntries[]` | Table of five `.Call`-registered functions (see `DL_FUNC.md`) |
| `R_registerRoutines` | Registers all four API tables (C, Call, Fortran, External) with `dll` |
| `R_useDynamicSymbols(dll, FALSE)` | Disables fallback symbol search by raw name; forces registration |
| `R_forceSymbols(dll, TRUE)` | Requires R-level calls to use the registered symbol object, not a string |

**Memory management macros present:** none. `init.c` contains no `PROTECT`, `UNPROTECT`, `allocVector`, or `SEXP` manipulation. Its only job is bookkeeping.

**Distinct usage pattern:** There is exactly one pattern — `DllInfo *` appears as the parameter of the mandatory `R_init_<pkgname>` hook and is passed verbatim into R's registration API. The hook exists solely to set up the symbol tables; `DllInfo *` does not appear in any other context.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`DllInfo` itself does not need to be removed or replaced. The struct type, the `R_init_<pkgname>` hook signature, `R_registerRoutines`, `R_useDynamicSymbols`, and `R_forceSymbols` are all equally present in both the `.Call` world and the `.C` world — they are part of R's dynamic loading layer, which is orthogonal to which dispatch mechanism (`.Call` vs. `.C`) is used at runtime.

The conversion impact on `init.c` is therefore confined to what is registered inside the hook, not to `DllInfo` or the hook itself:

| Aspect | `.Call` (current) | `.C` (target) |
|---|---|---|
| `DllInfo *dll` parameter | Unchanged | Unchanged |
| `R_init_rpart` hook name | Unchanged | Unchanged |
| `R_useDynamicSymbols` call | Unchanged | Unchanged |
| `R_forceSymbols` call | Unchanged | Unchanged |
| Registration struct type | `R_CallMethodDef` | `R_CMethodDef` |
| `R_registerRoutines` slot | second argument (`callRoutines`) | first argument (`croutines`) |

Because `DllInfo *` is an opaque pass-through, the migration requires no changes to the type, its declaration, its initialization, or any call that uses it. The only edits inside `R_init_rpart` are: (1) replace `R_CallMethodDef CallEntries[]` with `R_CMethodDef CEntries[]`, and (2) move the table pointer from the second to the first argument of `R_registerRoutines`. See the companion guide `DL_FUNC.md` for the full treatment of those changes.

### Why this approach ensures `.C` API compatibility

R's `.C` dispatcher and `.Call` dispatcher share the same dynamic loading infrastructure. Both rely on `R_registerRoutines` to locate compiled symbols; both respect the `R_useDynamicSymbols` and `R_forceSymbols` flags. `DllInfo *` is the token that binds a symbol table to a specific shared library. Keeping the hook and its parameter unchanged ensures that R can still locate and validate every compiled routine when the package is loaded, regardless of which dispatch API those routines are accessed through.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Opaque DLL Handle in the Package Load Hook

- **Locations:** `init.c`, line 23

- **Original Context (.Call):**

```c
#include "R_ext/Rdynload.h"
#include <Rversion.h>

/* Registration table built with R_CallMethodDef (see DL_FUNC.md) */
static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart",           (DL_FUNC) &rpart,            11},
    {"xpred",           (DL_FUNC) &xpred,            15},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,         2},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,       12},
    {NULL, NULL, 0}
};

/* R_init_<pkgname> is the mandatory hook called by R when the shared
   library is loaded.  The DllInfo * is supplied by R; the package
   never allocates or frees it. */
void
R_init_rpart(DllInfo * dll)
{
    /* dll passed in the second (callRoutines) slot */
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

- **C/C++ Equivalent (.C):**

```c
#include "R_ext/Rdynload.h"
#include <Rversion.h>

/*
 * DllInfo * and R_init_rpart are UNCHANGED.
 * Only the registration table type and the slot index passed to
 * R_registerRoutines differ from the .Call version.
 *
 * For the full construction of CEntries (R_CMethodDef, type arrays,
 * void function signatures) see DL_FUNC.md.
 */

static R_NativePrimitiveArgType init_rpcallback_t[] = {
    INTSXP, INTSXP, INTSXP, REALSXP, REALSXP
};
static R_NativePrimitiveArgType rpart_t[] = {
    INTSXP, INTSXP, REALSXP, REALSXP,
    REALSXP, REALSXP, INTSXP, INTSXP,
    REALSXP, INTSXP, REALSXP
};
static R_NativePrimitiveArgType xpred_t[] = {
    INTSXP, INTSXP, REALSXP, REALSXP,
    INTSXP, INTSXP, REALSXP, REALSXP,
    REALSXP, INTSXP, REALSXP, INTSXP,
    REALSXP, REALSXP, INTSXP
};
static R_NativePrimitiveArgType rpartexp2_t[]   = { REALSXP, REALSXP };
static R_NativePrimitiveArgType pred_rpart_t[]  = {
    INTSXP, INTSXP, INTSXP, INTSXP,
    INTSXP, INTSXP, INTSXP, REALSXP,
    INTSXP, INTSXP, REALSXP, INTSXP
};

static const R_CMethodDef CEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback,  5, init_rpcallback_t},
    {"rpart",           (DL_FUNC) &rpart,            11, rpart_t},
    {"xpred",           (DL_FUNC) &xpred,            15, xpred_t},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,         2, rpartexp2_t},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,       12, pred_rpart_t},
    {NULL, NULL, 0, NULL}
};

/* Hook signature is identical; DllInfo * is not touched */
void
R_init_rpart(DllInfo * dll)
{
    /* Table moved to first (croutines) slot; second (callRoutines) is now NULL */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

- **Explanation:**

  1. **`DllInfo *dll` is not modified.** The parameter declaration `DllInfo * dll` on line 23 of `init.c` is identical before and after migration. `DllInfo` is defined in `R_ext/Rdynload.h` as `typedef struct _DllInfo DllInfo`; the internal layout is private to R and is never accessed by package code. No include change is required.

  2. **`R_init_rpart` hook name is not modified.** R discovers the load hook by constructing the symbol name `R_init_<pkgname>` at runtime. Renaming the function or changing its signature would silently break package loading. The return type (`void`) and the single `DllInfo *` parameter are mandated by R's loading protocol and must be preserved.

  3. **`R_registerRoutines` slot index shifts.** The function signature is:
     ```c
     int R_registerRoutines(DllInfo *info,
                            const R_CMethodDef      * const croutines,
                            const R_CallMethodDef   * const callRoutines,
                            const R_FortranMethodDef* const fortranRoutines,
                            const R_ExternalMethodDef* const externalRoutines);
     ```
     In the original `.Call` version `CallEntries` occupies slot 2 (`callRoutines`) and slot 1 (`croutines`) is `NULL`. In the `.C` version `CEntries` occupies slot 1 (`croutines`) and slot 2 is `NULL`. The first argument — `dll` — and all remaining control flags are unchanged.

  4. **`R_useDynamicSymbols` and `R_forceSymbols` are unchanged.** Both functions accept `DllInfo *` as their first argument. Their semantics — disabling dynamic symbol lookup and requiring registered symbol objects at the R level — apply equally to `.Call` and `.C` registrations and require no adjustment.

  5. **`DL_FUNC` cast syntax is unchanged.** As detailed in `DL_FUNC.md`, the expression `(DL_FUNC) &fn` appears identically in both `R_CallMethodDef` and `R_CMethodDef` entries. `DllInfo` has no bearing on this cast.

  6. **No memory management is added or removed.** `init.c` contains no `SEXP`, `PROTECT`, `UNPROTECT`, or `allocVector` in either version. The hook is purely registration bookkeeping and has no interaction with R's garbage collector.

---

*Guide generated for `DllInfo` as found in `rpart/src/init.c`.*
