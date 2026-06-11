# Conversion Guide: `STRSXP`

## 1. Overview of `STRSXP` in R API

`STRSXP` is the integer constant `16` of type `SEXPTYPE`, defined in
`Rinternals.h`. It is the type tag that identifies an R character vector
(`typeof(x) == "character"`) inside R's internal `SEXPREC` representation. It
is passed as the first argument to `allocVector(STRSXP, n)` to request a
freshly heap-allocated, GC-managed array of `n` `CHARSXP` slots (each slot
holding one interned C string); individual elements are written with
`SET_STRING_ELT(sexp, i, mkChar("literal"))` and read back with
`CHAR(STRING_ELT(sexp, i))`. In the rpart codebase, `STRSXP` is used
exclusively to build a character names vector that is attached to a `VECSXP`
list as its `names` attribute, enabling R callers to access list elements by
name. Under the `.C` API, `STRSXP` has no direct equivalent: character vectors
cannot be passed through the `.C` interface, so the names-vector construction
must be moved entirely to the R side after the `.C` call returns.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 328 | `SEXP rname = allocVector(STRSXP, nout);` |

### Extended context (lines 325–349 of `rpart.c`)

```c
/* Create the output list */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));  /* line 327 */
SEXP rname = allocVector(STRSXP, nout);            /* line 328 – the STRSXP */
setAttrib(rlist, R_NamesSymbol, rname);            /* line 329 */
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

### Data types and memory management

- `allocVector(STRSXP, nout)` allocates a character vector of `nout` elements
  (6 or 7, determined at runtime by `catcount > 0`).
- The returned `SEXP rname` is **not individually `PROTECT`ed**: it is
  implicitly protected because `setAttrib` immediately attaches it to the
  already-protected `rlist`. R's garbage collector considers an object reachable
  once it is an attribute of a protected object.
- `mkChar("literal")` creates (or retrieves from a global hash) an interned
  `CHARSXP` for each string literal. `SET_STRING_ELT(rname, i, …)` stores the
  `CHARSXP` at position `i` of the character vector.
- The `STRSXP` is strictly an output-naming artefact: it carries no numeric
  data and is never accessed by downstream C computation. Its sole consumer is
  R's attribute system (`setAttrib` + `R_NamesSymbol`).

### Companion API calls observed alongside `STRSXP`

| Call | Role |
|------|------|
| `allocVector(STRSXP, n)` | Allocates the `n`-element character vector |
| `setAttrib(rlist, R_NamesSymbol, rname)` | Attaches the names vector to the list |
| `SET_STRING_ELT(rname, i, mkChar("…"))` | Writes a string literal into slot `i` |
| `mkChar(const char *)` | Creates or retrieves an interned `CHARSXP` from a literal |
| `CHAR(STRING_ELT(sexp, i))` | Reads back a `const char *` from slot `i` (not used here, but the read counterpart) |

### Distinct implementation patterns

Only one pattern exists in this codebase:

1. **Fixed string-literal names vector for a return list** — a `STRSXP` of
   known, compile-time-constant strings is built in C and attached as the
   `names` attribute of a `VECSXP` return list. The names are string literals
   (`"which"`, `"cptable"`, etc.) embedded directly in the source.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

The `.C` API does not support `SEXP` values, `VECSXP` lists, or `STRSXP`
character vectors as function arguments or return values. Consequently, the
entire list-assembly block — `allocVector(VECSXP, …)`, `allocVector(STRSXP, …)`,
`setAttrib`, `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`, and the final
`return rlist` — must be **removed from C entirely** and **re-expressed in R**
after the `.C` call returns.

The transformation proceeds in three steps:

1. **Decompose the return list into separate output arguments.** Each `SEXP`
   that was a `VECSXP` element (`which3`, `cptable3`, `dsplit3`, `isplit3`,
   `dnode3`, `inode3`, `csplit3`) becomes a separate pre-allocated output
   argument of the appropriate basic C type (`int *` or `double *`). The R
   caller allocates these vectors/matrices with `integer(n)` or `double(n)`
   before calling `.C`.

2. **Remove all character-vector and list construction from C.** The
   `STRSXP`/`VECSXP` block collapses to nothing in the C function. No string
   literals, no `mkChar`, no `setAttrib`, no `R_NamesSymbol`. The C function
   becomes `void`-returning.

3. **Reconstruct the named list in R.** After `.C` returns, the R caller
   assembles a named list using `list(which = result$which, cptable = …, …)`.
   The names that were previously hard-coded as `mkChar("which")` etc. are now
   standard R argument names, which is the natural R idiom and requires no C
   involvement.

This strategy is fully `.C`-compatible because:
- `.C` communicates exclusively through typed C pointers (`int *`, `double *`).
- Character string handling belongs to R's interpreter layer, which is
  inaccessible from `.C` functions.
- Named-list construction is trivial in R and adds zero overhead to the C code.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Fixed String-Literal Names Vector for a Return List

- **Locations:** `rpart.c` lines 326–348

- **Original Context (.Call):**

```c
/* rpart.c:326-348 — STRSXP used to name the elements of a VECSXP return list */
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
 * The entire STRSXP/VECSXP assembly block is removed.
 * Each former list element becomes a separate pre-allocated output argument.
 * The function returns void; the R caller builds the named list.
 *
 * Only the relevant tail of the converted function is shown below.
 * All preceding computation (partition, rpmatrix, etc.) is unchanged.
 */
