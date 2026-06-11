# Conversion Guide: `SET_VECTOR_ELT`

## 1. Overview of `SET_VECTOR_ELT` in R API

`SET_VECTOR_ELT` is a void function declared in `Rinternals.h` with the
signature `void SET_VECTOR_ELT(SEXP x, R_xlen_t i, SEXP v)`. It performs a
write-barrier-safe assignment that stores the `SEXP` value `v` into slot `i`
(0-based) of the `VECSXP` generic vector `x`, making `v` an element of R's list
object `x` without copying `v`'s data — only the `SEXP` pointer is stored. Its
read counterpart is `VECTOR_ELT(x, i)`, which retrieves the `SEXP` stored at
slot `i`. In the rpart codebase, `SET_VECTOR_ELT` is used exclusively in the
tail of the `rpart()` function to populate a `VECSXP` list with 6 or 7
previously-allocated output `SEXP` objects (`which3`, `cptable3`, `dsplit3`,
`isplit3`, `dnode3`, `inode3`, and optionally `csplit3`), which is then returned
as the single named-list result of the `.Call` function. Under the `.C` API,
`SET_VECTOR_ELT` — and the `VECSXP` container it writes into — have no
equivalent and must be removed from C entirely; list assembly is moved to the R
caller after the `.C` call returns.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 330 | `SET_VECTOR_ELT(rlist, 0, which3);` |
| `rpart.c` | 332 | `SET_VECTOR_ELT(rlist, 1, cptable3);` |
| `rpart.c` | 334 | `SET_VECTOR_ELT(rlist, 2, dsplit3);` |
| `rpart.c` | 336 | `SET_VECTOR_ELT(rlist, 3, isplit3);` |
| `rpart.c` | 338 | `SET_VECTOR_ELT(rlist, 4, dnode3);` |
| `rpart.c` | 340 | `SET_VECTOR_ELT(rlist, 5, inode3);` |
| `rpart.c` | 343 | `SET_VECTOR_ELT(rlist, 6, csplit3);` (conditional) |

### Extended context (lines 315–349 of `rpart.c`)

The 35-line window centred on the call cluster (lines 325–348) shows the
complete list-assembly block at the tail of the `rpart()` function.

```c
/* rpart.c:315-349 */

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
int nout = catcount > 0 ? 7 : 6;                           /* line 326 */
SEXP rlist = PROTECT(allocVector(VECSXP, nout));            /* line 327 */
SEXP rname = allocVector(STRSXP, nout);                     /* line 328 */
setAttrib(rlist, R_NamesSymbol, rname);                     /* line 329 */
SET_VECTOR_ELT(rlist, 0, which3);                           /* line 330 */
SET_STRING_ELT(rname, 0, mkChar("which"));                  /* line 331 */
SET_VECTOR_ELT(rlist, 1, cptable3);                         /* line 332 */
SET_STRING_ELT(rname, 1, mkChar("cptable"));                /* line 333 */
SET_VECTOR_ELT(rlist, 2, dsplit3);                          /* line 334 */
SET_STRING_ELT(rname, 2, mkChar("dsplit"));                 /* line 335 */
SET_VECTOR_ELT(rlist, 3, isplit3);                          /* line 336 */
SET_STRING_ELT(rname, 3, mkChar("isplit"));                 /* line 337 */
SET_VECTOR_ELT(rlist, 4, dnode3);                           /* line 338 */
SET_STRING_ELT(rname, 4, mkChar("dnode"));                  /* line 339 */
SET_VECTOR_ELT(rlist, 5, inode3);                           /* line 340 */
SET_STRING_ELT(rname, 5, mkChar("inode"));                  /* line 341 */
if (catcount > 0) {                                         /* line 342 */
    SET_VECTOR_ELT(rlist, 6, csplit3);                      /* line 343 */
    SET_STRING_ELT(rname, 6, mkChar("csplit"));             /* line 344 */
}
UNPROTECT(1 + nout);                                        /* line 347 */
return rlist;                                               /* line 348 */
```

### Data types of the `SEXP` values stored by `SET_VECTOR_ELT`

Each call stores a previously `PROTECT`-ed `SEXP` whose concrete type is:

