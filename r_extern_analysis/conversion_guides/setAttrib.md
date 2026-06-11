# Conversion Guide: `setAttrib`

## 1. Overview of `setAttrib` in R API

`setAttrib` is a function declared in `Rinternals.h` with the prototype
`SEXP Rf_setAttrib(SEXP x, SEXP name, SEXP val)`, exposed as the macro
`#define setAttrib Rf_setAttrib`. It attaches the R object `val` as an
attribute named `name` on the R object `x`, returning `val` after the
assignment; the most common invocation is
`setAttrib(x, R_NamesSymbol, names_vec)`, which assigns a `STRSXP` character
vector as the `names` attribute of a list or vector. In the `.Call` API, it is
the canonical way to give an R object any metadata attribute (names, dimnames,
class, etc.) from C code; under the `.C` API, `setAttrib` must be removed in
its entirety from C because it operates exclusively on `SEXP` objects, which
are forbidden in `.C` functions — all attribute assignment must instead be
expressed in R after the `.C` call returns.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 329 | `setAttrib(rlist, R_NamesSymbol, rname);` |

### Extended context (lines 314–349 of `rpart.c`)

The 31-line window centred on line 329 shows the complete output list-assembly
block at the tail of the `rpart()` entry-point function.

```c
/* rpart.c:314-349 */

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
setAttrib(rlist, R_NamesSymbol, rname);                    /* line 329 — target */
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

### Argument types in the specific call

The `setAttrib` call on line 329 maps to the three-argument prototype as
follows:

| Position | Argument | SEXP type | Role |
|----------|----------|-----------|------|
| `x` | `rlist` | `VECSXP` | The generic list receiving the attribute |
| `name` | `R_NamesSymbol` | `SYMSXP` | Pre-interned singleton symbol for `"names"` |
| `val` | `rname` | `STRSXP` | Character vector of 6 or 7 element-name strings |

`rlist` is allocated on line 327 (`allocVector(VECSXP, nout)`) and immediately
`PROTECT`-ed. `rname` is allocated on line 328 (`allocVector(STRSXP, nout)`)
but is **not** separately `PROTECT`-ed: `setAttrib` attaches it to the
already-protected `rlist`, making `rname` transitively reachable by R's garbage
collector through the attribute chain of `rlist`. `R_NamesSymbol` is a
pre-interned global `SEXP` (`LibExtern SEXP R_NamesSymbol; /* "names" */`)
declared in `Rinternals.h` at line 448.

### Effect of the call

After `setAttrib(rlist, R_NamesSymbol, rname)` executes, `rlist` becomes a
proper **named R list**: the `names` attribute of `rlist` is the character
vector `rname`. The subsequent `SET_STRING_ELT(rname, i, mkChar("..."))` calls
fill in the individual name strings; because `rname` is attached by reference
(not copied), those writes are immediately visible through `names(rlist)` in R.
The net result is that `rlist$which`, `rlist$cptable`, etc., become valid
element accesses on the R side.

### Companion API calls observed alongside `setAttrib`

| Call | Role |
|------|------|
| `allocVector(VECSXP, nout)` | Allocates the 6- or 7-slot generic list that receives the attribute |
| `PROTECT(rlist)` | Pins `rlist` against GC; `rname` piggybacks through this protection after `setAttrib` |
| `allocVector(STRSXP, nout)` | Allocates the character vector passed as `val` |
| `R_NamesSymbol` | The `SYMSXP` constant used as the attribute key |
| `SET_STRING_ELT(rname, i, mkChar("..."))` | Fills each name string into `rname` |
| `SET_VECTOR_ELT(rlist, i, sexp)` | Stores each output `SEXP` into the list |
| `UNPROTECT(1 + nout)` | Releases all protections before `return rlist` |

### Distinct implementation patterns

Only one pattern exists in this codebase:

1. **Attaching a fixed-string names vector to a heterogeneous return list** —
   `setAttrib` is called once, immediately after `rlist` and `rname` are
   allocated, to link a compile-time-constant `STRSXP` character vector to a
   `VECSXP` output list as its `names` attribute, producing a proper named R
   list that is returned as the function's sole result.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`setAttrib` has the prototype `SEXP Rf_setAttrib(SEXP x, SEXP name, SEXP val)`.
All three of its arguments are `SEXP` values, and the return value is also a
`SEXP`. The `.C` API forbids any use of `SEXP` — as a function argument, a
local variable, or a return value — inside the C function body. Consequently,
`setAttrib` cannot appear anywhere in a `.C` function, and all three of its
arguments (`rlist`, `R_NamesSymbol`, `rname`) must also be removed.

The complete transformation proceeds as follows:

1. **Remove `setAttrib` and its entire argument chain from C.** Removing
   `setAttrib(rlist, R_NamesSymbol, rname)` also mandates removing `rlist`
   (`VECSXP`), `rname` (`STRSXP`), and `R_NamesSymbol` (`SYMSXP`), because all
   three are `SEXP` values with no `.C`-compatible equivalents. This in turn
   requires removing every other API call that creates or depends on those
   three objects: `allocVector(VECSXP, ...)`, `allocVector(STRSXP, ...)`,
   `PROTECT`, `UNPROTECT`, `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`, and
   `return rlist`.

2. **Decompose the return list into separate pre-allocated output pointer
   arguments.** Each `SEXP` that would have been stored in `rlist` via
   `SET_VECTOR_ELT` (`which3`, `cptable3`, `dsplit3`, `isplit3`, `dnode3`,
   `inode3`, optionally `csplit3`) becomes an independent `int *` or `double *`
   argument pre-allocated by the R caller with `integer(n)` or `double(n)`
   before the `.C` call.

3. **Reconstruct the named list entirely on the R side.** After `.C` returns,
   the R caller builds the list with `list(which = result$which, cptable = ...,
   ...)`. R's named-argument syntax in `list()` implicitly sets the `names`
   attribute of the resulting list object. This is the exact semantic equivalent
   of `setAttrib(rlist, R_NamesSymbol, rname)` combined with the
   `SET_STRING_ELT` calls: the name strings `"which"`, `"cptable"`, etc. become
   R argument names rather than C heap-allocated `CHARSXP` values.

4. **Expose internally-computed shape scalars as output arguments.** Variables
   such as `nodecount`, `splitcount`, `catcount`, and `rp.num_unique_cp` are
   computed inside C and are needed by R to correctly trim and reshape the flat
   pre-allocated output buffers. They must be returned as additional `int *`
   output arguments.

This strategy is fully `.C`-compatible because the `.C` dispatcher communicates
exclusively through basic C pointer types (`int *`, `double *`, etc.). Attribute
assignment is an R-interpreter-layer operation that has no meaning outside a
live R session and belongs entirely on the R side.

### Relationship to companion guides

The removal of `setAttrib` is inseparable from the removal of the surrounding
`VECSXP`/`STRSXP` block. The following guides cover the parallel removals:

- `R_NamesSymbol.md` — the `SYMSXP` attribute key passed as the second argument
- `VECSXP.md` — the `VECSXP` container (`rlist`) passed as the first argument
- `STRSXP.md` — the `STRSXP` names vector (`rname`) passed as the third argument
- `SET_VECTOR_ELT.md` — the per-slot list assignments that follow `setAttrib`
- `SET_STRING_ELT.md` — the per-slot name assignments in the parallel `rname` vector
- `mkChar.md` — the `CHARSXP` literals supplied to `SET_STRING_ELT`
- `PROTECT.md` / `UNPROTECT.md` — the GC-protection bookkeeping that surrounds the block
- `allocVector.md` — the allocations of both `rlist` and `rname`

---

## 4. Step-by-Step Conversion Examples

### Pattern: Attaching a Fixed-String Names Vector to a Heterogeneous Return List

- **Locations:** `rpart.c` line 329 (within the block spanning lines 326–348)

- **Original Context (.Call):**

```c
/* rpart.c:326-348
 * setAttrib is called once, immediately after both SEXP objects are allocated,
 * to bind rname as the `names` attribute of rlist. All subsequent
 * SET_STRING_ELT writes on rname are visible through names(rlist) in R
 * because the attachment is by reference, not by copy.
 */

