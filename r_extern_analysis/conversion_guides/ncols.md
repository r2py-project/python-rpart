# Conversion Guide: `ncols`

## 1. Overview of `ncols` in R API

`ncols` is a C API function declared in `Rinternals.h` as `int Rf_ncols(SEXP)` and
exposed via the macro `#define ncols Rf_ncols`. It accepts any R matrix or
array `SEXP` and returns an `int` equal to the number of columns — specifically,
the value of the second element of the object's `dim` attribute (i.e.,
`REAL/INTEGER(getAttrib(x, R_DimSymbol))[1]`). For a plain vector with no `dim`
attribute it returns 1. Under the `.Call/.External` API, `ncols` is the
canonical way to extract the column count from a caller-supplied matrix `SEXP`
without manually reading the `dim` attribute. Under the `.C/.Fortran` API there
are no `SEXP` objects at all, so `ncols` cannot be called; the column count must
be communicated to the C function as an explicit `int *` scalar argument supplied
by the R caller.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 111 | `rp.nvar = ncols(xmat2);` |
| `xpred.c` | 109 | `rp.nvar = ncols(xmat2);` |

### Data types involved

In both occurrences `ncols` is applied to `xmat2`, a `SEXP` of type `REALSXP`
that wraps the predictor matrix passed by the R caller. `xmat2` is declared as a
formal `SEXP` parameter in the `.Call`-dispatched entry-point functions `rpart`
(rpart.c line 43) and `xpred` (xpred.c line 34). The result of `ncols(xmat2)` is
assigned directly to `rp.nvar`, an `int` field of the global `rp` struct
(declared in `rpart.h` line 60 as `int nvar; /* number of predictors */`).

`ncols` always appears alongside its row-dimension counterpart on the immediately
preceding line:

```c
rp.n    = nrows(xmat2);   /* total observations — row count */
rp.nvar = ncols(xmat2);   /* number of predictor variables — column count */
```

`rp.nvar` is then used as the loop bound and allocation count when building the
ragged-array pointer `rp.xdata`:

```c
dptr = REAL(xmat2);
rp.xdata = (double **) ALLOC(rp.nvar, sizeof(double *));
for (i = 0; i < rp.nvar; i++) {
    rp.xdata[i] = dptr;
    dptr += n;          /* advance by rp.n per column (column-major) */
}
```

### Memory management macros used alongside `ncols`

`ncols` is a pure query function — it performs no allocation and requires no
`PROTECT`/`UNPROTECT` pairing. In both files it is called in the parameter
setup block before any output `SEXP` objects are allocated.

### Distinct implementation patterns

There is exactly one usage pattern across both files:

**Column-count extraction from a matrix argument** — `ncols(xmat2)` is called
once per function entry to derive `rp.nvar`, which then drives loop bounds and
pointer-arithmetic steps throughout the function. The companion call
`nrows(xmat2)` extracts the row count into `rp.n` on the line immediately above.
Both dimensions together fully describe the flat, column-major `double *` buffer
that backs the matrix.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under the `.Call` API the column count of a matrix `SEXP` can be queried
anywhere inside the C function with `ncols(x)` because the `SEXP` carries its
`dim` attribute at all times. Under the `.C` API there are no `SEXP` objects: the
matrix is passed as a flat `double *` (or `int *`) buffer, and the buffer
pointer carries no shape metadata. The column count must therefore be **passed
explicitly as an additional `int *` scalar argument** alongside the data pointer.

The same requirement applies to the companion `nrows` call; both dimensions are
needed simultaneously to interpret the column-major layout. In practice this
means the two calls:

```c
rp.n    = nrows(xmat2);
rp.nvar = ncols(xmat2);
```

become two `int *` parameters — `n` and `nvar` — added to the `.C` function
signature. On the R side they are supplied as `as.integer(nrow(xmat))` and
`as.integer(ncol(xmat))`.

### Type mapping

| `.Call` expression | `.C` equivalent |
|--------------------|-----------------|
| `ncols(xmat2)` | `*nvar` (received as `const int *nvar`) |
| `nrows(xmat2)` | `*n` (received as `const int *n`) |
| `REAL(xmat2)` | `xmat` (received as `const double *xmat`) |

The flat column-major layout of `xmat` is identical in both APIs; only the
mechanism for discovering its shape changes.

### Why this ensures `.C` compatibility

The `.C` API exclusively communicates through basic C pointer types (`int *`,
`double *`, etc.). No `SEXP` introspection functions (`ncols`, `nrows`, `REAL`,
`INTEGER`, `LENGTH`, …) are callable inside a function dispatched via `.C`
because those functions depend on the R internal type system. Passing dimensions
as dedicated scalar `int *` arguments is the only portable, standard-compliant
way to convey matrix shape across the `.C` boundary.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Column-Count Extraction from a Matrix Argument

- **Locations:** `rpart.c` line 111; `xpred.c` line 109

- **Original Context (.Call):**