| Slot | Variable | SEXP type | Dimensions | C element type |
|------|----------|-----------|------------|----------------|
| 0 | `which3` | `INTSXP` | 1-D vector, length `n` | `int *` |
| 1 | `cptable3` | `REALSXP` | 2-D matrix, `(3 or 5) x num_unique_cp` | `double *` |
| 2 | `dsplit3` | `REALSXP` | 2-D matrix, `splitcount x 3` | `double *` |
| 3 | `isplit3` | `INTSXP` | 2-D matrix, `splitcount x 3` | `int *` |
| 4 | `dnode3` | `REALSXP` | 2-D matrix, `nodecount x (3 + num_resp)` | `double *` |
| 5 | `inode3` | `INTSXP` | 2-D matrix, `nodecount x 6` | `int *` |
| 6 | `csplit3` | `INTSXP` | 2-D matrix, `catcount x maxcat` (conditional) | `int *` |

### Memory management context

- `rlist` is a `VECSXP` allocated by `allocVector(VECSXP, nout)` on line 327
  and immediately wrapped in `PROTECT`. It holds `nout` (6 or 7) `SEXP` slots.
- `SET_VECTOR_ELT(rlist, i, v)` stores the address of the `SEXP` `v` into slot
  `i` of `rlist`. No data is copied; the slot records the pointer. R's internal
  write barrier is notified so that the garbage collector can track the
  inter-object reference correctly.
- All six (or seven) values passed to `SET_VECTOR_ELT` (`which3`, `cptable3`,
  etc.) are individually `PROTECT`-ed earlier in the same function (lines
  194–293). They remain on the protection stack for the duration of the
  `SET_VECTOR_ELT` calls, ensuring they are not collected while the assignments
  are being made.
- `UNPROTECT(1 + nout)` on line 347 pops the one protection for `rlist` plus
  the `nout` protections for the individual output objects from the stack in one
  step immediately before `return rlist;`. After the return, R itself holds a
  reference to the returned `rlist` and — transitively — to all objects stored
  inside it.
- The companion `allocVector(STRSXP, nout)` for the names vector (`rname`) is
  not separately `PROTECT`-ed: attaching it to the already-protected `rlist` via
  `setAttrib` on line 329 makes `rname` transitively reachable.

### Companion API calls observed alongside `SET_VECTOR_ELT`

| Call | Role |
|------|------|
| `allocVector(VECSXP, nout)` | Allocates the `nout`-slot generic list that `SET_VECTOR_ELT` populates |
| `PROTECT(rlist)` | Pins the list against GC while the slot assignments execute |
| `UNPROTECT(1 + nout)` | Releases all protections before return |
| `SET_STRING_ELT(rname, i, mkChar("…"))` | Parallel call that names each slot — always paired with `SET_VECTOR_ELT` |
| `allocVector(STRSXP, nout)` | Allocates the parallel names character vector |
| `setAttrib(rlist, R_NamesSymbol, rname)` | Attaches the names vector as the `names` attribute of the list |
| `return rlist;` | Returns the completed named list as the `.Call` function's single `SEXP` result |

### Distinct implementation patterns

There is exactly one functional pattern in this codebase:

1. **Sequential slot assignment to a heterogeneous named-list return value** —
   `SET_VECTOR_ELT` is called once per output object, in index order 0–5
   unconditionally and optionally at index 6 (`csplit3`) when `catcount > 0`.
   Every `SEXP` assigned is a previously-allocated and individually protected
   numeric (`INTSXP` or `REALSXP`) vector or matrix. The completed list is the
   sole return value of the `.Call` entry point.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`SET_VECTOR_ELT` operates on a `VECSXP` — R's generic list type — which is a
GC-managed array of `SEXP` pointers. Neither `VECSXP` nor `SEXP` exist in the
`.C` API: `.C` functions must be `void`-returning and may only accept basic C
pointer types (`int *`, `double *`). Consequently:

1. **`SET_VECTOR_ELT` is removed from C with no C-level replacement.** The call
   stores a `SEXP` address into a `VECSXP` slot. Under `.C` there are no `SEXP`
   values and no list object in C, so the operation has nothing to act on. It is
   deleted in its entirety at all seven call sites (lines 330, 332, 334, 336,
   338, 340, 343).

2. **The `VECSXP` list (`rlist`) is also removed.** `allocVector(VECSXP, nout)`
   and its `PROTECT` call (line 327) are deleted. The concept of a heterogeneous
   R list is a purely R-interpreter-layer abstraction that cannot be created or
   manipulated inside a `.C` function.

