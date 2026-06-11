# Conversion Guide: `SET_STRING_ELT`

## 1. Overview of `SET_STRING_ELT` in R API

`SET_STRING_ELT` is a void function declared in `Rinternals.h` with the
signature `void SET_STRING_ELT(SEXP x, R_xlen_t i, SEXP v)`. It writes the
`CHARSXP` value `v` into slot `i` of the `STRSXP` character vector `x`,
performing a write-barrier-safe element assignment into R's internal string
array. Its typical usage pattern is `SET_STRING_ELT(rname, i, mkChar("literal"))`,
where `mkChar` (`Rf_mkChar`) creates or retrieves the interned `CHARSXP` for a
C string literal, and `rname` is a `STRSXP` allocated with
`allocVector(STRSXP, n)`. In the rpart codebase, `SET_STRING_ELT` is used
exclusively to populate the `names` attribute vector of a `VECSXP` return list,
making each output element accessible by name from R. Under the `.C` API,
`SET_STRING_ELT` — along with the entire `STRSXP`/`CHARSXP` infrastructure it
depends on — has no equivalent and must be removed entirely from C; the
names-vector construction is moved to the R side after the `.C` call returns.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 331 | `SET_STRING_ELT(rname, 0, mkChar("which"));` |
| `rpart.c` | 333 | `SET_STRING_ELT(rname, 1, mkChar("cptable"));` |
| `rpart.c` | 335 | `SET_STRING_ELT(rname, 2, mkChar("dsplit"));` |
| `rpart.c` | 337 | `SET_STRING_ELT(rname, 3, mkChar("isplit"));` |
| `rpart.c` | 339 | `SET_STRING_ELT(rname, 4, mkChar("dnode"));` |
| `rpart.c` | 341 | `SET_STRING_ELT(rname, 5, mkChar("inode"));` |
| `rpart.c` | 344 | `SET_STRING_ELT(rname, 6, mkChar("csplit"));` (conditional) |

### Extended context (lines 316–349 of `rpart.c`)

```c
/* rpart.c:325-349 — full list-assembly block where all SET_STRING_ELT calls live */

/* Create the output list */
int nout = catcount > 0 ? 7 : 6;                          /* line 326 */
SEXP rlist = PROTECT(allocVector(VECSXP, nout));           /* line 327 */
SEXP rname = allocVector(STRSXP, nout);                    /* line 328 */
setAttrib(rlist, R_NamesSymbol, rname);                    /* line 329 */
SET_VECTOR_ELT(rlist, 0, which3);                          /* line 330 */
SET_STRING_ELT(rname, 0, mkChar("which"));                 /* line 331 */
SET_VECTOR_ELT(rlist, 1, cptable3);                        /* line 332 */
SET_STRING_ELT(rname, 1, mkChar("cptable"));               /* line 333 */
SET_VECTOR_ELT(rlist, 2, dsplit3);                         /* line 334 */
SET_STRING_ELT(rname, 2, mkChar("dsplit"));                /* line 335 */
SET_VECTOR_ELT(rlist, 3, isplit3);                         /* line 336 */
SET_STRING_ELT(rname, 3, mkChar("isplit"));                /* line 337 */
SET_VECTOR_ELT(rlist, 4, dnode3);                          /* line 338 */
SET_STRING_ELT(rname, 4, mkChar("dnode"));                 /* line 339 */
SET_VECTOR_ELT(rlist, 5, inode3);                          /* line 340 */
SET_STRING_ELT(rname, 5, mkChar("inode"));                 /* line 341 */
if (catcount > 0) {                                        /* line 342 */
    SET_VECTOR_ELT(rlist, 6, csplit3);                     /* line 343 */
    SET_STRING_ELT(rname, 6, mkChar("csplit"));            /* line 344 */
}
UNPROTECT(1 + nout);                                       /* line 347 */
return rlist;                                              /* line 348 */
```

### Data types and memory management

- **`SEXP rname`** is a `STRSXP` (type tag `16`), allocated by
  `allocVector(STRSXP, nout)` on line 328. It holds `nout` (6 or 7) slots,
  each of which is a `CHARSXP` (type tag `9`) — R's internal scalar string type.
- **`mkChar(const char *)`** (`Rf_mkChar`) creates or retrieves from a global
  hash table the interned `CHARSXP` for each compile-time string literal
  (`"which"`, `"cptable"`, `"dsplit"`, `"isplit"`, `"dnode"`, `"inode"`,
  `"csplit"`). The returned `CHARSXP` is owned by R's string-interning table and
  does not need to be individually `PROTECT`ed.
