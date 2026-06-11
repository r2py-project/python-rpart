# Conversion Guide: `R_NamesSymbol`

## 1. Overview of `R_NamesSymbol` in R API

`R_NamesSymbol` is a pre-interned `SEXP` symbol declared in `Rinternals.h` as
`LibExtern SEXP R_NamesSymbol; /* "names" */`. It is a global variable
(expanded to `extern SEXP` on Linux) that holds the singleton R symbol object
corresponding to the string `"names"`. Its sole role in the C API is as the
second argument to `setAttrib(object, R_NamesSymbol, names_vector)` (or
equivalently `getAttrib(object, R_NamesSymbol)`), which sets or retrieves the
`names` attribute of an R object. Under the `.Call` API, it is the canonical
way to attach a character-vector of element names to any R object (typically a
`VECSXP` list or a `STRSXP` vector) from C code; under the `.C` API, `R_NamesSymbol`
and the entire `setAttrib`/`names`-attribute mechanism must be removed from C
entirely, because `.C` functions cannot create, hold, or manipulate any `SEXP`
values.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 329 | `setAttrib(rlist, R_NamesSymbol, rname);` |

### Extended context (lines 314–349 of `rpart.c`)

The 31-line window centred on line 329 shows the complete list-assembly block
at the tail of the `rpart()` function, which is the only location in the
codebase where `R_NamesSymbol` appears.

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
setAttrib(rlist, R_NamesSymbol, rname);                    /* line 329 — the only use */
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

### Role of `R_NamesSymbol` in this block

`R_NamesSymbol` is passed as the second argument of `setAttrib`, which has the
signature `SEXP Rf_setAttrib(SEXP x, SEXP name, SEXP val)`. Here:

- `x` is `rlist`, a `VECSXP` list of 6 or 7 output `SEXP` elements.
- `name` is `R_NamesSymbol`, the pre-interned symbol for the string `"names"`.
- `val` is `rname`, a `STRSXP` character vector of 6 or 7 string literals
  (`"which"`, `"cptable"`, `"dsplit"`, `"isplit"`, `"dnode"`, `"inode"`,
  and optionally `"csplit"`).

The effect is that `rlist` becomes a proper named R list: after this call,
`rlist$which`, `rlist$cptable`, etc., are all valid accesses in R. Because
`setAttrib` attaches `rname` to the already-`PROTECT`ed `rlist`, `rname` itself
does not need its own `PROTECT` call — it becomes reachable through the
attributes chain of `rlist`.

### Companion API calls observed alongside `R_NamesSymbol`

| Call | Role |
|------|------|
| `allocVector(VECSXP, nout)` | Allocates the generic list that receives the names attribute |
| `PROTECT(sexp)` | Shields `rlist` from the garbage collector |
| `allocVector(STRSXP, nout)` | Allocates the character vector passed as `val` to `setAttrib` |
| `setAttrib(rlist, R_NamesSymbol, rname)` | Attaches the character vector as the `names` attribute |
| `SET_STRING_ELT(rname, i, mkChar("..."))` | Fills each slot of the character vector |
| `mkChar(const char *)` | Creates or retrieves an interned `CHARSXP` for each string literal |
| `SET_VECTOR_ELT(rlist, i, sexp)` | Stores each output `SEXP` into its slot in the list |
| `UNPROTECT(1 + nout)` | Releases all protected `SEXP` values before return |

### Distinct implementation patterns

Only one pattern exists in this codebase:

1. **Attaching a fixed-string names vector to a heterogeneous return list** —
   `R_NamesSymbol` is used as the attribute key inside a single `setAttrib`
   call that links a compile-time-constant `STRSXP` names vector to a `VECSXP`
   output list, giving it the `names` attribute that makes it a proper named R
   list.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_NamesSymbol` is a `SEXP` value. The `.C` API forbids any use of `SEXP` as a
function argument, a local variable, or a return value. Therefore `R_NamesSymbol`
itself, and the `setAttrib` call that uses it, must be completely removed from
the C function.

More broadly, the purpose of `setAttrib(rlist, R_NamesSymbol, rname)` is to
make the output object a named R list so that R callers can reference elements
by name. Under the `.C` API, a C function cannot produce any R object at all —
it communicates results exclusively through pre-allocated raw pointer arguments
(`int *`, `double *`). The concept of a "named list" is therefore a pure R-layer
concern that is reconstructed after `.C` returns.

The complete transformation proceeds as follows:

1. **Remove `setAttrib`, `R_NamesSymbol`, and all dependent SEXP construction
   from C.** This means also removing `allocVector(VECSXP, …)`,
   `allocVector(STRSXP, …)`, `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`,
   `PROTECT`, `UNPROTECT`, and the `return rlist` statement. The C function
   becomes `void`-returning with no `SEXP` variables.

2. **Replace each `VECSXP` slot with a separate pre-allocated output pointer
   argument.** Each component that was placed into the list (`which3`,
   `cptable3`, `dsplit3`, `isplit3`, `dnode3`, `inode3`, `csplit3`) becomes an
   individual `int *` or `double *` argument. R pre-allocates these buffers with
   `integer(n)` or `double(n)` before calling `.C`.

3. **Reconstruct the named list entirely in R.** After `.C` returns, the R
   caller builds the named list with `list(which = result$which, cptable = …,
   …)`. The argument names in the `list()` call — `which`, `cptable`, `dsplit`,
   etc. — are the direct R-language equivalents of the `mkChar("which")`,
   `mkChar("cptable")`, etc. string literals that were passed to
   `SET_STRING_ELT`. The `setAttrib(…, R_NamesSymbol, …)` call is implicitly
   performed by R's named-argument syntax, with zero C involvement.

This strategy is fully `.C`-compatible because:
- The `.C` dispatcher communicates exclusively through typed C pointers.
- `R_NamesSymbol` is a runtime `SEXP` object managed by R's garbage collector;
  it is meaningless outside a live R interpreter context.
- Named list construction (`list(a = …, b = …)`) is idiomatic R and imposes no
  overhead on the C code.

### Relationship to companion guides

The transformation of `R_NamesSymbol` is inseparable from the removal of the
entire `VECSXP`/`STRSXP` return block. Refer to the `VECSXP.md` and `STRSXP.md`
guides for detailed treatments of those parallel removals. The conversion
described here is the portion specifically attributed to the `setAttrib` /
`R_NamesSymbol` call on line 329.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Attaching a Fixed-String Names Vector to a Heterogeneous Return List

- **Locations:** `rpart.c` line 329 (within the block spanning lines 326–348)

- **Original Context (.Call):**

```c
/* rpart.c:326-348
 * R_NamesSymbol is used as the attribute key in the setAttrib call at line 329.
 * It links the STRSXP names vector (rname) to the VECSXP output list (rlist),
 * producing a named R list that is returned to the caller.
 */