int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));    /* first argument to setAttrib  */
SEXP rname = allocVector(STRSXP, nout);             /* third argument to setAttrib  */
setAttrib(rlist, R_NamesSymbol, rname);             /* line 329 — target call       */
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
 * The entire VECSXP/STRSXP list-assembly block — including setAttrib,
 * R_NamesSymbol, allocVector, SET_VECTOR_ELT, SET_STRING_ELT, mkChar,
 * PROTECT, UNPROTECT, and return rlist — is removed completely.
 * The function is void-returning; the R caller reconstructs the named list.
 *
 * Only the converted tail of the function is shown; all preceding logic
 * (partition, rpmatrix, which-array fixup, etc.) is otherwise unchanged,
 * except that INTEGER(which3), REAL(cptable3), etc. are replaced by direct
 * writes into the corresponding pointer arguments listed below.
 */
void rpart_c(/* --- input arguments (types unchanged) --- */
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
             /* --- output arguments: one per former VECSXP element --- */
             int    *which,          /* pre-allocated: integer(n)                         */
             double *cptable,        /* pre-allocated: double(cptable_nrow * cp_ncol)     */
             double *dsplit,         /* pre-allocated: double(splitcount_max * 3)          */
             int    *isplit,         /* pre-allocated: integer(splitcount_max * 3)         */
             double *dnode,          /* pre-allocated: double(nodecount_max*(3+nresp))     */
             int    *inode,          /* pre-allocated: integer(nodecount_max * 6)          */
             int    *csplit,         /* pre-allocated: integer(catcount_max * maxcat)
                                        or integer(1) as a stub when catcount_max == 0    */
             /* --- shape scalars written by C so R can trim/reshape outputs --- */
             int    *nodecount_out,
             int    *splitcount_out,
             int    *catcount_out,
             int    *cptable_nrow_out)
{
    /*
     * All computation that previously wrote into INTEGER(which3),
     * REAL(cptable3), REAL(dsplit3), INTEGER(isplit3), REAL(dnode3),
     * INTEGER(inode3), and INTEGER(csplit3) now writes directly into the
     * pointer arguments above.
     *
     * The following block is COMPLETELY REMOVED — no SEXP variables,
     * no setAttrib, no R_NamesSymbol, no allocVector, no PROTECT/UNPROTECT,
     * no SET_VECTOR_ELT, no SET_STRING_ELT, no mkChar, no return value:
     *
     *   REMOVED:
     *     int nout = catcount > 0 ? 7 : 6;
     *     SEXP rlist = PROTECT(allocVector(VECSXP, nout));
     *     SEXP rname = allocVector(STRSXP, nout);
     *     setAttrib(rlist, R_NamesSymbol, rname);   // <-- line 329: removed here
     *     SET_VECTOR_ELT / SET_STRING_ELT / mkChar calls (7 pairs)
     *     UNPROTECT(1 + nout);
     *     return rlist;
     *
     * Instead, expose internally-computed sizes so R can reshape flat buffers:
     */
    *nodecount_out    = nodecount;
    *splitcount_out   = splitcount;
    *catcount_out     = catcount;
    *cptable_nrow_out = rp.num_unique_cp;
    /* function ends here — void return, no SEXP constructed */
}
```

- **R-side call and named-list reconstruction:**

```r
# Upper-bound buffer sizes must be determined before the .C call.
n              <- as.integer(nrow(xmat))
nodecount_max  <- as.integer(2L * n)           # conservative upper bound
splitcount_max <- as.integer(2L * n)
catcount_max   <- as.integer(sum(ncat > 0L))
maxcat         <- as.integer(max(c(ncat, 1L)))
nresp          <- as.integer(ny)
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
             # --- pre-allocated output buffers (one per former VECSXP element) ---
             which   = integer(n),
             cptable = double(nodecount_max * cp_ncol),
             dsplit  = double(splitcount_max * 3L),
             isplit  = integer(splitcount_max * 3L),
             dnode   = double(nodecount_max * (3L + nresp)),
             inode   = integer(nodecount_max * 6L),
             csplit  = integer(max(1L, catcount_max * maxcat)),
             # --- shape scalars written by C ---
             nodecount_out    = integer(1L),
             splitcount_out   = integer(1L),
             catcount_out     = integer(1L),
             cptable_nrow_out = integer(1L))

