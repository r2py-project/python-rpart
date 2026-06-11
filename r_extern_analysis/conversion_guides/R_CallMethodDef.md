# Conversion Guide: `R_CallMethodDef`

## 1. Overview of `R_CallMethodDef` in R API

`R_CallMethodDef` is a plain C struct defined in `R_ext/Rdynload.h` that
describes a single entry in a package's `.Call`-API registration table. Each
instance holds three fields: `const char *name` (the R-visible symbol name),
`DL_FUNC fun` (a type-erased pointer to the implementing C function cast via
`(DL_FUNC) &fn`), and `int numArgs` (the number of `SEXP` arguments the
function expects). An array of these structs, terminated by a `{NULL, NULL, 0}`
sentinel, is passed to `R_registerRoutines` as the `callRoutines` (second)
argument so that R's dynamic loader can bind `.Call("name", ...)` invocations
to the corresponding compiled routines at package load time.

---

## 2. Contextual Usage Analysis

### Source location

| File | Line | Context |
|------|------|---------|
| `init.c` | 12–19 | `static const R_CallMethodDef CallEntries[]` — the full registration table |

### 31-line window analysis (`init.c`, lines 1–30)

The complete `init.c` file is 30 lines and is reproduced in full below:

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

### Struct definition (from `R_ext/Rdynload.h`)

```c
typedef struct {
    const char *name;    /* R-level symbol name used in .Call("name", ...) */
    DL_FUNC     fun;     /* type-erased function pointer: (DL_FUNC) &fn     */
    int         numArgs; /* number of SEXP arguments expected               */
} R_CallMethodDef;

typedef R_CallMethodDef R_ExternalMethodDef;  /* alias used by .External   */
```

### Registered functions and their `.Call` signatures

| R-level name | C function | numArgs | C signature |
|---|---|---|---|
| `init_rpcallback` | `init_rpcallback` | 5 | `SEXP(SEXP, SEXP, SEXP, SEXP, SEXP)` |
| `rpart` | `rpart` | 11 | `SEXP(SEXP x11)` |
| `xpred` | `xpred` | 15 | `SEXP(SEXP x15)` |
| `rpartexp2` | `rpartexp2` | 2 | `SEXP(SEXP, SEXP)` |
| `pred_rpart` | `pred_rpart` | 12 | `SEXP(SEXP x12)` |

### Key observations

- `R_CallMethodDef` appears **once** in `init.c`: as the element type of the
  `CallEntries` array (lines 12–19). No other source file in `rpart/src/`
  references this struct directly; all other files contain only the function
  bodies that are pointed to by entries in the table.
- Every entry casts its function pointer with `(DL_FUNC) &fn`. This cast is
  required because `DL_FUNC` is `typedef void *(*DL_FUNC)(void)` — a
  void/void function pointer used as a universal storage type. The actual
  dispatch is performed by R's `.Call` dispatcher, which re-casts the pointer
  to the correct signature at call time.
- The array is terminated by the mandatory `{NULL, NULL, 0}` sentinel row.
  R's registration loop iterates until `name == NULL`.
- `CallEntries` is passed to `R_registerRoutines` in the **second** argument
  slot (`callRoutines`); the first (`.C`), third (`.Fortran`), and fourth
  (`.External`) slots are all `NULL`.
- `R_useDynamicSymbols(dll, FALSE)` prevents R from searching the shared
  library for unregistered symbols; `R_forceSymbols(dll, TRUE)` requires that
  callers use the registered name rather than a raw string. Both settings are
  API-agnostic and must be preserved in the converted version.
