# Conversion Guide: `VECSXP`

## 1. Overview of `VECSXP` in R API

`VECSXP` is the integer constant `19` of type `SEXPTYPE`, defined in
`Rinternals.h` as the type tag for R's generic vector (R's `list` type,
`typeof(x) == "list"`). It is passed as the first argument to
`allocVector(VECSXP, n)` to request a freshly heap-allocated, GC-managed
array of `n` `SEXP` slots, where each slot can hold an independent R object of
any type; individual elements are written with `SET_VECTOR_ELT(sexp, i, value)`
and read back with `VECTOR_ELT(sexp, i)`. In the rpart codebase, `VECSXP` is
used exclusively as the container for the multi-component return value of the
main `rpart()` `.Call` function: it bundles heterogeneous output arrays
(`INTSXP`, `REALSXP`) together with a `STRSXP` names vector into a single
named-list object that is returned to R. Under the `.C` API, `VECSXP` has no
equivalent: `.C` functions are `void`-returning and cannot construct or return R
objects of any kind, so the list-assembly step must be removed from C entirely
and re-expressed in R after the `.C` call returns.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 327 | `SEXP rlist = PROTECT(allocVector(VECSXP, nout));` |

### Extended context (lines 312–349 of `rpart.c`)

The 31-line window centred on line 327 shows the complete list-assembly block
at the tail of the `rpart()` function.

```c
/* rpart.c:312-349 */

/* Fix up the 'which' array */
for (i = 0; i < n; i++) {
    k = rp.which[i];
    do {
        for (j = 0; j < nodecount; j++)
            if (iinode[0][j] == k) {
                rp.which[i] = j + 1;
                break;
            }
        k /= 2;
    } while (j >= nodecount);
}

/* Create the output list */
int nout = catcount > 0 ? 7 : 6;                          /* line 326 */
SEXP rlist = PROTECT(allocVector(VECSXP, nout));           /* line 327 */
SEXP rname = allocVector(STRSXP, nout);                    /* line 328 */
setAttrib(rlist, R_NamesSymbol, rname);                    /* line 329 */
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

### Data types and memory management

- `allocVector(VECSXP, nout)` allocates a generic list of `nout` slots (6 when
  `catcount == 0`, 7 when `catcount > 0`). `nout` is a runtime value, not a
  compile-time constant.
- The returned `SEXP rlist` is immediately wrapped in `PROTECT` to shield it
  from the garbage collector while the remaining `SET_VECTOR_ELT` and
  `SET_STRING_ELT` calls execute.
- `SET_VECTOR_ELT(rlist, i, sexp)` stores the address of an existing `SEXP`
  (previously allocated and protected on the same protection stack) into slot
  `i` of the list. The list does not copy the element's data; it stores a
  pointer to the already-protected `SEXP` object.
- The companion `allocVector(STRSXP, nout)` is **not separately `PROTECT`ed**:
  `setAttrib(rlist, R_NamesSymbol, rname)` immediately attaches it to the
  already-protected `rlist`, making it reachable by the GC transitively.
- `UNPROTECT(1 + nout)` at line 347 pops `rlist` (the `1`) plus each of the
  `nout` individual output `SEXP` values (`which3`, `cptable3`, `dsplit3`,
  `isplit3`, `dnode3`, `inode3`, and optionally `csplit3`) from the protection
  stack before the function returns.

### Companion API calls observed alongside `VECSXP`

| Call | Role |
|------|------|
| `allocVector(VECSXP, n)` | Allocates the `n`-slot generic list |
| `PROTECT(sexp)` | Pins the list `SEXP` against GC |
| `SET_VECTOR_ELT(list, i, elem)` | Stores an element `SEXP` into slot `i` |
| `VECTOR_ELT(list, i)` | Reads the `SEXP` from slot `i` (not used in this block, but the read counterpart) |
| `allocVector(STRSXP, n)` | Allocates the parallel names character vector |
| `setAttrib(list, R_NamesSymbol, names)` | Attaches the names vector as the `names` attribute |
| `SET_STRING_ELT(names, i, mkChar("…"))` | Writes a string literal into the names vector |
| `UNPROTECT(1 + nout)` | Releases all protected `SEXP`s before return |

### Distinct implementation patterns

Only one pattern exists in this codebase:

1. **Named generic-list assembly as a heterogeneous return value** — a `VECSXP`
   of 6 or 7 slots is built from previously-allocated `SEXP` outputs of mixed
   types (`INTSXP` vectors/matrices and `REALSXP` matrices), a parallel `STRSXP`
   names vector is attached as the `names` attribute, and the list is returned
   as the function's single `SEXP` return value to R.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

The `.C` API forbids `SEXP` values everywhere. A `.C` function must be
`void`-returning; it can only communicate results through basic C pointer types
(`int *`, `double *`) that are pre-allocated by R before the call. Consequently,
`VECSXP` — which is fundamentally a GC-managed array of `SEXP` pointers — has
no direct mapping to any `.C`-compatible type and must be removed from C
entirely.

The complete transformation for the `VECSXP`-based return pattern is:

1. **Decompose the list into separate output pointer arguments.** Each `SEXP`
   that would have been stored as a `VECSXP` element (`which3`, `cptable3`,
   `dsplit3`, `isplit3`, `dnode3`, `inode3`, `csplit3`) becomes an individual
   pre-allocated output argument with the corresponding raw C pointer type
   (`int *` for `INTSXP`, `double *` for `REALSXP`). The R caller allocates
   these buffers with `integer(n)` or `double(n)` before invoking `.C`.

2. **Remove all VECSXP and STRSXP construction from C.** The entire block at
   lines 326–348 (`allocVector(VECSXP, …)`, `allocVector(STRSXP, …)`,
   `setAttrib`, `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`,
   `R_NamesSymbol`, `PROTECT`, `UNPROTECT`, and `return rlist`) collapses to
   nothing in the converted `.C` function. The function ends with no return
   statement (or an explicit `return;`).

3. **Expose internally-computed shape scalars as output arguments.** The
   variables `nodecount`, `splitcount`, and `catcount` are computed inside C
   by `rpcountup()` and determine the sizes of the other output arrays. Under
   `.C` the R caller must know these values after the call in order to correctly
   interpret and reshape the flat output buffers. They must therefore be returned
   as additional `int *` output arguments.

4. **Reconstruct the named list in R.** After `.C` returns, the R caller
   assembles the named list using `list(which = result$which, cptable = …, …)`
   and `matrix(…)` to restore the original two-dimensional shapes. This
   replaces the combined `VECSXP`/`STRSXP` block in C with idiomatic R code and
   zero C overhead.

This approach is `.C`-compatible because the `.C` dispatcher communicates
exclusively through typed C pointers; all R-object construction belongs to the
R interpreter layer, which is inaccessible from `.C` functions.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Named Generic-List Assembly as a Heterogeneous Return Value

- **Locations:** `rpart.c` lines 326–348

- **Original Context (.Call):**

```c
/* rpart.c:326-348 — VECSXP used to bundle 6 or 7 output SEXPs into a named list */

