# Conversion Guide: `INTSXP`

## 1. Overview of `INTSXP` in R API

`INTSXP` is an integer constant (`13`) of type `SEXPTYPE` defined in
`Rinternals.h`. It is the type tag that identifies an R integer vector
(`typeof(x) == "integer"`) inside R's internal `SEXPREC` representation. It is
passed as the first argument to `allocVector(INTSXP, n)` or
`allocMatrix(INTSXP, nrow, ncol)` to request a freshly heap-allocated,
GC-managed block of `int` values of length `n` (or `nrow * ncol`); the returned
`SEXP` is then unwrapped to a raw `int *` via `INTEGER(sexp)`. Under the `.C`
API, `INTSXP` appears additionally as a value in `R_NativePrimitiveArgType[]`
arrays to declare that a given `.C` argument carries an `int *` pointer.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `pred_rpart.c` | 139 | `SEXP where = PROTECT(allocVector(INTSXP, n));` |
| `rpart.c` | 194 | `which3 = PROTECT(allocVector(INTSXP, n));` |
| `rpart.c` | 278 | `inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));` |
| `rpart.c` | 285 | `isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));` |
| `rpart.c` | 293 | `csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));` |
| `rpartexp2.c` | 47 | `SEXP keep = PROTECT(allocVector(INTSXP, n));` |

### Data types and memory management

- In every case `INTSXP` is the type selector passed to `allocVector` or
  `allocMatrix`; it is never used standalone.
- `PROTECT` / `UNPROTECT` wrap every allocation to pin the resulting `SEXP`
  against the garbage collector for the lifetime of the enclosing `.Call`
  function.
- `INTEGER(sexp)` immediately follows each allocation to obtain the underlying
  `int *` that is then used for all read/write access within the C code.

### Distinct implementation patterns

1. **1-D integer vector** (`allocVector(INTSXP, n)`) — used in `pred_rpart.c`
   line 139, `rpart.c` line 194, and `rpartexp2.c` line 47.
2. **2-D integer matrix with fixed column count** (`allocMatrix(INTSXP, nrow, ncol)`)
   — used in `rpart.c` lines 278 (6 columns), 285 (3 columns), and
   293 (conditional allocation with `catcount` rows and `maxcat` columns).

### Role of `INTEGER()` accessor

After allocation `INTEGER(sexp)` returns the `int *` base pointer of the
underlying data array. All C-level arithmetic operates on that pointer, not on
the `SEXP` wrapper. This means the `.Call`-to-`.C` migration is primarily a
matter of removing the allocation and `PROTECT` machinery and replacing the
`SEXP` variable with a pre-allocated `int *` argument.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under `.Call`, the C function allocates its output integer storage internally
via `allocVector`/`allocMatrix`, protects it from the GC with `PROTECT`, and
returns it (or places it into a list) as a `SEXP`. The `.C` API forbids `SEXP`
arguments and return values entirely: the C function must be `void`-returning
and must accept only basic C pointer types (`int *`, `double *`, etc.).

The required transformation is therefore:

1. **Remove `allocVector(INTSXP, …)` and `allocMatrix(INTSXP, …, …)`.** Every
   such allocation becomes a pre-allocated `int *` argument supplied by the R
   caller before the `.C(…)` call.
2. **Remove `PROTECT(…)` / `UNPROTECT(n)`.** Because the memory is now owned by
   R's `integer()` vector (allocated on the R side), the GC automatically
   protects it for the duration of the `.C` call — no explicit protection is
   needed in C.
3. **Remove `INTEGER(sexp)` unwrapping calls.** The `int *` pointer arrives
   directly as a function argument; there is no `SEXP` wrapper to strip.
4. **Declare the argument type** as `INTSXP` in the corresponding
   `R_NativePrimitiveArgType[]` array so that R's `.C` dispatcher performs
   type coercion automatically.
5. **R-side allocation.** The calling R code creates the output vector with
   `integer(n)` (for a vector) or `integer(nrow * ncol)` (for a matrix, since
   R stores matrices as column-major flat arrays). After the `.C` call, the R
   code can `dim()` the result appropriately.

