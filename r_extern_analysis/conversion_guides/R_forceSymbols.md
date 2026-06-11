# Conversion Guide: `R_forceSymbols`

## 1. Overview of `R_forceSymbols` in R API

`R_forceSymbols` is a DLL-initialization API function declared in
`R_ext/Rdynload.h` with the signature:

```c
Rboolean R_forceSymbols(DllInfo *info, Rboolean value);
```

It is called from a package's `R_init_<pkgname>` entry point — the function
that R's dynamic loader invokes automatically when the package shared library
is loaded via `library()`. When called with `value = TRUE`, it instructs R to
require that every `.Call`, `.External`, or `.C` invocation targeting this
package DLL must supply a pre-resolved native symbol object (obtained via
`getNativeSymbolInfo()` or implicitly by NAMESPACE `useDynLib` registration),
rather than a plain character string for runtime symbol lookup. This enforces
strict symbol-registration discipline at the R level, prevents ambiguous
symbol resolution across packages, and complements `R_useDynamicSymbols(dll, FALSE)`
which disables ad-hoc name-based lookup on the C side. `R_forceSymbols` was
introduced in R 2.16.0 and carries no heap allocation, no GC interaction, and
no direct relationship to `SEXP` objects or the `.Call`/`.C` argument-marshalling
mechanism.

---

## 2. Contextual Usage Analysis

### Source location

| File | Line | Context |
|------|------|---------|
| `init.c` | 28 | `R_forceSymbols(dll, TRUE);` |

### 31-line window analysis (`init.c`, lines 1–30)

The file is 30 lines in total; the complete listing is reproduced below:

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
Rboolean R_forceSymbols(DllInfo *info, Rboolean value);
```

The two parameters are:
- `info` — a pointer to the `DllInfo` opaque struct representing the loaded
  shared library. Supplied by R's loader at `R_init_<pkg>` call time; never
  constructed, copied, or freed by package code.
- `value` — a `Rboolean` flag (`TRUE = 1` or `FALSE = 0`) controlling whether
  R-level callers are required to use pre-resolved native symbol objects
  (`TRUE`) or are permitted to pass plain character strings for runtime
  lookup (`FALSE`).

The function returns the previous value of the flag (a `Rboolean`), which is
discarded at this call site as is conventional.

### Pattern analysis

The call appears inside `R_init_rpart`, wrapped in a compile-time version guard:

```c
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
```

The guard ensures the call is emitted only on R 2.16.0 and later, where
`R_forceSymbols` exists in the API. On any R version current enough to build
this package, `R_VERSION` is always defined and always `>= R_Version(2, 16, 0)`,
so the guarded block is always compiled in.

The two registration-policy calls work as a pair:

| Call | Effect |
|------|--------|
| `R_useDynamicSymbols(dll, FALSE)` | Prevents unregistered symbols from being resolved by name at the C level |
| `R_forceSymbols(dll, TRUE)` | Requires R-level callers to use pre-resolved native symbol objects |

Together they constitute the recommended strict registration discipline for any
package that exports symbols through `R_registerRoutines`.

### Key observations

- `R_forceSymbols` is **pure DLL-registration infrastructure**. It is
  called once during package load and has no connection to any computational
  kernel or data-processing function.
- Its arguments — `DllInfo *dll` and `Rboolean TRUE` — are both
  infrastructure types (see companion guides `DllInfo.md` and `TRUE.md`).
  Neither involves `SEXP` objects, heap allocation, or GC interaction.
- The function is **API-agnostic**: it does not distinguish between `.Call`,
  `.External`, or `.C` registered routines. It controls symbol-lookup policy
  for the entire DLL regardless of which registration table type
  (`R_CallMethodDef` or `R_CMethodDef`) is used.
- The return value (`Rboolean`, the previous flag state) is discarded. This
  is the standard idiom throughout R package source code.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_forceSymbols` is not a `.Call`-only construct — it is a DLL-loader hook
that is equally applicable (and equally required for correctness) in any
package that uses `R_registerRoutines`, regardless of whether the registered
routines use the `.Call` API or the `.C` API.

The conversion strategy is therefore:

1. **Retain `R_forceSymbols(dll, TRUE)` verbatim.** When migrating
   computational kernels from `.Call` to `.C`, the `R_init_rpart` function
   is updated to register the new `.C` methods in an `R_CMethodDef` table
   (passed as the first argument to `R_registerRoutines`). The
   `R_forceSymbols` call — and its surrounding `R_VERSION` compile-time
   guard — are left entirely unchanged. The flag value `TRUE`, the `dll`
   pointer, and the `#if defined(R_VERSION)` guard have no `.Call`-specific
   semantics.

2. **No header changes are needed.** `R_forceSymbols` is declared in
   `R_ext/Rdynload.h`, which must remain included in `init.c` regardless of
   whether the package uses `.Call` or `.C`. The `Rboolean` type it requires
   is brought in transitively via `R_ext/Boolean.h`.

3. **No type mapping is required.** Unlike `SEXP`, `PROTECT`, `allocVector`,
   or `INTEGER`, `R_forceSymbols` is not a memory-management or
   data-access construct. It accepts a `DllInfo *` and a `Rboolean` — both
   of which are also DLL-infrastructure types that persist unchanged in any
   migrated `init.c`.