int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);          /* <-- line 329: R_NamesSymbol used here */
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
 * The entire VECSXP/STRSXP/setAttrib/R_NamesSymbol assembly block is removed.
 * R_NamesSymbol does not appear anywhere in the converted function.
 * setAttrib is not called anywhere in the converted function.
 * The function is void-returning; the R caller reconstructs the named list.
 *
 * Only the converted tail of the function is shown; all preceding logic
 * (partition, rpmatrix, which-array fixup, etc.) is otherwise unchanged,
 * except that INTEGER(which3), REAL(cptable3), etc. are replaced by direct
 * writes into the corresponding pointer arguments.
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
             /* --- output arguments (one per former VECSXP element) --- */
             int    *which,           /* pre-allocated: integer(n)                       */
             double *cptable,         /* pre-allocated: double(cptable_nrow * cp_ncol)   */
             double *dsplit,          /* pre-allocated: double(splitcount_max * 3)        */
             int    *isplit,          /* pre-allocated: integer(splitcount_max * 3)       */
             double *dnode,           /* pre-allocated: double(nodecount_max*(3+nresp))   */
             int    *inode,           /* pre-allocated: integer(nodecount_max * 6)        */
             int    *csplit,          /* pre-allocated: integer(catcount_max * maxcat)
                                         or integer(1) as a stub when catcount_max == 0  */
             /* --- shape scalars written by C so R can slice/reshape outputs --- */
             int    *nodecount_out,
             int    *splitcount_out,
             int    *catcount_out,
             int    *cptable_nrow_out)
{
    /*
     * All computation that previously wrote into INTEGER(which3), REAL(cptable3),
     * REAL(dsplit3), INTEGER(isplit3), REAL(dnode3), INTEGER(inode3), and
     * INTEGER(csplit3) now writes directly into the pointer arguments above.
     *
     * The following block is COMPLETELY REMOVED — no SEXP variables, no PROTECT,
     * no UNPROTECT, no allocVector, no SET_VECTOR_ELT, no SET_STRING_ELT,
     * no mkChar, no setAttrib, no R_NamesSymbol, no return value:
     *
     *   REMOVED:
     *     int nout = catcount > 0 ? 7 : 6;
     *     SEXP rlist = PROTECT(allocVector(VECSXP, nout));
     *     SEXP rname = allocVector(STRSXP, nout);
     *     setAttrib(rlist, R_NamesSymbol, rname);      // <-- R_NamesSymbol removed here
     *     SET_VECTOR_ELT(rlist, 0, which3);    SET_STRING_ELT(rname, 0, mkChar("which"));
     *     SET_VECTOR_ELT(rlist, 1, cptable3);  SET_STRING_ELT(rname, 1, mkChar("cptable"));
     *     SET_VECTOR_ELT(rlist, 2, dsplit3);   SET_STRING_ELT(rname, 2, mkChar("dsplit"));
     *     SET_VECTOR_ELT(rlist, 3, isplit3);   SET_STRING_ELT(rname, 3, mkChar("isplit"));
     *     SET_VECTOR_ELT(rlist, 4, dnode3);    SET_STRING_ELT(rname, 4, mkChar("dnode"));
     *     SET_VECTOR_ELT(rlist, 5, inode3);    SET_STRING_ELT(rname, 5, mkChar("inode"));
     *     if (catcount > 0) {
     *         SET_VECTOR_ELT(rlist, 6, csplit3);
     *         SET_STRING_ELT(rname, 6, mkChar("csplit"));
     *     }
     *     UNPROTECT(1 + nout);
     *     return rlist;
     *
     * Instead, expose the internally-computed sizes so R can correctly reshape
     * the flat output buffers:
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
# Upper-bound buffer sizes must be determined before .C.
# A conservative approach is to use theoretical maxima (e.g., at most n nodes
# and n-1 splits for n observations).
n              <- as.integer(nrow(xmat))
nodecount_max  <- as.integer(2L * n)
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
             which        = integer(n),
             cptable      = double(nodecount_max * cp_ncol),
             dsplit       = double(splitcount_max * 3L),
             isplit       = integer(splitcount_max * 3L),
             dnode        = double(nodecount_max * (3L + nresp)),
             inode        = integer(nodecount_max * 6L),
             csplit       = integer(max(1L, catcount_max * maxcat)),
             # --- shape scalars written by C ---
             nodecount_out     = integer(1L),
             splitcount_out    = integer(1L),
             catcount_out      = integer(1L),
             cptable_nrow_out  = integer(1L))

# Read the actual sizes filled by C
nc  <- result$nodecount_out
sc  <- result$splitcount_out
cc  <- result$catcount_out
cpr <- result$cptable_nrow_out

# Reconstruct the named list — this is the R-side replacement for the entire
# setAttrib(rlist, R_NamesSymbol, rname) + SET_VECTOR_ELT/SET_STRING_ELT block.
# The named argument syntax list(which = ..., cptable = ..., ...) implicitly
# sets the `names` attribute, which is exactly what
# setAttrib(rlist, R_NamesSymbol, rname) did in C.
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
# The optional 7th element mirrors the original `if (catcount > 0)` guard in C.
# R_NamesSymbol / setAttrib is not needed here either: the assignment
# output$csplit = ... automatically sets names(output)[7] <- "csplit".
if (cc > 0L)
    output$csplit <- matrix(result$csplit[seq_len(cc * maxcat)],
                            nrow = cc, ncol = maxcat)
```

- **Explanation:**

  - `R_NamesSymbol` is a `SEXP` global variable (`extern SEXP`, expanded from
    `LibExtern SEXP` in `Rinternals.h`). It is a live pointer into R's internal
    symbol table, which only exists while an R interpreter session is active. It
    cannot be declared, dereferenced, or used in any way inside a `.C` function,
    which is compiled as an ordinary shared-library routine without access to
    interpreter internals.

  - `setAttrib(x, R_NamesSymbol, val)` attaches a character vector as the
    `names` attribute of an R object. In the converted code, this operation is
    replaced by R's named-argument syntax in the `list(which = …, cptable = …,
    …)` call. R sets the `names` attribute implicitly whenever a list is
    constructed with named arguments; no C involvement is required or possible.

  - `allocVector(STRSXP, nout)` and the companion `SET_STRING_ELT` / `mkChar`
    calls are also removed. The string literals `"which"`, `"cptable"`, etc.
    become R symbol names (argument names in the `list()` call) rather than
    heap-allocated `CHARSXP` objects. See `STRSXP.md` for details.

  - `allocVector(VECSXP, nout)`, `SET_VECTOR_ELT`, and `PROTECT`/`UNPROTECT`
    are removed for the same reason. See `VECSXP.md` for details.

  - Because `nodecount`, `splitcount`, `catcount`, and `rp.num_unique_cp` are
    computed inside C and are required by R to correctly trim and reshape the
    flat output buffers, they are exposed as additional scalar `int *` output
    arguments. This is a general requirement whenever a `.Call` function uses
    internally-computed sizes to determine the shape of its output `SEXP`s.

  - The conditional seventh element (`csplit`, present only when `catcount > 0`)
    is handled on the R side with `if (cc > 0L) output$csplit <- …`. This
    directly mirrors the original `if (catcount > 0)` guard in C and has the
    same effect on the `names` attribute: R's `$<-` assignment automatically
    extends `names(output)` to include `"csplit"`.

  - No changes are needed to the C headers. Because `R_NamesSymbol`,
    `setAttrib`, and all other `SEXP`-related identifiers are removed from the
    `.C` function, the `#include "Rinternals.h"` directive that exports them
    can also be dropped from the converted file (though other headers such as
    `rpart.h` may retain it if other parts of the codebase still use the
    `.Call` API).