- **`SET_STRING_ELT(rname, i, v)`** stores the `CHARSXP v` into slot `i` of
  `rname`. It performs an internal write-barrier notification so that R's
  incremental garbage collector can track the reference.
- **`rname` is not individually `PROTECT`ed.** After `setAttrib(rlist,
  R_NamesSymbol, rname)` on line 329 attaches `rname` as an attribute of the
  already-`PROTECT`ed `rlist`, `rname` becomes transitively reachable through
  `rlist`'s attribute chain and is therefore protected from collection without a
  separate `PROTECT` call.
- Lines 331–341 are unconditional (always executed). Line 344 is inside an
  `if (catcount > 0)` branch, making the seventh element optional.

### Companion API calls observed alongside `SET_STRING_ELT`

| Call | Role |
|------|------|
| `allocVector(STRSXP, nout)` | Allocates the `STRSXP` character vector to be populated |
| `mkChar(const char *)` | Creates/retrieves the `CHARSXP` for each string literal argument |
| `setAttrib(rlist, R_NamesSymbol, rname)` | Attaches the completed `STRSXP` as the `names` attribute |
| `allocVector(VECSXP, nout)` | Allocates the parent list whose elements are being named |
| `SET_VECTOR_ELT(rlist, i, sexp)` | Stores each numeric output `SEXP` into the parent list |
| `PROTECT(rlist)` / `UNPROTECT(1 + nout)` | Guards the list from garbage collection |
| `R_NamesSymbol` | The pre-interned attribute key `"names"` passed to `setAttrib` |

### Distinct implementation patterns

Only one functional pattern is present in the codebase:

1. **Sequential string-literal assignment to a fixed-size names vector** —
   `SET_STRING_ELT` is called once per slot of a `STRSXP` names vector, each
   time passing `mkChar("compile-time-literal")` as the value. The string
   literals are all known at compile time. Six slots are always populated; the
   seventh (`"csplit"`) is populated conditionally when `catcount > 0`.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`SET_STRING_ELT` is part of R's internal `SEXP` write-barrier infrastructure. It
operates on `STRSXP` and `CHARSXP` objects that only exist inside a live R
interpreter session and that are managed by R's garbage collector. The `.C` API
does not expose any `SEXP` type — function arguments and return values must be
basic C pointer types (`int *`, `double *`, `char **` for fixed-length strings).
Consequently:

1. **`SET_STRING_ELT` is removed from C with no C-level replacement.** The
   write-barrier call and its `mkChar` argument are both deleted entirely. No
   `char **` array, `strcpy`, or similar C string operation is required in its
   place.

2. **The `STRSXP` allocation (`allocVector(STRSXP, nout)`) is also removed.**
   There is no `.C`-compatible allocation for a character vector of arbitrary
   named elements. The character data (i.e., the names `"which"`, `"cptable"`,
   etc.) are compile-time string literals that are expressed in R as named
   argument syntax in the `list()` call, not as a heap-allocated array in C.

3. **The entire names-attribution chain is moved to R.** The sequence
   `allocVector(STRSXP, …)` → `SET_STRING_ELT(…, mkChar("…"))` ×n →
   `setAttrib(rlist, R_NamesSymbol, rname)` is replaced by a single `list(which
   = …, cptable = …, …)` call on the R side. R's named-argument syntax implicitly
   sets the `names` attribute of the constructed list, which is exactly the effect
   the C code was achieving through `SET_STRING_ELT` and `setAttrib`.

4. **`mkChar` is also removed.** `Rf_mkChar` creates an interned `CHARSXP` from a
   C string; it has no analogue in pure C code that does not link against
   `Rinternals.h`. The string literal passed to `mkChar("which")` becomes the R
   symbol name `which` in `list(which = result$which, …)`.

5. **The conditional seventh element is handled in R.** The original
   `if (catcount > 0) { SET_STRING_ELT(rname, 6, mkChar("csplit")); }` guard is
   replaced by `if (cc > 0L) output$csplit <- …` in R after the `.C` call
   returns. R's `$<-` assignment automatically extends `names(output)` with
   `"csplit"`, mirroring the original conditional write to slot 6 of `rname`.

This approach is fully `.C`-compatible because:
- `.C` communicates exclusively through typed C pointers; character-vector
  construction is an R interpreter-layer operation that cannot be performed
  inside a `.C` function.
- Named list construction (`list(a = …, b = …)`) is idiomatic R and requires
  zero C involvement.
- The string literals `"which"`, `"cptable"`, etc. are compile-time constants
  that belong naturally in R source code as argument names, not in C as
  `mkChar` arguments.

