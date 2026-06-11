# Conversion Guide: `DL_FUNC`

## 1. Overview of `DL_FUNC` in R API

`DL_FUNC` is a generic function-pointer type defined in `R_ext/Rdynload.h` as
`typedef void * (*DL_FUNC)(void)`. It serves as a universal, type-erased
handle to any C function that is to be registered with R's dynamic-loading
subsystem. In practice it is used exclusively inside `R_CallMethodDef`,
`R_CMethodDef`, and `R_FortranMethodDef` registration tables, where each entry
pairs a string name with a cast-to-`DL_FUNC` function pointer and an argument
count, allowing R's `R_registerRoutines` to bind R-level `.Call`/`.C`/`.Fortran`
symbols to compiled routines at package load time.

---

## 2. Contextual Usage Analysis

### Source location

| File | Line | Context |
|------|------|---------|
| `init.c` | 12–19 | `static const R_CallMethodDef CallEntries[]` array definition |

### 31-line window analysis (`init.c`, lines 1–31)

The entire `init.c` file is reproduced below for reference:

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
R_init_rpart(DllInfo *dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

### Observations

- `DL_FUNC` appears **only as a cast operator** inside `R_CallMethodDef`
  initializer entries: `(DL_FUNC) &<function_name>`.
- Every registered function has a `SEXP`-returning, `SEXP`-argument signature
  consistent with the `.Call` API.
- The table is passed as the second (`callRoutines`) argument of
  `R_registerRoutines`, with `NULL` for the `.C` and `.Fortran` slots.
- `R_useDynamicSymbols(dll, FALSE)` and `R_forceSymbols(dll, TRUE)` lock the
  package so that only the explicitly registered names are accessible; this is a
  security/stability best practice that must be preserved (or adapted) in the
  converted version.
- There are no memory-management macros (`PROTECT`, `UNPROTECT`, `allocVector`)
  inside `init.c` itself; those live in the individual registered functions.

### Registered functions and their signatures

| R-level name | C function | Arg count | C signature |
|---|---|---|---|
| `init_rpcallback` | `init_rpcallback` | 5 | `SEXP(SEXP, SEXP, SEXP, SEXP, SEXP)` |
| `rpart`            | `rpart`           | 11 | `SEXP(SEXP×11)` |
| `xpred`            | `xpred`           | 15 | `SEXP(SEXP×15)` |
| `rpartexp2`        | `rpartexp2`       | 2  | `SEXP(SEXP, SEXP)` |
| `pred_rpart`       | `pred_rpart`      | 12 | `SEXP(SEXP×12)` |

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under the `.Call` API, every registered function receives and returns `SEXP`
objects; `DL_FUNC` is used purely as a type-erasing cast to store those
function pointers uniformly in `R_CallMethodDef`. When migrating to the `.C`
API the following changes apply:

1. **Registration struct changes.**
   Replace `R_CallMethodDef` / `(DL_FUNC) &fn` with `R_CMethodDef` /
   `(DL_FUNC) &fn`. `R_CMethodDef` carries an additional
   `R_NativePrimitiveArgType *types` field that must list the native type of
   every argument (e.g., `INTSXP`, `REALSXP`).

2. **`R_registerRoutines` call changes.**
   The `.C`-method table goes into the *first* (`croutines`) argument, and the
   `.Call`-method slot (second argument) becomes `NULL`:
   ```c
   R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
   ```

3. **`DL_FUNC` cast syntax is unchanged.**
   The `(DL_FUNC) &fn` idiom is identical for `.C` registration; only the
   surrounding struct type and the additional `types` field change.

4. **Function signatures change.**
   `.C`-registered functions return `void` and receive only basic C pointer
   types (`int *`, `double *`, `char **`). The `SEXP` arguments and return
   values must be decomposed into raw pointers in both the C function and the
   calling R code. Memory allocation (previously handled by `allocVector` /
   `PROTECT` inside the C functions) must be performed in R before the `.C`
   call.

5. **`DL_FUNC` itself requires no redefinition.**
   The `typedef void * (*DL_FUNC)(void)` in `Rdynload.h` is generic enough to
   hold both `.Call`-style and `.C`-style function pointers after the
   appropriate cast. No source change to the typedef is needed.

6. **`R_useDynamicSymbols` and `R_forceSymbols` are unchanged.**
   These calls operate on `DllInfo` and are independent of the API flavour.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Registration of `.Call`-style functions using `R_CallMethodDef`

- **Locations:** `init.c`, lines 12–19 (the `CallEntries` table and its use in
  `R_init_rpart`)

- **Original Context (.Call):**

```c
#include "R_ext/Rdynload.h"

/* Forward declarations – all functions return SEXP and accept SEXP args */
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

void R_init_rpart(DllInfo *dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
    R_forceSymbols(dll, TRUE);
}
```

- **C/C++ Equivalent (.C):**

```c
#include "R_ext/Rdynload.h"

/*
 * Forward declarations – all functions now return void and accept only
 * basic C pointer types.  Memory for output arrays is allocated in R
 * and passed in as pre-allocated pointers.
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
 * Common values: REALSXP = 14, INTSXP = 13, LGLSXP = 10.
 */
static R_NativePrimitiveArgType init_rpcallback_types[] = {
    REALSXP, REALSXP, REALSXP, INTSXP, INTSXP, INTSXP   /* 6 args */
};
static R_NativePrimitiveArgType rpartexp2_types[] = {
    REALSXP, INTSXP, REALSXP, INTSXP                     /* 4 args */
};
static R_NativePrimitiveArgType pred_rpart_types[] = {
    INTSXP, INTSXP, INTSXP, INTSXP, INTSXP, INTSXP,
    INTSXP, REALSXP, INTSXP, INTSXP, REALSXP, INTSXP, INTSXP  /* 13 args */
};
/* (define analogous arrays for rpart_c and xpred_c) */

static const R_CMethodDef CEntries[] = {
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c, 6,  init_rpcallback_types},
    {"rpart_c",           (DL_FUNC) &rpart_c,           11, NULL /* fill in */},
    {"xpred_c",           (DL_FUNC) &xpred_c,           15, NULL /* fill in */},
    {"rpartexp2_c",       (DL_FUNC) &rpartexp2_c,        4,  rpartexp2_types},
    {"pred_rpart_c",      (DL_FUNC) &pred_rpart_c,      13, pred_rpart_types},
    {NULL, NULL, 0, NULL}
};

void R_init_rpart(DllInfo *dll)
{
    /* croutines slot (first arg) receives the .C table;
       callRoutines slot (second arg) is now NULL.          */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
    R_forceSymbols(dll, TRUE);
}
```

- **Explanation:**

  | Aspect | `.Call` original | `.C` converted |
  |--------|-----------------|----------------|
  | Registration struct | `R_CallMethodDef` (3 fields: name, fun, numArgs) | `R_CMethodDef` (4 fields: name, fun, numArgs, **types**) |
  | Terminator row | `{NULL, NULL, 0}` | `{NULL, NULL, 0, NULL}` |
  | `R_registerRoutines` slot | 2nd argument (`callRoutines`) | 1st argument (`croutines`) |
  | `(DL_FUNC)` cast syntax | `(DL_FUNC) &fn` | **identical** — no change |
  | Function return type | `SEXP` | `void` |
  | Function argument types | `SEXP` per argument | `int *`, `double *`, etc. per argument |
  | Output values | returned as `SEXP` | passed as additional pointer arguments; pre-allocated in R |
  | `types` field | absent | required; use `R_NativePrimitiveArgType[]` array or `NULL` to skip type-checking |

  The `(DL_FUNC) &fn` cast is purely a type-erasure mechanism and requires
  **no syntactic change** during migration. The structural changes are entirely
  in the surrounding `R_CMethodDef` struct (addition of the `types` field) and
  in the `R_registerRoutines` argument order. Each concrete registered function
  must separately be rewritten to accept raw pointers instead of `SEXP` objects,
  but that transformation is governed by the guides for `SEXP`, `PROTECT`,
  `INTEGER`, `REAL`, etc., not by `DL_FUNC` itself.

---

### Pattern: Type-erasing cast of a function pointer to `DL_FUNC`

- **Locations:** `init.c`, lines 13–17 (every `(DL_FUNC) &<fn>` expression)

- **Original Context (.Call):**

```c
{"rpartexp2", (DL_FUNC) &rpartexp2, 2},
```

  where `rpartexp2` has signature `SEXP rpartexp2(SEXP, SEXP)`.

- **C/C++ Equivalent (.C):**

```c
{"rpartexp2_c", (DL_FUNC) &rpartexp2_c, 4, rpartexp2_types},
```

  where `rpartexp2_c` has signature
  `void rpartexp2_c(double *dtimes, int *n, double *eps, int *keep)`.

- **Explanation:**

  The `(DL_FUNC)` cast is a C-standard void-function-pointer cast and is
  valid for any function pointer regardless of the actual signature. It is
  needed because `R_CMethodDef.fun` is typed as `DL_FUNC` (i.e.,
  `void *(*)(void)`) to allow a heterogeneous table of functions with different
  signatures. The programmer is responsible for ensuring the actual call site
  (R's `.C()` dispatcher) invokes the function with the correct argument types
  as declared in the `types` array. No change to the cast syntax is required
  during migration; only the pointed-to function's signature changes.
