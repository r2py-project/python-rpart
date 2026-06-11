# Conversion Guide: `UNPROTECT`

## 1. Overview of `UNPROTECT` in R API

`UNPROTECT` is a macro defined in `Rinternals.h` as `#define UNPROTECT(n) Rf_unprotect(n)`, where `Rf_unprotect` has the signature `void Rf_unprotect(int)`. It pops `n` entries off R's internal garbage-collector protection stack, releasing the protection that was previously established by `n` matching `PROTECT` calls. It accepts a single integer argument indicating how many stack entries to pop and returns nothing. `UNPROTECT` is the mandatory counterpart to `PROTECT`: every function that calls `PROTECT` must call `UNPROTECT(n)` exactly once before returning, where `n` equals the total number of `PROTECT` calls made in that function. In the `.C/.Fortran` API, `UNPROTECT` is entirely absent because no `SEXP` objects are ever allocated or protected in C — all output memory is pre-allocated in R before the call.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | `UNPROTECT` call | Paired `PROTECT` count | Protection stack at `UNPROTECT` |
|------|------|------------------|------------------------|----------------------------------|
| `pred_rpart.c` | 145 | `UNPROTECT(1)` | 1 (`where`, line 139) | 1 |
| `rpart.c` | 347 | `UNPROTECT(1 + nout)` | 8 total (lines 194, 241, 261, 269, 278, 285, 293\*, 327) | 7 fixed + 1 conditional = 7 or 8 |
| `rpartexp2.c` | 49 | `UNPROTECT(1)` | 1 (`keep`, line 47) | 1 |
| `xpred.c` | 294 | `UNPROTECT(1)` | 1 (`predict2`, line 209) | 1 |

\* `csplit3` at line 293 is only `PROTECT`ed when `catcount > 0`; this is why `rpart.c` uses the expression `1 + nout` rather than a compile-time constant, where `nout = catcount > 0 ? 7 : 6`.

### Data types and memory management

- `UNPROTECT` never appears without a preceding `PROTECT`; it is structurally inseparable from the allocation-and-protection pattern.
- In `pred_rpart.c`, `rpartexp2.c`, and `xpred.c`, each function allocates exactly one `SEXP` output via `PROTECT(allocVector(…))` and immediately balances it with `UNPROTECT(1)` just before `return`.
- In `rpart.c`, multiple `SEXP` outputs are accumulated over the function body. The final `UNPROTECT(1 + nout)` is a single call that unwinds the entire protection stack in one shot. The variable `nout` is computed at runtime (`int nout = catcount > 0 ? 7 : 6`), making the argument to `UNPROTECT` a runtime expression rather than a literal.
- All four `UNPROTECT` calls appear immediately before the `return` statement, confirming that the protection lifetime of each `SEXP` spans the entire function body up to the point of return.
- The objects on the protection stack at the time of each `UNPROTECT` call cover all three element types used in rpart: `INTSXP` (`int *`), `REALSXP` (`double *`), and `VECSXP` (named list).

### Distinct implementation patterns

1. **Single fixed `UNPROTECT(1)`** — balances exactly one `PROTECT` call; the function allocates one output `SEXP` and returns it directly. Found in `pred_rpart.c` line 145, `rpartexp2.c` line 49, and `xpred.c` line 294.
2. **Arithmetic `UNPROTECT(1 + nout)` with runtime count** — balances a mix of unconditional and conditionally-executed `PROTECT` calls accumulated over the function body; the integer argument is a runtime expression. Found in `rpart.c` line 347.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`UNPROTECT` exists solely to release entries from R's GC protection stack that were registered by `PROTECT`. Because the `.C` API forbids `SEXP` entirely, `PROTECT` is never called in a `.C`-compatible function — and therefore `UNPROTECT` is also never needed. The complete removal strategy is as follows:

1. **Delete every `UNPROTECT(n)` call.** Since no `PROTECT` calls remain after conversion, no corresponding `UNPROTECT` is required. The deletion is unconditional regardless of whether the original argument was a literal integer (`1`) or a runtime expression (`1 + nout`).

2. **Delete the variables used only to track the `UNPROTECT` count.** In `rpart.c`, `int nout = catcount > 0 ? 7 : 6` was introduced solely to supply the argument to `UNPROTECT(1 + nout)`. Once `UNPROTECT` is gone, `nout` can be removed unless it also controls other logic (such as the `allocVector(VECSXP, nout)` and `SET_VECTOR_ELT` list assembly, which must also be removed as described in the `PROTECT` conversion guide).

3. **Memory safety is preserved by the `.C` API itself.** Any R object passed as an argument to `.C` is automatically protected from garbage collection by the R runtime for the entire duration of the call. Pre-allocated output vectors created with `integer(n)` or `double(n)` on the R side before calling `.C` are therefore protected without any C-side action.

4. **The removal of `UNPROTECT` is a consequence, not an independent step.** The root action is removing `PROTECT(allocVector/allocMatrix)` and replacing each allocation with a pre-allocated pointer argument (as described in the `PROTECT` conversion guide). `UNPROTECT` removal follows automatically because there is nothing left to unprotect.

