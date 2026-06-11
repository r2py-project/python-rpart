# Conversion Guide: `INTEGER`

## 1. Overview of `INTEGER` in R API

`INTEGER` is a function declared in `Rinternals.h` as `int *(INTEGER)(SEXP x)`.
It accepts a `SEXP` that must be of type `INTSXP` (R's integer vector type, type
code 13) and returns a writable `int *` pointer to the contiguous block of `int`
values stored inside that object. In the `.Call/.External` API it serves as the
standard accessor macro for both input integer vectors (extracting the raw data
pointer for use in C arithmetic) and freshly allocated output buffers (unwrapping
the `SEXP` returned by `allocVector(INTSXP, n)` or `allocMatrix(INTSXP, r, c)`
immediately after allocation). Under the `.C/.Fortran` API `INTEGER` is entirely
absent: integer data arrives directly as a pre-allocated `int *` argument, so no
SEXP wrapper exists to be unwrapped.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `pred_rpart.c` | 140 | `pred_rpart0(INTEGER(dimx), …, INTEGER(where));` |
| `rpart.c` | 75 | `ncat = INTEGER(ncat2);` |
| `rpart.c` | 76 | `xgrp = INTEGER(xgrp2);` |
| `rpart.c` | 112 | `rp.numcat = INTEGER(ncat2);` |
| `rpart.c` | 195 | `rp.which = INTEGER(which3);` |
| `rpart.c` | 279 | `iptr = INTEGER(inode3);` |
| `rpart.c` | 286 | `iptr = INTEGER(isplit3);` |
| `rpart.c` | 295 | `iptr = INTEGER(csplit3);` |
| `rpart_callback.c` | 69 | `ndata = INTEGER(stemp);` |
| `rpartexp2.c` | 48 | `Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));` |
| `xpred.c` | 69 | `ncat = INTEGER(ncat2);` |
| `xpred.c` | 70 | `xgrp = INTEGER(xgrp2);` |
| `xpred.c` | 110 | `rp.numcat = INTEGER(ncat2);` |

### Data types involved

- `INTEGER` always returns `int *`. The receiving variables in the source code are:
  - `int *ncat` (local pointer, `rpart.c` line 57 and `xpred.c` line 54)
  - `int *xgrp` (local pointer, `rpart.c` line 57 and `xpred.c` line 54)
  - `int *numcat` (struct member `rp.numcat`, declared `int *numcat` in `rpart.h` line 56)
  - `int *which` (struct member `rp.which`, declared `int *which` in `rpart.h` line 71)
  - `int *iptr` (local pointer used to walk matrix buffers)
  - `int *ndata` (static module-level pointer in `rpart_callback.c` line 40)
  - Direct passing as function argument (e.g. `INTEGER(where)` in `pred_rpart.c:140` and `INTEGER(keep)` in `rpartexp2.c:48`)

### Memory management context

All `SEXP` objects whose data is extracted by `INTEGER` fall into two categories:

1. **Input SEXPs** — `ncat2`, `xgrp2`, `dimx`, `nodes2`, `vnum`, `csplit2`,
   `usesur`, `xmiss2`, `stemp` — arrive as function arguments or from
   `R_getVar`. They are owned by the R caller; no `PROTECT` is needed in C.
2. **Output SEXPs** — `where`, `which3`, `inode3`, `isplit3`, `csplit3`, `keep`
   — are created by `PROTECT(allocVector(INTSXP, …))` or
   `PROTECT(allocMatrix(INTSXP, …))` immediately before `INTEGER` is called to
   obtain the writable pointer. The `UNPROTECT` matching call appears at the end
   of each function.

### Distinct implementation patterns

1. **Unwrapping an input integer vector into a local `int *` variable** —
   `rpart.c` lines 75–76 and 112; `xpred.c` lines 69–70 and 110. A `SEXP` input
   argument is unwrapped once at the start of the function and the resulting
   pointer is used throughout.