### Relationship to companion guides

`SET_STRING_ELT` is inseparable from `STRSXP` (the type of the vector it writes
into), `mkChar` (the function that produces its `CHARSXP` argument), and
`setAttrib`/`R_NamesSymbol` (the subsequent call that consumes the completed
names vector). The full removal of this cluster is also described from each of
those perspectives in `STRSXP.md` and `R_NamesSymbol.md`. The `VECSXP.md`,
`PROTECT.md`, and `SET_VECTOR_ELT`-related guides cover the parallel removal of
the parent list construction.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Sequential String-Literal Assignment to a Fixed-Size Names Vector

- **Locations:** `rpart.c` lines 331, 333, 335, 337, 339, 341 (unconditional);
  `rpart.c` line 344 (conditional on `catcount > 0`)

- **Original Context (.Call):**

```c
/* rpart.c:326-348
 * A STRSXP names vector is allocated, populated with SET_STRING_ELT + mkChar,
 * then attached to a VECSXP return list via setAttrib.
 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));   /* parent list */
SEXP rname = allocVector(STRSXP, nout);            /* names vector */
setAttrib(rlist, R_NamesSymbol, rname);

/* Unconditional elements: indices 0-5 */
SET_VECTOR_ELT(rlist, 0, which3);    SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);  SET_STRING_ELT(rname, 1, mkChar("cptable"));
SET_VECTOR_ELT(rlist, 2, dsplit3);   SET_STRING_ELT(rname, 2, mkChar("dsplit"));
SET_VECTOR_ELT(rlist, 3, isplit3);   SET_STRING_ELT(rname, 3, mkChar("isplit"));
SET_VECTOR_ELT(rlist, 4, dnode3);    SET_STRING_ELT(rname, 4, mkChar("dnode"));
SET_VECTOR_ELT(rlist, 5, inode3);    SET_STRING_ELT(rname, 5, mkChar("inode"));

/* Conditional element: index 6 */
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
 * The entire STRSXP/CHARSXP/mkChar/SET_STRING_ELT/setAttrib block is removed.
 * The converted C function is void-returning. Each former VECSXP slot becomes
 * a separate pre-allocated output argument of the appropriate pointer type.
 * No SET_STRING_ELT, no mkChar, no STRSXP, no CHARSXP, no setAttrib,
 * no R_NamesSymbol, no PROTECT, no UNPROTECT, no return value.
 *
 * Only the converted tail of the function is shown below. All preceding
 * computation (partition, rpmatrix, which-array fixup, etc.) is unchanged
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
             /* --- output arguments (one per former VECSXP slot) --- */
             int    *which,           /* pre-allocated: integer(n)                        */
             double *cptable,         /* pre-allocated: double(cptable_nrow * cp_ncol)    */
             double *dsplit,          /* pre-allocated: double(splitcount_max * 3)         */
             int    *isplit,          /* pre-allocated: integer(splitcount_max * 3)        */
             double *dnode,           /* pre-allocated: double(nodecount_max*(3+nresp))    */
             int    *inode,           /* pre-allocated: integer(nodecount_max * 6)         */
             int    *csplit,          /* pre-allocated: integer(catcount_max * maxcat)
                                         or integer(1) stub when catcount_max == 0        */
             /* --- shape scalars written by C so R can trim/reshape outputs --- */
             int    *nodecount_out,
             int    *splitcount_out,
             int    *catcount_out,
             int    *cptable_nrow_out)
{
    /*
     * COMPLETELY REMOVED (the SET_STRING_ELT cluster and its dependencies):
     *
     *   int nout = catcount > 0 ? 7 : 6;
     *   SEXP rlist = PROTECT(allocVector(VECSXP, nout));
     *   SEXP rname = allocVector(STRSXP, nout);       <-- STRSXP allocation removed
     *   setAttrib(rlist, R_NamesSymbol, rname);
     *   SET_VECTOR_ELT(rlist, 0, which3);
     *   SET_STRING_ELT(rname, 0, mkChar("which"));    <-- removed: line 331
     *   SET_VECTOR_ELT(rlist, 1, cptable3);
     *   SET_STRING_ELT(rname, 1, mkChar("cptable"));  <-- removed: line 333
     *   SET_VECTOR_ELT(rlist, 2, dsplit3);
     *   SET_STRING_ELT(rname, 2, mkChar("dsplit"));   <-- removed: line 335
     *   SET_VECTOR_ELT(rlist, 3, isplit3);
     *   SET_STRING_ELT(rname, 3, mkChar("isplit"));   <-- removed: line 337
     *   SET_VECTOR_ELT(rlist, 4, dnode3);
     *   SET_STRING_ELT(rname, 4, mkChar("dnode"));    <-- removed: line 339
     *   SET_VECTOR_ELT(rlist, 5, inode3);
     *   SET_STRING_ELT(rname, 5, mkChar("inode"));    <-- removed: line 341
     *   if (catcount > 0) {
     *       SET_VECTOR_ELT(rlist, 6, csplit3);
     *       SET_STRING_ELT(rname, 6, mkChar("csplit")); <-- removed: line 344
     *   }
     *   UNPROTECT(1 + nout);
     *   return rlist;
     *
     * Instead, expose the internally-computed sizes so that R can correctly
     * trim the over-allocated flat output buffers and reshape them.
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
# Determine upper-bound buffer sizes before the .C call.
n              <- as.integer(nrow(xmat))
nodecount_max  <- as.integer(2L * n)       # conservative upper bound
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
             # --- pre-allocated output buffers (one per former VECSXP slot) ---
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

# Read the actual sizes filled by C.
nc  <- result$nodecount_out
sc  <- result$splitcount_out
cc  <- result$catcount_out
cpr <- result$cptable_nrow_out

# Reconstruct the named list on the R side.
# list(which = ..., cptable = ..., ...) replaces the entire
# allocVector(STRSXP, …) + SET_STRING_ELT + setAttrib(…, R_NamesSymbol, …)
# block.  R's named-argument syntax automatically sets the `names` attribute.
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

# Conditional seventh element: mirrors `if (catcount > 0)` from C (line 342).
# output$csplit <- ... extends names(output) automatically, replacing
# SET_STRING_ELT(rname, 6, mkChar("csplit")) from line 344.
if (cc > 0L)
    output$csplit <- matrix(result$csplit[seq_len(cc * maxcat)],
                            nrow = cc, ncol = maxcat)
```

