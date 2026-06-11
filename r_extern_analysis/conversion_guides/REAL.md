# Conversion Guide: `REAL`

## 1. Overview of `REAL` in R API

`REAL` is a function declared in `Rinternals.h` as `double *(REAL)(SEXP x)`. It accepts a `SEXP` that must be of type `REALSXP` (R's double-precision floating-point vector type, type code 14) and returns a writable `double *` pointer to the contiguous block of `double` values stored inside that object. In the `.Call/.External` API it serves as the standard accessor for both input numeric vectors (extracting the raw data pointer for downstream C arithmetic) and freshly allocated output buffers (unwrapping the `SEXP` returned by `allocVector(REALSXP, n)` or `allocMatrix(REALSXP, nrow, ncol)` immediately after protection). Under the `.C/.Fortran` API, `REAL` is entirely absent: numeric data arrives directly as a pre-allocated `double *` argument, so no `SEXP` wrapper exists to be unwrapped.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `pred_rpart.c` | 140 | `pred_rpart0(…, REAL(split2), …, REAL(xdata2), …);` |
| `rpart.c` | 78 | `wt = REAL(wt2);` |
| `rpart.c` | 79 | `parms = REAL(parms2);` |
| `rpart.c` | 96 | `dptr = REAL(opt2);` |
| `rpart.c` | 115 | `rp.vcost = REAL(cost2);` |
| `rpart.c` | 122 | `dptr = REAL(xmat2);` |
| `rpart.c` | 130 | `dptr = REAL(ymat2);` |
| `rpart.c` | 243 | `dptr = REAL(cptable3);` |
| `rpart.c` | 263 | `dptr = REAL(dnode3);` |
| `rpart.c` | 270 | `dptr = REAL(dsplit3);` |
| `rpart_callback.c` | 60 | `ydata = REAL(stemp);` |
| `rpart_callback.c` | 63 | `wdata = REAL(stemp);` |
| `rpart_callback.c` | 66 | `xdata = REAL(stemp);` |
| `rpart_callback.c` | 117 | `dptr = REAL(value);` |
| `rpart_callback.c` | 150 | `dptr = REAL(goodness);` |
| `rpartexp2.c` | 48 | `Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));` |
| `xpred.c` | 72 | `wt = REAL(wt2);` |
| `xpred.c` | 73 | `parms = REAL(parms2);` |
| `xpred.c` | 75 | `cp = REAL(cp2);` |
| `xpred.c` | 94 | `dptr = REAL(opt2);` |
| `xpred.c` | 113 | `rp.vcost = REAL(cost2);` |
| `xpred.c` | 121 | `dptr = REAL(xmat2);` |
| `xpred.c` | 129 | `dptr = REAL(ymat2);` |
| `xpred.c` | 210 | `predict = REAL(predict2);` |

### Data types involved

`REAL` always returns `double *`. The receiving variables in the source code are:

- `double *wt` — local pointer to case weights vector (`rpart.c` line 78; `xpred.c` line 72)
- `double *parms` — local pointer to extra split-function parameters (`rpart.c` line 79; `xpred.c` line 73)
- `double *cp` — local pointer to the cp cutpoints vector (`xpred.c` line 75)
- `double *dptr` — general-purpose traversal/temp pointer used to walk flat option, matrix, or output buffers (`rpart.c` lines 96, 122, 130, 243, 263, 270; `xpred.c` lines 94, 121, 129; `rpart_callback.c` lines 117, 150)
- `rp.vcost` — struct member of type `double *`, pointing to variable cost vector (`rpart.c` line 115; `xpred.c` line 113)
- Static module-level `double *ydata`, `double *wdata`, `double *xdata` — persistent pointers in the callback subsystem (`rpart_callback.c` lines 60, 63, 66)
- `double *predict` — output prediction buffer (`xpred.c` line 210)
- Inline pass directly as a function argument: `REAL(split2)`, `REAL(xdata2)` in `pred_rpart.c` line 140; `REAL(dtimes)` in `rpartexp2.c` line 48

### Memory management context

All `SEXP` objects whose data is extracted by `REAL` fall into two categories:

1. **Input SEXPs** — `wt2`, `parms2`, `opt2`, `cost2`, `xmat2`, `ymat2`, `cp2`, `split2`, `xdata2`, `dtimes` — arrive as `.Call` function arguments or from R environment lookups (`R_getVar`). They are owned by the R caller; no `PROTECT` is needed for them in C.
2. **Output SEXPs** — `cptable3`, `dnode3`, `dsplit3`, `predict2` — are created immediately before the `REAL` call by `PROTECT(allocMatrix(REALSXP, …))` or `PROTECT(allocVector(REALSXP, …))` and must be included in the terminal `UNPROTECT` count. The guide for `REALSXP` covers these allocation patterns in detail.

The callback SEXPs (`value`, `goodness`) are created internally by R's `eval()` call and are not protected by the C code, as documented in the source comment: "no need to protect as no memory allocation (or error) below".

### Distinct implementation patterns

1. **Unwrapping an input real vector into a local `double *` variable** — `rpart.c` lines 78–79, 96, 115; `xpred.c` lines 72–73, 75, 94, 113. A `SEXP` input argument is unwrapped once early in the function and the resulting pointer is used throughout.

2. **Unwrapping an input real matrix to build a ragged-array index** — `rpart.c` lines 122–126, 130–133; `xpred.c` lines 121–125, 129–132. `REAL(xmat2)` / `REAL(ymat2)` is assigned to `dptr`, which is then incremented in a loop to populate `rp.xdata[]` or `rp.ydata[]` (arrays of `double *` column/row pointers).

3. **Unwrapping a real vector inline as a function argument** — `pred_rpart.c` line 140; `rpartexp2.c` line 48. `REAL(sexp)` appears directly inside a function call argument list without an intermediate assignment.

4. **Unwrapping a freshly allocated output real matrix** — `rpart.c` lines 243, 263, 270; `xpred.c` line 210. The `SEXP` was just created by `PROTECT(allocMatrix/allocVector(REALSXP, …))` and `REAL` returns its base pointer immediately. These patterns are covered as allocation-side conversions in the `REALSXP` guide; the `REAL` call itself is replaced by the incoming `double *` argument.

5. **Unwrapping a dynamically evaluated SEXP in the callback subsystem** — `rpart_callback.c` lines 60, 63, 66, 117, 150. `REAL(stemp)` extracts data from a `SEXP` retrieved via `R_getVar` (lines 59, 62, 65) or from the result of `eval()` (lines 112, 146). This pattern depends on the `.Call` evaluator and cannot be mechanically ported to `.C`.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under `.Call`, `REAL(sexp)` is the universal gate between R's opaque `SEXP` handle and the raw `double *` pointer that C code needs. Under `.C`, this gate does not exist and is not needed: the `.C` dispatcher passes each `numeric` (double) R vector directly as a `double *` to the C function, so the pointer is available immediately as a function argument with no unwrapping step.

The complete transformation is:

1. **Remove `REAL(sexp)` calls entirely.** Every occurrence is replaced by the corresponding `double *` function argument name. The assignment `ptr = REAL(sexp)` becomes `ptr = sexp_arg`; the inline use `func(…, REAL(sexp), …)` becomes `func(…, sexp_arg, …)`.

2. **Replace input `SEXP` function parameters with `double *`.** Each `SEXP` argument that is unwrapped via `REAL` becomes a `const double *` parameter. The `const` qualifier signals read-only intent for input-only vectors.

3. **Replace output `SEXP` allocations with pre-allocated `double *` arguments.** Each `SEXP out = PROTECT(allocVector(REALSXP, n))` or `SEXP out = PROTECT(allocMatrix(REALSXP, r, c))` pattern is removed from C and replaced by a pre-allocated `double *` argument. The R caller supplies it as `numeric(n)` or `numeric(r * c)` respectively before the `.C(…)` call. See the `REALSXP` guide for full allocation-side details.

4. **Remove `PROTECT` / `UNPROTECT` pairs** associated with removed `REALSXP` allocations.

5. **Declare argument types in `R_NativePrimitiveArgType[]`.** Each `double *` argument in the new signature must be annotated as `REALSXP` in the registration array so that R's `.C` dispatcher coerces and type-checks it automatically.

6. **The callback subsystem cannot be ported.** The `REAL(stemp)` calls at `rpart_callback.c` lines 60, 63, and 66 depend on `R_getVar` and a persistent `SEXP rho` environment handle; the calls at lines 117 and 150 depend on R's `eval()`. These are `.Call`-only mechanisms. This subsystem must remain as `.Call` functions or be restructured by moving R-level evaluation to the R caller.

This strategy is fully `.C`-compatible because after the transformation every double argument is a plain `double *` pointer known at call time; no R object introspection or garbage-collector interaction is required inside C.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Unwrapping Input Real Vectors into Local Pointers

- **Locations:** `rpart.c` lines 78–79, 96, 115; `xpred.c` lines 72–73, 75, 94, 113

- **Original Context (.Call):**

```c
/* rpart.c:40-115 — function signature and unwrapping */
SEXP
rpart(SEXP ncat2, SEXP method2, SEXP opt2,
      SEXP parms2, SEXP xvals2, SEXP xgrp2,
      SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2)
{
    double *wt, *parms;
    double *dptr;
    /* ... */
    wt    = REAL(wt2);       /* line 78: input weights vector */
    parms = REAL(parms2);    /* line 79: extra split parameters */
    /* ... */
    dptr = REAL(opt2);       /* line 96: options double vector */
    rp.min_node  = (int) dptr[1];
    rp.min_split = (int) dptr[0];
    rp.complexity = dptr[2];
    /* ... */
    rp.vcost = REAL(cost2);  /* line 115: variable-cost pointer stored in struct */
}

/* xpred.c:34-113 — identical pattern */
SEXP
xpred(SEXP ncat2, SEXP method2, SEXP opt2,
      SEXP parms2, SEXP xvals2, SEXP xgrp2,
      SEXP ymat2, SEXP xmat2, SEXP wt2,
      SEXP ny2, SEXP cost2, SEXP all2, SEXP cp2, SEXP toprisk2, SEXP nresp2)
{
    double *wt, *parms, *cp;
    double *dptr;
    /* ... */
    wt    = REAL(wt2);       /* line 72 */
    parms = REAL(parms2);    /* line 73 */
    cp    = REAL(cp2);       /* line 75 */
    /* ... */
    dptr = REAL(opt2);       /* line 94 */
    /* ... */
    rp.vcost = REAL(cost2);  /* line 113 */
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Each SEXP input argument unwrapped via REAL becomes a const double * directly.
 * REAL() calls are removed; the pointer arguments are used as-is.
 */
void rpart_c(const int    *ncat,    /* was: SEXP ncat2  -> INTEGER */
             const int    *method,  /* was: SEXP method2 -> asInteger */
             const double *opt,     /* was: SEXP opt2   -> REAL(opt2)   */
             const double *parms,   /* was: SEXP parms2 -> REAL(parms2) */
             const int    *xvals_arg,
             const int    *xgrp,
             const double *ymat,    /* was: SEXP ymat2  -> REAL(ymat2)  */
             const double *xmat,    /* was: SEXP xmat2  -> REAL(xmat2)  */
             const double *wt,      /* was: SEXP wt2    -> REAL(wt2)    */
             const int    *ny,
             const double *cost,    /* was: SEXP cost2  -> REAL(cost2)  */
             /* ... output args ... */)
{
    /* No unwrapping step — pointers are already available */
    rp.wt    = wt;             /* was: rp.wt = wt; where wt = REAL(wt2)   */
    rp.vcost = cost;           /* was: rp.vcost = REAL(cost2)              */

    const double *dptr = opt;  /* was: dptr = REAL(opt2)                   */
    rp.min_node  = (int) dptr[1];
    rp.min_split = (int) dptr[0];
    rp.complexity = dptr[2];
    rp.maxpri = (int) dptr[3] + 1;
    rp.maxsur = (int) dptr[4];
    rp.usesurrogate = (int) dptr[5];
    rp.sur_agree    = (int) dptr[6];
    rp.maxnode = (int) pow(2.0, dptr[7]) - 1;
    /* remaining logic unchanged */
}
```

Corresponding R-side call:

```r
result <- .C("rpart_c",
             ncat    = as.integer(ncat_vec),
             method  = as.integer(method_val),
             opt     = as.double(opt_vec),
             parms   = as.double(parms_vec),
             xvals_arg = as.integer(xvals_val),
             xgrp    = as.integer(xgrp_vec),
             ymat    = as.double(ymat_vec),
             xmat    = as.double(xmat_vec),
             wt      = as.double(wt_vec),
             ny      = as.integer(ny_val),
             cost    = as.double(cost_vec),
             # ... output args (numeric() / integer() pre-allocated) ...
             )
```

- **Explanation:**
  - `SEXP wt2` is replaced by `const double *wt`; `wt = REAL(wt2)` disappears entirely because `wt` is already a `double *`.
  - The same applies to `parms`, `opt` (formerly written to `dptr` after `REAL`), and `cost` (formerly stored in `rp.vcost`).
  - All index arithmetic and struct-member assignments using those pointers are preserved unchanged.
  - Scalar values previously read as `dptr[i]` from an options vector continue to work the same way — `opt[0]`, `opt[1]`, etc.

---

### Pattern: Unwrapping an Input Real Matrix to Build a Ragged-Array Index

- **Locations:** `rpart.c` lines 122–126, 130–133; `xpred.c` lines 121–125, 129–132

- **Original Context (.Call):**

```c
/* rpart.c:122-133 */
dptr = REAL(xmat2);
rp.xdata = (double **) ALLOC(rp.nvar, sizeof(double *));
for (i = 0; i < rp.nvar; i++) {
    rp.xdata[i] = dptr;
    dptr += n;              /* step one column (n rows) forward */
}

dptr = REAL(ymat2);
rp.ydata = (double **) ALLOC(n, sizeof(double *));
for (i = 0; i < n; i++) {
    rp.ydata[i] = dptr;
    dptr += rp.num_y;       /* step one row (num_y columns) forward */
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * xmat and ymat become const double * arguments directly.
 * REAL() is removed; ragged-array index setup is preserved unchanged.
 */
void rpart_c(/* ... other args ... */,
             const double *xmat,    /* was: SEXP xmat2 -> REAL(xmat2); column-major */
             const double *ymat,    /* was: SEXP ymat2 -> REAL(ymat2); row-major    */
             const int    *nvar_arg,/* scalar: rp.nvar = ncols(xmat2)               */
             const int    *n_arg,   /* scalar: rp.n    = nrows(xmat2)               */
             const int    *ny_arg,  /* scalar: rp.num_y                             */
             /* ... */)
{
    int nvar  = *nvar_arg;
    int n     = *n_arg;
    int num_y = *ny_arg;

    const double *dptr;

    /* Build column-pointer ragged array for xmat (column-major) */
    rp.xdata = (double **) R_alloc(nvar, sizeof(double *));
    dptr = xmat;               /* was: dptr = REAL(xmat2) */
    for (int i = 0; i < nvar; i++) {
        rp.xdata[i] = (double *) dptr;
        dptr += n;
    }

    /* Build row-pointer ragged array for ymat (row-major) */
    rp.ydata = (double **) R_alloc(n, sizeof(double *));
    dptr = ymat;               /* was: dptr = REAL(ymat2) */
    for (int i = 0; i < n; i++) {
        rp.ydata[i] = (double *) dptr;
        dptr += num_y;
    }
}
```

Corresponding R-side call:

```r
result <- .C("rpart_c",
             # ... other args ...
             xmat    = as.double(xmat_matrix),   # as.double() flattens column-major
             ymat    = as.double(ymat_matrix),
             nvar_arg = as.integer(ncol(xmat_matrix)),
             n_arg    = as.integer(nrow(xmat_matrix)),
             ny_arg   = as.integer(ncol(ymat_matrix)),
             # ...)
```

- **Explanation:**
  - `SEXP xmat2` is replaced by `const double *xmat`; `dptr = REAL(xmat2)` becomes `dptr = xmat`.
  - `ALLOC(n, sizeof(double *))` — which calls `R_alloc` internally (see `rpart.h`) — is replaced by the explicit `R_alloc(n, sizeof(double *))`. This scratch memory is automatically freed when the `.C` call returns.
  - The `const` cast is dropped when assigning to the `rp.xdata[i]` / `rp.ydata[i]` pointers (which are `double *` not `const double *`) since the rpart computation engine writes through these pointers to temporary scratch. If the engine is known to be read-only, `const double **` is preferred.
  - Dimension values `rp.nvar` (previously computed from `ncols(xmat2)`) and `rp.n` (from `nrows(xmat2)`) must now be passed as explicit scalar `int *` arguments because `ncols()` and `nrows()` query `SEXP` attributes that do not exist under `.C`.

---

### Pattern: Unwrapping a Real Vector Inline in a Function Call

- **Locations:** `pred_rpart.c` line 140; `rpartexp2.c` line 48

- **Original Context (.Call):**

```c
/* pred_rpart.c:133-147 */
SEXP
pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
           SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
           SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2)
{
    int n = asInteger(dimx);
    SEXP where = PROTECT(allocVector(INTSXP, n));
    pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit),
                INTEGER(dimc), INTEGER(nnum), INTEGER(nodes2),
                INTEGER(vnum), REAL(split2), INTEGER(csplit2),    /* REAL inline */
                INTEGER(usesur), REAL(xdata2), INTEGER(xmiss2),  /* REAL inline */
                INTEGER(where));
    UNPROTECT(1);
    return where;
}

/* rpartexp2.c:43-51 */
SEXP
rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));   /* REAL inline */
    UNPROTECT(1);
    return keep;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Every SEXP argument that was passed via REAL() inline becomes a const double *
 * argument directly. REAL() disappears; the argument name is used in its place.
 */

/* pred_rpart pattern */
void pred_rpart_c(const int    *n,        /* scalar: was asInteger(dimx)           */
                  const int    *dimx,     /* was INTEGER(dimx)                     */
                  const int    *nnode,    /* was asInteger(nnode) — scalar         */
                  const int    *nsplit,   /* was asInteger(nsplit) — scalar        */
                  const int    *dimc,
                  const int    *nnum,
                  const int    *nodes2,
                  const int    *vnum,
                  const double *split2,   /* was REAL(split2) inline               */
                  const int    *csplit2,
                  const int    *usesur,
                  const double *xdata2,   /* was REAL(xdata2) inline               */
                  const int    *xmiss2,
                  int          *where)    /* pre-allocated output: integer(n[0])   */
{
    pred_rpart0(dimx, *nnode, *nsplit,
                dimc, nnum, nodes2,
                vnum, split2,   /* was: REAL(split2)  -> split2 directly */
                csplit2,
                usesur, xdata2, /* was: REAL(xdata2)  -> xdata2 directly */
                xmiss2,
                where);
    /* No PROTECT/UNPROTECT; no return value */
}

/* rpartexp2 pattern */
void rpartexp2_c(const double *dtimes,   /* was: SEXP dtimes -> REAL(dtimes)      */
                 const int    *n_arg,    /* was: LENGTH(dtimes) — must be explicit */
                 const double *eps_arg,  /* was: asReal(eps) — scalar double      */
                 int          *keep)     /* pre-allocated output: integer(*n_arg) */
{
    Rpartexp2(*n_arg, dtimes, *eps_arg, keep);
    /* was: Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep)) */
}
```

Corresponding R-side calls:

```r
# pred_rpart pattern
n_val  <- as.integer(dimx[1])
result <- .C("pred_rpart_c",
             n       = n_val,
             dimx    = as.integer(dimx),
             nnode   = as.integer(nnode),
             nsplit  = as.integer(nsplit),
             dimc    = as.integer(dimc),
             nnum    = as.integer(nnum),
             nodes2  = as.integer(nodes2),
             vnum    = as.integer(vnum),
             split2  = as.double(split2),   # formerly REAL(split2)
             csplit2 = as.integer(csplit2),
             usesur  = as.integer(usesur),
             xdata2  = as.double(xdata2),   # formerly REAL(xdata2)
             xmiss2  = as.integer(xmiss2),
             where   = integer(n_val))
where_vec <- result$where

# rpartexp2 pattern
n_val  <- as.integer(length(dtimes))
result <- .C("rpartexp2_c",
             dtimes  = as.double(dtimes),   # formerly REAL(dtimes)
             n_arg   = n_val,
             eps_arg = as.double(eps),
             keep    = integer(n_val))
keep_vec <- result$keep
```

- **Explanation:**
  - `REAL(split2)` and `REAL(xdata2)` inline in the `pred_rpart0(…)` argument list are replaced by the corresponding `const double *` argument names `split2` and `xdata2` directly.
  - `REAL(dtimes)` in `rpartexp2` becomes the `const double *dtimes` argument.
  - `LENGTH(dtimes)` cannot be derived inside a `.C` function; it must be passed as an explicit `const int *n_arg` from R using `as.integer(length(dtimes))`.
  - `asReal(eps)` becomes `*eps_arg` (scalars arrive as single-element `double *` under `.C`).
  - `PROTECT(allocVector(INTSXP, n))` and `UNPROTECT(1)` are removed; the output `where`/`keep` buffer is supplied as `integer(n)` by the R caller.
  - The function signature changes from `SEXP func(SEXP …)` to `void func(…)`.

---

### Pattern: Unwrapping a Freshly Allocated Output Real Matrix

- **Locations:** `rpart.c` lines 243, 263, 270; `xpred.c` line 210

- **Original Context (.Call):**

```c
/* rpart.c:241-276 — three output real matrices allocated then immediately unwrapped */

/* cptable (conditionally sized) */
cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));
dptr = REAL(cptable3);     /* line 243 */
for (cp = cptable; cp; cp = cp->forward) {
    dptr[i++] = cp->cp * scale;
    /* ... */
}

/* dnode matrix */
dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));
ddnode = (double **) ALLOC(3 + rp.num_resp, sizeof(double *));
dptr = REAL(dnode3);       /* line 263 */
for (i = 0; i < 3 + rp.num_resp; i++) {
    ddnode[i] = dptr;
    dptr += nodecount;
}

/* dsplit matrix */
dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));
dptr = REAL(dsplit3);      /* line 270 */
for (i = 0; i < 3; i++) {
    ddsplit[i] = dptr;
    dptr += splitcount;
    for (j = 0; j < splitcount; j++)
        ddsplit[i][j] = 0.0;
}

/* xpred.c:209-210 — output prediction vector */
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);  /* line 210 */
```

- **C/C++ Equivalent (.C):**

```c
/*
 * All allocVector/allocMatrix(REALSXP, …) calls are removed from C.
 * The REAL() unwrapping calls are replaced by the pre-allocated double *
 * output arguments supplied by the R caller.
 */
void rpart_c(/* ... input args ... */,
             const int *nrow_cp_arg,       /* scalar: xvals > 1 ? 5 : 3            */
             const int *num_unique_cp_arg, /* scalar: rp.num_unique_cp             */
             const int *nodecount_arg,     /* scalar                               */
             const int *ncols_dnode_arg,   /* scalar: 3 + rp.num_resp              */
             const int *splitcount_arg,    /* scalar                               */
             double    *cptable_out,       /* pre-allocated: numeric(nrow_cp * num_unique_cp) */
             double    *dnode_out,         /* pre-allocated: numeric(nodecount * ncols_dnode) */
             double    *dsplit_out,        /* pre-allocated: numeric(splitcount * 3) */
             /* ... */)
{
    int nrow_cp     = *nrow_cp_arg;
    int num_ucp     = *num_unique_cp_arg;
    int nodecount   = *nodecount_arg;
    int ncols_dnode = *ncols_dnode_arg;
    int splitcount  = *splitcount_arg;

    /* cptable fill */
    double *dptr = cptable_out;            /* was: dptr = REAL(cptable3) */
    int i = 0;
    for (CpTable cp = cptable; cp; cp = cp->forward) {
        dptr[i++] = cp->cp * scale;
        dptr[i++] = cp->nsplit;
        dptr[i++] = cp->risk * scale;
        if (xvals > 1) {
            dptr[i++] = cp->xrisk * scale;
            dptr[i++] = cp->xstd  * scale;
        }
    }

    /* dnode ragged-array index */
    double **ddnode = (double **) R_alloc(ncols_dnode, sizeof(double *));
    dptr = dnode_out;                      /* was: dptr = REAL(dnode3) */
    for (i = 0; i < ncols_dnode; i++) {
        ddnode[i] = dptr;
        dptr += nodecount;
    }

    /* dsplit ragged-array index with zero-fill */
    double *ddsplit[3];
    dptr = dsplit_out;                     /* was: dptr = REAL(dsplit3) */
    for (i = 0; i < 3; i++) {
        ddsplit[i] = dptr;
        dptr += splitcount;
        for (int j = 0; j < splitcount; j++)
            ddsplit[i][j] = 0.0;
    }

    /* No PROTECT/UNPROTECT needed */
}

void xpred_c(/* ... input args ... */,
             const int *n_arg,
             const int *ncp_arg,
             const int *nresp_arg,
             double    *predict_out)       /* pre-allocated: numeric(n * ncp * nresp) */
{
    int n     = *n_arg;
    int ncp   = *ncp_arg;
    int nresp = *nresp_arg;
    double *predict = predict_out;         /* was: predict = REAL(predict2) */
    /* cross-validation loop unchanged */
}
```

Corresponding R-side call (rpart):

```r
nrow_cp  <- if (xvals > 1L) 5L else 3L
num_ucp  <- as.integer(rp_num_unique_cp)
ncols_dn <- 3L + rp_num_resp

result <- .C("rpart_c",
             # ... input args ...
             nrow_cp_arg       = nrow_cp,
             num_unique_cp_arg = num_ucp,
             nodecount_arg     = as.integer(nodecount),
             ncols_dnode_arg   = ncols_dn,
             splitcount_arg    = as.integer(splitcount),
             cptable_out       = numeric(nrow_cp * num_ucp),
             dnode_out         = numeric(nodecount * ncols_dn),
             dsplit_out        = numeric(splitcount * 3L),
             # ...)

cptable_mat <- matrix(result$cptable_out, nrow = nrow_cp,   ncol = num_ucp)
dnode_mat   <- matrix(result$dnode_out,   nrow = nodecount,  ncol = ncols_dn)
dsplit_mat  <- matrix(result$dsplit_out,  nrow = splitcount, ncol = 3L)
```

- **Explanation:**
  - `allocMatrix(REALSXP, …)` / `allocVector(REALSXP, …)` are removed from C; the R caller provides pre-initialised `numeric()` buffers.
  - `REAL(cptable3)`, `REAL(dnode3)`, `REAL(dsplit3)`, and `REAL(predict2)` each become the corresponding `double *` argument name — no unwrapping step.
  - `PROTECT` / `UNPROTECT` for all these matrices are removed. See the `PROTECT` and `REALSXP` guides for details on the full protection stack removal.
  - Dimension expressions that were previously computed inside C (e.g., `xvals > 1 ? 5 : 3`, `3 + rp.num_resp`) must be pre-evaluated in R and passed as scalar `int *` arguments.
  - After the `.C` call, `matrix(result$dnode_out, nrow = nodecount, ncol = ncols_dn)` restores the 2-D structure previously embedded in the `SEXP`'s `dim` attribute. R stores matrices column-major, matching the memory layout used by the C loops.

---

### Pattern: Unwrapping Dynamically Evaluated SEXPs (Callback Subsystem — Not Portable to `.C`)

- **Locations:** `rpart_callback.c` lines 60, 63, 66 (environment lookup); lines 117, 150 (eval result)

- **Original Context (.Call):**

```c
/* rpart_callback.c:47-71 — REAL from R_getVar */
SEXP
init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;
    rho = rhox;
    /* ... */
    stemp = R_getVar(install("yback"), rho, FALSE);
    ydata = REAL(stemp);    /* line 60: REAL applied to env-retrieved SEXP */

    stemp = R_getVar(install("wback"), rho, FALSE);
    wdata = REAL(stemp);    /* line 63 */

    stemp = R_getVar(install("xback"), rho, FALSE);
    xdata = REAL(stemp);    /* line 66 */
    return R_NilValue;
}

/* rpart_callback.c:88-120 — REAL from eval() result */
void
rpart_callback1(int n, double *y[], double *wt, double *z)
{
    SEXP value;
    double *dptr;
    /* ... fill ydata[], wdata[], ndata[] ... */
    value = eval(expr2, rho);        /* evaluate R expression */
    if (!isReal(value)) error(…);
    dptr = REAL(value);              /* line 117: REAL applied to eval() result */
    for (i = 0; i <= rsave; i++)
        z[i] = dptr[i];
}

/* rpart_callback.c:126-162 — REAL from eval() result */
void
rpart_callback2(int n, int ncat, double *y[], double *wt,
                double *x, double *good)
{
    SEXP goodness;
    double *dptr;
    /* ... */
    goodness = eval(expr1, rho);     /* evaluate R expression */
    dptr = REAL(goodness);           /* line 150 */
    for (i = 0; i < j; i++)
        good[i] = dptr[i];
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Direct .C conversion is NOT possible for any of these five REAL() calls.
 *
 * Lines 60, 63, 66 (init_rpcallback):
 *   REAL(stemp) depends on R_getVar, which retrieves a named SEXP from a live
 *   R environment (SEXP rho). The .C API provides no equivalent for
 *   environment lookup, symbol installation (install()), or SEXP handles.
 *
 * Lines 117, 150 (rpart_callback1 / rpart_callback2):
 *   REAL(value) / REAL(goodness) are applied to the return value of eval(),
 *   which executes an R expression (expr1/expr2) in an R environment (rho).
 *   R's evaluator is not available under .C.
 *
 * Additionally, the static SEXP variables rho, expr1, expr2 persist across
 * C function calls — a stateful pattern incompatible with .C's argument-only
 * communication model.
 *
 * Recommended migration strategy:
 *
 *   Option A — Keep init_rpcallback and rpart_callback1/2 as .Call functions.
 *     Register only the callback-initialisation and callback-invocation
 *     routines under .Call. The main rpart computation (which does not call
 *     eval()) can be ported to .C independently.
 *
 *   Option B — Move environment lookups and expression evaluation to R.
 *     Pre-extract the double vectors (yback, wback, xback) in R before
 *     the .C call and pass them as explicit double * arguments:
 *
 *       ydata_vec <- get("yback", envir = rho)
 *       wdata_vec <- get("wback", envir = rho)
 *       xdata_vec <- get("xback", envir = rho)
 *       result <- .C("rpcallback_init_c",
 *                    ydata = as.double(ydata_vec),
 *                    wdata = as.double(wdata_vec),
 *                    xdata = as.double(xdata_vec),
 *                    ...)
 *
 *     For the eval() callbacks, the R-level expression results (value, goodness)
 *     must be computed in R wrapper code and passed back into C as pre-filled
 *     double * arguments rather than being evaluated inside C.
 */
```

- **Explanation:**
  - `R_getVar(install("yback"), rho, FALSE)` retrieves a named R vector from a live R environment using a `SEXP` environment handle. The `.C` API provides no equivalent for environment lookup, symbol installation, or `SEXP` handles of any kind.
  - `eval(expr1/expr2, rho)` executes an R-language expression object inside C — a `.Call`-only capability. Even if environment lookup were somehow bypassed, there is no `SEXP` to pass to `REAL` under `.C`.
  - The `static SEXP rho`, `static SEXP expr1`, `static SEXP expr2` module-level state — which stores R objects between C function calls — is a fundamentally stateful pattern that has no equivalent in the stateless, argument-only `.C` dispatch model.
  - These are the only `REAL` occurrences in the codebase that are not mechanically convertible. All other `REAL` usages in the five files follow one of the four portable patterns above.