void rpart_c(/* ... input args ... */,
             int    *which,      /* pre-allocated: integer(n)                    */
             double *cptable,    /* pre-allocated: double(cptable_rows * cp_len) */
             double *dsplit,     /* pre-allocated: double(splitcount * 3)        */
             int    *isplit,     /* pre-allocated: integer(splitcount * 3)       */
             double *dnode,      /* pre-allocated: double(nodecount * (3+nresp)) */
             int    *inode,      /* pre-allocated: integer(nodecount * 6)        */
             int    *csplit,     /* pre-allocated: integer(catcount * maxcat)
                                    or integer(0) when catcount == 0            */
             /* scalar shape outputs so R can reshape the matrices: */
             int    *nodecount_out,
             int    *splitcount_out,
             int    *catcount_out)
{
    /*
     * All downstream logic that previously wrote into INTEGER(which3),
     * REAL(cptable3), etc. now writes directly into the pointer arguments:
     *   which3  -> which
     *   cptable3-> cptable
     *   dsplit3 -> dsplit
     *   isplit3 -> isplit
     *   dnode3  -> dnode
     *   inode3  -> inode
     *   csplit3 -> csplit  (only populated when catcount > 0)
     *
     * The following block is completely removed — no SEXP, no STRSXP,
     * no mkChar, no SET_STRING_ELT, no setAttrib, no UNPROTECT, no return.
     *
     * REMOVED:
     *   int nout = catcount > 0 ? 7 : 6;
     *   SEXP rlist = PROTECT(allocVector(VECSXP, nout));
     *   SEXP rname = allocVector(STRSXP, nout);
     *   setAttrib(rlist, R_NamesSymbol, rname);
     *   SET_VECTOR_ELT / SET_STRING_ELT / mkChar calls
     *   UNPROTECT(1 + nout);
     *   return rlist;
     */
    *nodecount_out  = nodecount;
    *splitcount_out = splitcount;
    *catcount_out   = catcount;
    /* function ends here — void return */
}
```

- **R-side call and list reconstruction:**

```r
# Pre-allocate all output buffers before .C
n            <- as.integer(nrow(xmat))
# nodecount, splitcount, catcount are not known before the call;
# allocate conservatively (upper bounds) or call a sizing pre-pass.
result <- .C("rpart_c",
             # ... input arguments ...
             which         = integer(n),
             cptable       = double(cptable_rows * cp_len),
             dsplit        = double(splitcount_max * 3L),
             isplit        = integer(splitcount_max * 3L),
             dnode         = double(nodecount_max * (3L + nresp)),
             inode         = integer(nodecount_max * 6L),
             csplit        = integer(max(0L, catcount_max * maxcat)),
             nodecount_out = integer(1L),
             splitcount_out= integer(1L),
             catcount_out  = integer(1L))

# Read the actual counts filled by C
nc <- result$nodecount_out
sc <- result$splitcount_out
cc <- result$catcount_out

# Reconstruct the named list — replaces the STRSXP/VECSXP block in C
output <- list(
    which   = result$which,
    cptable = matrix(result$cptable, nrow = cptable_rows, ncol = cp_len),
    dsplit  = matrix(result$dsplit[seq_len(sc * 3L)],  nrow = sc, ncol = 3L),
    isplit  = matrix(result$isplit[seq_len(sc * 3L)],  nrow = sc, ncol = 3L),
    dnode   = matrix(result$dnode[seq_len(nc * (3L + nresp))],
                     nrow = nc, ncol = 3L + nresp),
    inode   = matrix(result$inode[seq_len(nc * 6L)],   nrow = nc, ncol = 6L)
)
if (cc > 0L)
    output$csplit <- matrix(result$csplit[seq_len(cc * maxcat)],
                            nrow = cc, ncol = maxcat)
```

- **Explanation:**

  - `allocVector(STRSXP, nout)` is removed entirely from C. There is no
    `char **` equivalent to pass through `.C`; the `.C` API does not support
    character-vector arguments that store arbitrary named strings.
  - `SET_STRING_ELT(rname, i, mkChar("literal"))` collapses to the R argument
    name in the `list(which = …, cptable = …, …)` call. The string literals
    `"which"`, `"cptable"`, `"dsplit"`, `"isplit"`, `"dnode"`, `"inode"`, and
    `"csplit"` become R symbol names, not heap-allocated C strings.
  - `setAttrib(rlist, R_NamesSymbol, rname)` and `R_NamesSymbol` are removed;
    the `names` attribute of an R `list()` is set automatically by the named
    argument syntax.
  - `mkChar` is removed. This function creates an interned `CHARSXP` (an
    internal scalar string object); it has no counterpart in pure C code that
    does not link against `Rinternals.h`.
  - `allocVector(VECSXP, nout)`, `SET_VECTOR_ELT`, and `PROTECT`/`UNPROTECT`
    are also removed as part of the same transformation (covered in detail in
    the `SEXP.md` guide, Pattern: Named-List Return Value).
  - The conditional element (`csplit`, present only when `catcount > 0`) is
    handled on the R side with an `if (cc > 0L)` guard after the `.C` call,
    directly mirroring the original `if (catcount > 0)` guard in C.
  - Because `nodecount`, `splitcount`, and `catcount` are computed inside C
    and needed by R to properly reshape the flat output arrays, they must be
    returned as additional scalar `int *` output arguments. This is a general
    requirement whenever a `.Call` function uses internally computed sizes to
    determine the shape of its `SEXP` outputs.