# Read actual sizes filled by C
nc  <- result$nodecount_out
sc  <- result$splitcount_out
cc  <- result$catcount_out
cpr <- result$cptable_nrow_out

# Reconstruct the named list — this is the complete R-side replacement for
# the setAttrib(rlist, R_NamesSymbol, rname) call combined with all the
# SET_STRING_ELT(rname, i, mkChar("...")) calls.
# R's named-argument syntax in list() implicitly sets the `names` attribute,
# which is exactly what setAttrib(rlist, R_NamesSymbol, rname) did in C.
output <- list(
    which   = result$which,
    cptable = matrix(result$cptable[seq_len(cpr * cp_ncol)],
                     nrow = cpr, ncol = cp_ncol),
    dsplit  = matrix(result$dsplit[seq_len(sc * 3L)],
                     nrow = sc,  ncol = 3L),
    isplit  = matrix(result$isplit[seq_len(sc * 3L)],
                     nrow = sc,  ncol = 3L),
    dnode   = matrix(result$dnode[seq_len(nc * (3L + nresp))],
                     nrow = nc,  ncol = 3L + nresp),
    inode   = matrix(result$inode[seq_len(nc * 6L)],
                     nrow = nc,  ncol = 6L)
)

# Mirrors the original `if (catcount > 0)` guard in C.
# The assignment output$csplit = ... automatically extends names(output)
# to include "csplit", mirroring what SET_STRING_ELT(rname, 6, mkChar("csplit"))
# plus setAttrib would have exposed through R_NamesSymbol.
if (cc > 0L)
    output$csplit <- matrix(result$csplit[seq_len(cc * maxcat)],
                            nrow = cc, ncol = maxcat)