- **Explanation:**

  - `SET_STRING_ELT(rname, i, mkChar("literal"))` is removed from C at all
    seven call sites (lines 331, 333, 335, 337, 339, 341, 344). There is no C
    replacement. The string literals `"which"`, `"cptable"`, `"dsplit"`,
    `"isplit"`, `"dnode"`, `"inode"`, and `"csplit"` become R argument names in
    the `list(which = …, cptable = …, …)` call on the R side.

  - `mkChar(const char *)` (`Rf_mkChar`) is removed together with every
    `SET_STRING_ELT` call. It creates an interned `CHARSXP` from a C string, an
    operation that requires a live R interpreter and has no counterpart in pure
    C code. Because the string literals are compile-time constants, they are
    expressed as R symbol names rather than heap-allocated C string objects.

  - `allocVector(STRSXP, nout)` is also removed. The `STRSXP` type represents an
    R character vector — a GC-managed array of `CHARSXP` pointers. There is no
    way to pass such an object through the `.C` interface, and no such allocation
    is needed once the names are expressed as R argument names.

  - `setAttrib(rlist, R_NamesSymbol, rname)` and `R_NamesSymbol` are removed.
    The `names` attribute is set implicitly by R's `list(name = value, …)` syntax
    with zero C involvement.

  - The conditional write at line 344 (`if (catcount > 0) SET_STRING_ELT(rname,
    6, mkChar("csplit"))`) is mirrored by `if (cc > 0L) output$csplit <- …` in
    R. R's `$<-` assignment automatically appends `"csplit"` to `names(output)`,
    achieving the same conditional naming effect.

  - Because `nodecount`, `splitcount`, `catcount`, and `rp.num_unique_cp` are
    computed inside C and are required by R to correctly trim and reshape the
    flat output buffers, they are exposed as additional scalar `int *` output
    arguments (`nodecount_out`, `splitcount_out`, `catcount_out`,
    `cptable_nrow_out`). This is a general requirement whenever a `.Call`
    function uses internally-computed sizes to determine the shape of its output
    `SEXP` objects.

  - Indexing is unaffected by the conversion: `SET_STRING_ELT` used 0-based
    indices (slots 0–6) and the replacement R `list()` also uses 0-based
    positional assignment implicitly — no index adjustment is needed.

  - After the conversion, `#include "Rinternals.h"` can be removed from the
    converted C file if `SET_STRING_ELT`, `mkChar`, `STRSXP`, `CHARSXP`,
    `setAttrib`, and `R_NamesSymbol` are the only identifiers from that header
    that remain in use. Other compilation units that still use the `.Call` API
    can retain the include independently.