2. **Unwrapping an input integer vector to pass directly as a function argument**
   — `pred_rpart.c` line 140. `INTEGER(dimx)`, `INTEGER(dimc)`, etc. appear
   inline within a function call argument list.

3. **Unwrapping a freshly allocated output integer vector** — `rpart.c` line 195
   (`rp.which = INTEGER(which3)`); `rpartexp2.c` line 48 (inline pass to
   `Rpartexp2`). The `SEXP` was just created with `allocVector(INTSXP, n)`.

4. **Unwrapping a freshly allocated output integer matrix to build a ragged-array
   index** — `rpart.c` lines 279, 286, 295. The `SEXP` was created with
   `allocMatrix(INTSXP, …)` and `INTEGER` returns the base pointer; a loop then
   sets up an array of `int *` column pointers (`iinode[]`, `iisplit[]`,
   `ccsplit[]`).

5. **Unwrapping a dynamically retrieved SEXP variable** — `rpart_callback.c`
   line 69. `stemp` is obtained via `R_getVar` from an R environment rather than
   being a direct function argument. This pattern is part of the callback
   mechanism that depends on R's evaluator and cannot be ported to `.C`.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under `.Call`, `INTEGER(sexp)` is the universal gate between R's opaque `SEXP`
handle and the raw `int *` pointer that C code actually needs. Under `.C`, this
gate does not exist and is not needed: the `.C` dispatcher passes each `integer`
R vector directly as an `int *` to the C function, so the pointer is available
immediately as a function argument with no unwrapping step.

The complete transformation is:

1. **Remove `INTEGER(sexp)` calls entirely.** Every occurrence is replaced by the
   corresponding `int *` function argument name. The assignment
   `ptr = INTEGER(sexp)` becomes `ptr = sexp_arg`; the inline use
   `func(…, INTEGER(sexp), …)` becomes `func(…, sexp_arg, …)`.

2. **Replace input `SEXP` function parameters with `int *`.** Each `SEXP`
   argument that is unwrapped via `INTEGER` becomes a `const int *` parameter.
   The `const` qualifier is appropriate for input-only vectors to signal
   read-only intent.

3. **Replace output `SEXP` allocations with pre-allocated `int *` arguments.**
   Each `SEXP out = PROTECT(allocVector(INTSXP, n))` or
   `SEXP out = PROTECT(allocMatrix(INTSXP, r, c))` pattern is removed from C and
   replaced by a pre-allocated `int *` argument. The R caller supplies it as
   `integer(n)` or `integer(r * c)` respectively before the `.C(…)` call.

4. **Remove `PROTECT` / `UNPROTECT` pairs** associated with the removed
   allocations.

5. **Declare argument types in `R_NativePrimitiveArgType[]`.** Each `int *`
   argument in the new signature must be annotated as `INTSXP` in the
   registration array so that R's `.C` dispatcher coerces and type-checks it
   automatically.

6. **The `rpart_callback.c` pattern cannot be ported.** The `INTEGER(stemp)`
   call at line 69 is embedded in a function that uses `R_getVar`, `eval`, and a
   persistent `SEXP rho` environment handle. These are `.Call`-only mechanisms
   with no `.C` equivalent. This subsystem must remain as a `.Call` function or
   be restructured by moving R-level evaluation to the R caller.

This strategy is fully `.C`-compatible because after the transformation every
integer argument is a plain `int *` pointer known at call time; no R object
introspection or garbage-collector interaction is required inside C.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Unwrapping Input Integer Vectors into Local Pointers

- **Locations:** `rpart.c` lines 75–76, 112; `xpred.c` lines 69–70, 110

- **Original Context (.Call):**

