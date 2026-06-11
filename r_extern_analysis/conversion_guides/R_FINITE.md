# Conversion Guide: `R_FINITE`

## 1. Overview of `R_FINITE` in R API

`R_FINITE(x)` is a macro defined in `R_ext/Arith.h` (pulled in transitively by `R.h`) that tests whether a `double` value is a finite real number — i.e., it returns a non-zero (true) result if and only if `x` is neither a positive infinity, negative infinity, an IEEE 754 NaN, **nor** R's special `NA_real_` sentinel. It accepts a single `double` argument and returns an `int` (non-zero for finite, zero for non-finite). On systems that provide a working C99 `isfinite` (virtually all modern platforms), the macro expands directly to `isfinite(x)` from `<math.h>`; on older systems it falls back to R's internal `R_finite(double)` function. `R_FINITE` is the logical complement of `ISNAN`/`isnan` extended to also reject infinities, and it is the primary tool used throughout rpart's C sources to distinguish valid predictor values from missing or degenerate ones.

## 2. Contextual Usage Analysis

### Data types involved

All five call sites operate on elements of `double **xdata` (or `double **rp.xdata`), a two-dimensional jagged array where the first index is the variable (predictor column) and the second index is the observation row. The scalars tested by `R_FINITE` are therefore plain `double` values; no `SEXP` wrapper is involved at the point of the check.

### Memory-management macros used alongside

`R_FINITE` is a pure predicate with no side effects. None of the five call sites involve `PROTECT`, `UNPROTECT`, `allocVector`, or any other R memory-management macro. The surrounding logic uses only standard C constructs (`for` loops, pointer arithmetic, integer sentinel encoding).

### Distinct usage patterns

Two functionally distinct patterns are present across the five locations:

| Pattern | Files / Lines | Description |
|---|---|---|
| **A — Positive guard: branch on finite value** | `branch.c:39`, `branch.c:59` | `if (R_FINITE(...))` — execute the split/surrogate logic only when the predictor value is present (finite). |
| **B — Negative guard: skip or mark non-finite value** | `nodesplit.c:107`, `rpart.c:154`, `xpred.c:153` | `if (!R_FINITE(...))` — skip the observation or encode it as missing (negative sort index) when the predictor value is absent. |

### Pattern A detail — `branch.c` lines 39 and 59

```
xdata = rp.xdata;   // double **
j = tsplit->var_num;
if (R_FINITE(xdata[j][obs])) {
    // process primary split (line 39) or surrogate split (line 59)
}
```

`xdata[j][obs]` is a `double`. The guard ensures that the split logic (continuous threshold comparison or categorical lookup) runs only when the predictor is not missing.

### Pattern B detail — `nodesplit.c` line 107

```
double **xdata;   // local alias for rp.xdata
var = tsplit->var_num;
if (!R_FINITE(xdata[var][j]))
    continue;   // skip observation; surrogate is missing
```

### Pattern B detail — `rpart.c` line 154 and `xpred.c` line 153 (identical logic)

```
for (i = 0; i < rp.nvar; i++) {
    rp.sorts[i] = rp.sorts[0] + i * n;
    for (k = 0; k < n; k++) {
        if (!R_FINITE(rp.xdata[i][k])) {
            rp.tempvec[k] = -(k + 1);   /* encode as missing */
            rp.xtemp[k] = 0;
        } else {
            rp.tempvec[k] = k;
            rp.xtemp[k] = rp.xdata[i][k];
        }
    }
    ...
}
```

The non-finite test drives the missing-value sentinel encoding scheme: observation `k` is stored as the negative value `-(k+1)` in the sort index array when its predictor is missing. This sentinel convention is a pure C design choice and is unaffected by the API migration.

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_FINITE` has no dependency on R's object model, memory management, or `SEXP` types. Its entire implementation reduces to a single C99 standard-library call. The conversion strategy is therefore a direct textual substitution rather than a structural rewrite:

| Remove | Replace with | Header required |
|---|---|---|
| `#include <R.h>` (pulls in `R_ext/Arith.h`) | `#include <math.h>` | `<math.h>` (C) or `<cmath>` (C++) |
| `R_FINITE(x)` | `isfinite(x)` | `<math.h>` / C99 |