3. **Each former `VECSXP` element becomes a separate pre-allocated output
   argument.** The seven output `SEXP` variables (`which3`, `cptable3`,
   `dsplit3`, `isplit3`, `dnode3`, `inode3`, `csplit3`) — which were stored into
   the list via `SET_VECTOR_ELT` — instead become independent `int *` or
   `double *` arguments that the R caller pre-allocates with `integer(n)` or
   `double(n)` and passes into `.C`. R's GC automatically protects any R vector
   passed as an argument for the duration of the `.C` call; no `PROTECT` is
   needed in C.

4. **The complete list-assembly tail of the function is removed from C.** The
   block spanning lines 326–348 (`int nout = …; allocVector(VECSXP, …);
   allocVector(STRSXP, …); setAttrib(…); SET_VECTOR_ELT ×7; SET_STRING_ELT ×7;
   UNPROTECT(…); return rlist;`) collapses to nothing. The converted function is
   `void`-returning with an explicit `return;` or simply falling off the end.

5. **Internally-computed shape scalars are exposed as output arguments.** The
   variables `nodecount`, `splitcount`, `catcount`, and `rp.num_unique_cp` are
   computed inside C and determine the meaningful portion of the flat output
   buffers. They must be returned as additional `int *` output arguments so that
   the R caller can correctly trim and reshape the pre-allocated flat arrays.

6. **List assembly is performed in R after the `.C` call.** The R caller uses
   `list(which = result$which, cptable = matrix(…), …)` to reconstruct the
   named list. This is the direct semantic equivalent of the removed
   `allocVector(VECSXP, …) + SET_VECTOR_ELT + SET_STRING_ELT + setAttrib`
   block, expressed in idiomatic R with zero C involvement. The companion
   `SET_STRING_ELT` calls are also removed — the element names become R argument
   names in the `list()` call (see `SET_STRING_ELT.md` for the full treatment of
   that half of the pattern).

This approach is `.C`-compatible because the `.C` dispatcher communicates
exclusively through typed C pointers. All R-object construction (lists,
character vectors, attributes) is an interpreter-layer operation that belongs
entirely on the R side.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Sequential Slot Assignment to a Heterogeneous Named-List Return Value

- **Locations:** `rpart.c` lines 330, 332, 334, 336, 338, 340 (unconditional);
  `rpart.c` line 343 (conditional on `catcount > 0`)

- **Original Context (.Call):**