This approach is fully `.C`-compatible: `.C` communicates exclusively through basic C pointer types, R handles GC protection of those pointers transparently, and no C-side stack management is needed.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Single Fixed `UNPROTECT(1)` — Balancing One Output Allocation

- **Locations:** `pred_rpart.c` line 145; `rpartexp2.c` line 49; `xpred.c` line 294

- **Original Context (.Call):**

```c
/* pred_rpart.c:133-147 */
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
                SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
                SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2)
{
    int n = asInteger(dimx);
    SEXP where = PROTECT(allocVector(INTSXP, n));   /* push 1 onto protection stack */
    pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit),
                INTEGER(dimc), INTEGER(nnum), INTEGER(nodes2),
                INTEGER(vnum), REAL(split2), INTEGER(csplit2),
                INTEGER(usesur), REAL(xdata2), INTEGER(xmiss2),
                INTEGER(where));
    UNPROTECT(1);   /* pop 1 from protection stack before return */
    return where;
}

/* rpartexp2.c:43-51 */
SEXP rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));   /* push 1 */
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);                                   /* pop 1 */
    return keep;
}

/* xpred.c:205-295 (abbreviated) */
SEXP xpred(/* ... */)
{
    /* ... */
    predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));  /* push 1 */
    predict  = REAL(predict2);
    /* ... fill predict[] ... */
    UNPROTECT(1);           /* pop 1 */
    return predict2;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The SEXP output variable is replaced by a pre-allocated pointer argument.
 * PROTECT, UNPROTECT(1), INTEGER()/REAL() unwrapping, and the return
 * statement for the SEXP are all removed.
 */
void pred_rpart_c(const int    *n,
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
                  int          *where)  /* was: SEXP where = PROTECT(allocVector(INTSXP, n)) */
{
    pred_rpart0(dimx, nnode[0], nsplit[0], dimc, nnum, nodes2,
                vnum, split2, csplit2, usesur, xdata2, xmiss2,
                where);   /* was: INTEGER(where) */
    /* UNPROTECT(1) removed — nothing to unprotect */
    /* no return value; output is in 'where' argument */
}

void rpartexp2_c(const int    *n,
                 const double *dtimes,
                 const double *eps,
                 int          *keep)   /* was: SEXP keep = PROTECT(allocVector(INTSXP, n)) */
{
    Rpartexp2(n[0], dtimes, eps[0], keep);  /* was: INTEGER(keep) */
    /* UNPROTECT(1) removed */
}

void xpred_c(/* ... input args ... */,
             double *predict)          /* was: SEXP predict2 = PROTECT(allocVector(REALSXP, n*ncp*nresp)) */
{
    /* 'predict' is used directly; was: predict = REAL(predict2) */
    /* ... fill predict[] as before ... */
    /* UNPROTECT(1) removed */
}
```

Corresponding R-side call:

```r
# pred_rpart
n <- as.integer(nrow(xdata))
result <- .C("pred_rpart_c",
             n       = n,
             dimx    = as.integer(dimx),
             # ... remaining integer/double arguments ...
             where   = integer(n))   # pre-allocated; replaces allocVector(INTSXP, n)
where_vec <- result$where

# rpartexp2
n <- length(dtimes)
result <- .C("rpartexp2_c",
             n      = as.integer(n),
             dtimes = as.double(dtimes),
             eps    = as.double(eps),
             keep   = integer(n))    # pre-allocated; replaces allocVector(INTSXP, n)
keep_vec <- result$keep

# xpred
out_len <- as.integer(n * ncp * nresp)
result <- .C("xpred_c",
             # ... input args ...
             predict = double(out_len))  # pre-allocated; replaces allocVector(REALSXP, n*ncp*nresp)
predict_vec <- result$predict
```

- **Explanation:**
  - `UNPROTECT(1)` is deleted entirely. It was balancing the single `PROTECT(allocVector(…))` immediately above it; since `allocVector` is also deleted (replaced by a pre-allocated argument), there is nothing on the protection stack to pop.
  - The `SEXP` variable declaration (`SEXP where`, `SEXP keep`, `SEXP predict2`) is removed; the pre-allocated pointer (`int *where`, `int *keep`, `double *predict`) arrives as an extra function argument.
  - `INTEGER(where)`, `INTEGER(keep)`, and `REAL(predict2)` — which unwrapped `SEXP -> raw pointer` — are removed; the raw pointer is now the argument itself.
  - The `return sexp_var;` statement is removed; the filled output is recovered from the `.C` result list on the R side (e.g., `result$where`).
  - The function return type changes from `SEXP` to `void`.

---

### Pattern: Arithmetic `UNPROTECT(1 + nout)` — Balancing Multiple Accumulated Allocations

- **Locations:** `rpart.c` line 347

- **Original Context (.Call):**