Under the `.C`/`.Fortran` API, all predictor data arrives as pre-allocated `double *` (or `double **` reconstructed from a flat pointer) arguments — exactly the type that `isfinite` operates on. There is no `SEXP` unwrapping step, no `REAL()` accessor, and no `PROTECT`/`UNPROTECT` pair needed at these sites. The surrounding loop structures, sentinel encoding logic, and surrogate traversal code remain syntactically identical after the substitution.

### Why this ensures `.C` API compatibility

The `.C` interface passes raw C pointers (`double *`, `int *`, etc.) directly between R and compiled code. `isfinite` from `<math.h>` is a standard C99 predicate that works on plain `double` scalars with no runtime dependency on R's internals. Replacing `R_FINITE` with `isfinite` therefore removes the only R-specific symbol at these call sites without changing any observable behavior.

Note: `isfinite` returns true (non-zero) for exactly the same set of values as `R_FINITE` on all platforms where `HAVE_WORKING_ISFINITE` is defined (the common case). On platforms where `R_FINITE` would fall back to `R_finite()`, `isfinite` from a standards-conforming `<math.h>` provides identical semantics for all standard IEEE 754 values. R's `NA_real_` is stored as an IEEE NaN, so `isfinite(NA_real_)` correctly returns 0 (false), matching `R_FINITE` behavior.

## 4. Step-by-Step Conversion Examples

### Pattern A: Positive guard — execute split logic only for finite predictor value

- **Locations:** `branch.c` line 39, `branch.c` line 59
- **Original Context (.Call):**

```c
/* branch.c — compiled against R.h / R_ext/Arith.h */
#include "rpart.h"   /* pulls in <R.h> which defines R_FINITE */

pNode
branch(pNode tree, int obs)
{
    int j, dir;
    double **xdata;

    xdata = rp.xdata;
    tsplit = me->primary;
    j = tsplit->var_num;

    /* Pattern A — primary split */
    if (R_FINITE(xdata[j][obs])) {
        if (rp.numcat[j] == 0) {        /* continuous */
            dir = (xdata[j][obs] < tsplit->spoint) ?
                tsplit->csplit[0] : -tsplit->csplit[0];
            goto down;
        } else {                        /* categorical predictor */
            category = (int) xdata[j][obs];
            dir = (tsplit->csplit)[category - 1];
            if (dir)
                goto down;
        }
    }

    /* Pattern A — surrogate split (line 59) */
    for (tsplit = me->surrogate; tsplit; tsplit = tsplit->nextsplit) {
        j = tsplit->var_num;
        if (R_FINITE(xdata[j][obs])) {  /* not missing */
            ...
        }
    }
}
```

- **C/C++ Equivalent (.C):**

```c
/* branch.c — compiled without R.h; uses standard <math.h> */
#include <math.h>   /* provides isfinite() */
/* Remove: #include "rpart.h" if it pulls in <R.h>.
   Replace rpart.h's R_FINITE usage with isfinite() throughout,
   or redefine the project macro:
       #define R_FINITE(x) isfinite(x)
   in the updated rpart.h */

/* Pattern A — primary split */
if (isfinite(xdata[j][obs])) {
    if (rp.numcat[j] == 0) {        /* continuous */
        dir = (xdata[j][obs] < tsplit->spoint) ?
            tsplit->csplit[0] : -tsplit->csplit[0];
        goto down;
    } else {                        /* categorical predictor */
        category = (int) xdata[j][obs];
        dir = (tsplit->csplit)[category - 1];
        if (dir)
            goto down;
    }
}

/* Pattern A — surrogate split */
for (tsplit = me->surrogate; tsplit; tsplit = tsplit->nextsplit) {
    j = tsplit->var_num;
    if (isfinite(xdata[j][obs])) {  /* not missing */
        ...
    }
}
```

