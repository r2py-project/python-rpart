# Conversion Guide: `DL_FUNC`

---

## 1. Overview of `DL_FUNC` in R API

`DL_FUNC` is a generic function pointer type defined in `R_ext/Rdynload.h` as `typedef void * (*DL_FUNC)(void)`. Its sole purpose is to serve as a uniform, type-erased function pointer used when registering native C/C++ routines with R's dynamic loading infrastructure. It appears exclusively inside `R_CallMethodDef`, `R_CMethodDef`, `R_FortranMethodDef`, and `R_ExternalMethodDef` registration tables, which are passed to `R_registerRoutines()` during package initialization so that R can locate and dispatch compiled functions via `.Call`, `.External`, `.C`, or `.Fortran`.

---

## 2. Contextual Usage Analysis

### Source Window: `rpart/src/init.c`, line 12

The complete `init.c` file is short (31 lines) and entirely devoted to registration bookkeeping. Its structure is:

1. **Lines 6-10** — Forward declarations of functions whose definitions live in other translation units (`init_rpcallback`, `rpartexp2`, `pred_rpart`). The signatures of `rpart` and `xpred` come from `rpartproto.h`.
2. **Lines 12-19** — A `static const R_CallMethodDef CallEntries[]` table. Each entry is a three-field struct `{name, DL_FUNC-cast function pointer, argument count}`. The sentinel `{NULL, NULL, 0}` terminates the array.
3. **Lines 22-30** — `R_init_rpart(DllInfo *dll)`, the mandatory package load hook. It calls `R_registerRoutines`, `R_useDynamicSymbols(dll, FALSE)` (disabling symbol search by name to force use of the registration table), and `R_forceSymbols(dll, TRUE)` (requiring that R-level calls use `getNativeSymbolInfo` rather than bare string names).

### Registered functions and their `.Call` signatures

| R name | C function | SEXP argument count |
|---|---|---|
| `init_rpcallback` | `init_rpcallback` | 5 |
| `rpart` | `rpart` | 11 |
| `xpred` | `xpred` | 15 |
| `rpartexp2` | `rpartexp2` | 2 |
| `pred_rpart` | `pred_rpart` | 12 |

All five functions return `SEXP` and accept only `SEXP` arguments, which is the canonical `.Call` convention.

### Data types and memory management macros present

- `DL_FUNC` — generic function pointer; used only for casting, not for calling.
- `R_CallMethodDef` — struct `{const char *name; DL_FUNC fun; int numArgs;}`.
- `DllInfo *` — opaque handle to the loaded shared object; supplied by R to `R_init_<pkg>`.
- No `PROTECT`/`UNPROTECT`, no `allocVector`, no `SEXP` object manipulation occurs in `init.c` itself.

### Distinct usage pattern

There is exactly one usage pattern: **casting a C function pointer to `DL_FUNC` inside an `R_CallMethodDef` entry for `.Call` registration**. No `.C`/`.Fortran` registration is present.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

When migrating functions from the `.Call` API to the `.C` API, the registration mechanism must change in two coordinated ways:

| Aspect | `.Call` (current) | `.C` (target) |
|---|---|---|
| Registration struct | `R_CallMethodDef` | `R_CMethodDef` |
| Function pointer field | `DL_FUNC fun` | `DL_FUNC fun` (same field) |
| Arg-type information | `int numArgs` only | `int numArgs` + `R_NativePrimitiveArgType *types` array |
| Function signature | `SEXP fn(SEXP, SEXP, ...)` | `void fn(int *, double *, ...)` |
| `R_registerRoutines` slot | second argument (`callRoutines`) | first argument (`croutines`) |
| R-side call | `.Call("name", ...)` | `.C("name", ...)` |

`DL_FUNC` itself — `typedef void * (*DL_FUNC)(void)` — is **not removed**. It is reused without change inside `R_CMethodDef` as well. The cast `(DL_FUNC) &fn` remains identical in syntax. The key transformation is that:

1. The surrounding struct type changes from `R_CallMethodDef` to `R_CMethodDef`.
2. The struct literal gains an additional `types` field pointing to an array of `R_NativePrimitiveArgType` values that encode each argument's primitive C type.
3. The `R_registerRoutines` call passes the table in the first (C) slot instead of the second (Call) slot.
4. Each registered C function must be rewritten from `SEXP fn(SEXP a, SEXP b, ...)` to `void fn(type1 *a, type2 *b, ...)` with all memory pre-allocated by the R caller.

This approach ensures `.C` API compatibility because R's `.C` dispatcher does not pass `SEXP` objects; it copies raw C scalars and vectors across the R–C boundary using the type table.

---

## 4. Step-by-Step Conversion Examples

### Pattern: `.Call` Registration Table Using `DL_FUNC` Casts

- **Locations:** `init.c`, line 12 (the entire `CallEntries` array and `R_init_rpart` body)

- **Original Context (.Call):**

```c
#include "R_ext/Rdynload.h"

/* Forward declarations — all functions return SEXP and accept only SEXP args */
SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x);
SEXP rpart(SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2, SEXP ymat2,
           SEXP xmat2, SEXP xvals2, SEXP xgrp2, SEXP wt2, SEXP ny2, SEXP cost2);
SEXP xpred(SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2, SEXP xvals2,
           SEXP xgrp2, SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2,
           SEXP cost2, SEXP all2, SEXP cp2, SEXP toprisk2, SEXP nresp2);
SEXP rpartexp2(SEXP dtimes, SEXP seps);
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
                SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
                SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2);

/* Registration table for .Call */
static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart",           (DL_FUNC) &rpart,            11},
    {"xpred",           (DL_FUNC) &xpred,            15},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,         2},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,       12},
    {NULL, NULL, 0}
};

void R_init_rpart(DllInfo *dll) {
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
    R_forceSymbols(dll, TRUE);
}
```

- **C/C++ Equivalent (.C):**

```c
#include "R_ext/Rdynload.h"

/*
 * Step 1: Rewrite every registered function.
 * - Return type changes from SEXP to void.
 * - Every SEXP argument becomes a raw C pointer (int *, double *, etc.)
 *   whose storage is allocated by the R caller before .C() is invoked.
 * - Internal PROTECT/UNPROTECT/allocVector calls are removed entirely.
 *
 * Example sketches (actual argument types depend on each function's logic):
 */
void init_rpcallback(int *nr, int *ny, int *n_expr,
                     double *rho_vals, double *expr_vals);

void rpart(int *ncat, int *method, double *opt, double *parms,
           double *ymat, double *xmat, int *xvals, int *xgrp,
           double *wt, int *ny, double *cost);

void xpred(int *ncat, int *method, double *opt, double *parms,
           int *xvals, int *xgrp, double *ymat, double *xmat,
           double *wt, int *ny, double *cost, int *all,
           double *cp, double *toprisk, int *nresp);

void rpartexp2(double *dtimes, double *seps);

void pred_rpart(int *dimx, int *nnode, int *nsplit, int *dimc,
                int *nnum, int *nodes, int *vnum, double *split,
                int *csplit, int *usesur, double *xdata, int *xmiss);

/*
 * Step 2: Build a type descriptor array for each function.
 * R_NativePrimitiveArgType values:
 *   INTSXP  = 13  (int *)
 *   REALSXP = 14  (double *)
 *   LGLSXP  =  10  (int *, logical)
 *
 * One array per function, length == numArgs.
 */
static R_NativePrimitiveArgType init_rpcallback_t[] = {
    INTSXP, INTSXP, INTSXP, REALSXP, REALSXP   /* 5 args */
};

static R_NativePrimitiveArgType rpart_t[] = {
    INTSXP, INTSXP, REALSXP, REALSXP,
    REALSXP, REALSXP, INTSXP, INTSXP,
    REALSXP, INTSXP, REALSXP                    /* 11 args */
};

static R_NativePrimitiveArgType xpred_t[] = {
    INTSXP, INTSXP, REALSXP, REALSXP,
    INTSXP, INTSXP, REALSXP, REALSXP,
    REALSXP, INTSXP, REALSXP, INTSXP,
    REALSXP, REALSXP, INTSXP                    /* 15 args */
};

static R_NativePrimitiveArgType rpartexp2_t[] = {
    REALSXP, REALSXP                            /* 2 args */
};

static R_NativePrimitiveArgType pred_rpart_t[] = {
    INTSXP, INTSXP, INTSXP, INTSXP,
    INTSXP, INTSXP, INTSXP, REALSXP,
    INTSXP, INTSXP, REALSXP, INTSXP            /* 12 args */
};

/*
 * Step 3: Replace R_CallMethodDef with R_CMethodDef.
 * Each entry gains a fourth field: the types array pointer.
 * The DL_FUNC cast syntax is identical.
 */
static const R_CMethodDef CEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback,  5, init_rpcallback_t},
    {"rpart",           (DL_FUNC) &rpart,            11, rpart_t},
    {"xpred",           (DL_FUNC) &xpred,            15, xpred_t},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,         2, rpartexp2_t},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,       12, pred_rpart_t},
    {NULL, NULL, 0, NULL}
};

/*
 * Step 4: Pass the table in the first (croutines) slot of
 * R_registerRoutines instead of the second (callRoutines) slot.
 * DllInfo * and the overall hook name are unchanged.
 */
void R_init_rpart(DllInfo *dll) {
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
    R_forceSymbols(dll, TRUE);
}
```

