# Conversion Guide: `mkChar`

## 1. Overview of `mkChar` in R API

`mkChar` is a macro defined in `Rinternals.h` as `#define mkChar Rf_mkChar`, where
`Rf_mkChar` is declared as `SEXP Rf_mkChar(const char *)`. It accepts a
null-terminated C string literal and returns a `SEXP` of internal type `CHARSXP`
(type code 9) — R's interned, immutable scalar string object. Internally,
`Rf_mkChar` looks up the string in a process-wide hash table and returns an
existing `CHARSXP` if the string has been seen before, or allocates and interns a
new one otherwise; the returned object is owned by R's string-interning cache and
does not need to be individually `PROTECT`ed. In the rpart codebase `mkChar` is
used exclusively as the value argument to `SET_STRING_ELT` when building a
`STRSXP` names vector for a `VECSXP` return list; it has no role in numeric
computation. Under the `.C/.Fortran` API, `mkChar` — together with the entire
`CHARSXP`/`STRSXP` infrastructure it produces — is completely removed from C
because the `.C` interface does not support `SEXP` types and the names-vector
construction is moved to the R side.

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

### Extended context (lines 325–349 of `rpart.c`)

```c
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

### Data types and memory management

- **`mkChar(const char *)`** takes a compile-time string literal (`"which"`,
  `"cptable"`, `"dsplit"`, `"isplit"`, `"dnode"`, `"inode"`, `"csplit"`) and
  returns a `SEXP` of internal type `CHARSXP` (type code 9). `CHARSXP` is R's
  private scalar string type; it is not a `char *` and cannot be passed to
  standard C string functions.
- The returned `CHARSXP` is stored in R's global string-interning hash table and
  is therefore reachable by the GC at all times. It does not require a separate
  `PROTECT` call; it will not be collected between the `mkChar` call and the
  immediately following `SET_STRING_ELT` call.
- **`SET_STRING_ELT(rname, i, v)`** stores the `CHARSXP v` produced by `mkChar`
  into slot `i` of the `STRSXP rname`. The two calls always appear as a matched
  pair: `mkChar` produces the `CHARSXP`; `SET_STRING_ELT` consumes it.
- **`SEXP rname`** is a `STRSXP` (type code 16) allocated on line 328 by
  `allocVector(STRSXP, nout)`. It is not individually `PROTECT`ed because
  `setAttrib(rlist, R_NamesSymbol, rname)` on line 329 attaches it as an
  attribute of the already-`PROTECT`ed `rlist`, making it transitively reachable.
- Lines 331–341 are unconditional (always executed for 6-element output). Line
  344 is guarded by `if (catcount > 0)`, making the seventh `mkChar("csplit")`
  call optional.
- All seven string literals (`"which"`, `"cptable"`, `"dsplit"`, `"isplit"`,
  `"dnode"`, `"inode"`, `"csplit"`) are compile-time constants. None is computed
  at runtime.

### Companion API calls observed alongside `mkChar`

| Call | Role |
|------|------|
| `SET_STRING_ELT(rname, i, …)` | Consumes every `CHARSXP` produced by `mkChar` |
| `allocVector(STRSXP, nout)` | Allocates the `STRSXP` into whose slots `mkChar` results are stored |
| `setAttrib(rlist, R_NamesSymbol, rname)` | Attaches the completed `STRSXP` as the `names` attribute of `rlist` |
| `allocVector(VECSXP, nout)` | Allocates the parent list whose elements are being named |
| `SET_VECTOR_ELT(rlist, i, sexp)` | Stores each numeric output `SEXP` into the parent list |
| `PROTECT(rlist)` / `UNPROTECT(1 + nout)` | GC guards for the list and its numeric-data children |
| `R_NamesSymbol` | Pre-interned attribute key `"names"` consumed by `setAttrib` |

### Distinct implementation patterns

Only one functional pattern is present in the codebase:

1. **Compile-time string-literal `CHARSXP` production for a fixed-size names
   vector** — `mkChar` is called once per slot of a `STRSXP` names vector, each
   time with a distinct compile-time string literal. Six calls are unconditional;
   one (`mkChar("csplit")`) is conditional on `catcount > 0`. The `CHARSXP`
   values produced are used immediately by `SET_STRING_ELT` and have no other
   consumers.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`mkChar` (`Rf_mkChar`) is part of R's `SEXP`-based internal string infrastructure
and requires a live R interpreter session to operate. It allocates (or retrieves)
objects inside R's GC-managed heap and returns a `SEXP` handle. The `.C` API
communicates exclusively through basic C pointer types (`int *`, `double *`,
`char **`); `SEXP` handles cannot be passed through the `.C` interface. Therefore:

1. **`mkChar` is removed from C with no C-level replacement.** The function call
   and the `CHARSXP` it produces are both deleted entirely. No `char *`, no
   `strdup`, no `strcpy`, and no `char **` argument is introduced as a substitute.

2. **`SET_STRING_ELT` is removed at the same time.** `mkChar` exists solely to
   supply the third argument to `SET_STRING_ELT`; when `SET_STRING_ELT` is
   removed (as required by the `.C` migration — see `SET_STRING_ELT.md`),
   `mkChar` has no remaining call site and disappears automatically.

3. **The string literals become R argument names.** Each literal that was passed
   to `mkChar("which")`, `mkChar("cptable")`, etc. becomes the named argument
   label in an R `list(which = …, cptable = …, …)` call that assembles the output
   on the R side after the `.C` call returns. This is the natural R idiom and
   requires zero C involvement.

4. **The conditional seventh call is handled in R.** The original
   `if (catcount > 0) { SET_STRING_ELT(rname, 6, mkChar("csplit")); }` is
   replaced by `if (cc > 0L) output$csplit <- …` in R. R's `$<-` assignment
   automatically appends `"csplit"` to `names(output)`, exactly mirroring the
   effect of the original conditional `mkChar` + `SET_STRING_ELT` pair.

5. **`#include "Rinternals.h"` can be dropped from the converted file** if
   `mkChar`, `SET_STRING_ELT`, `STRSXP`, `CHARSXP`, `setAttrib`, and
   `R_NamesSymbol` are the only identifiers from that header that remain in use.
   Other compilation units that still use `.Call` retain the include independently.

