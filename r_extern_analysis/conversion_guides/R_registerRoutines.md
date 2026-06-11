# Conversion Guide: `R_registerRoutines`

## 1. Overview of `R_registerRoutines` in R API

`R_registerRoutines` is the central DLL-initialization function declared in
`R_ext/Rdynload.h` with the following signature:

```c
int R_registerRoutines(DllInfo *info,
                       const R_CMethodDef    * const croutines,
                       const R_CallMethodDef * const callRoutines,
                       const R_FortranMethodDef * const fortranRoutines,
                       const R_ExternalMethodDef * const externalRoutines);
```

It accepts a `DllInfo *` handle (supplied by R's dynamic loader to the
mandatory `R_init_<pkgname>` entry point) and four null-terminated arrays of
method-definition structs — one per supported dispatch mechanism (`.C`,
`.Call`, `.Fortran`, `.External`). Any slot that is not used by the package
must be passed as `NULL`. The function registers the supplied symbols with R's
internal runtime so that R-level calls such as `.Call("name", ...)` or
`.C("name", ...)` can locate and invoke the corresponding compiled routine
without performing a raw symbol lookup in the shared library at call time.
It returns an `int` (conventionally ignored by package code).

---

## 2. Contextual Usage Analysis

### Source location

| File | Line | Context |
|------|------|---------|
| `init.c` | 25 | `R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);` |

### 31-line window analysis (`init.c`, lines 10–30)

The complete `init.c` file is only 30 lines. The full listing is the window:

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

### Full signature from `R_ext/Rdynload.h`

```c
int R_registerRoutines(DllInfo *info,
                       const R_CMethodDef    * const croutines,
                       const R_CallMethodDef * const callRoutines,
                       const R_FortranMethodDef * const fortranRoutines,
                       const R_ExternalMethodDef * const externalRoutines);
```

The five parameters map directly to argument positions in the call at line 25:

| Position | Parameter | Type | Value in `rpart` |
|---|---|---|---|
| 1 | `info` | `DllInfo *` | `dll` — the handle supplied by R's loader |
| 2 | `croutines` | `const R_CMethodDef * const` | `NULL` — no `.C` routines registered |
| 3 | `callRoutines` | `const R_CallMethodDef * const` | `CallEntries` — the `.Call` registration table |
| 4 | `fortranRoutines` | `const R_FortranMethodDef * const` | `NULL` — no `.Fortran` routines |
| 5 | `externalRoutines` | `const R_ExternalMethodDef * const` | `NULL` — no `.External` routines |

### Struct types referenced

`R_CallMethodDef` (three fields: `name`, `fun`, `numArgs`) is the entry type
for the `.Call` dispatch table. Its null-terminated array is `CallEntries`,
defined at lines 12–19. Each entry pairs a string name with a type-erased
`DL_FUNC` function pointer and an argument count.

`R_CMethodDef` (four fields: `name`, `fun`, `numArgs`, `types`) is the
equivalent struct for the `.C` dispatch table. It adds a
`R_NativePrimitiveArgType *types` field that encodes the C type of every
argument for optional runtime type checking by R's `.C` dispatcher.

Both structs are defined in `R_ext/Rdynload.h`. See companion guides
`R_CallMethodDef.md` and `DllInfo.md` for detailed treatment of those types.

### Registered functions

| R-level name | C function | numArgs | C signature (`.Call`) |
|---|---|---|---|
| `init_rpcallback` | `init_rpcallback` | 5 | `SEXP(SEXP, SEXP, SEXP, SEXP, SEXP)` |
| `rpart` | `rpart` | 11 | `SEXP(SEXP x11)` |
| `xpred` | `xpred` | 15 | `SEXP(SEXP x15)` |
| `rpartexp2` | `rpartexp2` | 2 | `SEXP(SEXP, SEXP)` |
| `pred_rpart` | `pred_rpart` | 12 | `SEXP(SEXP x12)` |

### Key observations

- `R_registerRoutines` is called **exactly once** in `rpart`: inside
  `R_init_rpart`, which is the mandatory package-load entry point that R's
  dynamic loader calls automatically when the shared library is attached.
- The `.C`, `.Fortran`, and `.External` slots are all `NULL`; only the second
  slot (`callRoutines`) carries a non-null value, confirming that all five
  registered routines use the `.Call` dispatch mechanism.
