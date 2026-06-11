# Conversion Guide: `PROTECT`

## 1. Overview of `PROTECT` in R API

`PROTECT` is a macro defined in `Rinternals.h` as `#define PROTECT(s) Rf_protect(s)`, where `Rf_protect` has the signature `SEXP Rf_protect(SEXP)`. It registers a freshly allocated `SEXP` object on R's internal garbage-collector protection stack so that the GC will not reclaim the object's memory for as long as the protection remains active. Every `PROTECT` call must be paired with a corresponding `UNPROTECT(n)` (or `UNPROTECT_PTR`) call before the function returns, which pops `n` entries off the protection stack. In the `.Call/.External` API, wrapping every `allocVector`/`allocMatrix` result in `PROTECT` is mandatory; in the `.C/.Fortran` API, `PROTECT` and `UNPROTECT` are entirely absent because all output memory is pre-allocated in R before the call and is automatically protected by the garbage collector for the duration of the `.C` invocation.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `pred_rpart.c` | 139 | `SEXP where = PROTECT(allocVector(INTSXP, n));` |
| `rpart.c` | 194 | `which3 = PROTECT(allocVector(INTSXP, n));` |
| `rpart.c` | 241 | `cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));` |
| `rpart.c` | 261 | `dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));` |
| `rpart.c` | 269 | `dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));` |
| `rpart.c` | 278 | `inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));` |
| `rpart.c` | 285 | `isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));` |
| `rpart.c` | 293 | `csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));` |
| `rpart.c` | 327 | `SEXP rlist = PROTECT(allocVector(VECSXP, nout));` |
| `rpartexp2.c` | 47 | `SEXP keep = PROTECT(allocVector(INTSXP, n));` |
| `xpred.c` | 209 | `predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));` |

### Data types and memory management

- `PROTECT` is never used standalone; every occurrence wraps the return value of `allocVector` or `allocMatrix` and assigns it to a `SEXP` variable.
- The corresponding `UNPROTECT` call appears at the end of each function: `UNPROTECT(1)` in `pred_rpart.c` (line 145), `rpartexp2.c` (line 49), and `xpred.c` (line 294); `UNPROTECT(1 + nout)` in `rpart.c` (line 347) covering all intermediate allocations plus the final list.
- The `SEXP` returned by `PROTECT` is immediately unwrapped via `INTEGER()` or `REAL()` to obtain the underlying `int *` or `double *` pointer used in all downstream computation.
- The protected objects fall into three element types: `INTSXP` (integer, `int *`), `REALSXP` (double, `double *`), and `VECSXP` (list, used for the named return list in `rpart.c`).

### Distinct implementation patterns

1. **1-D output vector protection** — `PROTECT(allocVector(INTSXP/REALSXP, n))` wrapping a simple one-dimensional allocation, found in `pred_rpart.c` line 139, `rpart.c` line 194, `rpartexp2.c` line 47, and `xpred.c` line 209.
2. **2-D output matrix protection (fixed dimensions)** — `PROTECT(allocMatrix(REALSXP/INTSXP, nrow, ncol))` with compile-time-constant column counts, found in `rpart.c` lines 261, 269, 278, and 285.
3. **2-D output matrix protection (runtime-computed dimensions)** — `PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp))` where at least one dimension is a runtime expression, found in `rpart.c` line 241.
4. **Conditionally allocated matrix protection** — `PROTECT(allocMatrix(INTSXP, catcount, maxcat))` inside an `if (catcount > 0)` branch, found in `rpart.c` line 293.
5. **Named-list (`VECSXP`) protection** — `PROTECT(allocVector(VECSXP, nout))` for the final multi-element return list, found in `rpart.c` line 327.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`PROTECT` exists solely to shield GC-managed `SEXP` allocations from being collected. Because the `.C` API forbids `SEXP` entirely, `PROTECT` and `UNPROTECT` are simply removed with no replacement:

1. **Remove `PROTECT(allocVector(…))` and `PROTECT(allocMatrix(…))`.** Every such expression is deleted. The corresponding output buffer becomes a pre-allocated `int *` or `double *` argument that the R caller supplies via `integer(n)` or `double(n)` before the `.C(…)` call. R's garbage collector automatically protects any R object passed as an argument to `.C` for the duration of the call — no explicit protection is needed in C.

2. **Remove `UNPROTECT(n)`.** Since no `PROTECT` calls remain, the paired `UNPROTECT` calls are also deleted.