This approach is fully `.C`-compatible because:
- `.C` functions have no access to R's object heap or the string-interning table
  that `Rf_mkChar` queries.
- All seven string literals are compile-time constants that belong naturally in R
  source code as argument names, not in C as interned `CHARSXP` objects.
- Named-list construction (`list(name = value, …)`) is idiomatic R and
  introduces no performance cost compared with the C-side `mkChar` +
  `SET_STRING_ELT` + `setAttrib` chain.

### Relationship to companion guides

`mkChar` is functionally inseparable from `SET_STRING_ELT` (its sole consumer),
`STRSXP` (the type of the vector its result is stored into), and
`setAttrib`/`R_NamesSymbol` (which attach the completed names vector to `rlist`).
The full removal of this cluster is described from each of those perspectives in
`SET_STRING_ELT.md`, `STRSXP.md`, and (for the parent list and its elements)
`VECSXP.md`, `PROTECT.md`, and `SET_VECTOR_ELT`-related guides.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Compile-Time String-Literal CHARSXP Production for a Fixed-Size Names Vector

- **Locations:** `rpart.c` lines 331, 333, 335, 337, 339, 341 (unconditional);
  `rpart.c` line 344 (conditional on `catcount > 0`)

- **Original Context (.Call):**

```c
/* rpart.c:326-348
 * mkChar is called once per slot of the STRSXP names vector.
 * Each call produces a CHARSXP immediately consumed by SET_STRING_ELT.
 * The six unconditional calls populate the fixed names;
 * the seventh is guarded by if (catcount > 0).
 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));   /* parent list */
SEXP rname = allocVector(STRSXP, nout);            /* names vector */
setAttrib(rlist, R_NamesSymbol, rname);

SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));         /* line 331 */
SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable"));       /* line 333 */
SET_VECTOR_ELT(rlist, 2, dsplit3);
SET_STRING_ELT(rname, 2, mkChar("dsplit"));        /* line 335 */
SET_VECTOR_ELT(rlist, 3, isplit3);
SET_STRING_ELT(rname, 3, mkChar("isplit"));        /* line 337 */
SET_VECTOR_ELT(rlist, 4, dnode3);
SET_STRING_ELT(rname, 4, mkChar("dnode"));         /* line 339 */
SET_VECTOR_ELT(rlist, 5, inode3);
SET_STRING_ELT(rname, 5, mkChar("inode"));         /* line 341 */
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));    /* line 344 */
}
UNPROTECT(1 + nout);
return rlist;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The entire mkChar / SET_STRING_ELT / STRSXP / VECSXP / setAttrib block
 * is removed.  No C replacement exists for mkChar.  The converted function
 * is void-returning.  Each former VECSXP slot becomes a separate
 * pre-allocated output pointer argument.
 *
 * Only the relevant tail of the converted function is shown.
 * All preceding computation is unchanged except that INTEGER(which3),
 * REAL(cptable3), etc. are replaced by direct writes into the
 * corresponding pointer arguments.
 */
void rpart_c(/* --- input arguments --- */
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
             int    *which,           /* pre-allocated: integer(n)                       */
             double *cptable,         /* pre-allocated: double(cptable_rows * cp_ncol)   */
             double *dsplit,          /* pre-allocated: double(splitcount_max * 3)       */
             int    *isplit,          /* pre-allocated: integer(splitcount_max * 3)      */
             double *dnode,           /* pre-allocated: double(nodecount_max*(3+nresp))  */
             int    *inode,           /* pre-allocated: integer(nodecount_max * 6)       */
             int    *csplit,          /* pre-allocated: integer(catcount_max * maxcat)
                                         or integer(1) stub when catcount_max == 0      */
             /* --- scalar shape outputs written by C so R can trim buffers --- */
             int    *nodecount_out,
             int    *splitcount_out,
             int    *catcount_out,
             int    *cptable_nrow_out)
{
    /*
     * COMPLETELY REMOVED — the mkChar cluster and all its dependencies:
     *
     *   int nout = catcount > 0 ? 7 : 6;
     *   SEXP rlist = PROTECT(allocVector(VECSXP, nout));
     *   SEXP rname = allocVector(STRSXP, nout);
     *   setAttrib(rlist, R_NamesSymbol, rname);
     *   SET_VECTOR_ELT(rlist, 0, which3);
     *   SET_STRING_ELT(rname, 0, mkChar("which"));    <- removed: line 331
     *   SET_VECTOR_ELT(rlist, 1, cptable3);
     *   SET_STRING_ELT(rname, 1, mkChar("cptable"));  <- removed: line 333
     *   SET_VECTOR_ELT(rlist, 2, dsplit3);
     *   SET_STRING_ELT(rname, 2, mkChar("dsplit"));   <- removed: line 335
     *   SET_VECTOR_ELT(rlist, 3, isplit3);
     *   SET_STRING_ELT(rname, 3, mkChar("isplit"));   <- removed: line 337
     *   SET_VECTOR_ELT(rlist, 4, dnode3);
     *   SET_STRING_ELT(rname, 4, mkChar("dnode"));    <- removed: line 339
     *   SET_VECTOR_ELT(rlist, 5, inode3);
     *   SET_STRING_ELT(rname, 5, mkChar("inode"));    <- removed: line 341
     *   if (catcount > 0) {
     *       SET_VECTOR_ELT(rlist, 6, csplit3);
     *       SET_STRING_ELT(rname, 6, mkChar("csplit")); <- removed: line 344
     *   }
     *   UNPROTECT(1 + nout);
     *   return rlist;
     *
     * The shape scalars are exposed so R can correctly trim and reshape
     * the over-allocated flat output buffers.
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
             # --- pre-allocated output buffers (one per former VECSXP slot) ---
             which        = integer(n),
             cptable      = double(nodecount_max * cp_ncol),
             dsplit       = double(splitcount_max * 3L),
             isplit       = integer(splitcount_max * 3L),
             dnode        = double(nodecount_max * (3L + nresp)),
             inode        = integer(nodecount_max * 6L),
             csplit       = integer(max(1L, catcount_max * maxcat)),
             # --- shape scalars written by C ---
             nodecount_out    = integer(1L),
             splitcount_out   = integer(1L),
             catcount_out     = integer(1L),
             cptable_nrow_out = integer(1L))

# Read the actual sizes filled by C.
nc  <- result$nodecount_out
sc  <- result$splitcount_out
cc  <- result$catcount_out
cpr <- result$cptable_nrow_out

# Reconstruct the named list on the R side.
# list(which = ..., cptable = ..., ...) replaces the entire
# allocVector(STRSXP, ...) + mkChar(...) * 7 + SET_STRING_ELT(...) * 7
# + setAttrib(..., R_NamesSymbol, ...) block.
# R's named-argument syntax automatically sets the `names` attribute;
# no mkChar, no CHARSXP, no STRSXP is needed.
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
# output$csplit <- ... automatically appends "csplit" to names(output),
# replacing SET_STRING_ELT(rname, 6, mkChar("csplit")) at line 344.
if (cc > 0L)
    output$csplit <- matrix(result$csplit[seq_len(cc * maxcat)],
                            nrow = cc, ncol = maxcat)
```