- The return value of `R_registerRoutines` (an `int`) is discarded at this
  call site, which is the universal convention throughout R package source code.
- The call is immediately followed by `R_useDynamicSymbols(dll, FALSE)` and
  (conditionally) `R_forceSymbols(dll, TRUE)`. These two calls enforce strict
  symbol-registration discipline and must be preserved verbatim during any
  migration (see `R_forceSymbols.md`).
- There are no `SEXP`, `PROTECT`, `allocVector`, or any memory-management
  constructs inside `init.c`. All such constructs are confined to the bodies
  of the five registered functions.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_registerRoutines` itself is **not removed** during the migration from
`.Call` to `.C`. It is the mandatory registration function for all R C API
flavours — `.C`, `.Call`, `.Fortran`, and `.External` — and must remain the
mechanism by which routines are registered with R's dynamic loader. The
conversion therefore consists of a **slot swap**: moving the registration
table from the second argument position (the `.Call` slot, `callRoutines`) to
the first argument position (the `.C` slot, `croutines`), while simultaneously
changing the table type from `R_CallMethodDef[]` to `R_CMethodDef[]`.

The full set of coordinated changes required is:

1. **Replace the registration table type.**
   The existing `R_CallMethodDef[]` array (`CallEntries`) must be replaced by
   an `R_CMethodDef[]` array (conventionally named `CEntries`). `R_CMethodDef`
   adds a fourth field, `R_NativePrimitiveArgType *types`, that lists the C
   type of every argument accepted by the registered function. Common type
   constants (reused from `Rinternals.h` as `R_NativePrimitiveArgType` values)
   are `INTSXP` (13), `REALSXP` (14), and `LGLSXP` (10). Passing `NULL` for
   `types` disables per-argument type checking.

2. **Update the sentinel row.**
   The three-field `.Call` sentinel `{NULL, NULL, 0}` must become the
   four-field `.C` sentinel `{NULL, NULL, 0, NULL}`.

3. **Move the table to the first argument slot.**
   The `croutines` slot is the first positional argument of
   `R_registerRoutines`. Under the current `.Call` setup it is `NULL`; under
   `.C` it receives the `CEntries` table. The `callRoutines` slot (second
   argument) becomes `NULL`:

   ```c
   /* Before (.Call): */
   R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);

   /* After (.C): */
   R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
   ```

   The `dll` pointer in argument position 1, and the `NULL` values in the
   `.Fortran` (position 4) and `.External` (position 5) slots, are unchanged.

4. **Rewrite every registered function body.**
   Each C function that was registered under `.Call` must be converted
   independently: its return type changes from `SEXP` to `void`, each `SEXP`
   parameter becomes the appropriate raw C pointer type (`int *`, `double *`,
   `char **`), and any return value is replaced by an additional output pointer
   argument whose backing storage is pre-allocated in the calling R code before
   the `.C(...)` invocation. All `PROTECT`/`UNPROTECT`/`allocVector` calls are
   removed from the C function bodies; memory management moves entirely to R.
   The `numArgs` field in each `R_CMethodDef` entry must reflect the expanded
   argument count (inputs plus outputs).

5. **Retain `R_useDynamicSymbols` and `R_forceSymbols` verbatim.**
   Both calls take `DllInfo *` as their first argument and are API-agnostic —
   they operate on the loaded library handle, not on individual function entries
   or dispatch mechanism. Their syntax, argument values, and the surrounding
   `#if defined(R_VERSION)` compile-time guard do not change.

### Why this approach ensures `.C` compatibility

R's `.C` dispatcher passes each argument as a raw C pointer obtained from the
pre-allocated R object on the calling side. It cannot handle `SEXP`-returning
functions or R-internal memory allocation inside the called routine. By
registering functions in the `croutines` slot via `R_CMethodDef`, R's loader
and dispatcher know to apply `.C`-style argument marshalling (converting each
R vector to its underlying `int *` or `double *` pointer) rather than
`.Call`-style marshalling (wrapping arguments as opaque `SEXP` objects).

---

## 4. Step-by-Step Conversion Examples

### Pattern: Migrating the `.Call` registration table to a `.C` registration table

- **Locations:** `init.c`, line 25 (`R_registerRoutines` call), lines 12–19
  (`CallEntries` table definition)

- **Original Context (.Call):**