4. **The only change in `R_init_rpart` when adopting `.C` is the
   registration table.** The `R_registerRoutines` call must be updated so
   that the `R_CMethodDef` table is passed in the first (`croutines`) slot
   and the `R_CallMethodDef` slot (second argument) is set to `NULL`. The
   `R_forceSymbols` and `R_useDynamicSymbols` lines are not touched. See
   companion guides `DllInfo.md` and `R_CallMethodDef.md` for the full
   registration-table migration.

### Why this approach ensures `.C` compatibility

The `.C` API requires that the C function bodies called via `.C(...)` accept
only basic pointer arguments (`int *`, `double *`, etc.) and return `void`.
`R_forceSymbols` operates entirely outside those function bodies — it is
called by R's loader before any user function is invoked. There is therefore
no conflict and no migration work to be done for this specific item.

Retaining `R_forceSymbols(dll, TRUE)` also actively benefits a `.C`-based
package: it enforces that R-side callers must pass pre-resolved symbol
objects to `.C(...)` (the first `.NAME` argument) rather than bare strings,
which is the correct, portable usage pattern for both `.Call` and `.C`.

---

## 4. Step-by-Step Conversion Examples

### Pattern: DLL Symbol-Lookup Policy in the Package Initializer

- **Locations:** `init.c`, line 28

- **Original Context (.Call):**

```c
#include "R_ext/Rdynload.h"
#include <Rversion.h>

/* Registration table for .Call-based routines */
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
    R_forceSymbols(dll, TRUE);   /* require pre-resolved symbol objects */
#endif
}
```

- **C/C++ Equivalent (.C):**

```c
#include "R_ext/Rdynload.h"
#include <Rversion.h>

/*
 * Forward declarations for .C-style routines.
 * All functions return void; outputs are passed as pre-allocated pointer args.
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
 * Registration table for .C-style routines.
 * R_CMethodDef has four fields: name, fun, numArgs, types.
 * Passing NULL for types disables per-argument type checking.
 * The sentinel row must supply all four fields.
 */
static const R_CMethodDef CEntries[] = {
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c,  6, NULL},
    {"rpart_c",           (DL_FUNC) &rpart_c,            11, NULL},
    {"xpred_c",           (DL_FUNC) &xpred_c,            15, NULL},
    {"rpartexp2_c",       (DL_FUNC) &rpartexp2_c,         4, NULL},
    {"pred_rpart_c",      (DL_FUNC) &pred_rpart_c,       13, NULL},
    {NULL, NULL, 0, NULL}
};

void
R_init_rpart(DllInfo * dll)
{
    /*
     * .C table goes in the first (croutines) slot.
     * The second (.Call) slot is now NULL.
     * R_useDynamicSymbols and R_forceSymbols are UNCHANGED.
     */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);   /* identical to the .Call version */
#endif
}
```

- **Explanation:**

  | Aspect | `.Call` original | `.C` converted |
  |--------|-----------------|----------------|
  | `R_forceSymbols(dll, TRUE)` | present | **identical — no change** |
  | `#if defined(R_VERSION) ... R_Version(2, 16, 0)` guard | present | **identical — no change** |
  | `R_useDynamicSymbols(dll, FALSE)` | present | **identical — no change** |
  | `R_registerRoutines` first arg (`croutines`) | `NULL` | `CEntries` (the `R_CMethodDef[]` table) |
  | `R_registerRoutines` second arg (`callRoutines`) | `CallEntries` | `NULL` |
  | Registration struct type | `R_CallMethodDef` | `R_CMethodDef` (adds `types` field) |
  | Registration sentinel | `{NULL, NULL, 0}` | `{NULL, NULL, 0, NULL}` |
  | Registered function return type | `SEXP` | `void` |
  | Registered function argument types | `SEXP` per arg | `int *`, `double *`, etc. |

  `R_forceSymbols` enforces that callers of any routine registered in this
  DLL — whether registered under `.Call` via `R_CallMethodDef` or under `.C`
  via `R_CMethodDef` — must pass a native symbol object rather than a
  character string as the `.NAME` argument. Because this policy applies at
  the R-dispatch level, not inside any C function body, it is completely
  orthogonal to the `.Call`-to-`.C` migration and must be kept in place.

  The `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` guard is
  also preserved unchanged. `R_forceSymbols` was added to the R C API in
  R 2.16.0; any R version able to build this package today satisfies the
  version requirement, but the guard is retained for source compatibility and
  clarity. Full treatment of the `R_VERSION` and `R_Version` macros is in
  the companion guide `R_VERSION.md`.

  The only changes in `R_init_rpart` are in the registration table: the struct
  type (`R_CallMethodDef` becomes `R_CMethodDef`), the four-field sentinel, and
  the argument slot passed to `R_registerRoutines` (second slot to first slot).
  See `R_CallMethodDef.md` and `DllInfo.md` for the full registration-table
  migration details, and `TRUE.md` and `FALSE.md` for treatment of the
  `Rboolean` flag arguments used alongside `R_forceSymbols`.
