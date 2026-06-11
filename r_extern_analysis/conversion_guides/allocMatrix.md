# Conversion Guide: `allocMatrix`

## 1. Overview of `allocMatrix` in R API

`allocMatrix` is a C function declared in `Rinternals.h` as
`SEXP Rf_allocMatrix(SEXPTYPE type, int nrow, int ncol)` and exposed via the
macro `#define allocMatrix Rf_allocMatrix`. It allocates a fresh, GC-managed R
matrix object: an `SEXPREC` whose data block holds `nrow * ncol` elements of
the type specified by `type` (either `REALSXP` for `double`, or `INTSXP` for
`int`), and whose `dim` attribute is set to the integer vector `c(nrow, ncol)`.
The returned `SEXP` must be immediately registered with `PROTECT` to prevent
garbage collection, and its raw data pointer must be extracted with `REAL()` or
`INTEGER()` before any C-level read/write access. Under the `.C/.Fortran` API,
`allocMatrix` has no role: all output memory is pre-allocated in R before the
call as a flat `numeric()` or `integer()` vector and passed to C as a raw
`double *` or `int *`; the matrix dimensionality is restored by the R caller
with `matrix()` after the call returns.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 241 | `cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));` |
| `rpart.c` | 261 | `dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));` |
| `rpart.c` | 269 | `dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));` |
| `rpart.c` | 278 | `inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));` |
| `rpart.c` | 285 | `isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));` |
| `rpart.c` | 293 | `csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));` |

### Data types and memory management

All six allocations reside in the single `.Call`-entry-point function
`rpart()` (`rpart.c` lines 40–349). The relevant variable declarations appear at
lines 64–72:

```c
SEXP which3, cptable3, dsplit3, isplit3, csplit3 = R_NilValue,
     dnode3, inode3;
int  nodecount, catcount, splitcount;
double **ddnode, *ddsplit[3];
int  *iinode[6], *iisplit[3];
int  **ccsplit;
```

The dimension values `nodecount`, `splitcount`, and `catcount` are all computed
at runtime by `rpcountup(tree, &nodecount, &splitcount, &catcount)` at line 260,
after the decision tree has been fully built. `rp.num_unique_cp` is a running
counter incremented during `make_cp_list` (line 229). `rp.num_resp` is set
during `rp_init` (line 201). `maxcat` is the maximum category count across all
variables (lines 150–165). All six values are therefore unknown at compile time.

Every allocation follows the same three-step idiom:

1. `PROTECT(allocMatrix(TYPE, nrow, ncol))` — allocate and protect.
2. `REAL(sexp)` or `INTEGER(sexp)` — extract the base pointer.
3. A loop that either fills the buffer directly (`cptable3`, `csplit3`) or
   sets up a ragged-array index of column pointers (`dnode3`, `dsplit3`,
   `inode3`, `isplit3`), each stepped by `nrow` to reach the next column.

The `csplit3` allocation at line 293 is additionally gated by
`if (catcount > 0)`, making it conditionally absent.

All six matrices are ultimately packed into a named `VECSXP` return list
(`rlist`) via `SET_VECTOR_ELT` (lines 330–345) and released by a single
`UNPROTECT(1 + nout)` at line 347.

### Distinct implementation patterns

1. **Conditionally-sized `REALSXP` matrix, flat-fill loop** — `rpart.c` line
   241. Row count is a runtime ternary expression (`xvals > 1 ? 5 : 3`); the
   data pointer is walked element-by-element with `dptr[i++]`.

2. **Variable-column `REALSXP` matrix, ragged-array column index** — `rpart.c`
   line 261. Both `nrow` (`nodecount`) and `ncol` (`3 + rp.num_resp`) are
   runtime values; the base pointer is distributed into a `double **ddnode`
   column-pointer array by stepping `dptr += nodecount` in a loop.

3. **Fixed-column `REALSXP` matrix, ragged-array column index with
   zero-fill** — `rpart.c` line 269. `nrow` is `splitcount` (runtime), `ncol`
   is the compile-time constant `3`; column pointers are set up in `ddsplit[3]`
   and each element is explicitly zeroed.

4. **Fixed-column `INTSXP` matrix, ragged-array column index (fixed ncol)** —
   `rpart.c` lines 278 and 285. Identical structure to pattern 3 but element
   type is `int`; column counts are the compile-time constants `6` and `3`
   respectively.

