# Conversion Guide: `DllInfo`

## 1. Overview of `DllInfo` in R API

`DllInfo` is an opaque struct type defined in `R_ext/Rdynload.h` as
`typedef struct _DllInfo DllInfo`. It represents a handle to a loaded dynamic
library (shared object / DLL) within R's internal dynamic-loading subsystem.
Its sole role in package C code is as the argument type of the mandatory
`R_init_<pkgname>` entry-point function: R passes a `DllInfo *` pointer to
that function at library load time, and the package code forwards the pointer
to `R_registerRoutines`, `R_useDynamicSymbols`, and `R_forceSymbols` to
register its callable routines and configure symbol-lookup policy. `DllInfo`
carries no publicly accessible fields; its internal layout is entirely opaque
to package authors.

---

## 2. Contextual Usage Analysis

### Source location

| File | Line | Context |
|------|------|---------|
| `init.c` | 23 | `R_init_rpart(DllInfo * dll)` — function signature of the package initializer |

### 31-line window analysis (`init.c`, lines 1–31)

The complete `init.c` file is 30 lines; the full listing is the window:

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
    {"rpart",           (DL_FUNC) &rpart,            11},
    {"xpred",           (DL_FUNC) &xpred,            15},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,          2},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,        12},
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

### Observations

- `DllInfo *` appears **only in the signature of `R_init_rpart`** (line 23). The
  pointer is never dereferenced, cast, or stored; it is passed directly and
  unchanged to `R_registerRoutines`, `R_useDynamicSymbols`, and
  `R_forceSymbols`.
- The three functions that consume `dll` are all part of R's
  `R_ext/Rdynload.h` API and accept `DllInfo *info` as their first argument.
  Their signatures are:
  ```c
  int      R_registerRoutines(DllInfo *info,
               const R_CMethodDef    * const croutines,
               const R_CallMethodDef * const callRoutines,
               const R_FortranMethodDef * const fortranRoutines,
               const R_ExternalMethodDef * const externalRoutines);
  Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value);
  Rboolean R_forceSymbols(DllInfo *info, Rboolean value);
  ```
- The existing registration table (`CallEntries`) is of type
  `R_CallMethodDef[]`, meaning all currently registered functions use the
  `.Call` API.
- A related conversion guide for `DL_FUNC` (the function-pointer type used
  inside registration tables) is available at
  `/groups/jli9/Yufei/python-rpart/r_extern_analysis/conversion_guides/DL_FUNC.md`.

---

## 3. Pure C/C++ Conversion Strategy

### The role of `DllInfo` is unchanged across API flavours

`DllInfo` is not an R memory-management type and has no equivalent in the
`.C`/`.Fortran` domain that needs to be replaced. It is an infrastructure type
owned entirely by R's dynamic loader. The conversion strategy is therefore:

1. **Keep `DllInfo *` in `R_init_<pkgname>` unchanged.** The function
   signature `void R_init_rpart(DllInfo *dll)` must remain identical. R's
   loader locates this symbol by name and calls it with a valid `DllInfo *`
   regardless of whether the package uses `.Call` or `.C`.

2. **Redirect the registration table slot.** The only change inside
   `R_init_rpart` is the argument passed to `R_registerRoutines`. When
   migrating to `.C`, the `.C`-method table (`R_CMethodDef[]`) is placed in
   the first slot (`croutines`) instead of `NULL`, and the `.Call`-method
   table slot (second argument) becomes `NULL`:
   ```c
   /* Before (.Call): */
   R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);

   /* After (.C): */
   R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
   ```
   The `dll` pointer itself is passed in exactly the same position and manner.

3. **`R_useDynamicSymbols` and `R_forceSymbols` calls are preserved
   verbatim.** Both functions take `DllInfo *` as their first argument and are
   API-agnostic; they operate on the loaded library handle, not on individual
   function entries.

4. **No header changes are needed.** `DllInfo` is defined in
   `R_ext/Rdynload.h`, which must still be included in the converted
   `init.c`. No additional or replacement header is required.

5. **`DllInfo` has no pure-C equivalent.** Unlike `SEXP`, `PROTECT`, or
   `INTEGER`, `DllInfo` is not a computation or memory type that needs to be
   replaced with a standard C construct. It is an R infrastructure type that
   persists in any package that loads via R's dynamic loader, including
   `.C`-based packages.