```c
#include "rpart.h"
#include "R_ext/Rdynload.h"
#include "node.h"
#include "rpartproto.h"

/* Forward declarations — all functions return SEXP and accept SEXP arguments */
SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x);
SEXP rpartexp2(SEXP dtimes, SEXP seps);
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
        SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
        SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2);

/*
 * R_CallMethodDef: three fields per entry (name, fun, numArgs).
 * The .Call dispatch table is passed as the SECOND argument
 * (callRoutines) of R_registerRoutines.
 */
static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart",           (DL_FUNC) &rpart,            11},
    {"xpred",           (DL_FUNC) &xpred,            15},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,          2},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,        12},
    {NULL, NULL, 0}      /* three-field sentinel */
};

#include <Rversion.h>
void
R_init_rpart(DllInfo * dll)
{
    /*
     * Slot 2 (callRoutines) = CallEntries (.Call table).
     * Slots 1, 3, 4 are NULL (no .C, .Fortran, or .External routines).
     */
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

- **C/C++ Equivalent (.C):**

```c
#include "rpart.h"
#include "R_ext/Rdynload.h"
#include "node.h"
#include "rpartproto.h"

/*
 * Forward declarations — all functions now return void.
 * Output values are passed as additional pre-allocated pointer arguments.
 * The numArgs field in each R_CMethodDef entry counts ALL pointer arguments,
 * including the output ones.
 *
 * NOTE: The exact argument lists below are illustrative.  Each registered
 * function must be converted individually (see companion guides SEXP.md,
 * PROTECT.md, INTEGER.md, REAL.md for the per-function body transformation).
 */
void init_rpcallback_c(double *yback, double *wback, double *xback,
                       int *nback, int *ny, int *nr);          /* 6 args */
void rpart_c(int *ncat, int *method, double *opt, double *parms,
             double *ymat, double *xmat, int *xvals, int *xgrp,
             double *wt, int *ny, double *cost);               /* 11 args */
void xpred_c(int *ncat, int *method, double *opt, double *parms,
             int *xvals, int *xgrp, double *ymat, double *xmat,
             double *wt, int *ny, double *cost, int *all,
             double *cp, double *toprisk, int *nresp);         /* 15 args */
void rpartexp2_c(double *dtimes, int *n, double *eps, int *keep); /* 4 args */
void pred_rpart_c(int *dimx, int *nnode, int *nsplit, int *dimc,
                  int *nnum, int *nodes2, int *vnum, double *split2,
                  int *csplit2, int *usesur, double *xdata2,
                  int *xmiss2, int *where);                    /* 13 args */

/*
 * Optional: declare R_NativePrimitiveArgType arrays to enable per-argument
 * type checking by R's .C dispatcher.
 * Common SEXPTYPE constants: REALSXP = 14, INTSXP = 13, LGLSXP = 10.
 * Pass NULL in the types field to skip type checking for a given entry.
 */
static R_NativePrimitiveArgType rpartexp2_types[] = {
    REALSXP,  /* dtimes  */
    INTSXP,   /* n       */
    REALSXP,  /* eps     */
    INTSXP    /* keep    */
};

/*
 * R_CMethodDef: four fields per entry (name, fun, numArgs, types).
 * The .C dispatch table is passed as the FIRST argument (croutines)
 * of R_registerRoutines.
 * The sentinel row must supply all four fields: {NULL, NULL, 0, NULL}.
 */
static const R_CMethodDef CEntries[] = {
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c,  6, NULL},
    {"rpart_c",           (DL_FUNC) &rpart_c,            11, NULL},
    {"xpred_c",           (DL_FUNC) &xpred_c,            15, NULL},
    {"rpartexp2_c",       (DL_FUNC) &rpartexp2_c,         4, rpartexp2_types},
    {"pred_rpart_c",      (DL_FUNC) &pred_rpart_c,       13, NULL},
    {NULL, NULL, 0, NULL}   /* four-field sentinel required by R_CMethodDef */
};

