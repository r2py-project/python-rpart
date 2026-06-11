# Conversion Guide: `allocVector`

## 1. Overview of `allocVector` in R API

`allocVector` is a C function declared in `Rinternals.h` as
`SEXP Rf_allocVector(SEXPTYPE type, R_xlen_t length)` and exposed via the macro
`#define allocVector Rf_allocVector`. It allocates a fresh, GC-managed R vector
of `length` elements whose element type is determined by the `SEXPTYPE` tag
(e.g., `INTSXP` for `int`, `REALSXP` for `double`, `STRSXP` for character
strings, `VECSXP` for a generic list). The returned `SEXP` object owns the
backing memory buffer; callers must immediately register it on the GC protection
stack with `PROTECT` and subsequently extract a raw pointer via `INTEGER()`,
`REAL()`, or similar accessors to perform computation. Under the `.C/.Fortran`
API, `allocVector` must be removed entirely: memory allocation is the caller's
responsibility and is performed in R before the `.C` call, so the C function
receives a pre-allocated raw pointer and never interacts with the GC.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `pred_rpart.c` | 139 | `SEXP where = PROTECT(allocVector(INTSXP, n));` |
| `rpart.c` | 194 | `which3 = PROTECT(allocVector(INTSXP, n));` |
| `rpart.c` | 327 | `SEXP rlist = PROTECT(allocVector(VECSXP, nout));` |
| `rpart.c` | 328 | `SEXP rname = allocVector(STRSXP, nout);` |
| `rpartexp2.c` | 47 | `SEXP keep = PROTECT(allocVector(INTSXP, n));` |
| `xpred.c` | 209 | `predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));` |

### Data types and memory management

Every call to `allocVector` in this codebase follows the same structural pattern:

1. `allocVector(TYPE, length)` — allocates a typed R vector of the specified
   length.
2. The result is either immediately `PROTECT`ed (lines 139, 194, 327, 47, 209)
   or left unprotected because it is immediately attached to an already-protected
   parent object as an attribute (line 328: `rname` is attached to `rlist` via
   `setAttrib` on the very next line, which makes it reachable through the GC
   transitively from the protected `rlist`).
3. For numeric and integer vectors, the raw pointer is extracted with
   `INTEGER(sexp)` or `REAL(sexp)` and stored in a local variable for all
   subsequent reads and writes. For `VECSXP` and `STRSXP`, the SEXP is
   manipulated through `SET_VECTOR_ELT`/`SET_STRING_ELT` directly.

Four distinct `SEXPTYPE` tags appear across the six usage sites:

| SEXPTYPE | C element type | Usage files |
|----------|---------------|-------------|
| `INTSXP` (13) | `int` | `pred_rpart.c:139`, `rpart.c:194`, `rpartexp2.c:47` |
| `REALSXP` (14) | `double` | `xpred.c:209` |
| `VECSXP` (19) | `SEXP` (list slot) | `rpart.c:327` |
| `STRSXP` (16) | `CHARSXP` (string slot) | `rpart.c:328` |

### Distinct implementation patterns

Three functionally distinct patterns are present across the six usage sites.

1. **1-D numeric/integer output vector** — `allocVector(INTSXP/REALSXP, n)` where
   `n` is a simple scalar (or a product of scalars). The SEXP is protected, a raw
   pointer is extracted, computations write into it, and the SEXP is then either
   returned directly (as in `pred_rpart.c`, `rpartexp2.c`) or stored as an element
   of a return list (as in `rpart.c`, `xpred.c`). Sites: `pred_rpart.c:139`,
   `rpart.c:194`, `rpartexp2.c:47`, `xpred.c:209`.

2. **`VECSXP` named-list return value** — `allocVector(VECSXP, nout)` allocates
   a generic list of `nout` slots that bundles the function's heterogeneous output
   arrays together for return to R. Companion calls to `SET_VECTOR_ELT` fill the
   slots with previously allocated and protected `SEXP` objects; a corresponding
   `allocVector(STRSXP, nout)` attached via `setAttrib` provides the `names`
   attribute. Site: `rpart.c:327`.

3. **`STRSXP` names-attribute vector** — `allocVector(STRSXP, nout)` allocates a
   character vector that serves exclusively as the `names` attribute of the
   `VECSXP` return list. It is not independently protected; instead it is
   immediately attached to the already-protected `rlist` via `setAttrib`. Its
   elements are written with `SET_STRING_ELT(rname, i, mkChar("..."))`. Site:
   `rpart.c:328`.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under the `.Call` API, `allocVector` is the sole means by which a C function