---

## 4. Step-by-Step Conversion Examples

### Pattern: `DllInfo *` as the parameter of the package initializer entry point

- **Locations:** `init.c`, line 23

- **Original Context (.Call):**

```c
#include "R_ext/Rdynload.h"
#include <Rversion.h>

static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart",           (DL_FUNC) &rpart,            11},
    {"xpred",           (DL_FUNC) &xpred,            15},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,          2},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,        12},
    {NULL, NULL, 0}
};

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

- **C/C++ Equivalent (.C):**

```c
#include "R_ext/Rdynload.h"
#include <Rversion.h>

/*
 * Forward declarations for .C-style routines.
 * All functions return void; output is passed via pre-allocated pointer
 * arguments.  Each void* repartitioned from SEXP becomes int* or double*.
 */
void init_rpcallback_c(double *yback, double *wback, double *xback,
                       int *nback, int *ny, int *nr);
void rpart_c(int *ncat, int *method, double *opt, double *parms,
             double *ymat, double *xmat, int *xvals, int *xgrp,
             double *wt, int *ny, double *cost);
void xpred_c(int *ncat, int *method, double *opt, double *parms,
             int *xvals, int *xgrp, double *ymat, double *xmat,
             double *wt, int *ny, double *cost, int *all,
             double *cp, double *toprisk, int *nresp);
void rpartexp2_c(double *dtimes, int *n, double *eps, int *keep);
void pred_rpart_c(int *dimx, int *nnode, int *nsplit, int *dimc,
                  int *nnum, int *nodes2, int *vnum, double *split2,
                  int *csplit2, int *usesur, double *xdata2,
                  int *xmiss2, int *where);

/*
 * R_NativePrimitiveArgType arrays encode the type of each argument
 * in the order they appear in the C function signature.
 * Common SEXPTYPE values: INTSXP = 13, REALSXP = 14, LGLSXP = 10.
 * Supply NULL for the types field to skip argument-type checking.
 */
static const R_CMethodDef CEntries[] = {
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c,  6, NULL},
    {"rpart_c",           (DL_FUNC) &rpart_c,            11, NULL},
    {"xpred_c",           (DL_FUNC) &xpred_c,            15, NULL},
    {"rpartexp2_c",       (DL_FUNC) &rpartexp2_c,         4, NULL},
    {"pred_rpart_c",      (DL_FUNC) &pred_rpart_c,       13, NULL},
    {NULL, NULL, 0, NULL}
};

/*
 * The function signature is IDENTICAL to the .Call version.
 * DllInfo * dll is passed unchanged to R_registerRoutines.
 * The only structural change is the table type and the slot order.
 */
void
R_init_rpart(DllInfo * dll)
{
    /* .C table goes in the first (croutines) slot; .Call slot is now NULL */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

- **Explanation:**

  | Aspect | `.Call` original | `.C` converted |
  |--------|-----------------|----------------|
  | `DllInfo * dll` parameter | present | **identical — no change** |
  | `R_registerRoutines` first arg (`croutines`) | `NULL` | `CEntries` (the `R_CMethodDef[]` table) |
  | `R_registerRoutines` second arg (`callRoutines`) | `CallEntries` | `NULL` |
  | `R_useDynamicSymbols(dll, FALSE)` | present | **identical — no change** |
  | `R_forceSymbols(dll, TRUE)` | present | **identical — no change** |
  | Registration struct type | `R_CallMethodDef` | `R_CMethodDef` (adds `types` field) |
  | Registered function return type | `SEXP` | `void` |
  | Registered function argument types | `SEXP` per arg | `int *`, `double *`, etc. |

  `DllInfo *` is an opaque handle supplied by R at load time. Package code
  never constructs, copies, or frees it. Because it is purely a pass-through
  argument to R's own registration API functions, its declaration, usage, and
  the surrounding `R_init_rpart` function signature require **zero changes**
  when migrating from `.Call` to `.C`. All migration effort is in the
  registration-table type (`R_CallMethodDef` -> `R_CMethodDef`), the
  `R_registerRoutines` slot order, and the signatures of the individual
  registered routines (see the `DL_FUNC` conversion guide for the
  function-pointer casting details, and the `SEXP` / `PROTECT` / `INTEGER` /
  `REAL` guides for rewriting individual routine bodies).