- **Explanation:**

  - `mkChar(const char *)` (`Rf_mkChar`) creates or retrieves an interned
    `CHARSXP` from R's global string-interning hash table. This operation
    requires a live R interpreter and the `SEXP` type system. Both are
    inaccessible inside a `.C` function, so `mkChar` is removed at all seven
    call sites (lines 331, 333, 335, 337, 339, 341, 344) with no C-level
    replacement.

  - Because `mkChar` existed solely to produce the third argument to
    `SET_STRING_ELT`, and `SET_STRING_ELT` is itself removed as part of the
    `.C` migration (see `SET_STRING_ELT.md`), the two removals are always
    performed together. There is no scenario in which `SET_STRING_ELT` is
    removed but `mkChar` is retained, or vice versa.

  - The seven string literals (`"which"`, `"cptable"`, `"dsplit"`, `"isplit"`,
    `"dnode"`, `"inode"`, `"csplit"`) that were arguments to `mkChar` become R
    argument names in the `list(which = …, cptable = …, …)` call. R's
    named-argument syntax sets the `names` attribute of the list automatically,
    reproducing the effect of the original `mkChar` + `SET_STRING_ELT` +
    `setAttrib` chain at the R interpreter level with no C involvement.

  - `allocVector(STRSXP, nout)` (line 328) is also removed. The `STRSXP` type
    that served as the container for `mkChar` results has no equivalent in the
    `.C` API; the `.C` dispatcher does not support arbitrary character-vector
    arguments.

  - The conditional call `mkChar("csplit")` at line 344 (inside
    `if (catcount > 0)`) is mirrored by `if (cc > 0L) output$csplit <- …` on
    the R side. R's `$<-` assignment appends `"csplit"` to `names(output)`,
    achieving the identical conditional-naming effect without any `mkChar`
    invocation.

  - Indexing is unaffected: `SET_STRING_ELT` used 0-based slot indices (0–6);
    the R `list()` argument positions are also 0-based implicitly. No index
    adjustment is needed.

  - After the conversion, `#include "Rinternals.h"` can be removed from the
    converted C file if `mkChar`, `SET_STRING_ELT`, `STRSXP`, `CHARSXP`,
    `setAttrib`, and `R_NamesSymbol` are the only identifiers from that header
    still in use. Removing the include eliminates the dependency on R's
    internal object-representation API, which is the explicit goal of the
    `.Call` to `.C` migration.