5. **Variable-dimension `INTSXP` matrix, conditional allocation, ragged-array
   column index with zero-fill** — `rpart.c` line 293. Both `nrow` (`catcount`)
   and `ncol` (`maxcat`) are runtime values; the entire allocation block is
   wrapped in `if (catcount > 0)` and the column-pointer array `ccsplit` is
   set to `NULL` in the `else` branch.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`allocMatrix` performs two logically distinct operations at once: it allocates a
flat `nrow * ncol` element buffer of the requested type inside an R-managed heap
object, and it attaches a `dim` attribute to that object so R recognises it as a
2-D matrix. Under the `.C` API neither operation has a place in C:

1. **Remove `allocMatrix(TYPE, nrow, ncol)` entirely.** The buffer is replaced by
   a pre-allocated `double *` (for `REALSXP`) or `int *` (for `INTSXP`) argument.
   The R caller creates it with `numeric(nrow * ncol)` or `integer(nrow * ncol)`
   before the `.C(…)` call. R stores matrices column-major — element `[r, c]` of
   an `nrow`-row matrix is at flat index `c * nrow + r` — which exactly matches
   the stride used by the ragged-array setup loops (`ptr += nrow`), so no index
   arithmetic changes are needed in C.

2. **Remove `PROTECT(…)` / `UNPROTECT(n)`.** R's garbage collector automatically
   protects any R object passed as an argument to `.C` for the duration of the
   call; the C code needs no explicit protection.

3. **Remove `REAL(sexp)` and `INTEGER(sexp)` unwrapping calls.** These accessor
   macros convert the `SEXP` wrapper to a raw pointer. Once `allocMatrix` is gone
   and the buffer arrives as a direct `double *` or `int *` argument, no
   unwrapping is required; the raw pointer is used immediately.

4. **Remove `SEXP` variable declarations for the allocated matrices.** Each
   `SEXP cptable3`, `SEXP dnode3`, etc. is replaced by the corresponding `double *`
   or `int *` function parameter.

5. **Pass dimension scalars explicitly.** Any dimension expression that was
   evaluated inside `allocMatrix` (e.g., `xvals > 1 ? 5 : 3`,
   `3 + rp.num_resp`, `nodecount`, `splitcount`, `catcount`, `maxcat`) must be
   pre-computed in R and passed to the C function as scalar `int *` arguments.
   This is necessary because the `.C` API conveys no array-length metadata; the
   C function must receive all dimension information it needs to set up
   ragged-array indices.

6. **Restore the 2-D matrix structure on the R side.** The `dim` attribute that
   `allocMatrix` would have set is restored after the `.C` call using
   `matrix(result$arg, nrow = nrow_val, ncol = ncol_val)`. R's column-major
   storage guarantees that the flat layout written by C is identical to what
   `matrix()` expects.

7. **Handle conditional allocation in R.** The `if (catcount > 0)` guard around
   `csplit3` is mirrored in R: when `catcount == 0` pass `integer(0)`; when
   `catcount > 0` pass `integer(catcount * maxcat)`. The C-side `if (catcount > 0)`
   guard is preserved and all accesses inside it remain safe.

This approach is fully `.C`-compatible because after the transformation every
matrix output is a plain `double *` or `int *` pointer; R's memory management
and type system handle the rest transparently.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Conditionally-Sized `REALSXP` Matrix with Flat-Fill Loop

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
 * cptable_out: pre-allocated flat double buffer of length nrow_cp * num_unique_cp.
 * The ternary row-count expression (xvals > 1 ? 5 : 3) is evaluated in R and
 * passed as the scalar nrow_cp_arg. num_unique_cp is also passed as a scalar.
 * PROTECT, REAL(), and the SEXP variable are removed.
 */
void rpart_c(/* ... other args ... */,
             const int *xvals_arg,         /* scalar: number of cross-validations */
             const int *nrow_cp_arg,       /* scalar: 5 if xvals > 1, else 3      */
             const int *num_unique_cp_arg, /* scalar: rp.num_unique_cp            */
             double    *cptable_out,       /* pre-allocated: numeric(nrow_cp * num_unique_cp) */
             /* ... */)
{
    int    xvals       = *xvals_arg;
    double scale       = 1.0 / tree->risk;
    int    i           = 0;
    double *dptr       = cptable_out;   /* was: dptr = REAL(cptable3) */

    for (CpTable cp = cptable; cp; cp = cp->forward) {
        dptr[i++] = cp->cp    * scale;
        dptr[i++] = cp->nsplit;
        dptr[i++] = cp->risk  * scale;
        if (xvals > 1) {
            dptr[i++] = cp->xrisk * scale;
            dptr[i++] = cp->xstd  * scale;
        }
    }
    /* No PROTECT/UNPROTECT */
}
```

Corresponding R-side call:

```r
nrow_cp     <- if (xvals > 1L) 5L else 3L
num_ucp     <- as.integer(rp_num_unique_cp)