3. **Remove `SEXP` variable declarations for allocated objects.** Each `SEXP varname` that held the result of `PROTECT(allocVector/allocMatrix)` is replaced by a `int *` or `double *` function parameter.

4. **Remove `INTEGER(sexp)` and `REAL(sexp)` unwrapping calls.** These accessor macros strip the `SEXP` wrapper to yield a raw pointer. Once the `SEXP` variable is gone, the raw pointer arrives directly as a function argument — no unwrapping is needed.

5. **Handle `VECSXP` list allocation differently.** `PROTECT(allocVector(VECSXP, nout))` and its associated `SET_VECTOR_ELT`/`SET_STRING_ELT` calls cannot be translated to `.C`. The list assembly must be lifted entirely to the R caller: each formerly-protected output `SEXP` becomes a separate `int *` or `double *` output argument, and the R code constructs the named list with `list()` after `.C` returns.

6. **Conditional allocation (`if (catcount > 0) PROTECT(…)`) moves to R.** The R caller pre-computes the required length (`catcount * maxcat` or `0L`) and always passes a pre-allocated vector of that length. The C code guards all access on the same `if (catcount > 0)` condition, which remains unchanged.

This approach is fully `.C`-compatible because `.C` communicates exclusively through basic C pointer types; R's memory management of those pointers is handled transparently by the runtime without any C-side protection calls.

---

## 4. Step-by-Step Conversion Examples

### Pattern: 1-D Output Vector Protection

- **Locations:** `pred_rpart.c` line 139; `rpart.c` line 194; `rpartexp2.c` line 47; `xpred.c` line 209

- **Original Context (.Call):**

```c
/* pred_rpart.c:133-147 */
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
                SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
                SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2)
{
    int n = asInteger(dimx);
    SEXP where = PROTECT(allocVector(INTSXP, n));   /* allocate + protect */
    pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit),
                INTEGER(dimc), INTEGER(nnum), INTEGER(nodes2),
                INTEGER(vnum), REAL(split2), INTEGER(csplit2),
                INTEGER(usesur), REAL(xdata2), INTEGER(xmiss2),
                INTEGER(where));                     /* unwrap SEXP -> int * */
    UNPROTECT(1);
    return where;
}

/* rpartexp2.c:43-51 */
SEXP rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);
    return keep;
}

/* xpred.c:209-210 (inside SEXP xpred(...)) */
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);
/* ... fill predict[] ... */
UNPROTECT(1);
return predict2;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Output buffers are now pre-allocated int* / double* arguments.
 * PROTECT, UNPROTECT, and SEXP variable declarations are removed.
 * INTEGER()/REAL() unwrapping is removed; the pointer arrives directly.
 */
void pred_rpart_c(const int    *n,       /* scalar: number of observations */
                  const int    *dimx,
                  const int    *nnode,
                  const int    *nsplit,
                  const int    *dimc,
                  const int    *nnum,
                  const int    *nodes2,
                  const int    *vnum,
                  const double *split2,
                  const int    *csplit2,
                  const int    *usesur,
                  const double *xdata2,
                  const int    *xmiss2,
                  int          *where)   /* was: SEXP where = PROTECT(allocVector(INTSXP, n)) */
{
    pred_rpart0(dimx, nnode[0], nsplit[0], dimc, nnum, nodes2,
                vnum, split2, csplit2, usesur, xdata2, xmiss2,
                where);   /* was: INTEGER(where) */
    /* No UNPROTECT */
}

void rpartexp2_c(const double *dtimes,
                 const int    *n,        /* was: LENGTH(dtimes) */
                 const double *eps,
                 int          *keep)     /* was: SEXP keep = PROTECT(allocVector(INTSXP, n)) */
{
    Rpartexp2(n[0], dtimes, eps[0], keep);   /* was: INTEGER(keep) */
}

void xpred_c(/* ... input args ... */,
             const int    *out_len,     /* scalar: n * ncp * nresp */
             double       *predict)     /* was: SEXP predict2 = PROTECT(allocVector(REALSXP, n*ncp*nresp)) */
{
    /* REAL(predict2) -> predict directly; fill predict[] as before */
}
```

Corresponding R-side call:

```r
n <- as.integer(nrow(xdata))
result <- .C("pred_rpart_c",
             n       = n,
             dimx    = as.integer(dimx),
             # ... remaining integer/double arguments ...
             where   = integer(n))   # pre-allocated; replaces allocVector(INTSXP, n)
where_vec <- result$where

n_pred <- as.integer(n * ncp * nresp)
result2 <- .C("xpred_c",
              # ... input args ...
              out_len = n_pred,
              predict = double(n_pred))  # pre-allocated; replaces allocVector(REALSXP, n*ncp*nresp)
```