This approach is fully `.C` compatible because `.C` exclusively communicates
through raw C pointers; `INTSXP` in C source is only needed as a type tag in
the `R_NativePrimitiveArgType` registration array.

---

## 4. Step-by-Step Conversion Examples

### Pattern: 1-D Integer Vector Allocation

- **Locations:** `pred_rpart.c` line 139; `rpart.c` line 194; `rpartexp2.c`
  line 47

- **Original Context (.Call):**

```c
/* Inside a SEXP-returning .Call function */
int n = asInteger(dimx);              /* or LENGTH(dtimes), etc. */
SEXP where = PROTECT(allocVector(INTSXP, n));
/* ... work on INTEGER(where)[i] ... */
UNPROTECT(1);
return where;
```

Concrete instances:

```c
/* pred_rpart.c:133-147 */
SEXP pred_rpart(SEXP dimx, /* ... 11 more SEXP args ... */)
{
    int n = asInteger(dimx);
    SEXP where = PROTECT(allocVector(INTSXP, n));
    pred_rpart0(INTEGER(dimx), /* ... */, INTEGER(where));
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
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Converted signature: output array is now a pre-allocated int * argument.
 * The function returns void; the caller inspects the filled array via .C().
 */
void pred_rpart_c(const int *dimx, const int *nnode, const int *nsplit,
                  const int *dimc, const int *nnum, const int *nodes2,
                  const int *vnum, const double *split2, const int *csplit2,
                  const int *usesur, const double *xdata2, const int *xmiss2,
                  int *where)   /* <-- was: SEXP where = PROTECT(allocVector(INTSXP, n)) */
{
    int n = dimx[0];            /* dimx[0] carries nrow; no asInteger() needed */
    pred_rpart0(dimx, *nnode, *nsplit, dimc, nnum, nodes2,
                vnum, split2, csplit2, usesur, xdata2, xmiss2,
                where);         /* INTEGER(where) -> where directly */
    /* No UNPROTECT needed */
}

void rpartexp2_c(const double *dtimes, const int *n,
                 const double *eps, int *keep)
{
    Rpartexp2(*n, dtimes, *eps, keep);
}
```

Corresponding R-side call:

```r
# Allocate output before calling .C
n <- as.integer(nrow(xdata))
result <- .C("pred_rpart_c",
             dimx    = as.integer(dimx),
             # ... other integer/double arguments ...
             where   = integer(n))$where   # pre-allocated integer vector of length n
```

- **Explanation:**
  - `allocVector(INTSXP, n)` is replaced by `integer(n)` on the R side.
  - `PROTECT` / `UNPROTECT` are removed entirely; R's garbage collector protects
    the vector for the duration of the `.C` call automatically.
  - `INTEGER(where)` (which unwraps `SEXP -> int *`) is removed because `where`
    is already an `int *` arriving directly as a function argument.
  - `asInteger(dimx)` is replaced by `dimx[0]` (scalar integer scalars arrive as
    single-element `int *` arrays under `.C`).
  - The R-side `$where` extract recovers the filled integer vector after the call.

---

### Pattern: 2-D Integer Matrix Allocation (Fixed Column Count)

- **Locations:** `rpart.c` line 278 (`nodecount x 6`); `rpart.c` line 285
  (`splitcount x 3`)

- **Original Context (.Call):**

```c
/* rpart.c:278-290 – two consecutive matrix allocations */
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
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Both matrices are passed as pre-allocated flat int * arrays.
 * R stores matrices column-major, so element [row r, col c] of an
 * (nrow x ncol) matrix is at index c*nrow + r.
 */
void rpart_c(/* ... other args ... */,
             int *inode,       /* pre-allocated: integer(nodecount * 6)  */
             int *isplit,      /* pre-allocated: integer(splitcount * 3) */
             /* ... */)
{
    int *iptr;
    int *iinode[6], *iisplit[3];

    /* Rebuild the ragged-array index into the flat buffer */
    iptr = inode;                    /* was: INTEGER(inode3) */
    for (int i = 0; i < 6; i++) {
        iinode[i] = iptr;
        iptr += nodecount;
    }

    iptr = isplit;                   /* was: INTEGER(isplit3) */
    for (int i = 0; i < 3; i++) {
        iisplit[i] = iptr;
        iptr += splitcount;
    }

    /* downstream code using iinode[i][j] and iisplit[i][j] is unchanged */
}
```