```

- **Explanation:**

  - `setAttrib` has the prototype `SEXP Rf_setAttrib(SEXP x, SEXP name,
    SEXP val)`. All three arguments and the return value are `SEXP` objects.
    Because the `.C` API forbids `SEXP` in all positions (argument, local
    variable, return), the call cannot exist in a `.C` function and is removed
    unconditionally.

  - The R-side replacement is the named-argument syntax of `list()`. Writing
    `list(which = result$which, cptable = ..., ...)` causes R to internally
    execute the equivalent of `setAttrib(rlist, R_NamesSymbol, rname)` on the
    newly-constructed list. No explicit `names<-` assignment is needed; the
    `names` attribute is set as a side-effect of using named arguments.

  - The third argument `val` (here `rname`) is a `STRSXP` character vector
    populated by `SET_STRING_ELT(rname, i, mkChar("..."))` calls after
    `setAttrib` returns. In the converted code, the string literals
    (`"which"`, `"cptable"`, `"dsplit"`, `"isplit"`, `"dnode"`, `"inode"`,
    `"csplit"`) become R argument names in the `list()` call. They no longer
    need to be heap-allocated as `CHARSXP` objects via `mkChar`; they are
    ordinary R symbol names parsed at compile time.

  - The first argument `x` (`rlist`) is a `VECSXP` allocated by
    `allocVector(VECSXP, nout)` and protected by `PROTECT`. Both the
    allocation and the protection are removed from C. The `VECSXP` concept
    is replaced by the R `list()` constructor on the R side. See `VECSXP.md`
    for a full treatment.

  - The second argument `name` (`R_NamesSymbol`) is a pre-interned global
    `SEXP` symbol (`LibExtern SEXP R_NamesSymbol`) that lives in R's internal
    symbol table. It is a live runtime pointer into the R interpreter and
    has no meaning or C-accessible equivalent outside of a live R session.
    It is removed from C along with `setAttrib`. See `R_NamesSymbol.md` for
    a full treatment.

  - `PROTECT` and `UNPROTECT` are removed because they balanced the protection
    of `rlist` and the individual output `SEXP` objects. With no `SEXP` values
    remaining in the function, GC protection bookkeeping is entirely
    unnecessary. R's `.C` dispatcher automatically protects every R vector
    passed as an argument for the duration of the call.

  - The conditional seventh element (`csplit`, present only when `catcount > 0`)
    is handled entirely on the R side with `if (cc > 0L) output$csplit <- ...`.
    This mirrors the original `if (catcount > 0)` guard in C. The `csplit`
    buffer is always pre-allocated (minimum size 1 to avoid zero-length
    `.C` arguments), but is only incorporated into the output list when C
    confirms via `catcount_out` that it was populated.

  - Because `nodecount`, `splitcount`, `catcount`, and `rp.num_unique_cp` are
    computed inside C and control how much of each flat output buffer is
    meaningful, they are exposed as additional `int *` scalar output arguments.
    This is a general requirement whenever a `.Call` function uses
    internally-computed sizes to determine the shape of its `SEXP` outputs,
    and those sizes are not derivable from the inputs alone.

  - The `nout` variable and its `catcount > 0 ? 7 : 6` expression are removed
    from C. The branching between a 6- and 7-element list is replaced by the
    R-side `if (cc > 0L)` guard that conditionally appends the `csplit` element.