- **Explanation:**
  - `PROTECT(allocVector(INTSXP/REALSXP, n))` is replaced by `integer(n)` or `double(n)` allocated on the R side and passed as an extra argument.
  - `PROTECT` and `UNPROTECT(1)` are deleted entirely; R's GC automatically protects any object passed into `.C` for the duration of the call.
  - `INTEGER(where)` and `REAL(predict2)` — which unwrap `SEXP -> int *` / `SEXP -> double *` — are removed because the pointer arrives directly as a function argument.
  - The `return sexp_var;` statement is removed; the filled output is recovered from the `.C` result list on the R side (e.g., `result$where`).

---

### Pattern: 2-D Output Matrix Protection (Fixed Dimensions)

- **Locations:** `rpart.c` line 261 (`nodecount x (3 + num_resp)`), line 269 (`splitcount x 3`), line 278 (`nodecount x 6`), line 285 (`splitcount x 3`)

- **Original Context (.Call):**

```c
/* rpart.c:261-290 — four consecutive matrix allocations */
dnode3  = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));
dptr = REAL(dnode3);
for (i = 0; i < 3 + rp.num_resp; i++) {
    ddnode[i] = dptr;
    dptr += nodecount;
}

dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));
dptr = REAL(dsplit3);
for (i = 0; i < 3; i++) {
    ddsplit[i] = dptr;
    dptr += splitcount;
}

inode3  = PROTECT(allocMatrix(INTSXP, nodecount, 6));
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
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Each matrix is passed as a pre-allocated flat array.
 * R stores matrices column-major: element [row r, col c] of an (nrow x ncol)
 * matrix is at flat index c*nrow + r.  The ragged-array setup loops are
 * unchanged because they step through columns using iptr += nrow.
 */
void rpart_c(/* ... input args ... */,
             const int *num_resp_arg,        /* scalar */
             double    *dnode,               /* pre-allocated: double(nodecount * (3 + num_resp)) */
             double    *dsplit,              /* pre-allocated: double(splitcount * 3) */
             int       *inode,               /* pre-allocated: integer(nodecount * 6) */
             int       *isplit,              /* pre-allocated: integer(splitcount * 3) */
             /* ... */)
{
    int num_resp = num_resp_arg[0];
    double *dptr;
    int    *iptr;

    /* was: dptr = REAL(dnode3) */
    dptr = dnode;
    for (int i = 0; i < 3 + num_resp; i++) {
        ddnode[i] = dptr;
        dptr += nodecount;
    }

    /* was: dptr = REAL(dsplit3) */
    dptr = dsplit;
    for (int i = 0; i < 3; i++) {
        ddsplit[i] = dptr;
        dptr += splitcount;
    }

    /* was: iptr = INTEGER(inode3) */
    iptr = inode;
    for (int i = 0; i < 6; i++) {
        iinode[i] = iptr;
        iptr += nodecount;
    }

    /* was: iptr = INTEGER(isplit3) */
    iptr = isplit;
    for (int i = 0; i < 3; i++) {
        iisplit[i] = iptr;
        iptr += splitcount;
    }

    /* All downstream code using ddnode[i][j], ddsplit[i][j], etc. is unchanged */
}
```

Corresponding R-side call:

```r
result <- .C("rpart_c",
             # ... input args ...
             num_resp_arg = as.integer(num_resp),
             dnode        = double(nodecount * (3L + num_resp)),
             dsplit       = double(splitcount * 3L),
             inode        = integer(nodecount * 6L),
             isplit       = integer(splitcount * 3L))

# Recover as proper R matrices after the call
dnode_mat  <- matrix(result$dnode,  nrow = nodecount, ncol = 3L + num_resp)
dsplit_mat <- matrix(result$dsplit, nrow = splitcount, ncol = 3L)
inode_mat  <- matrix(result$inode,  nrow = nodecount, ncol = 6L)
isplit_mat <- matrix(result$isplit, nrow = splitcount, ncol = 3L)
```

- **Explanation:**
  - `PROTECT(allocMatrix(TYPE, nrow, ncol))` is replaced by `double(nrow * ncol)` or `integer(nrow * ncol)` in R before the `.C` call.
  - `PROTECT` and the corresponding `UNPROTECT` counter are removed.
  - `REAL(dnode3)` and `INTEGER(inode3)` disappear; the raw pointers `dnode` and `inode` arrive directly as function arguments.
  - The ragged-array index setup loops (`ddnode[i] = dptr; dptr += nodecount;`) are preserved exactly because R's column-major storage matches the C loop's stride.
  - After the `.C` call, `matrix(result$dnode, nrow = nodecount, ncol = ...)` on the R side restores the 2-D matrix structure that was previously encoded in the `SEXP`'s `dim` attribute.

