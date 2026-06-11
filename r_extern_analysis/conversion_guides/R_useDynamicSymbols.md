# Conversion Guide: `R_useDynamicSymbols`

## 1. Overview of `R_useDynamicSymbols` in R API

`R_useDynamicSymbols` is a DLL-initialization API function declared in
`R_ext/Rdynload.h` with the following signature:

```c
Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value);
```

It is called from a package's `R_init_<pkgname>` entry point — the function
that R's dynamic loader invokes automatically when the package shared library is
loaded via `library()`. When called with `value = FALSE`, it instructs R to
prevent any `.Call`, `.External`, or `.C` invocation from resolving a symbol in
this package's DLL by raw character-string name at runtime; only symbols that
have been explicitly registered via `R_registerRoutines` are resolvable. This
enforces strict symbol-registration discipline on the C side, complements
`R_forceSymbols(dll, TRUE)` (which enforces equivalent discipline on the R side),
and eliminates the cost and ambiguity of dynamic symbol lookup at call time.
`R_useDynamicSymbols` carries no heap allocation, no GC interaction, and no
direct relationship to `SEXP` objects or argument-marshalling.

---

## 2. Contextual Usage Analysis

### Source location

| File | Line | Context |
|------|------|---------|
| `init.c` | 26 | `R_useDynamicSymbols(dll, FALSE);` |

### 31-line window analysis (`init.c`, lines 1–30)

The file is 30 lines in total; the complete listing is the window:

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

### Full header signature (from `~/.conda/envs/r-to-python/lib/R/include/R_ext/Rdynload.h`)

```c
Rboolean R_useDynamicSymbols(DllInfo *info, Rboolean value);
```

The two parameters are:

- `info` — a pointer to the `DllInfo` opaque struct representing the loaded
  shared library. Supplied by R's loader at `R_init_<pkg>` call time; never
  constructed, copied, or freed by package code. See companion guide `DllInfo.md`.
- `value` — a `Rboolean` flag (`TRUE = 1` or `FALSE = 0`) controlling whether
  R may look up unregistered symbols by name at runtime (`TRUE`, the permissive
  default) or whether only explicitly registered symbols are resolvable (`FALSE`,
  the recommended strict setting). See companion guide `FALSE.md` and
  `Rboolean.md` for type details.

The function returns the previous value of the flag (a `Rboolean`), which is
discarded at this call site as is conventional throughout R package source code.

### Pattern analysis

The call appears as the second statement inside `R_init_rpart`, immediately
after `R_registerRoutines`:

```c
void
R_init_rpart(DllInfo * dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);           /* line 26 */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

The two registration-policy calls form a standard complementary pair:

| Call | Scope | Effect |
|------|-------|--------|
| `R_useDynamicSymbols(dll, FALSE)` | C side | Prevents any symbol in this DLL from being resolved by raw character-string name |
| `R_forceSymbols(dll, TRUE)` | R side | Requires R-level callers to pass a pre-resolved native symbol object rather than a string |

Together they constitute the recommended strict registration discipline for any
package that exports routines through `R_registerRoutines`. The `R_forceSymbols`
call is conditionally compiled under `#if defined(R_VERSION) && R_VERSION >=
R_Version(2, 16, 0)`, since that function was introduced in R 2.16.0. In
practice, all R versions capable of building this package satisfy the version
requirement.

### Key observations

- `R_useDynamicSymbols` is **pure DLL-registration infrastructure**. It is
  called once, during package load, before any user function is invoked. It has
  no connection to computational kernels, data processing, or `SEXP` objects.
- Its arguments — `DllInfo *dll` and `Rboolean FALSE` — are both infrastructure
  types. Neither involves heap allocation, GC interaction, or any
  `.Call`/`.C`-specific memory-management concern.
- The function is **API-agnostic**: it does not distinguish between `.Call`,
  `.External`, `.C`, or `.Fortran` registered routines. It controls
  name-based symbol-lookup policy for the entire DLL, regardless of which
  registration table type (`R_CallMethodDef` or `R_CMethodDef`) is used.
- The return value (`Rboolean`, the previous flag state) is discarded. This is
  the standard idiom throughout R package source code.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_useDynamicSymbols` is not a `.Call`-only construct — it is a DLL-loader hook