```c
/* rpart.c:326-348
 * A VECSXP of 6 or 7 slots is built from previously-protected SEXPs and
 * returned as the named-list result of the .Call entry point.
 */

int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));   /* allocate the list */
SEXP rname = allocVector(STRSXP, nout);            /* parallel names vector */
setAttrib(rlist, R_NamesSymbol, rname);

/* Unconditional assignments: slots 0-5 */
SET_VECTOR_ELT(rlist, 0, which3);    SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);  SET_STRING_ELT(rname, 1, mkChar("cptable"));
SET_VECTOR_ELT(rlist, 2, dsplit3);   SET_STRING_ELT(rname, 2, mkChar("dsplit"));
SET_VECTOR_ELT(rlist, 3, isplit3);   SET_STRING_ELT(rname, 3, mkChar("isplit"));
SET_VECTOR_ELT(rlist, 4, dnode3);    SET_STRING_ELT(rname, 4, mkChar("dnode"));
SET_VECTOR_ELT(rlist, 5, inode3);    SET_STRING_ELT(rname, 5, mkChar("inode"));

/* Conditional assignment: slot 6 */
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
 * The VECSXP/STRSXP list-assembly block is removed entirely.
 * Each former VECSXP slot becomes a separate pre-allocated output argument
 * of the corresponding plain C pointer type.
 * The function is void-returning; the R caller assembles the named list.
 *
 * Only the converted tail of the function is shown; all preceding computation
 * (partition, rpmatrix, which-array fixup, etc.) is otherwise unchanged except
 * that references to INTEGER(which3), REAL(cptable3), etc. are replaced by
 * direct writes into the corresponding pointer arguments.
 */
void rpart_c(/* --- input arguments (types unchanged from .Call version) --- */
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
             /* --- output arguments: one per former SET_VECTOR_ELT target --- */
             int    *which,           /* pre-allocated: integer(n)                         */
             double *cptable,         /* pre-allocated: double(cptable_nrow * cp_ncol)     */
             double *dsplit,          /* pre-allocated: double(splitcount_max * 3)          */
             int    *isplit,          /* pre-allocated: integer(splitcount_max * 3)         */
             double *dnode,           /* pre-allocated: double(nodecount_max*(3+num_resp))  */
             int    *inode,           /* pre-allocated: integer(nodecount_max * 6)          */
             int    *csplit,          /* pre-allocated: integer(catcount_max * maxcat)
                                         or integer(1) stub when catcount_max == 0         */
             /* --- shape scalars written by C so R can trim/reshape outputs --- */
             int    *nodecount_out,
             int    *splitcount_out,
             int    *catcount_out,
             int    *cptable_nrow_out)
{
    /*
     * All internal computation that previously wrote into INTEGER(which3),
     * REAL(cptable3), REAL(dsplit3), INTEGER(isplit3), REAL(dnode3),
     * INTEGER(inode3), and INTEGER(csplit3) now writes directly into the
     * corresponding pointer arguments above.
     *
     * The following block is COMPLETELY REMOVED — every line of it:
     *
     *   int nout = catcount > 0 ? 7 : 6;
     *   SEXP rlist = PROTECT(allocVector(VECSXP, nout));
     *   SEXP rname = allocVector(STRSXP, nout);
     *   setAttrib(rlist, R_NamesSymbol, rname);
     *   SET_VECTOR_ELT(rlist, 0, which3);    <- line 330, removed
     *   SET_STRING_ELT(rname, 0, mkChar("which"));
     *   SET_VECTOR_ELT(rlist, 1, cptable3);  <- line 332, removed
     *   SET_STRING_ELT(rname, 1, mkChar("cptable"));
     *   SET_VECTOR_ELT(rlist, 2, dsplit3);   <- line 334, removed
     *   SET_STRING_ELT(rname, 2, mkChar("dsplit"));
     *   SET_VECTOR_ELT(rlist, 3, isplit3);   <- line 336, removed
     *   SET_STRING_ELT(rname, 3, mkChar("isplit"));
     *   SET_VECTOR_ELT(rlist, 4, dnode3);    <- line 338, removed
     *   SET_STRING_ELT(rname, 4, mkChar("dnode"));
     *   SET_VECTOR_ELT(rlist, 5, inode3);    <- line 340, removed
     *   SET_STRING_ELT(rname, 5, mkChar("inode"));
     *   if (catcount > 0) {
     *       SET_VECTOR_ELT(rlist, 6, csplit3); <- line 343, removed
     *       SET_STRING_ELT(rname, 6, mkChar("csplit"));
     *   }
     *   UNPROTECT(1 + nout);
     *   return rlist;
     *
     * Instead, expose the internally-computed sizes so that R can correctly
     * trim the over-allocated flat output buffers and reshape them:
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
# Upper-bound buffer sizes must be determined before the .C call.
# A common approach is a lightweight pre-pass that returns only the counts,
# or using conservative upper bounds such as n nodes, n-1 splits.
n              <- as.integer(nrow(xmat))
nodecount_max  <- as.integer(2L * n)           # conservative upper bound
splitcount_max <- as.integer(2L * n)
catcount_max   <- as.integer(sum(ncat > 0L))
maxcat         <- as.integer(max(c(ncat, 1L)))
num_resp       <- as.integer(ny)
cp_ncol        <- if (xvals > 1L) 5L else 3L

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
             # --- pre-allocated outputs (one per former SET_VECTOR_ELT target) ---
             which        = integer(n),
             cptable      = double(nodecount_max * cp_ncol),
             dsplit       = double(splitcount_max * 3L),
             isplit       = integer(splitcount_max * 3L),
             dnode        = double(nodecount_max * (3L + num_resp)),
             inode        = integer(nodecount_max * 6L),
             csplit       = integer(max(1L, catcount_max * maxcat)),
             # --- shape scalars written by C ---
             nodecount_out     = integer(1L),
             splitcount_out    = integer(1L),
             catcount_out      = integer(1L),
             cptable_nrow_out  = integer(1L))

# Read the actual sizes filled in by C
nc  <- result$nodecount_out
sc  <- result$splitcount_out
cc  <- result$catcount_out
cpr <- result$cptable_nrow_out

# Reconstruct the named list on the R side.
# This list() call is the direct semantic replacement for the entire
# allocVector(VECSXP) + SET_VECTOR_ELT + SET_STRING_ELT + setAttrib block.
# R's named-argument syntax implicitly sets the `names` attribute of the list.
output <- list(
    which   = result$which,
    cptable = matrix(result$cptable[seq_len(cpr * cp_ncol)],
                     nrow = cpr, ncol = cp_ncol),
    dsplit  = matrix(result$dsplit[seq_len(sc * 3L)],
                     nrow = sc,  ncol = 3L),
    isplit  = matrix(result$isplit[seq_len(sc * 3L)],
                     nrow = sc,  ncol = 3L),
    dnode   = matrix(result$dnode[seq_len(nc * (3L + num_resp))],
                     nrow = nc,  ncol = 3L + num_resp),
    inode   = matrix(result$inode[seq_len(nc * 6L)],
                     nrow = nc,  ncol = 6L)
)

# Mirrors the original `if (catcount > 0)` guard at line 342.
# Replacing SET_VECTOR_ELT(rlist, 6, csplit3) with R-side conditional assignment.
if (cc > 0L)
    output$csplit <- matrix(result$csplit[seq_len(cc * maxcat)],
                            nrow = cc, ncol = maxcat)
```