```c
/* rpart.c:57-76 — function signature excerpt and unwrapping */
SEXP rpart(SEXP ncat2, SEXP method2, SEXP opt2,
           SEXP parms2, SEXP xvals2, SEXP xgrp2,
           SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2)
{
    int *ncat, *xgrp;
    /* ... */
    ncat = INTEGER(ncat2);   /* line 75 */
    xgrp = INTEGER(xgrp2);   /* line 76 */
    /* ... */
    rp.numcat = INTEGER(ncat2); /* line 112 — second use of same SEXP */
}

/* xpred.c:34-70 — identical pattern */
SEXP xpred(SEXP ncat2, …, SEXP xgrp2, …)
{
    int *ncat, *xgrp;
    ncat = INTEGER(ncat2);   /* line 69 */
    xgrp = INTEGER(xgrp2);   /* line 70 */
    /* ... */
    rp.numcat = INTEGER(ncat2); /* line 110 */
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * ncat2 and xgrp2 become const int * arguments directly.
 * INTEGER() calls are removed; the pointer is used as-is.
 */
void rpart_c(const int *ncat,   /* was: SEXP ncat2, then ncat = INTEGER(ncat2) */
             const int *xgrp,   /* was: SEXP xgrp2, then xgrp = INTEGER(xgrp2) */
             /* ... other args ... */)
{
    /* No unwrapping needed — ncat and xgrp are already int * */
    rp.numcat = ncat;   /* was: rp.numcat = INTEGER(ncat2) */

    /* downstream code using ncat[i] and xgrp[i] is unchanged */
}
```

Corresponding R-side call:

```r
result <- .C("rpart_c",
             ncat  = as.integer(ncat_vec),
             xgrp  = as.integer(xgrp_vec),
             # ... other args ...
             )
```

- **Explanation:**
  - `SEXP ncat2` is replaced by `const int *ncat`; `INTEGER(ncat2)` disappears
    entirely because `ncat` already is an `int *`.
  - The second use of the same pointer (`rp.numcat = INTEGER(ncat2)` /
    `rp.numcat = ncat`) becomes a direct struct-member assignment from the
    already-available argument.
  - No length information is embedded in the argument itself; if the function
    body needs `LENGTH(ncat2)`, an additional `const int *ncat_len` scalar must
    be added and supplied as `as.integer(length(ncat_vec))` from R.

---

### Pattern: Unwrapping Input Integer Vectors Inline in a Function Call

- **Locations:** `pred_rpart.c` line 140

- **Original Context (.Call):**

```c
/* pred_rpart.c:133-147 */
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
                SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
                SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2)
{
    int n = asInteger(dimx);
    SEXP where = PROTECT(allocVector(INTSXP, n));
    pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit),
                INTEGER(dimc), INTEGER(nnum), INTEGER(nodes2),
                INTEGER(vnum), REAL(split2), INTEGER(csplit2),
                INTEGER(usesur), REAL(xdata2), INTEGER(xmiss2),
                INTEGER(where));
    UNPROTECT(1);
    return where;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Every SEXP argument becomes a typed C pointer.
 * INTEGER(x) inline uses disappear; the pointer argument is passed directly.
 * The output SEXP (where) becomes a pre-allocated int * output argument.
 */
void pred_rpart_c(const int    *n,        /* scalar: was asInteger(dimx)        */
                  const int    *dimx,     /* was INTEGER(dimx) — full int array */
                  const int    *nnode,    /* was asInteger(nnode) — scalar      */
                  const int    *nsplit,   /* was asInteger(nsplit) — scalar     */
                  const int    *dimc,
                  const int    *nnum,
                  const int    *nodes2,
                  const int    *vnum,
                  const double *split2,
                  const int    *csplit2,
                  const int    *usesur,
                  const double *xdata2,
                  const int    *xmiss2,
                  int          *where)    /* pre-allocated output: integer(n[0]) */
{
    pred_rpart0(dimx, nnode[0], nsplit[0],
                dimc, nnum, nodes2,
                vnum, split2, csplit2,
                usesur, xdata2, xmiss2,
                where);
    /* No UNPROTECT needed; no return value */
}
```