- There are no R memory-management macros (`PROTECT`, `UNPROTECT`,
  `allocVector`) inside `init.c`; those are confined to the bodies of the
  individual registered functions.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_CallMethodDef` is the registration infrastructure for the `.Call` API,
where every registered function receives `SEXP` objects as arguments and
returns a `SEXP`. Moving to the `.C` API requires replacing this struct and
its table with the analogous `.C` infrastructure type, `R_CMethodDef`, which
is defined in the same header:

```c
typedef struct {
    const char *name;
    DL_FUNC     fun;
    int         numArgs;
    R_NativePrimitiveArgType *types;   /* additional field absent in R_CallMethodDef */
} R_CMethodDef;
```

The conversion involves four coordinated changes:

1. **Replace `R_CallMethodDef[]` with `R_CMethodDef[]`.**
   The `R_CMethodDef` struct adds a fourth field, `types`, which is a pointer
   to an array of `R_NativePrimitiveArgType` values (one per argument)
   declaring the C type of each parameter. Supplying `NULL` disables
   argument-type checking at the R level; supplying a filled array enables it.
   Common type constants are `INTSXP` (13), `REALSXP` (14), and `LGLSXP` (10),
   reused from `Rinternals.h` as `R_NativePrimitiveArgType` values.

2. **Update the sentinel row.**
   `R_CallMethodDef`'s three-field sentinel `{NULL, NULL, 0}` must become
   `R_CMethodDef`'s four-field sentinel `{NULL, NULL, 0, NULL}`.

3. **Move the table to the correct slot in `R_registerRoutines`.**
   The `.C`-method table occupies the **first** argument (`croutines`); the
   `.Call` slot (second argument) becomes `NULL`:
   ```c
   /* Before (.Call): */
   R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);

   /* After (.C): */
   R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
   ```
   The `dll` pointer, `R_useDynamicSymbols`, and `R_forceSymbols` calls are
   unchanged.

4. **Rewrite every registered function.**
   Each C function body must be converted independently:
   - Return type changes from `SEXP` to `void`.
   - Each `SEXP` parameter becomes the appropriate C pointer type (`int *`,
     `double *`, `char **`).
   - Return values become additional pointer arguments whose storage is
     pre-allocated in the calling R code before the `.C(...)` call.
   - All `PROTECT`/`UNPROTECT`/`allocVector` calls are removed from C;
     allocation moves to R.
   The `numArgs` field must be updated to reflect the new, expanded argument
   list (since output pointers count as additional arguments under `.C`).

This approach is required because R's `.C` dispatcher passes each argument as
a raw C pointer obtained from the pre-allocated R object; it does not support
`SEXP`-returning functions or R-internal memory allocation inside the called
routine.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Full `.Call` registration table (`R_CallMethodDef[]` array)

- **Locations:** `init.c`, lines 12–19

- **Original Context (.Call):**

```c
#include "R_ext/Rdynload.h"

/* Forward declarations — all functions return SEXP and accept SEXP arguments */
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
 * Forward declarations — all functions now return void.
 * Output values are passed as additional pre-allocated pointer arguments.
 * The numArgs field in each R_CMethodDef entry counts ALL pointer arguments,
 * including the output ones.
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
 * type checking by R's .C dispatcher.  Use INTSXP=13, REALSXP=14, LGLSXP=10.
 * Pass NULL in the types field to skip checking.
 */
static R_NativePrimitiveArgType rpartexp2_types[] = {
    REALSXP,  /* dtimes  */
    INTSXP,   /* n       */
    REALSXP,  /* eps     */
    INTSXP    /* keep    */
};

/*
 * R_CMethodDef has four fields: name, fun, numArgs, types.
 * The sentinel row must provide all four fields: {NULL, NULL, 0, NULL}.
 */
static const R_CMethodDef CEntries[] = {
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c,  6, NULL},
    {"rpart_c",           (DL_FUNC) &rpart_c,            11, NULL},
    {"xpred_c",           (DL_FUNC) &xpred_c,            15, NULL},
    {"rpartexp2_c",       (DL_FUNC) &rpartexp2_c,         4, rpartexp2_types},
    {"pred_rpart_c",      (DL_FUNC) &pred_rpart_c,       13, NULL},
    {NULL, NULL, 0, NULL}   /* four-field sentinel required by R_CMethodDef */
};