```c
/* rpart.c / xpred.c — function entry-point boilerplate (condensed) */

/* .Call entry-point signature — xmat2 is a SEXP wrapping the predictor matrix */
SEXP rpart(SEXP ncat2, SEXP method2, SEXP opt2,
           SEXP parms2, SEXP xvals2, SEXP xgrp2,
           SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2)
{
    int n;
    double *dptr;

    /* ... option unpacking omitted ... */

    /* Extract matrix dimensions directly from SEXP metadata */
    rp.n    = nrows(xmat2);          /* row count   — number of observations */
    rp.nvar = ncols(xmat2);          /* column count — number of predictors  */
    n = rp.n;

    /* Use rp.nvar to build column-pointer array over flat column-major buffer */
    dptr = REAL(xmat2);
    rp.xdata = (double **) ALLOC(rp.nvar, sizeof(double *));
    for (i = 0; i < rp.nvar; i++) {
        rp.xdata[i] = dptr;
        dptr += n;
    }
    /* ... rest of function ... */
}
```

R-side caller passes only the matrix object:

```r
.Call("rpart", ncat, method, opt, parms, xvals, xgrp, ymat, xmat, wt, ny, cost)
# R automatically wraps xmat as a SEXP; ncols()/nrows() recover shape inside C.
```

- **C/C++ Equivalent (.C):**

```c
/*
 * .C entry-point: xmat2 becomes a flat double * buffer; its dimensions
 * are passed as explicit int * scalars n_obs (rows) and n_var (columns).
 * ncols() and nrows() are completely removed.
 */
void rpart_c(const int    *ncat,
             const int    *method,
             const double *opt,
             const double *parms,
             const int    *xvals,
             const int    *xgrp,
             const double *ymat,
             const double *xmat,    /* flat column-major matrix, nrow=*n_obs, ncol=*n_var */
             const int    *n_obs,   /* was: nrows(xmat2) */
             const int    *n_var,   /* was: ncols(xmat2) */
             const double *wt,
             const int    *ny,
             const double *cost
             /* ... output pointer arguments ... */)
{
    int n    = *n_obs;   /* replaces: rp.n    = nrows(xmat2) */
    int nvar = *n_var;   /* replaces: rp.nvar = ncols(xmat2) */

    /* Reconstruct column pointers over the flat column-major buffer.
     * Memory is managed by R (pre-allocated before .C call); no ALLOC needed
     * for the input matrix itself.  ALLOC / R_alloc is still valid for
     * internal scratch space not returned to R. */
    double **xdata = (double **) R_alloc(nvar, sizeof(double *));
    const double *dptr = xmat;
    for (int i = 0; i < nvar; i++) {
        xdata[i] = (double *) dptr;   /* cast away const for internal use */
        dptr += n;
    }
    /* ... rest of function uses n and nvar instead of rp.n and rp.nvar ... */
}
```

Corresponding R-side call:

```r
n_obs <- nrow(xmat)          # replaces ncols() / nrows() inside C
n_var <- ncol(xmat)

result <- .C("rpart_c",
             ncat   = as.integer(ncat),
             method = as.integer(method),
             opt    = as.double(opt),
             parms  = as.double(parms),
             xvals  = as.integer(xvals),
             xgrp   = as.integer(xgrp),
             ymat   = as.double(ymat),
             xmat   = as.double(xmat),   # matrix coerced to flat double vector
             n_obs  = as.integer(n_obs), # explicit row count
             n_var  = as.integer(n_var), # explicit column count
             wt     = as.double(wt),
             ny     = as.integer(ny),
             cost   = as.double(cost)
             # ... output arguments pre-allocated here ...
             )
```

- **Explanation:**
  - `ncols(xmat2)` and `nrows(xmat2)` are replaced by `*n_var` and `*n_obs`
    respectively. Both arrive as single-element `int *` arrays (the `.C`
    convention for scalar integers) and are immediately dereferenced into local
    `int` variables for readability.
  - On the R side, `ncol(xmat)` and `nrow(xmat)` are called before the `.C`
    dispatch and passed as `as.integer(...)` arguments. When `xmat` is passed as
    `as.double(xmat)`, R flattens the matrix to a column-major `double` vector,
    preserving the same memory layout that `REAL(xmat2)` exposes under `.Call`.
  - The ragged-array setup loop (`rp.xdata[i] = dptr; dptr += n`) is structurally
    unchanged; only the source of `n` and `nvar` changes from `SEXP`-introspection
    calls to dereferenced `int *` parameters.
  - No `PROTECT`/`UNPROTECT` or `REAL()`/`INTEGER()` unwrapping is needed inside
    the `.C` function because all data arrives as plain C pointers.
  - The companion `nrows` call must be converted at the same time, since both
    dimensions are required to interpret the flat column-major buffer correctly.
    The two new parameters (`n_obs` and `n_var`) should be added adjacent to the
    `xmat` argument in the signature to keep the pairing visually clear.