- **Explanation:**

  1. **`DL_FUNC` cast syntax is unchanged.** The expression `(DL_FUNC) &fn` is identical in both `R_CallMethodDef` and `R_CMethodDef` entries. `DL_FUNC` itself requires no conversion; it is a stable type in `R_ext/Rdynload.h`.

  2. **Struct type changes from `R_CallMethodDef` to `R_CMethodDef`.** `R_CMethodDef` carries a fourth field `R_NativePrimitiveArgType *types`, which encodes each argument's primitive C type. The `.Call` struct omits this field because `.Call` passes raw `SEXP` objects and does not need type coercion metadata.

  3. **`R_registerRoutines` slot shifts.** The signature is `R_registerRoutines(dll, croutines, callRoutines, fortranRoutines, externalRoutines)`. Moving the table from slot 2 (Call) to slot 1 (C) is the only change to this call site. `R_useDynamicSymbols` and `R_forceSymbols` remain identical.

  4. **Function signatures must be rewritten.** Every `SEXP fn(SEXP, ...)` becomes `void fn(type *, ...)`. R's `.C` dispatcher does not pass `SEXP` handles; it performs a shallow copy of each argument into a C-typed buffer and passes a pointer to that buffer. Return values are communicated by mutating one of the pointer arguments in place, not by returning a value. All `PROTECT`/`UNPROTECT` and `allocVector` calls inside the function bodies must be removed; the R script is responsible for pre-allocating every output vector before calling `.C(...)`.

  5. **Indexing convention.** R vectors are 1-based at the R level but 0-based when addressed through a `int *` or `double *` pointer in C. This is unchanged by the migration — the same offset arithmetic that applied inside the original `.Call` functions applies unchanged to the raw pointer versions.

  6. **R-side call site.** Every `.Call("rpart", arg1, ..., arg11)` invocation in R scripts must be replaced with a `.C("rpart", as.integer(arg1), ..., as.double(arg11))` invocation, and the pre-allocated output buffers must be passed as additional arguments. The return value of `.C` is a named list of the (possibly modified) argument vectors.

---

*Guide generated for `DL_FUNC` as found in `rpart/src/init.c`.*