- **Explanation:**

  - `SET_VECTOR_ELT(rlist, i, sexp)` stores the address of an existing `SEXP`
    into slot `i` of a `VECSXP` list. Under `.C`, there is no `VECSXP` and no
    `SEXP`; the operation is removed from C at all seven call sites (lines 330,
    332, 334, 336, 338, 340, 343). Each former target `SEXP` is instead an
    independent pre-allocated `int *` or `double *` output argument accessible
    by argument name from the `.C` result list on the R side.

  - `allocVector(VECSXP, nout)` and `PROTECT(rlist)` are removed together with
    every `SET_VECTOR_ELT` call. A `VECSXP` is a GC-managed array of `SEXP`
    pointers; there is no C struct or pointer type that is equivalent and
    compatible with the `.C` dispatcher. R's `list()` on the R side is the
    natural replacement.

  - `VECTOR_ELT(x, i)` (the read counterpart of `SET_VECTOR_ELT`) is not used
    in this code block but would similarly be removed under `.C`: reading back an
    element is replaced by direct use of the named `.C` output argument (e.g.,
    `result$which`).

  - `UNPROTECT(1 + nout)` is removed in its entirety. It balanced the one
    `PROTECT` for `rlist` plus the `nout` earlier `PROTECT` calls for the
    individual output objects. Because no `PROTECT` calls remain in the converted
    function, no `UNPROTECT` is needed. R's GC automatically protects every
    vector passed as a `.C` argument for the duration of the call.

  - `return rlist;` is removed. The converted function is `void`-returning; it
    ends by writing shape scalars (`*nodecount_out`, etc.) and then returning
    with no value. Each output buffer is recovered independently from the named
    list that `.C` returns to R.

  - The conditional seventh element (`csplit3`, guarded by `if (catcount > 0)`)
    is handled entirely on the R side with `if (cc > 0L) output$csplit <- …`,
    directly mirroring the original C guard at line 342. The `csplit` buffer is
    always pre-allocated (minimum size 1 to avoid zero-length allocations under
    `.C`), but is appended to the output list only when C confirms `catcount > 0`
    via the `catcount_out` scalar.

  - Index semantics are preserved: `SET_VECTOR_ELT` used 0-based slot indices
    (0–6), and the replacement R `list()` also assigns elements in the same
    left-to-right order. No index adjustment is needed.

  - The `nout` runtime variable (`catcount > 0 ? 7 : 6`) is removed from C. Its
    role — branching between a 6- and 7-element list — is replaced by the R-side
    `if (cc > 0L)` guard that conditionally extends the output list with
    `output$csplit`.

  - Because `nodecount`, `splitcount`, `catcount`, and `rp.num_unique_cp` are
    computed inside C and determine the meaningful portion of the over-allocated
    output buffers, they must be returned as additional `int *` output arguments
    (`nodecount_out`, `splitcount_out`, `catcount_out`, `cptable_nrow_out`). This
    is a general requirement whenever a `.Call` function uses internally-computed
    sizes to determine the shape of its `SEXP` outputs.

  - `SET_STRING_ELT`, `mkChar`, `allocVector(STRSXP, …)`, `setAttrib`, and
    `R_NamesSymbol` are all removed as part of the same transformation. Refer to
    `SET_STRING_ELT.md` for the detailed treatment of the names-vector half of
    this pattern, and to `VECSXP.md` for the full list-container perspective.