---

### Pattern: 2-D Output Matrix Protection (Runtime-Computed Dimensions)

- **Locations:** `rpart.c` line 241

- **Original Context (.Call):**

```c
/* rpart.c:239-252 */
scale = 1 / tree->risk;
i = 0;
cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));
dptr = REAL(cptable3);
for (cp = cptable; cp; cp = cp->forward) {
    dptr[i++] = cp->cp * scale;
    dptr[i++] = cp->nsplit;
    dptr[i++] = cp->risk * scale;
    if (xvals > 1) {
        dptr[i++] = cp->xrisk * scale;
        dptr[i++] = cp->xstd * scale;
    }
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The conditional row count (xvals > 1 ? 5 : 3) becomes a scalar int *
 * argument computed on the R side before the call.
 */
void rpart_c(/* ... */,
             const int *cptable_nrow_arg,  /* scalar: (xvals > 1 ? 5 : 3) */
             const int *num_unique_cp_arg, /* scalar: rp.num_unique_cp     */
             double    *cptable,           /* pre-allocated: double(cptable_nrow * num_unique_cp) */
             /* ... */)
{
    int cptable_nrow = cptable_nrow_arg[0];
    int num_unique_cp = num_unique_cp_arg[0];
    double scale = 1.0 / tree->risk;
    int i = 0;
    double *dptr = cptable;   /* was: REAL(cptable3) */

    for (cp = cptable_head; cp; cp = cp->forward) {
        dptr[i++] = cp->cp * scale;
        dptr[i++] = cp->nsplit;
        dptr[i++] = cp->risk * scale;
        if (cptable_nrow > 3) {
            dptr[i++] = cp->xrisk * scale;
            dptr[i++] = cp->xstd * scale;
        }
    }
}
```

Corresponding R-side call:

```r
cptable_nrow <- if (xvals > 1L) 5L else 3L

result <- .C("rpart_c",
             # ...
             cptable_nrow_arg  = cptable_nrow,
             num_unique_cp_arg = as.integer(num_unique_cp),
             cptable           = double(cptable_nrow * num_unique_cp))

cptable_mat <- matrix(result$cptable, nrow = cptable_nrow, ncol = num_unique_cp)
```

- **Explanation:**
  - The ternary expression `xvals > 1 ? 5 : 3` that was embedded inside `allocMatrix` is evaluated on the R side before the call and passed as the scalar `cptable_nrow_arg`.
  - `PROTECT` and `UNPROTECT` are removed; `REAL(cptable3)` becomes `cptable` directly.
  - The condition `if (xvals > 1)` in the fill loop is replaced by `if (cptable_nrow > 3)` using the already-scalar argument, avoiding any dependency on the original `xvals` variable inside the converted function.

---

### Pattern: Conditionally Allocated Matrix Protection

- **Locations:** `rpart.c` line 293

- **Original Context (.Call):**

```c
/* rpart.c:292-303 */
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
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The R caller always passes an integer() vector whose length is
 * catcount * maxcat when catcount > 0, or integer(0) when catcount == 0.
 * The C guard (if catcount > 0) is preserved unchanged.
 */
void rpart_c(/* ... */,
             const int *catcount_arg,  /* scalar */
             const int *maxcat_arg,    /* scalar */
             int       *csplit)        /* pre-allocated: integer(catcount * maxcat)
                                          or integer(0) when catcount == 0      */
{
    int catcount = *catcount_arg;
    int maxcat   = *maxcat_arg;
    int **ccsplit = NULL;
    int *iptr;

    if (catcount > 0) {
        ccsplit = (int **) R_alloc(maxcat, sizeof(int *));
        iptr = csplit;               /* was: INTEGER(csplit3) */
        for (int i = 0; i < maxcat; i++) {
            ccsplit[i] = iptr;
            iptr += catcount;
            for (int j = 0; j < catcount; j++)
                ccsplit[i][j] = 0;
        }
    }
    /* downstream code using ccsplit is unchanged */
}
```

Corresponding R-side call:

```r
csplit_len <- if (catcount > 0L) catcount * maxcat else 0L

result <- .C("rpart_c",
             # ...
             catcount_arg = as.integer(catcount),
             maxcat_arg   = as.integer(maxcat),
             csplit       = integer(csplit_len))

if (catcount > 0L)
    csplit_mat <- matrix(result$csplit, nrow = catcount, ncol = maxcat)
```