```c
/* rpart.c (abbreviated): 8 PROTECT calls accumulated over the function body,
 * then a single UNPROTECT(1 + nout) unwinds all of them. */

/* --- Allocation phase (lines 194-327) --- */
which3   = PROTECT(allocVector(INTSXP,  n));                                  /* +1 */
cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp)); /* +1 */
dnode3   = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));         /* +1 */
dsplit3  = PROTECT(allocMatrix(REALSXP, splitcount, 3));                         /* +1 */
inode3   = PROTECT(allocMatrix(INTSXP,  nodecount, 6));                          /* +1 */
isplit3  = PROTECT(allocMatrix(INTSXP,  splitcount, 3));                         /* +1 */
if (catcount > 0)
    csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));                    /* +1 (conditional) */

int nout = catcount > 0 ? 7 : 6;   /* nout = number of elements in the return list;
                                       also equals the number of PROTECTs above (including
                                       the conditional one), because rlist is PROTECT #8 */
SEXP rlist = PROTECT(allocVector(VECSXP, nout));                                 /* +1 */
/* ... SET_VECTOR_ELT / SET_STRING_ELT list assembly ... */

/* --- Single balanced UNPROTECT at the end --- */
UNPROTECT(1 + nout);   /* pops all 7 or 8 entries: the 6 unconditional SEXP
                          outputs + the optional csplit3 + rlist itself */
return rlist;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * All PROTECT calls are removed (see PROTECT.md for full details).
 * Because no entries are pushed onto the protection stack, the paired
 * UNPROTECT(1 + nout) is simply deleted.
 * The variable 'nout', which was introduced solely to compute the UNPROTECT
 * argument and to size the VECSXP list, is also removed.
 */
void rpart_c(/* ... input args ... */,
             int    *which,     /* pre-allocated: integer(n)                              */
             double *cptable,   /* pre-allocated: double(cptable_nrow * num_unique_cp)    */
             double *dnode,     /* pre-allocated: double(nodecount * (3 + num_resp))      */
             double *dsplit,    /* pre-allocated: double(splitcount * 3)                  */
             int    *inode,     /* pre-allocated: integer(nodecount * 6)                  */
             int    *isplit,    /* pre-allocated: integer(splitcount * 3)                 */
             int    *csplit,    /* pre-allocated: integer(catcount * maxcat) or integer(0)*/
             /* scalar dimension args so C knows sizes without recomputing them */
             const int *catcount_arg,
             const int *maxcat_arg,
             const int *nodecount_arg,
             const int *splitcount_arg,
             const int *num_unique_cp_arg,
             const int *cptable_nrow_arg,
             const int *num_resp_arg)
{
    /* All computation that previously wrote into which3, cptable3, etc.
     * now writes into the corresponding pointer arguments directly.
     * No PROTECT calls, so no UNPROTECT is needed.
     * 'nout' is removed entirely — list assembly moves to the R caller. */
}
```

Corresponding R-side call and list reconstruction:

```r
cptable_nrow <- if (xvals > 1L) 5L else 3L
csplit_len   <- if (catcount > 0L) catcount * maxcat else 0L
# 'nout' no longer needed in C; it is used only in the R list() call below

result <- .C("rpart_c",
             # ... input args ...
             which           = integer(n),
             cptable         = double(cptable_nrow * num_unique_cp),
             dnode           = double(nodecount * (3L + num_resp)),
             dsplit          = double(splitcount * 3L),
             inode           = integer(nodecount * 6L),
             isplit          = integer(splitcount * 3L),
             csplit          = integer(csplit_len),
             catcount_arg    = as.integer(catcount),
             maxcat_arg      = as.integer(maxcat),
             nodecount_arg   = as.integer(nodecount),
             splitcount_arg  = as.integer(splitcount),
             num_unique_cp_arg = as.integer(num_unique_cp),
             cptable_nrow_arg  = cptable_nrow,
             num_resp_arg      = as.integer(num_resp))

# Reconstruct the named list that was previously built with SET_VECTOR_ELT
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
  - `UNPROTECT(1 + nout)` is deleted in its entirety. The expression `1 + nout` was the sum of: 1 for the `VECSXP` list (`rlist`) plus `nout` for each individually-protected output `SEXP`. Since every `PROTECT` call has been removed, the stack depth at the end of the function is zero and nothing needs to be popped.
  - The variable `int nout = catcount > 0 ? 7 : 6` is removed from C. It served two purposes in the original: sizing the `VECSXP` and computing the `UNPROTECT` argument. Both purposes vanish after conversion — the list is assembled in R, and `UNPROTECT` is gone.
  - The conditional `PROTECT` for `csplit3` (line 293, only executed when `catcount > 0`) was the reason `UNPROTECT` used a runtime expression rather than a literal. Once `PROTECT` is removed, this conditionality has no remaining effect on `UNPROTECT` and is no longer a concern.
  - The entire `allocVector(VECSXP, …)` block, `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`, `R_NamesSymbol`, and `setAttrib` are removed from C. The R caller reconstructs the equivalent named list with `list()` after `.C` returns.
  - The `return rlist;` statement is removed; the function return type changes from `SEXP` to `void`; all outputs are recovered from the `.C` result list on the R side.