result <- .C("rpart_c",
             # ... other args ...
             xvals_arg         = as.integer(xvals),
             nrow_cp_arg       = nrow_cp,
             num_unique_cp_arg = num_ucp,
             cptable_out       = numeric(nrow_cp * num_ucp),
             # ...)

cptable_mat <- matrix(result$cptable_out, nrow = nrow_cp, ncol = num_ucp)
```

- **Explanation:**
  - `allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp)` is removed from C.
    The ternary expression is evaluated in R before the call and the resulting
    integer is passed as `nrow_cp_arg`.
  - `PROTECT(…)` and the corresponding contribution to `UNPROTECT(1 + nout)` are
    removed.
  - `REAL(cptable3)` is replaced by the argument `cptable_out` directly; no
    unwrapping step exists.
  - The `SEXP cptable3` variable declaration is deleted; its name does not appear
    in the converted function.
  - The fill loop and all index arithmetic are preserved exactly.
  - `matrix(result$cptable_out, nrow = nrow_cp, ncol = num_ucp)` on the R side
    restores the 2-D structure that `allocMatrix` would have encoded in the `dim`
    attribute.

---

### Pattern: Variable-Column `REALSXP` Matrix with Ragged-Array Column Index

- **Locations:** `rpart.c` line 261

- **Original Context (.Call):**

```c
/* rpart.c:260-267 */
rpcountup(tree, &nodecount, &splitcount, &catcount);
dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));
ddnode = (double **) ALLOC(3 + rp.num_resp, sizeof(double *));
dptr = REAL(dnode3);
for (i = 0; i < 3 + rp.num_resp; i++) {
    ddnode[i] = dptr;
    dptr += nodecount;
}
/* later: rpmatrix(..., ddnode, ...) writes via ddnode[col][row] */
```

- **C/C++ Equivalent (.C):**

```c
/*
 * dnode_out: pre-allocated flat double buffer of length nodecount * ncols_dnode,
 *            where ncols_dnode = 3 + rp.num_resp, pre-computed in R.
 * nodecount and ncols_dnode are passed as scalar int * arguments.
 */
void rpart_c(/* ... other args ... */,
             const int *nodecount_arg,    /* scalar                              */
             const int *ncols_dnode_arg,  /* scalar: 3 + rp.num_resp             */
             double    *dnode_out,        /* pre-allocated: numeric(nodecount * ncols_dnode) */
             /* ... */)
{
    int     nodecount   = *nodecount_arg;
    int     ncols_dnode = *ncols_dnode_arg;

    double **ddnode = (double **) R_alloc(ncols_dnode, sizeof(double *));
    double  *dptr   = dnode_out;         /* was: REAL(dnode3) */

    for (int i = 0; i < ncols_dnode; i++) {
        ddnode[i] = dptr;
        dptr += nodecount;
    }

    /* downstream: rpmatrix(..., ddnode, ...) is unchanged */
}
```

Corresponding R-side call:

```r
ncols_dnode <- 3L + rp_num_resp   # rp.num_resp known from R-level rpart machinery