creates output storage. Under the `.C` API, the C function is `void`-returning
and receives only basic C pointer types (`int *`, `double *`); it never allocates
R objects and never interacts with the garbage collector. The conversion therefore
requires a complete inversion of ownership:

1. **Remove every `allocVector(TYPE, …)` call from C.** Each such call is
   replaced by a pre-allocated output argument of the corresponding C pointer
   type (`int *` for `INTSXP`, `double *` for `REALSXP`). The R caller creates
   these buffers with `integer(n)` or `double(n)` (both zero-initialised) before
   invoking `.C`.

2. **Remove all `PROTECT`/`UNPROTECT` calls.** They exist solely because
   `allocVector` returns GC-managed objects that need shielding. Once
   `allocVector` is gone, there are no GC-managed objects in C to protect. R's
   runtime automatically protects every vector passed as an argument to `.C`
   for the duration of the call.

3. **Remove `INTEGER(sexp)` and `REAL(sexp)` unwrapping calls.** These macros
   strip the `SEXP` envelope to yield the raw pointer. Once the `SEXP` variable
   is gone, the raw pointer arrives directly as a function argument — no
   unwrapping is needed.

4. **Remove `VECSXP` and `STRSXP` allocation and the entire list-assembly block
   entirely.** `allocVector(VECSXP, …)`, `allocVector(STRSXP, …)`,
   `SET_VECTOR_ELT`, `SET_STRING_ELT`, `setAttrib`, `mkChar`, `R_NamesSymbol`,
   and the final `return rlist` have no equivalent under `.C`. The list is
   assembled on the R side after the call returns, using `list()` with named
   arguments. Each former `VECSXP` slot becomes an independent pre-allocated
   output argument.

5. **Lift dimension computation to R.** `allocVector` can accept a length
   expression computed at C runtime (e.g., `n * ncp * nresp`). When these
   expressions involve values that are only known at runtime inside C, the R
   caller must either pre-compute the length from values already available on the
   R side or obtain it via a lightweight sizing pre-pass. The computed length is
   then passed as a scalar `int *` argument if the C code still needs it.

This strategy is `.C`-compatible because the `.C` dispatcher communicates
exclusively through basic C pointer types. All GC interaction, SEXP construction,
and R-object assembly belong to the R interpreter layer, which is inaccessible
from `.C` functions.

---

## 4. Step-by-Step Conversion Examples

### Pattern: 1-D Integer Output Vector

- **Locations:** `pred_rpart.c` line 139; `rpart.c` line 194; `rpartexp2.c`
  line 47

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

/* rpart.c:194-195 (inside SEXP rpart(...)) */
which3 = PROTECT(allocVector(INTSXP, n));
rp.which = INTEGER(which3);
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The output array is now a pre-allocated int * argument supplied by the
 * R caller.  PROTECT, UNPROTECT, allocVector, and INTEGER() are all removed.
 * The function returns void.
 */
void pred_rpart_c(const int    *dimx,
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
    /* dimx[0] gives n; asInteger(dimx) is not needed under .C */
    pred_rpart0(dimx, dimx[1], *nnode, *nsplit,
                dimc, nnum, nodes2,
                vnum, split2, csplit2, usesur, xdata2, xmiss2,
                where);   /* was: INTEGER(where) */
    /* No UNPROTECT needed */
}

void rpartexp2_c(const double *dtimes,
                 const int    *n,
                 const double *eps,
                 int          *keep)    /* was: SEXP keep = PROTECT(allocVector(INTSXP, n)) */
{
    Rpartexp2(*n, dtimes, *eps, keep);  /* was: INTEGER(keep) */
    /* No UNPROTECT needed */
}

/* Inside rpart_c — rpart.c:194-195 becomes: */
void rpart_c(/* ... */,
             int *which,   /* pre-allocated: integer(n) — was: allocVector(INTSXP, n) */
             /* ... */)
{
    rp.which = which;      /* was: rp.which = INTEGER(which3) */
    /* ... */
}
```

Corresponding R-side call:

```r
n <- as.integer(nrow(xdata))

result <- .C("pred_rpart_c",
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
             where   = integer(n))    # pre-allocated; replaces allocVector(INTSXP, n)
where_vec <- result$where

# rpartexp2 equivalent
n2 <- length(dtimes)
result2 <- .C("rpartexp2_c",
              dtimes = as.double(dtimes),
              n      = as.integer(n2),
              eps    = as.double(eps),
              keep   = integer(n2))   # pre-allocated; replaces allocVector(INTSXP, n)