that is equally applicable (and equally required for correctness) in any package
that uses `R_registerRoutines`, regardless of whether the registered routines use
the `.Call` API or the `.C` API.

The conversion strategy is therefore:

1. **Retain `R_useDynamicSymbols(dll, FALSE)` verbatim.** When migrating
   computational kernels from `.Call` to `.C`, the `R_init_rpart` function is
   updated to register the new `.C` methods in an `R_CMethodDef` table (passed
   as the first argument to `R_registerRoutines`). The `R_useDynamicSymbols`
   call — and the `dll` handle and `FALSE` argument it receives — are left
   entirely unchanged. The `FALSE` value, the `DllInfo *` pass-through, and the
   call position (immediately after `R_registerRoutines`) all carry no
   `.Call`-specific semantics.

2. **No header changes are needed.** `R_useDynamicSymbols` is declared in
   `R_ext/Rdynload.h`, which must remain included in `init.c` regardless of
   whether the package uses `.Call` or `.C`. The `Rboolean` type it requires
   (for the second argument and return value) is brought in transitively via
   `R_ext/Boolean.h`.

3. **No type mapping is required.** Unlike `SEXP`, `PROTECT`, `allocVector`,
   or `INTEGER`, `R_useDynamicSymbols` is not a memory-management or
   data-access construct. It accepts a `DllInfo *` and a `Rboolean` — both DLL
   infrastructure types that persist unchanged in any migrated `init.c`.

4. **The only change in `R_init_rpart` when adopting `.C` is the registration
   table.** The `R_registerRoutines` call must be updated so that the
   `R_CMethodDef` table is passed in the first (`croutines`) slot and the
   `R_CallMethodDef` slot (second argument) is set to `NULL`. The
   `R_useDynamicSymbols` and `R_forceSymbols` lines are not touched. See
   companion guides `R_registerRoutines.md`, `DllInfo.md`, and
   `R_CallMethodDef.md` for the full registration-table migration.

### Why this approach ensures `.C` compatibility

The `.C` API requires that the C function bodies called via `.C(...)` accept
only basic pointer arguments (`int *`, `double *`, etc.) and return `void`.
`R_useDynamicSymbols` operates entirely outside those function bodies — it is
called by R's loader before any user function is invoked. There is therefore no
conflict and no migration work to be done for this specific item.

Retaining `R_useDynamicSymbols(dll, FALSE)` actively benefits a `.C`-based
package: it enforces that R's dispatcher resolves `.C(...)` symbol names only
against the explicitly registered `R_CMethodDef` table, preventing accidental
resolution of unregistered symbols by name, which is the correct and portable
usage pattern for both `.Call` and `.C`.

---

## 4. Step-by-Step Conversion Examples

### Pattern: DLL Dynamic-Symbol-Lookup Policy in the Package Initializer

- **Locations:** `init.c`, line 26

- **Original Context (.Call):**