result <- .C("rpart_c",
             # ... other args ...
             nodecount_arg   = as.integer(nodecount),
             ncols_dnode_arg = ncols_dnode,
             dnode_out       = numeric(nodecount * ncols_dnode),
             # ...)

dnode_mat <- matrix(result$dnode_out, nrow = nodecount, ncol = ncols_dnode)
```

- **Explanation:**
  - `allocMatrix(REALSXP, nodecount, 3 + rp.num_resp)` is removed; the buffer
    length `nodecount * (3 + rp.num_resp)` is computed in R and allocated as
    `numeric(…)`.
  - `PROTECT` and `UNPROTECT` contributions are removed.
  - `REAL(dnode3)` becomes `dnode_out` directly.
  - `ALLOC(3 + rp.num_resp, sizeof(double *))` — which wraps `R_alloc` (see
    `rpart.h`) — is replaced by the explicit `R_alloc(ncols_dnode, sizeof(double *))`.
    This scratch allocation for the ragged-array index is automatically freed when
    the `.C` call returns.
  - The column-pointer setup loop (`ddnode[i] = dptr; dptr += nodecount`) is
    preserved unchanged; R's column-major layout ensures `+= nodecount` steps to
    the next column.

---

### Pattern: Fixed-Column `REALSXP` Matrix with Ragged-Array Index and Zero-Fill

- **Locations:** `rpart.c` line 269

- **Original Context (.Call):**

```c
/* rpart.c:269-276 */
dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));
dptr = REAL(dsplit3);
for (i = 0; i < 3; i++) {
    ddsplit[i] = dptr;
    dptr += splitcount;
    for (j = 0; j < splitcount; j++)
        ddsplit[i][j] = 0.0;
}
/* later: rpmatrix(..., ddsplit, ...) */
```

- **C/C++ Equivalent (.C):**

```c
/*
 * dsplit_out: pre-allocated flat double buffer of length splitcount * 3.
 * splitcount is passed as a scalar int * argument.
 * The fixed column count (3) remains a compile-time constant.
 */
void rpart_c(/* ... other args ... */,
             const int *splitcount_arg,  /* scalar */
             double    *dsplit_out,      /* pre-allocated: numeric(splitcount * 3) */
             /* ... */)
{
    int     splitcount = *splitcount_arg;
    double *ddsplit[3];
    double *dptr = dsplit_out;            /* was: REAL(dsplit3) */

    for (int i = 0; i < 3; i++) {
        ddsplit[i] = dptr;
        dptr += splitcount;
        for (int j = 0; j < splitcount; j++)
            ddsplit[i][j] = 0.0;          /* explicit zero-fill preserved */
    }

    /* downstream: rpmatrix(..., ddsplit, ...) is unchanged */
}
```

Corresponding R-side call:

```r
result <- .C("rpart_c",
             # ... other args ...
             splitcount_arg = as.integer(splitcount),
             dsplit_out     = numeric(splitcount * 3L),
             # ...)

dsplit_mat <- matrix(result$dsplit_out, nrow = splitcount, ncol = 3L)
```

- **Explanation:**
  - `allocMatrix(REALSXP, splitcount, 3)` is replaced by `numeric(splitcount * 3L)`
    in R. The column count is a compile-time constant and does not need to be
    passed as an extra argument.
  - `PROTECT` and `UNPROTECT` are removed.
  - `REAL(dsplit3)` becomes `dsplit_out` directly.
  - The ragged-array setup and zero-fill logic are preserved unchanged. R's
    `numeric(n)` initialises all elements to `0.0`, but keeping the explicit C
    zero-fill loop is safe and maintains parity with the original behaviour.

---

### Pattern: Fixed-Column `INTSXP` Matrices with Ragged-Array Column Index

- **Locations:** `rpart.c` line 278 (`nodecount x 6`); `rpart.c` line 285 (`splitcount x 3`)

- **Original Context (.Call):**

```c
/* rpart.c:278-290 */
inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));
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
/* later: rpmatrix(..., iisplit, ..., iinode, ...) */
```

- **C/C++ Equivalent (.C):**

```c
/*
 * inode_out:  pre-allocated flat int buffer of length nodecount * 6.
 * isplit_out: pre-allocated flat int buffer of length splitcount * 3.
 * The fixed column counts (6 and 3) are compile-time constants; only the
 * row counts need to be passed as scalar arguments.
 */