Corresponding R-side call:

```r
result <- .C("rpart_c",
             # ... other args ...
             inode  = integer(nodecount * 6L),
             isplit = integer(splitcount * 3L),
             # ...)

# Recover as proper R matrices
inode_mat  <- matrix(result$inode,  nrow = nodecount,  ncol = 6L)
isplit_mat <- matrix(result$isplit, nrow = splitcount, ncol = 3L)
```

- **Explanation:**
  - `allocMatrix(INTSXP, nrow, ncol)` is replaced by `integer(nrow * ncol)` on
    the R side. R's `matrix()` storage order (column-major) matches C's loop
    structure (`iptr += nrow` steps through one column), so no index arithmetic
    changes are required in the ragged-array setup loops.
  - `PROTECT` / `UNPROTECT` are removed.
  - `INTEGER(inode3)` becomes simply `inode` (the raw pointer argument).
  - After the `.C` call, `matrix(result$inode, nrow = nodecount, ncol = 6)` on
    the R side restores the 2-D matrix structure that was previously encoded in
    the `SEXP`'s `dim` attribute.

---

### Pattern: Conditionally Allocated 2-D Integer Matrix (Variable Dimensions)

- **Locations:** `rpart.c` line 293 (`catcount x maxcat`, conditional on
  `catcount > 0`)

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
            ccsplit[i][j] = 0;       /* explicit zero initialisation */
    }
} else
    ccsplit = NULL;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The conditional nature is handled on the R side: pass a zero-length
 * integer(0) when catcount == 0, or integer(catcount * maxcat) when > 0.
 * The C function receives the flat buffer regardless and uses the
 * accompanying catcount argument to decide whether to populate it.
 */
void rpart_c(/* ... */,
             int *catcount_arg,  /* scalar */
             int *maxcat_arg,    /* scalar */
             int *csplit,        /* pre-allocated: integer(catcount * maxcat)
                                    or integer(0) when catcount == 0        */
             /* ... */)
{
    int catcount = *catcount_arg;
    int maxcat   = *maxcat_arg;
    int **ccsplit = NULL;
    int *iptr;

    if (catcount > 0) {
        ccsplit = (int **) R_alloc(maxcat, sizeof(int *));
        iptr = csplit;               /* was: INTEGER(csplit3) */
        for (int i = 0; i < maxcat; i++) {
            ccsplit[i] = iptr;
            iptr += catcount;
            for (int j = 0; j < catcount; j++)
                ccsplit[i][j] = 0;
        }
    }
    /* downstream code using ccsplit is unchanged */
}
```

Corresponding R-side call:

```r
csplit_len <- if (catcount > 0L) catcount * maxcat else 0L

result <- .C("rpart_c",
             # ...
             catcount_arg = as.integer(catcount),
             maxcat_arg   = as.integer(maxcat),
             csplit       = integer(csplit_len),
             # ...)

if (catcount > 0L)
    csplit_mat <- matrix(result$csplit, nrow = catcount, ncol = maxcat)
```

- **Explanation:**
  - The conditional allocation `if (catcount > 0) allocMatrix(…)` maps to a
    conditional `integer(…)` allocation in R before the `.C` call. Passing
    `integer(0)` when `catcount == 0` is safe because the C code guards all
    access on `if (catcount > 0)`.
  - The explicit zero-initialisation loop (`ccsplit[i][j] = 0`) is preserved
    unchanged; R's `integer(n)` initialises to zero, but since the zero-fill
    loop is already present in C it is harmless to keep it.
  - `PROTECT` / `UNPROTECT` and `INTEGER(csplit3)` are removed by the same
    mechanism as the fixed-dimension patterns above.
  - `R_alloc` is used for the ragged-array index (`ccsplit`) instead of R's
    `ALLOC` macro, which is the correct scratch-allocation primitive for `.C`
    functions (its memory is automatically freed when the `.C` call returns).