int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);
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
 * The VECSXP/STRSXP assembly block is removed entirely.
 * Each former list element becomes a separate pre-allocated output argument.
 * The function is void-returning; the R caller assembles the named list.
 *
 * Only the converted tail of the function is shown; all preceding logic
 * (partition, rpmatrix, which-array fixup, etc.) is otherwise unchanged,
 * except that references to INTEGER(which3), REAL(cptable3), etc. are
 * replaced by direct use of the pointer arguments which, cptable, etc.
 */
void rpart_c(/* --- input arguments (unchanged types) --- */
             const int    *ncat,
             const int    *method,
             const double *opt,
             const double *parms,
             const int    *xvals,
             const int    *xgrp,
             const double *ymat,
             const double *xmat,
             const double *wt,
             const int    *ny,
             const double *cost,
             /* --- output arguments (one per former VECSXP element) --- */
             int    *which,          /* pre-allocated: integer(n)                      */
             double *cptable,        /* pre-allocated: double(cptable_nrow * cp_ncol)  */
             double *dsplit,         /* pre-allocated: double(splitcount_max * 3)      */
             int    *isplit,         /* pre-allocated: integer(splitcount_max * 3)     */
             double *dnode,          /* pre-allocated: double(nodecount_max*(3+nresp)) */
             int    *inode,          /* pre-allocated: integer(nodecount_max * 6)      */
             int    *csplit,         /* pre-allocated: integer(catcount_max * maxcat)
                                        or integer(0) when catcount_max == 0          */
             /* --- shape scalars written by C so R can reshape outputs --- */
             int    *nodecount_out,
             int    *splitcount_out,
             int    *catcount_out,
             int    *cptable_nrow_out)
{
    /*
     * All internal logic that previously wrote into INTEGER(which3),
     * REAL(cptable3), REAL(dsplit3), INTEGER(isplit3), REAL(dnode3),
     * INTEGER(inode3), and INTEGER(csplit3) now writes directly into the
     * corresponding pointer arguments.  No SEXP variables, no PROTECT,
     * no UNPROTECT, no SET_VECTOR_ELT, no SET_STRING_ELT, no mkChar,
     * no setAttrib, no R_NamesSymbol.
     *
     * The following block is completely removed:
     *
     *   int nout = catcount > 0 ? 7 : 6;
     *   SEXP rlist = PROTECT(allocVector(VECSXP, nout));
     *   SEXP rname = allocVector(STRSXP, nout);
     *   setAttrib(rlist, R_NamesSymbol, rname);
     *   SET_VECTOR_ELT / SET_STRING_ELT / mkChar calls  (7 pairs)
     *   UNPROTECT(1 + nout);
     *   return rlist;
     *
     * Instead, expose the internally-computed sizes for use by R:
     */
    *nodecount_out    = nodecount;
    *splitcount_out   = splitcount;
    *catcount_out     = catcount;
    *cptable_nrow_out = rp.num_unique_cp;
    /* function ends here — void return, no SEXP constructed */
}
```

- **R-side call and list reconstruction:**

```r
# Upper-bound sizes must be known or conservatively over-estimated before .C.
# A common approach is a lightweight pre-pass that returns only the counts,
# or using theoretical maxima (e.g., n nodes, n-1 splits).
n             <- as.integer(nrow(xmat))
nodecount_max <- as.integer(2L * n)          # conservative upper bound
splitcount_max<- as.integer(2L * n)
catcount_max  <- as.integer(max(ncat))
maxcat        <- as.integer(max(ncat))
nresp         <- as.integer(ny)
cp_ncol       <- if (xvals > 1L) 5L else 3L