Corresponding R-side call:

```r
n <- as.integer(dimx[1])   # first element of dimx is nrow
result <- .C("pred_rpart_c",
             n       = n,
             dimx    = as.integer(dimx),
             nnode   = as.integer(nnode),
             nsplit  = as.integer(nsplit),
             dimc    = as.integer(dimc),
             nnum    = as.integer(nnum),
             nodes2  = as.integer(nodes2),
             vnum    = as.integer(vnum),
             split2  = as.double(split2),
             csplit2 = as.integer(csplit2),
             usesur  = as.integer(usesur),
             xdata2  = as.double(xdata2),
             xmiss2  = as.integer(xmiss2),
             where   = integer(n))   # pre-allocated output
where_vec <- result$where
```

- **Explanation:**
  - Each `INTEGER(sexp)` inline in the argument list of `pred_rpart0` is replaced
    by the corresponding `const int *` argument name directly.
  - `asInteger(nnode)` and `asInteger(nsplit)` become `nnode[0]` and `nsplit[0]`
    (scalars arrive as single-element `int *` under `.C`).
  - `PROTECT(allocVector(INTSXP, n))` is removed; `where` is supplied as
    `integer(n)` by the R caller.
  - `UNPROTECT(1)` and `return where` are removed; the function is `void` and the
    output is recovered via `result$where` after the `.C` call.

---

### Pattern: Unwrapping a Freshly Allocated Output Integer Vector

- **Locations:** `rpart.c` line 195; `rpartexp2.c` line 48

- **Original Context (.Call):**

```c
/* rpart.c:194-198 — allocate then immediately unwrap */
which3 = PROTECT(allocVector(INTSXP, n));
rp.which = INTEGER(which3);
for (i = 0; i < n; i++)
    rp.which[i] = 1;

/* rpartexp2.c:46-50 — allocate, unwrap inline, return */
int n = LENGTH(dtimes);
SEXP keep = PROTECT(allocVector(INTSXP, n));
Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
UNPROTECT(1);
return keep;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The SEXP allocation and INTEGER() unwrapping are replaced by a pre-allocated
 * int * output argument supplied by the R caller.
 */

/* rpart pattern */
void rpart_c(/* ... other args ... */,
             int *which,        /* pre-allocated: integer(n) */
             /* ... */)
{
    rp.which = which;           /* was: rp.which = INTEGER(which3) */
    for (int i = 0; i < n; i++)
        rp.which[i] = 1;
    /* No UNPROTECT needed */
}

/* rpartexp2 pattern */
void rpartexp2_c(const double *dtimes,
                 const int    *n,       /* was: LENGTH(dtimes) — must be explicit */
                 const double *eps,     /* was: asReal(eps) */
                 int          *keep)    /* pre-allocated: integer(*n) */
{
    Rpartexp2(*n, dtimes, *eps, keep);  /* INTEGER(keep) -> keep directly */
}
```

Corresponding R-side calls:

```r
# rpartexp2 pattern
n <- as.integer(length(dtimes))
result <- .C("rpartexp2_c",
             dtimes = as.double(dtimes),
             n      = n,
             eps    = as.double(eps),
             keep   = integer(n))
keep_vec <- result$keep
```

- **Explanation:**
  - `PROTECT(allocVector(INTSXP, n))` is removed; the storage is provided by
    `integer(n)` on the R side.
  - `INTEGER(which3)` / `INTEGER(keep)` vanish because `which` and `keep` are
    already `int *` arguments.
  - For `rpartexp2`, `LENGTH(dtimes)` cannot be derived inside a `.C` function
    (there is no `SEXP` to query); it must be passed as an explicit `const int *n`
    scalar argument from R.
  - `UNPROTECT(1)` is removed. `return keep` / `return which3` are removed; the
    function returns `void` and outputs are read from the `.C` result list.

---