void rpart_c(/* ... other args ... */,
             const int *nodecount_arg,    /* scalar */
             const int *splitcount_arg,   /* scalar */
             int       *inode_out,        /* pre-allocated: integer(nodecount * 6)  */
             int       *isplit_out,       /* pre-allocated: integer(splitcount * 3) */
             /* ... */)
{
    int  nodecount  = *nodecount_arg;
    int  splitcount = *splitcount_arg;
    int *iinode[6], *iisplit[3];
    int *iptr;

    iptr = inode_out;                  /* was: INTEGER(inode3) */
    for (int i = 0; i < 6; i++) {
        iinode[i] = iptr;
        iptr += nodecount;
    }

    iptr = isplit_out;                 /* was: INTEGER(isplit3) */
    for (int i = 0; i < 3; i++) {
        iisplit[i] = iptr;
        iptr += splitcount;
    }

    /* downstream: rpmatrix(..., iisplit, ..., iinode, ...) is unchanged */
}
```

Corresponding R-side call:

```r
result <- .C("rpart_c",
             # ... other args ...
             nodecount_arg  = as.integer(nodecount),
             splitcount_arg = as.integer(splitcount),
             inode_out      = integer(nodecount * 6L),
             isplit_out     = integer(splitcount * 3L),
             # ...)

inode_mat  <- matrix(result$inode_out,  nrow = nodecount,  ncol = 6L)
isplit_mat <- matrix(result$isplit_out, nrow = splitcount, ncol = 3L)
```

- **Explanation:**
  - `allocMatrix(INTSXP, nodecount, 6)` and `allocMatrix(INTSXP, splitcount, 3)`
    are replaced by `integer(nodecount * 6L)` and `integer(splitcount * 3L)` in R.
  - `PROTECT` and `UNPROTECT` contributions for both matrices are removed.
  - `INTEGER(inode3)` and `INTEGER(isplit3)` are replaced by `inode_out` and
    `isplit_out` directly.
  - The ragged-array setup loops (`iptr += nodecount`, `iptr += splitcount`) are
    preserved exactly; R's column-major storage matches this stride.
  - `matrix(result$inode_out, nrow = nodecount, ncol = 6)` and
    `matrix(result$isplit_out, nrow = splitcount, ncol = 3)` restore the 2-D
    structure on the R side.

---

### Pattern: Conditionally Allocated Variable-Dimension `INTSXP` Matrix

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
 * csplit_out: pre-allocated flat int buffer of length catcount * maxcat when
 *             catcount > 0, or integer(0) when catcount == 0.
 * Both catcount and maxcat must be passed as scalar int * arguments since they
 * are runtime values needed to reconstruct the ragged-array index.
 */
void rpart_c(/* ... other args ... */,
             const int *catcount_arg,   /* scalar */
             const int *maxcat_arg,     /* scalar */
             int       *csplit_out,     /* pre-allocated: integer(catcount * maxcat)
                                           or integer(0) when catcount == 0       */
             /* ... */)
{
    int  catcount = *catcount_arg;
    int  maxcat   = *maxcat_arg;
    int **ccsplit = NULL;
    int  *iptr;

    if (catcount > 0) {
        ccsplit = (int **) R_alloc(maxcat, sizeof(int *));   /* scratch index */
        iptr = csplit_out;             /* was: INTEGER(csplit3) */
        for (int i = 0; i < maxcat; i++) {
            ccsplit[i] = iptr;
            iptr += catcount;
            for (int j = 0; j < catcount; j++)
                ccsplit[i][j] = 0;
        }
    }
    /* downstream code using ccsplit is unchanged (NULL guard already present) */
}
```

Corresponding R-side call:

```r
csplit_len <- if (catcount > 0L) catcount * maxcat else 0L

result <- .C("rpart_c",
             # ... other args ...
             catcount_arg = as.integer(catcount),
             maxcat_arg   = as.integer(maxcat),
             csplit_out   = integer(csplit_len),
             # ...)

if (catcount > 0L)
    csplit_mat <- matrix(result$csplit_out, nrow = catcount, ncol = maxcat)
```

- **Explanation:**
  - The conditional `if (catcount > 0) PROTECT(allocMatrix(INTSXP, catcount, maxcat))`
    is mirrored in R: pass `integer(catcount * maxcat)` when `catcount > 0`, or
    `integer(0)` when `catcount == 0`. Passing `integer(0)` is safe because the C
    guard `if (catcount > 0)` gates all access to `csplit_out`.
  - `PROTECT` and the conditional increment to `UNPROTECT(1 + nout)` are removed.
  - `INTEGER(csplit3)` becomes `csplit_out` directly.
  - `ALLOC(maxcat, sizeof(int *))` — a wrapper around `R_alloc` defined in
    `rpart.h` — is replaced by the explicit `R_alloc(maxcat, sizeof(int *))`.
    This scratch memory for the ragged-array column-pointer index is automatically
    freed when the `.C` call returns.
  - The explicit `ccsplit[i][j] = 0` zero-fill is preserved; R's `integer(n)`
    initialises to zero, but keeping the C-level fill maintains behavioural parity.
  - Both `catcount` and `maxcat` must be passed as scalar arguments because the C
    function needs them both to correctly step the column-pointer index.