result <- .C("rpart_c",
             # --- inputs ---
             ncat    = as.integer(ncat),
             method  = as.integer(method),
             opt     = as.double(opt),
             parms   = as.double(parms),
             xvals   = as.integer(xvals),
             xgrp    = as.integer(xgrp),
             ymat    = as.double(ymat),
             xmat    = as.double(xmat),
             wt      = as.double(wt),
             ny      = as.integer(ny),
             cost    = as.double(cost),
             # --- outputs (pre-allocated, one per former VECSXP element) ---
             which         = integer(n),
             cptable       = double(nodecount_max * cp_ncol),
             dsplit        = double(splitcount_max * 3L),
             isplit        = integer(splitcount_max * 3L),
             dnode         = double(nodecount_max * (3L + nresp)),
             inode         = integer(nodecount_max * 6L),
             csplit        = integer(max(1L, catcount_max * maxcat)),
             # --- shape scalars ---
             nodecount_out     = integer(1L),
             splitcount_out    = integer(1L),
             catcount_out      = integer(1L),
             cptable_nrow_out  = integer(1L))

# Read the actual sizes filled by C
nc  <- result$nodecount_out
sc  <- result$splitcount_out
cc  <- result$catcount_out
cpr <- result$cptable_nrow_out

# Reconstruct the named list — replaces the VECSXP/STRSXP block in C.
# This is the direct R equivalent of the removed allocVector/SET_VECTOR_ELT code.
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
# The optional 7th element mirrors the original `if (catcount > 0)` guard
if (cc > 0L)
    output$csplit <- matrix(result$csplit[seq_len(cc * maxcat)],
                            nrow = cc, ncol = maxcat)
```

- **Explanation:**

  - `allocVector(VECSXP, nout)` is removed entirely from C. A `VECSXP` is an
    array of `SEXP` pointers managed by R's garbage collector; there is no C
    struct or pointer type that is equivalent and compatible with the `.C`
    dispatcher. The concept of "a list of heterogeneous R objects" is a
    purely R-layer abstraction that cannot exist inside a `.C` function.

  - `SET_VECTOR_ELT(rlist, i, sexp)` is the write accessor for `VECSXP` slots.
    It stores the address of an existing `SEXP` at position `i`. Under `.C`,
    each former element is a separate pointer argument; the "slot assignment"
    simply disappears because each output is independently addressable by
    argument name.

  - `VECTOR_ELT(x, i)` (the read counterpart) is likewise unused in `.C`
    code; the R caller accesses each output by its argument name in the list
    returned by `.C`.

  - `PROTECT(allocVector(VECSXP, nout))` and `UNPROTECT(1 + nout)` are removed.
    R's GC automatically protects every vector passed through `.C` for the
    duration of the call; there is no per-allocation protection bookkeeping.

  - `allocVector(STRSXP, nout)`, `setAttrib`, `R_NamesSymbol`,
    `SET_STRING_ELT`, and `mkChar` are all removed as part of the same
    transformation. Named-list construction in R (`list(which = …, …)`) is the
    natural replacement and requires no C involvement. Refer to the `STRSXP.md`
    guide for a detailed treatment of the `STRSXP` half of this pattern.

  - The conditional seventh element (`csplit`, present only when `catcount > 0`)
    is handled on the R side with `if (cc > 0L)` after `.C` returns, directly
    mirroring the original C guard. The `csplit` output buffer is always
    pre-allocated (with a minimum size of 1 to avoid zero-length allocations),
    but it is only appended to the output list when the C code confirms it was
    populated.

  - Because `nodecount`, `splitcount`, `catcount`, and `rp.num_unique_cp` are
    computed inside C and are needed by R to correctly slice and reshape the
    flat output buffers, they are returned as additional scalar `int *` output
    arguments (`nodecount_out`, `splitcount_out`, `catcount_out`,
    `cptable_nrow_out`). This is a general requirement whenever a `.Call`
    function uses internally-computed sizes to determine the shape of its `SEXP`
    outputs.

  - The `nout` variable and its conditional `catcount > 0 ? 7 : 6` expression
    are removed from C. This runtime branching is replaced in R by the
    `if (cc > 0L) output$csplit <- …` guard that conditionally extends the
    output list.