### Pattern: Unwrapping a Freshly Allocated Integer Matrix to Build a Ragged-Array Index

- **Locations:** `rpart.c` lines 279 (`inode3`), 286 (`isplit3`), 295 (`csplit3`)

- **Original Context (.Call):**

```c
/* rpart.c:278-303 */
inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));
iptr = INTEGER(inode3);
for (i = 0; i < 6; i++) {
    iinode[i] = iptr;
    iptr += nodecount;
}

isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));
iptr = INTEGER(isplit3);
for (i = 0; i < 3; i++) {
    iisplit[i] = iptr;
    iptr += splitcount;
}

if (catcount > 0) {
    csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));
    ccsplit = (int **) ALLOC(maxcat, sizeof(int *));
    iptr = INTEGER(csplit3);
    for (i = 0; i < maxcat; i++) {
        ccsplit[i] = iptr;
        iptr += catcount;
        for (j = 0; j < catcount; j++)
            ccsplit[i][j] = 0;
    }
} else
    ccsplit = NULL;

rpmatrix(tree, rp.numcat, ddsplit, iisplit, ccsplit, ddnode, iinode, 1);
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Each matrix becomes a pre-allocated flat int * buffer.
 * INTEGER(mat) -> the corresponding argument pointer.
 * Ragged-array setup loops and downstream rpmatrix call are unchanged.
 */
void rpart_c(/* ... */,
             const int *nodecount_arg,   /* scalar */
             const int *splitcount_arg,  /* scalar */
             const int *catcount_arg,    /* scalar */
             const int *maxcat_arg,      /* scalar */
             int       *inode,           /* pre-allocated: integer(nodecount * 6)          */
             int       *isplit,          /* pre-allocated: integer(splitcount * 3)         */
             int       *csplit,          /* pre-allocated: integer(catcount * maxcat) or
                                            integer(0) when catcount == 0                 */
             /* ... */)
{
    int nodecount  = *nodecount_arg;
    int splitcount = *splitcount_arg;
    int catcount   = *catcount_arg;
    int maxcat     = *maxcat_arg;
    int *iinode[6], *iisplit[3];
    int **ccsplit_ptr = NULL;
    int *iptr;

    /* inode matrix ragged-array setup */
    iptr = inode;                   /* was: INTEGER(inode3) */
    for (int i = 0; i < 6; i++) {
        iinode[i] = iptr;
        iptr += nodecount;
    }

    /* isplit matrix ragged-array setup */
    iptr = isplit;                  /* was: INTEGER(isplit3) */
    for (int i = 0; i < 3; i++) {
        iisplit[i] = iptr;
        iptr += splitcount;
    }

    /* csplit matrix ragged-array setup — conditional */
    if (catcount > 0) {
        ccsplit_ptr = (int **) R_alloc(maxcat, sizeof(int *));
        iptr = csplit;              /* was: INTEGER(csplit3) */
        for (int i = 0; i < maxcat; i++) {
            ccsplit_ptr[i] = iptr;
            iptr += catcount;
            for (int j = 0; j < catcount; j++)
                ccsplit_ptr[i][j] = 0;
        }
    }

    rpmatrix(tree, rp.numcat, ddsplit, iisplit, ccsplit_ptr, ddnode, iinode, 1);
    /* No UNPROTECT needed */
}
```

Corresponding R-side call:

```r
csplit_len <- if (catcount > 0L) catcount * maxcat else 0L

result <- .C("rpart_c",
             # ...
             nodecount_arg  = as.integer(nodecount),
             splitcount_arg = as.integer(splitcount),
             catcount_arg   = as.integer(catcount),
             maxcat_arg     = as.integer(maxcat),
             inode          = integer(nodecount * 6L),
             isplit         = integer(splitcount * 3L),
             csplit         = integer(csplit_len),
             # ...)

# Recover as proper R matrices
inode_mat  <- matrix(result$inode,  nrow = nodecount,  ncol = 6L)
isplit_mat <- matrix(result$isplit, nrow = splitcount, ncol = 3L)
if (catcount > 0L)
    csplit_mat <- matrix(result$csplit, nrow = catcount, ncol = maxcat)
```