keep_vec <- result2$keep
```

- **Explanation:**
  - `allocVector(INTSXP, n)` is removed from C. The R caller provides the output
    buffer with `integer(n)`, which is zero-initialised and automatically
    protected by R's GC for the duration of the `.C` call.
  - `PROTECT(…)` and `UNPROTECT(1)` are deleted; there is no GC-managed object
    left in C to protect.
  - `INTEGER(where)` — which strips the `SEXP` envelope to yield `int *` — is
    removed because the pointer now arrives directly as a function argument.
  - `asInteger(dimx)` is replaced by `dimx[0]`; under `.C`, integer scalars are
    passed as single-element `int *` arrays, so dereferencing element zero gives
    the scalar value without any R API call.
  - The R-side `result$where` and `result$keep` recover the filled output
    vectors after the `.C` call returns.

---

### Pattern: 1-D Real Output Vector from a Product of Dimensions

- **Locations:** `xpred.c` line 209

- **Original Context (.Call):**

```c
/* xpred.c:205-210 */
if (asInteger(all2) == 1)
    nresp = rp.num_resp;
else
    nresp = 1;
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);

/* later, inside a cross-validation loop: */
rundown2(xtree, j, cp, (predict + j * ncp * nresp), nresp);

/* ... */
UNPROTECT(1);
return predict2;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * predict is now a pre-allocated double * argument.
 * The conditional nresp selection is done in R before the call.
 * The total buffer length (n * ncp * nresp) is computed in R and
 * passed as a scalar for validation if needed; the pointer itself
 * carries the pre-allocated storage.
 */
void xpred_c(/* ... input args ... */,
             const int *n_arg,       /* scalar: number of observations      */
             const int *ncp_arg,     /* scalar: number of cp cutpoints      */
             const int *nresp_arg,   /* scalar: 1 or rp.num_resp ("all" flag) */
             double    *predict)     /* pre-allocated: double(n * ncp * nresp)
                                        was: PROTECT(allocVector(REALSXP, n*ncp*nresp)) */
{
    int     n     = *n_arg;
    int     ncp   = *ncp_arg;
    int     nresp = *nresp_arg;
    /* was: predict = REAL(predict2) — the pointer arrives directly */

    for (int xgroup = 0; xgroup < xvals; xgroup++) {
        /* ... cross-validation logic unchanged ... */
        for (int i = k; i < rp.n; i++) {
            int j = rp.sorts[0][i];
            rundown2(xtree, j, cp, (predict + j * ncp * nresp), nresp);
        }
    }
    /* No UNPROTECT needed */
}
```

Corresponding R-side call:

```r
nresp <- if (all_flag == 1L) rp_num_resp else 1L

result <- .C("xpred_c",
             # ... input args ...
             n_arg     = as.integer(n),
             ncp_arg   = as.integer(ncp),
             nresp_arg = nresp,
             predict   = double(n * ncp * nresp))   # replaces allocVector(REALSXP, n*ncp*nresp)

predict_flat <- result$predict   # flat vector of length n * ncp * nresp
```

- **Explanation:**
  - `allocVector(REALSXP, n * ncp * nresp)` is replaced by `double(n * ncp *
    nresp)` on the R side. All three scalar factors (`n`, `ncp`, `nresp`) are
    available in R before the call.
  - The conditional `nresp` selection (`if (asInteger(all2) == 1) nresp = rp.num_resp;
    else nresp = 1;`) is lifted to R and passed as the scalar `nresp_arg`.
  - `PROTECT(…)` and `UNPROTECT(1)` are removed; `REAL(predict2)` disappears
    because `predict` is already a `double *` argument.
  - The 3-D indexing arithmetic `predict + j * ncp * nresp` is unchanged because
    it is pure pointer arithmetic over the flat buffer and does not depend on the
    SEXP wrapper in any way.
  - The function's return type changes from `SEXP` to `void`; the filled
    `predict` buffer is recovered via `result$predict` on the R side.

---

### Pattern: `VECSXP` Named-List Return Value

- **Locations:** `rpart.c` lines 327–348

- **Original Context (.Call):**

```c
/* rpart.c:326-348 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));   /* allocate list of nout slots */
SEXP rname = allocVector(STRSXP, nout);            /* allocate names vector (not separately PROTECTed) */
setAttrib(rlist, R_NamesSymbol, rname);            /* attach names, GC-reachable through rlist */
SET_VECTOR_ELT(rlist, 0, which3);    SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);  SET_STRING_ELT(rname, 1, mkChar("cptable"));
SET_VECTOR_ELT(rlist, 2, dsplit3);   SET_STRING_ELT(rname, 2, mkChar("dsplit"));
SET_VECTOR_ELT(rlist, 3, isplit3);   SET_STRING_ELT(rname, 3, mkChar("isplit"));
SET_VECTOR_ELT(rlist, 4, dnode3);    SET_STRING_ELT(rname, 4, mkChar("dnode"));
SET_VECTOR_ELT(rlist, 5, inode3);    SET_STRING_ELT(rname, 5, mkChar("inode"));
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
 * The entire VECSXP/STRSXP assembly block is removed.
 * Each former VECSXP slot becomes a separate pre-allocated output argument.
 * The function is void-returning; the R caller assembles the named list.
 *
 * Only the relevant tail of the converted function is shown.
 * All preceding computation (partition, rpmatrix, which-array fixup, etc.)
 * is otherwise unchanged, except that INTEGER(which3), REAL(cptable3), etc.
 * are replaced by the corresponding pointer arguments which, cptable, etc.
 */