void R_init_rpart(DllInfo *dll)
{
    /* .C table goes in the first (croutines) slot; second slot is now NULL */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
    R_forceSymbols(dll, TRUE);
}
```

- **Explanation:**

  | Aspect | `.Call` original | `.C` converted |
  |--------|-----------------|----------------|
  | Struct type | `R_CallMethodDef` | `R_CMethodDef` |
  | Struct fields | `name`, `fun`, `numArgs` (3 fields) | `name`, `fun`, `numArgs`, `types` (4 fields) |
  | Sentinel row | `{NULL, NULL, 0}` | `{NULL, NULL, 0, NULL}` |
  | `R_registerRoutines` slot | 2nd argument (`callRoutines`) | 1st argument (`croutines`) |
  | `(DL_FUNC) &fn` cast syntax | unchanged | **identical — no change required** |
  | Registered function return type | `SEXP` | `void` |
  | Registered function argument types | `SEXP` per argument | `int *`, `double *`, etc. |
  | `numArgs` count | number of `SEXP` inputs | number of ALL pointer args (inputs + outputs) |
  | Output values | returned as `SEXP` | additional pointer args; pre-allocated in R |
  | `R_useDynamicSymbols` / `R_forceSymbols` | present | **identical — no change** |
  | `types` field | absent | `R_NativePrimitiveArgType[]` array, or `NULL` to skip |

  The `(DL_FUNC) &fn` cast is purely a type-erasure mechanism shared by both
  `R_CallMethodDef` and `R_CMethodDef`; its syntax does not change. The only
  structural changes to the table are: (a) the enclosing struct gains a
  `types` field, (b) the sentinel gains a fourth `NULL`, (c) the table is
  passed to a different argument position of `R_registerRoutines`, and (d)
  the function bodies pointed to by each entry must be independently converted
  to void-returning, pointer-argument functions (see the `DL_FUNC`, `SEXP`,
  `PROTECT`, `INTSXP`, and `REALSXP` conversion guides for those details).

---

### Pattern: Individual `R_CallMethodDef` entry — `.Call`-registered function with SEXP output

- **Locations:** `init.c`, line 16 (`rpartexp2` entry, representative of all five entries)

- **Original Context (.Call):**

```c
/* Entry in R_CallMethodDef table */
{"rpartexp2", (DL_FUNC) &rpartexp2, 2},

/* Corresponding C function — returns SEXP, accepts SEXP inputs */
SEXP rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);
    return keep;
}
```

- **C/C++ Equivalent (.C):**

```c
/* Entry in R_CMethodDef table — numArgs increased from 2 to 4 */
{"rpartexp2_c", (DL_FUNC) &rpartexp2_c, 4, rpartexp2_types},

/* Corresponding C function — void return, raw pointer arguments */
void rpartexp2_c(double *dtimes, int *n, double *eps, int *keep)
{
    /* 'keep' is pre-allocated by the caller (R) as integer(n[0])  */
    /* 'n' is passed as a length-1 integer pointer per .C convention */
    Rpartexp2(*n, dtimes, *eps, keep);
}
```

```r
# Corresponding R caller — allocates output before invoking .C
rpartexp2_r <- function(dtimes, eps) {
    n <- length(dtimes)
    result <- .C("rpartexp2_c",
                 dtimes  = as.double(dtimes),
                 n       = as.integer(n),
                 eps     = as.double(eps),
                 keep    = integer(n))   # pre-allocated output vector
    result$keep
}
```

- **Explanation:**

  Under `.Call`, the C wrapper (`rpartexp2`) allocates the output vector
  (`allocVector(INTSXP, n)`), protects it from garbage collection (`PROTECT`),
  extracts raw pointers (`REAL`, `INTEGER`) to pass to the internal worker
  (`Rpartexp2`), then returns the `SEXP`. The `R_CallMethodDef` entry records
  `numArgs = 2` because only two `SEXP` objects cross the `.Call` boundary.

  Under `.C`, allocation moves entirely to R: the caller creates `integer(n)`
  before the `.C(...)` call. The C function receives four raw pointers —
  `double *dtimes`, `int *n`, `double *eps`, `int *keep` — and writes results
  directly into the pre-allocated `keep` buffer. The `R_CMethodDef` entry
  therefore records `numArgs = 4`. The scalar arguments `n` and `eps` are
  wrapped in length-1 vectors by R's `.C` dispatcher (which always passes
  pointers), so the C code dereferences them with `*n` and `*eps`. All
  `PROTECT`, `UNPROTECT`, and `allocVector` calls are absent from the
  converted C function.