- **Explanation:**
  - `allocMatrix(INTSXP, r, c)` is replaced by `integer(r * c)` in R. R stores
    matrices column-major, so the flat buffer layout matches the C loop structure
    (`iptr += nrow` steps one column forward).
  - `INTEGER(inode3)`, `INTEGER(isplit3)`, and `INTEGER(csplit3)` each become the
    corresponding pre-allocated `int *` argument (`inode`, `isplit`, `csplit`).
  - `PROTECT` / `UNPROTECT` for all three matrices are removed.
  - `ALLOC(maxcat, sizeof(int *))` (which uses `R_alloc` under the hood; see
    `rpart.h` line 25) is preserved as `R_alloc(maxcat, sizeof(int *))` for the
    ragged-array index — this is scratch memory automatically freed when the `.C`
    call returns.
  - The conditional `integer(0)` path for `csplit` when `catcount == 0` is safe
    because the C code guards all access with `if (catcount > 0)`.
  - After the call, `matrix(result$inode, nrow = nodecount, ncol = 6)` on the R
    side restores the 2-D structure previously encoded in the `SEXP`'s `dim`
    attribute.

---

### Pattern: Unwrapping a Dynamically Retrieved SEXP (Callback — Not Portable to `.C`)

- **Locations:** `rpart_callback.c` line 69

- **Original Context (.Call):**

```c
/* rpart_callback.c:47-71 */
SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;
    rho = rhox;
    /* ... */
    stemp = R_getVar(install("nback"), rho, FALSE);
    ndata = INTEGER(stemp);    /* line 69: unwrap SEXP from R environment */
    return R_NilValue;
}

static int *ndata;   /* module-level pointer, used by later callbacks */
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Direct .C conversion is NOT possible for this pattern.
 *
 * The INTEGER(stemp) call at line 69 depends on:
 *   - R_getVar: retrieving a named R object from a live R environment (SEXP rho)
 *   - A persistent static SEXP rho held across multiple C function calls
 *   - R_NilValue as a sentinel return value
 *
 * None of these operations exist in the .C API.
 *
 * Recommended migration strategy:
 *   Option A — Keep init_rpcallback as a .Call function.
 *     Register only the callback-initialisation and callback-invocation
 *     routines under .Call.  The main rpart computation (which does not use
 *     eval()) can be ported to .C independently.
 *
 *   Option B — Move environment lookups to R.
 *     Pre-extract the integer vector (nback) in R before calling .C, and
 *     pass it as an explicit integer() argument.  The C function receives
 *     the raw int * directly without any R_getVar / INTEGER unwrapping.
 *
 *     Example R-side preparation:
 *       ndata_vec <- get("nback", envir = rho)
 *       result <- .C("rpart_callback_init_c",
 *                    ndata = as.integer(ndata_vec),
 *                    n     = as.integer(length(ndata_vec)),
 *                    ...)
 */
```

- **Explanation:**
  - `R_getVar(install("nback"), rho, FALSE)` retrieves a named variable from an
    R environment using a `SEXP` environment handle. The `.C` API provides no
    equivalent for environment lookup or symbol installation.
  - `INTEGER(stemp)` on the retrieved `SEXP` is the immediate second dependency.
    Even if the environment lookup were somehow bypassed, there is no `SEXP` to
    pass to `INTEGER` under `.C`.
  - The `static SEXP rho` and `static SEXP expr1/expr2` state that persists
    between calls is incompatible with `.C`'s stateless argument-passing model.
  - This is the sole pattern in the CSV that is not mechanically convertible;
    all other `INTEGER` uses in the codebase follow one of the four portable
    patterns above.