void rpart_c(/* --- input arguments (unchanged) --- */
             /* ... */,
             /* --- output arguments, one per former VECSXP element --- */
             int    *which,           /* pre-allocated: integer(n)                      */
             double *cptable,         /* pre-allocated: double(cptable_nrow * num_ucp)  */
             double *dsplit,          /* pre-allocated: double(splitcount_max * 3)      */
             int    *isplit,          /* pre-allocated: integer(splitcount_max * 3)     */
             double *dnode,           /* pre-allocated: double(nodecount_max*(3+nresp)) */
             int    *inode,           /* pre-allocated: integer(nodecount_max * 6)      */
             int    *csplit,          /* pre-allocated: integer(catcount_max * maxcat)
                                         or integer(1) when catcount_max == 0          */
             /* --- shape scalars for R to reshape the flat output buffers --- */
             int    *nodecount_out,
             int    *splitcount_out,
             int    *catcount_out,
             int    *cptable_nrow_out)
{
    /* ... all computation unchanged, writing into the pointer arguments ... */

    /*
     * REMOVED — the entire block below is deleted:
     *
     *   int nout = catcount > 0 ? 7 : 6;
     *   SEXP rlist = PROTECT(allocVector(VECSXP, nout));
     *   SEXP rname = allocVector(STRSXP, nout);
     *   setAttrib(rlist, R_NamesSymbol, rname);
     *   SET_VECTOR_ELT / SET_STRING_ELT / mkChar calls  (6 or 7 pairs)
     *   UNPROTECT(1 + nout);
     *   return rlist;
     *
     * Instead, expose the internally-computed sizes so R can reshape outputs:
     */
    *nodecount_out    = nodecount;
    *splitcount_out   = splitcount;
    *catcount_out     = catcount;
    *cptable_nrow_out = rp.num_unique_cp;
    /* void return — no SEXP constructed */
}
```

Corresponding R-side call and list reconstruction:

```r
n             <- as.integer(nrow(xmat))
nodecount_max <- as.integer(2L * n)        # conservative upper bound
splitcount_max<- as.integer(2L * n)
catcount_max  <- as.integer(max(0L, max(ncat)))
maxcat        <- as.integer(max(1L, max(ncat)))
nresp         <- as.integer(ny)
cp_ncol       <- if (xvals > 1L) 5L else 3L

result <- .C("rpart_c",
             # --- inputs ---
             # ... (as.integer / as.double casts for each input arg) ...,
             # --- outputs (pre-allocated, one per former VECSXP element) ---
             which         = integer(n),
             cptable       = double(nodecount_max * cp_ncol),
             dsplit        = double(splitcount_max * 3L),
             isplit        = integer(splitcount_max * 3L),
             dnode         = double(nodecount_max * (3L + nresp)),
             inode         = integer(nodecount_max * 6L),
             csplit        = integer(max(1L, catcount_max * maxcat)),
             # --- shape scalars ---
             nodecount_out    = integer(1L),
             splitcount_out   = integer(1L),
             catcount_out     = integer(1L),
             cptable_nrow_out = integer(1L))

nc  <- result$nodecount_out
sc  <- result$splitcount_out
cc  <- result$catcount_out
cpr <- result$cptable_nrow_out

# Reconstruct the named list — replaces the allocVector(VECSXP,...) block in C.
output <- list(
    which   = result$which,
    cptable = matrix(result$cptable[seq_len(cpr * cp_ncol)],
                     nrow = cpr, ncol = cp_ncol),
    dsplit  = matrix(result$dsplit[seq_len(sc * 3L)],
                     nrow = sc, ncol = 3L),
    isplit  = matrix(result$isplit[seq_len(sc * 3L)],
                     nrow = sc, ncol = 3L),
    dnode   = matrix(result$dnode[seq_len(nc * (3L + nresp))],
                     nrow = nc, ncol = 3L + nresp),
    inode   = matrix(result$inode[seq_len(nc * 6L)],
                     nrow = nc, ncol = 6L)
)
if (cc > 0L)
    output$csplit <- matrix(result$csplit[seq_len(cc * maxcat)],
                            nrow = cc, ncol = maxcat)