- **Explanation:**
  - `R_FINITE(xdata[j][obs])` is replaced by `isfinite(xdata[j][obs])`. Both evaluate to non-zero when the `double` value is a normal, finite real number.
  - `xdata` is `double **` in both the original and converted code; the argument type to `isfinite` is unchanged.
  - No indexing adjustments are required: arrays remain zero-based throughout.
  - No R memory management macros are present at these sites; no changes to the argument list are needed.
  - `<math.h>` must be present. `xpred.c` and `rpart.c` already include it; `branch.c` must add `#include <math.h>` (or have it provided transitively via the updated `rpart.h`).

---

### Pattern B: Negative guard — skip or sentinel-encode non-finite predictor value

- **Locations:** `nodesplit.c` line 107, `rpart.c` line 154, `xpred.c` line 153
- **Original Context (.Call):**

```c
/* rpart.c / xpred.c — compiled against R.h */
#include <math.h>
#include "rpart.h"   /* pulls in R_FINITE via <R.h> */

/* Variant B1 — sentinel encoding (rpart.c:154, xpred.c:153) */
for (i = 0; i < rp.nvar; i++) {
    rp.sorts[i] = rp.sorts[0] + i * n;
    for (k = 0; k < n; k++) {
        if (!R_FINITE(rp.xdata[i][k])) {
            rp.tempvec[k] = -(k + 1);   /* encode missing as negative index */
            rp.xtemp[k] = 0;            /* avoid NaN in sort */
        } else {
            rp.tempvec[k] = k;
            rp.xtemp[k] = rp.xdata[i][k];
        }
    }
    if (ncat[i] == 0)
        mysort(0, n - 1, rp.xtemp, rp.tempvec);
}

/* nodesplit.c — compiled against R.h */
/* Variant B2 — continue past missing surrogate (nodesplit.c:107) */
for (tsplit = me->surrogate; tsplit; tsplit = tsplit->nextsplit) {
    var = tsplit->var_num;
    if (!R_FINITE(xdata[var][j]))
        continue;   /* surrogate value is missing; try next */
    /* ... process surrogate ... */
}
```

- **C/C++ Equivalent (.C):**

```c
/* rpart.c / xpred.c — no R.h dependency */
#include <math.h>   /* isfinite() */

/* Variant B1 — sentinel encoding */
for (i = 0; i < rp.nvar; i++) {
    rp.sorts[i] = rp.sorts[0] + i * n;
    for (k = 0; k < n; k++) {
        if (!isfinite(rp.xdata[i][k])) {
            rp.tempvec[k] = -(k + 1);   /* encode missing as negative index */
            rp.xtemp[k] = 0.0;          /* avoid NaN in sort */
        } else {
            rp.tempvec[k] = k;
            rp.xtemp[k] = rp.xdata[i][k];
        }
    }
    if (ncat[i] == 0)
        mysort(0, n - 1, rp.xtemp, rp.tempvec);
}

/* nodesplit.c — no R.h dependency */
#include <math.h>

/* Variant B2 — continue past missing surrogate */
for (tsplit = me->surrogate; tsplit; tsplit = tsplit->nextsplit) {
    var = tsplit->var_num;
    if (!isfinite(xdata[var][j]))
        continue;   /* surrogate value is missing; try next */
    /* ... process surrogate ... */
}
```

- **Explanation:**
  - `!R_FINITE(x)` is replaced by `!isfinite(x)`. The logical sense (non-finite implies missing) is preserved exactly.
  - R's `NA_real_` is an IEEE NaN; `isfinite(NA_real_)` returns 0 (false), so `!isfinite(NA_real_)` correctly evaluates to true, preserving the missing-value detection semantics of the original `R_FINITE` check.
  - The missing-value sentinel encoding (`-(k+1)`) is a pure C integer convention. It is completely independent of the R API and is retained unchanged.
  - `rp.xdata` is a `double **` populated from a flat `double *` argument received via `.C`. The two-dimensional indexing `rp.xdata[i][k]` remains valid as long as the pointer-to-pointer structure is reconstructed in the same way as under the original `.Call` entry point.
  - No `PROTECT`/`UNPROTECT`, no `allocVector`, and no other R memory-management calls appear at these sites. The argument list of the enclosing C function is unchanged by this substitution.
  - `rpart.c` and `xpred.c` already include `<math.h>` (line 27 of both files); `nodesplit.c` must add `#include <math.h>` after removing its dependence on `<R.h>`.