#include <Rversion.h>
void
R_init_rpart(DllInfo * dll)
{
    /*
     * Slot 1 (croutines)    = CEntries (.C table).       <-- CHANGED
     * Slot 2 (callRoutines) = NULL (.Call slot cleared). <-- CHANGED
     * Slots 3, 4 remain NULL (no .Fortran or .External routines).
     *
     * R_useDynamicSymbols and R_forceSymbols are UNCHANGED.
     */
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
  | `R_registerRoutines` call present | yes | **yes — identical function, different arguments** |
  | Argument 1 (`dll`) | `dll` | **identical — no change** |
  | Argument 2 (`croutines`, `.C` slot) | `NULL` | `CEntries` (the `R_CMethodDef[]` table) |
  | Argument 3 (`callRoutines`, `.Call` slot) | `CallEntries` | `NULL` |
  | Argument 4 (`fortranRoutines`) | `NULL` | **identical — no change** |
  | Argument 5 (`externalRoutines`) | `NULL` | **identical — no change** |
  | Registration table type | `R_CallMethodDef` (3 fields) | `R_CMethodDef` (4 fields, adds `types`) |
  | Sentinel row | `{NULL, NULL, 0}` | `{NULL, NULL, 0, NULL}` |
  | `(DL_FUNC) &fn` cast syntax | present in each entry | **identical — no change** |
  | Registered function return type | `SEXP` | `void` |
  | Registered function argument types | `SEXP` per argument | `int *`, `double *`, etc. |
  | `numArgs` count | number of `SEXP` inputs only | number of ALL pointer args (inputs + outputs) |
  | Output values | returned as `SEXP` | additional pointer args; pre-allocated in R |
  | `R_useDynamicSymbols(dll, FALSE)` | present | **identical — no change** |
  | `R_forceSymbols(dll, TRUE)` | present | **identical — no change** |
  | `#if defined(R_VERSION) ...` guard | present | **identical — no change** |
  | `R_init_rpart` function signature | `void R_init_rpart(DllInfo * dll)` | **identical — no change** |

  The key insight is that `R_registerRoutines` itself is not a `.Call`-only
  construct — it is the universal registration point for all four R dispatch
  mechanisms. The **only change to the `R_registerRoutines` call line** is the
  positional swap of `NULL` and the method table: the table moves from the
  second argument to the first. All other aspects of `R_init_rpart` — the
  function signature, the `DllInfo *` parameter, the `R_useDynamicSymbols` and
  `R_forceSymbols` calls, the `Rversion.h` include, and the compile-time guard
  — are preserved verbatim.

  The substantial migration work is not in `R_registerRoutines` itself but in
  the definitions of the individual registered routines (removal of `SEXP`
  return types, `PROTECT`/`UNPROTECT`/`allocVector` calls, and `REAL`/`INTEGER`
  accessor macros). Those transformations are detailed in the companion guides:
  `SEXP.md`, `PROTECT.md`, `R_CallMethodDef.md`, `DL_FUNC.md`, `DllInfo.md`,
  `INTEGER.md`, `REAL.md`, `INTSXP.md`, and `REALSXP.md`.

---

### Pattern: R-side caller update when switching from `.Call` to `.C`

- **Locations:** Any R wrapper function in `rpart/R/` that calls `.Call` against
  one of the five registered symbols.

- **Original Context (.Call):**

```r
# R wrapper — .Call passes SEXP objects; return value is a SEXP
rpartexp2_r <- function(dtimes, eps) {
    .Call("rpartexp2", dtimes, eps)
    # or equivalently, after useDynLib registration:
    # .Call(C_rpartexp2, dtimes, eps)
}
```

- **C/C++ Equivalent (.C):**

```r
# R wrapper — .C passes pre-allocated raw vectors; output is extracted from
# the returned named list.
rpartexp2_r <- function(dtimes, eps) {
    n <- length(dtimes)
    result <- .C("rpartexp2_c",
                 dtimes = as.double(dtimes),
                 n      = as.integer(n),
                 eps    = as.double(eps),
                 keep   = integer(n))   # pre-allocated output vector
    result$keep
}
```

- **Explanation:**

  Under `.Call`, R passes its objects as `SEXP` handles directly to the C
  function; the C function performs all allocation and returns a new `SEXP`.
  Under `.C`, R must pre-allocate every output buffer before the call (here,
  `integer(n)`) and pass it as a named argument. R's `.C` dispatcher passes
  each element as its underlying raw C pointer (e.g., `int *` for `integer(n)`,
  `double *` for `as.double(...)`). The C function writes results directly
  into these pre-allocated buffers and returns `void`. The R caller retrieves
  outputs by indexing the named list that `.C(...)` returns.

  This caller-side change is a direct consequence of the `R_registerRoutines`
  slot swap: registering functions in the `croutines` slot instructs R's
  dispatcher to apply `.C`-style marshalling, which requires all output
  buffers to be resident in R memory before the call.