```

- **Explanation:**
  - `allocVector(VECSXP, nout)` has no equivalent under `.C`. A `VECSXP` is a
    GC-managed array of `SEXP` pointers; there is no basic C type that maps to
    it. The concept of "a named R list" is a purely R-layer abstraction that
    cannot exist inside a `.C` function.
  - `allocVector(STRSXP, nout)`, `setAttrib`, `SET_VECTOR_ELT`,
    `SET_STRING_ELT`, `mkChar`, and `R_NamesSymbol` are all removed as part of
    the same transformation. Named-list construction (`list(which = …, …)`) is
    trivial in R and requires no C involvement.
  - Each formerly `PROTECT`-ed output `SEXP` (`which3`, `cptable3`, `dsplit3`,
    `isplit3`, `dnode3`, `inode3`, `csplit3`) becomes a separate pre-allocated
    pointer argument. The `PROTECT` / `UNPROTECT(1 + nout)` pair that bracketed
    all of them is removed entirely.
  - `nout = catcount > 0 ? 7 : 6` disappears; the conditional seventh element
    is represented on the R side by `if (cc > 0L) output$csplit <- …`, mirroring
    the original `if (catcount > 0)` C guard.
  - Because `nodecount`, `splitcount`, `catcount`, and `rp.num_unique_cp` are
    computed inside C and needed by R to correctly trim and reshape the flat
    output buffers, they must be returned as additional scalar `int *` output
    arguments. This is a general requirement whenever a `.Call` function uses
    internally-computed sizes to dimension its `SEXP` outputs.
  - The R caller allocates conservatively large buffers (upper bounds) or uses a
    lightweight sizing pre-pass before the main `.C` call to obtain exact sizes.
    After the call, `seq_len(nc * 6L)` etc. trim each flat array to its actual
    populated length before `matrix()` reshaping.

---

### Pattern: `STRSXP` Names-Attribute Vector (Unprotected Allocation)

- **Locations:** `rpart.c` line 328

- **Original Context (.Call):**

```c
/* rpart.c:327-331 */
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);    /* not separately PROTECTed */
setAttrib(rlist, R_NamesSymbol, rname);    /* attaches rname to rlist; GC-reachable */
SET_STRING_ELT(rname, 0, mkChar("which"));
SET_STRING_ELT(rname, 1, mkChar("cptable"));
/* ... 4-5 more SET_STRING_ELT calls ... */
```

- **C/C++ Equivalent (.C):**

```c
/*
 * allocVector(STRSXP, nout) and the entire SET_STRING_ELT / mkChar block
 * are removed entirely.  Character strings cannot be passed through the
 * .C interface; names are expressed in R as named argument assignments.
 * No C code is needed for this pattern.
 */

/* The rpart_c function shown in the VECSXP pattern above already incorporates
 * this removal.  There is no C-side replacement for the STRSXP allocation. */
```

Corresponding R-side names assignment:

```r
# The names that were formerly mkChar("which"), mkChar("cptable"), etc.
# become the argument names in the list() call on the R side:
output <- list(
    which   = result$which,
    cptable = matrix(result$cptable[...], ...),
    dsplit  = matrix(result$dsplit[...],  ...),
    isplit  = matrix(result$isplit[...],  ...),
    dnode   = matrix(result$dnode[...],   ...),
    inode   = matrix(result$inode[...],   ...)
)
```

- **Explanation:**
  - `allocVector(STRSXP, nout)` is deleted with no C-side replacement. The `.C`
    API does not support character-vector arguments that carry arbitrary
    heap-allocated strings; only the `character` type in R's `.C` type-checking
    layer handles individual `const char *` scalars, not `STRSXP` objects.
  - The reason this `allocVector` call is unprotected (unlike the others) is
    that `setAttrib` on the very next line attaches `rname` to `rlist`, making
    it transitively reachable through the already-protected `rlist`. Under the
    `.C` conversion, the entire mechanism disappears since there is no parent
    `rlist` object in C for `rname` to be attached to.
  - `SET_STRING_ELT(rname, i, mkChar("literal"))`, `setAttrib`, and
    `R_NamesSymbol` are removed alongside the allocation. The string literals
    become the R argument names in the `list()` call — a zero-overhead
    replacement in idiomatic R.
  - This pattern always co-occurs with the `VECSXP` pattern at the same call
    site; see that pattern's conversion example for the complete picture.