- **Explanation:**
  - The conditional `if (catcount > 0) PROTECT(allocMatrix(…))` is replaced by a conditional `integer(…)` length computation in R; the C guard on `catcount > 0` is preserved.
  - `PROTECT` is removed; `INTEGER(csplit3)` becomes `csplit` directly.
  - Passing `integer(0)` when `catcount == 0` is safe because all accesses to `csplit` are gated by `if (catcount > 0)`.
  - `R_alloc` replaces `ALLOC` for the ragged-array index pointer (`ccsplit`); `R_alloc` memory is automatically freed when the `.C` call returns.
  - Because `integer(n)` in R initialises to zero, the explicit zero-fill loop is redundant but harmless to keep.

---

### Pattern: Named-List (`VECSXP`) Protection

- **Locations:** `rpart.c` line 327

- **Original Context (.Call):**

```c
/* rpart.c:326-348 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);
SET_VECTOR_ELT(rlist, 0, which3);   SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3); SET_STRING_ELT(rname, 1, mkChar("cptable"));
SET_VECTOR_ELT(rlist, 2, dsplit3);  SET_STRING_ELT(rname, 2, mkChar("dsplit"));
SET_VECTOR_ELT(rlist, 3, isplit3);  SET_STRING_ELT(rname, 3, mkChar("isplit"));
SET_VECTOR_ELT(rlist, 4, dnode3);   SET_STRING_ELT(rname, 4, mkChar("dnode"));
SET_VECTOR_ELT(rlist, 5, inode3);   SET_STRING_ELT(rname, 5, mkChar("inode"));
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
}
UNPROTECT(1 + nout);
return rlist;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * allocVector(VECSXP, …) and the entire list-assembly block are removed.
 * Each SEXP element becomes a separate pre-allocated output argument.
 * The function is void; the R caller assembles the named list.
 */
void rpart_c(/* ... input args ... */,
             int    *which,    /* integer(n)                              */
             double *cptable,  /* double(cptable_nrow * num_unique_cp)    */
             double *dsplit,   /* double(splitcount * 3)                  */
             int    *isplit,   /* integer(splitcount * 3)                 */
             double *dnode,    /* double(nodecount * (3 + num_resp))      */
             int    *inode,    /* integer(nodecount * 6)                  */
             int    *csplit)   /* integer(catcount * maxcat) or integer(0)*/
{
    /* All computation that previously wrote into which3, cptable3, etc.
     * now writes into the corresponding pointer argument directly.
     * No PROTECT, no UNPROTECT, no SET_VECTOR_ELT, no mkChar. */
}
```

Corresponding R-side call and list reconstruction:

```r
result <- .C("rpart_c",
             # ... input args ...
             which   = integer(n),
             cptable = double(cptable_nrow * num_unique_cp),
             dsplit  = double(splitcount * 3L),
             isplit  = integer(splitcount * 3L),
             dnode   = double(nodecount * (3L + num_resp)),
             inode   = integer(nodecount * 6L),
             csplit  = integer(max(0L, catcount * maxcat)))

output <- list(
    which   = result$which,
    cptable = matrix(result$cptable, nrow = cptable_nrow, ncol = num_unique_cp),
    dsplit  = matrix(result$dsplit,  nrow = splitcount,   ncol = 3L),
    isplit  = matrix(result$isplit,  nrow = splitcount,   ncol = 3L),
    dnode   = matrix(result$dnode,   nrow = nodecount),
    inode   = matrix(result$inode,   nrow = nodecount,    ncol = 6L)
)
if (catcount > 0L)
    output$csplit <- matrix(result$csplit, nrow = catcount, ncol = maxcat)
```

- **Explanation:**
  - `PROTECT(allocVector(VECSXP, nout))` has no `.C` equivalent; the entire list-object is removed from C.
  - `allocVector(STRSXP, nout)`, `setAttrib`, `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`, and `R_NamesSymbol` are all removed.
  - Each previously-protected output `SEXP` (`which3`, `cptable3`, etc.) becomes a separate pre-allocated output argument of the appropriate pointer type.
  - `UNPROTECT(1 + nout)` — which balanced the one `PROTECT` for `rlist` plus the `nout` earlier `PROTECT` calls — is removed in its entirety.
  - The R caller reconstructs the named list with `list()` and `matrix()` using the flat arrays returned by `.C`.