```c
#include "rpart.h"
#include "R_ext/Rdynload.h"
#include "node.h"
#include "rpartproto.h"

/* Forward declarations — .Call functions return SEXP and accept SEXP arguments */
SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x);
SEXP rpartexp2(SEXP dtimes, SEXP seps);
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
        SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
        SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2);

/* .Call registration table: three-field entries, three-field sentinel */
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
    R_useDynamicSymbols(dll, FALSE);   /* disable name-based symbol resolution */
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
 * Forward declarations for .C-style routines.
 * All functions return void; output values are passed as pre-allocated
 * pointer arguments.  The numArgs field in each R_CMethodDef entry counts
 * ALL pointer arguments including output ones.
 *
 * NOTE: The exact argument lists below are illustrative.  Each registered
 * function must be converted individually (see companion guides SEXP.md,
 * PROTECT.md, INTEGER.md, REAL.md for per-function body transformation).
 */
void init_rpcallback_c(const int *ny, const int *nr,
                       const double *yback, const double *wback,
                       const double *xback, const int *nback);
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
 * .C registration table: four-field entries (name, fun, numArgs, types),
 * four-field sentinel {NULL, NULL, 0, NULL}.
 * Passing NULL for types disables per-argument type checking.
 */
static const R_CMethodDef CEntries[] = {
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c,  6, NULL},
    {"rpart_c",           (DL_FUNC) &rpart_c,            11, NULL},
    {"xpred_c",           (DL_FUNC) &xpred_c,            15, NULL},
    {"rpartexp2_c",       (DL_FUNC) &rpartexp2_c,         4, NULL},
    {"pred_rpart_c",      (DL_FUNC) &pred_rpart_c,       13, NULL},
    {NULL, NULL, 0, NULL}
};

#include <Rversion.h>
void
R_init_rpart(DllInfo * dll)
{
    /*
     * Slot 1 (croutines)    = CEntries (.C table).       <-- CHANGED
     * Slot 2 (callRoutines) = NULL (.Call slot cleared). <-- CHANGED
     * Slots 3 and 4 remain NULL (no .Fortran or .External routines).
     *
     * R_useDynamicSymbols and R_forceSymbols are UNCHANGED.
     */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);   /* identical to the .Call version */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

- **Explanation:**

  | Aspect | `.Call` original | `.C` converted |
  |--------|-----------------|----------------|
  | `R_useDynamicSymbols(dll, FALSE)` | present | **identical — no change** |
  | `dll` argument (first parameter) | `DllInfo *` passed through | **identical — no change** |
  | `FALSE` argument (second parameter) | `Rboolean` value `0` | **identical — no change** |
  | Return value handling | discarded | **identical — no change** |
  | `R_forceSymbols(dll, TRUE)` | present | **identical — no change** |
  | `#if defined(R_VERSION) ... R_Version(2, 16, 0)` guard | present | **identical — no change** |
  | `R_registerRoutines` first arg (`croutines`) | `NULL` | `CEntries` (the `R_CMethodDef[]` table) |
  | `R_registerRoutines` second arg (`callRoutines`) | `CallEntries` | `NULL` |
  | Registration struct type | `R_CallMethodDef` (3 fields) | `R_CMethodDef` (4 fields, adds `types`) |
  | Sentinel row | `{NULL, NULL, 0}` | `{NULL, NULL, 0, NULL}` |
  | Registered function return type | `SEXP` | `void` |
  | Registered function argument types | `SEXP` per argument | `int *`, `double *`, etc. |
  | `numArgs` count | input-only `SEXP` count | all pointer args (inputs + outputs) |

  `R_useDynamicSymbols` enforces that symbol resolution for this DLL is
  restricted to names that have been explicitly registered via
  `R_registerRoutines`. Because this policy is applied at the DLL level — not
  inside any individual C function body — it is completely orthogonal to whether
  the registered routines use the `.Call` or `.C` dispatch mechanism. The call
  must be kept in place in the converted `R_init_rpart` to preserve the
  registration discipline.

  The `FALSE` argument (a `Rboolean` value resolving to the integer `0`) has
  exactly the same meaning under `.C` registration as under `.Call` registration:
  it tells R not to fall back to dynamic name-based lookup for any symbol in
  this DLL. Because `R_ext/Rdynload.h` (which declares `R_useDynamicSymbols`)
  is included in `init.c` for both `.Call` and `.C` packages, the `Rboolean`
  type and the `FALSE` constant remain available without any additional includes.

  The substantial migration work is not in `R_useDynamicSymbols` itself but in
  (a) swapping the `R_CallMethodDef` table to an `R_CMethodDef` table in the
  `R_registerRoutines` call, and (b) rewriting each individual registered
  routine body to remove `SEXP` return types, `PROTECT`/`UNPROTECT`/`allocVector`
  calls, and `REAL`/`INTEGER` accessor macros. Those transformations are detailed
  in companion guides `R_registerRoutines.md`, `R_CallMethodDef.md`, `DllInfo.md`,
  `SEXP.md`, `PROTECT.md`, `INTEGER.md`, `REAL.md`, `INTSXP.md`, `REALSXP.md`,
  `FALSE.md`, and `Rboolean.md`.
