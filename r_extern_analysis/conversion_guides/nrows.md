# Conversion Guide: `nrows`

## 1. Overview of `nrows` in R API

`nrows` is a C API function declared in `Rinternals.h` as `int Rf_nrows(SEXP)` and
exposed via the macro `#define nrows Rf_nrows`. It accepts any R matrix, array, or
plain vector `SEXP` and returns an `int` equal to the number of rows — specifically,
the value of the first element of the object's `dim` attribute when one exists, or
the total length of the object when no `dim` attribute is present (i.e., a plain
vector is treated as a single-column matrix whose row count equals its length).
Under the `.Call/.External` API, `nrows` is the canonical way to extract the row
count from a caller-supplied matrix `SEXP` without manually reading the `dim`
attribute. Under the `.C/.Fortran` API there are no `SEXP` objects at all, so
`nrows` cannot be called; the row count must be communicated to the C function as
an explicit `int *` scalar argument supplied by the R caller.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 108 | `rp.n = nrows(xmat2);` |
| `xpred.c` | 106 | `rp.n = nrows(xmat2);` |

### Data types involved

In both occurrences `nrows` is applied to `xmat2`, a `SEXP` of type `REALSXP`
that wraps the predictor matrix passed by the R caller. `xmat2` is declared as a
formal `SEXP` parameter in the `.Call`-dispatched entry-point functions `rpart`
(`rpart.c` line 43) and `xpred` (`xpred.c` line 34). The result of `nrows(xmat2)`
is assigned directly to `rp.n`, an `int` field of the global `rp` struct declared
in `rpart.h` line 58 as `int n; /* total number of subjects */`. The local alias
`n = rp.n` is then set immediately afterward (both files) to save repetitive
field-access typing throughout the function body.

`nrows` always appears immediately before its column-dimension counterpart:

```c
rp.n    = nrows(xmat2);   /* row count — number of observations */
n = rp.n;
rp.nvar = ncols(xmat2);   /* column count — number of predictors */
```

`rp.n` (and its alias `n`) is subsequently used as:
- the loop bound and column stride when building the ragged-array pointer `rp.xdata`
  from the flat column-major buffer returned by `REAL(xmat2)`:

```c
dptr = REAL(xmat2);
rp.xdata = (double **) ALLOC(rp.nvar, sizeof(double *));
for (i = 0; i < rp.nvar; i++) {
    rp.xdata[i] = dptr;
    dptr += n;          /* advance by rp.n rows per column */
}
```

- the size argument in subsequent `allocVector` calls for output objects (e.g.,
  `PROTECT(allocVector(INTSXP, n))` in `rpart.c` line ~194).

### Memory management macros used alongside `nrows`

`nrows` is a pure query function — it performs no allocation and requires no
`PROTECT`/`UNPROTECT` pairing. In both files it is called in the parameter setup
block before any output `SEXP` objects are allocated.

### Distinct implementation patterns

There is exactly one usage pattern across both files:

**Row-count extraction from a matrix argument** — `nrows(xmat2)` is called once
per function entry to derive `rp.n`, which then drives loop bounds, column strides
in pointer arithmetic, and allocation sizes throughout the function. The companion
call `ncols(xmat2)` extracts the column count into `rp.nvar` on the line
immediately after the local alias assignment. Both dimensions together fully
describe the flat, column-major `double *` buffer that backs the matrix.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under the `.Call` API the row count of a matrix `SEXP` can be queried anywhere
inside the C function with `nrows(x)` because the `SEXP` carries its `dim`
attribute at all times. Under the `.C` API there are no `SEXP` objects: the matrix
is passed as a flat `double *` (or `int *`) buffer, and the buffer pointer carries
no shape metadata. The row count must therefore be **passed explicitly as an
additional `int *` scalar argument** alongside the data pointer.

The same requirement applies to the companion `ncols` call (see `ncols.md`); both
dimensions are needed simultaneously to interpret the column-major layout. In
practice, the two calls:

```c
rp.n    = nrows(xmat2);
rp.nvar = ncols(xmat2);
```

become two `int *` parameters — `n_obs` and `n_var` — added to the `.C` function
signature. On the R side they are supplied as `as.integer(nrow(xmat))` and
`as.integer(ncol(xmat))`.

### Type mapping

| `.Call` expression | `.C` equivalent |
|--------------------|-----------------|
| `nrows(xmat2)` | `*n_obs` (received as `const int *n_obs`) |
| `ncols(xmat2)` | `*n_var` (received as `const int *n_var`) |
| `REAL(xmat2)` | `xmat` (received as `const double *xmat`) |

The flat column-major layout of `xmat` is identical in both APIs; only the
mechanism for discovering its row count changes.

### Why this ensures `.C` compatibility

The `.C` API exclusively communicates through basic C pointer types (`int *`,
`double *`, etc.). No `SEXP` introspection functions (`nrows`, `ncols`, `REAL`,
`INTEGER`, `LENGTH`, …) are callable inside a function dispatched via `.C` because
those functions depend on the R internal type system. Passing dimensions as
dedicated scalar `int *` arguments is the only portable, standard-compliant way to
convey matrix shape across the `.C` boundary.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Row-Count Extraction from a Matrix Argument

- **Locations:** `rpart.c` line 108; `xpred.c` line 106

- **Original Context (.Call):**

```c
/* rpart.c / xpred.c — function entry-point boilerplate (condensed) */

/* .Call entry-point signature — xmat2 is a SEXP wrapping the predictor matrix */
SEXP rpart(SEXP ncat2, SEXP method2, SEXP opt2,
           SEXP parms2, SEXP xvals2, SEXP xgrp2,
           SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2)
{
    int i, n;
    double *dptr;

    /* ... option unpacking omitted ... */

    /* Extract matrix dimensions directly from SEXP metadata */
    rp.n    = nrows(xmat2);          /* row count — number of observations */
    n = rp.n;
    rp.nvar = ncols(xmat2);          /* column count — number of predictors */

    /* Use n as the per-column stride to build column-pointer array */
    dptr = REAL(xmat2);
    rp.xdata = (double **) ALLOC(rp.nvar, sizeof(double *));
    for (i = 0; i < rp.nvar; i++) {
        rp.xdata[i] = dptr;
        dptr += n;                   /* advance n rows per column */
    }
    /* ... rest of function ... */
}
```

R-side caller passes only the matrix object:

```r
.Call("rpart", ncat, method, opt, parms, xvals, xgrp, ymat, xmat, wt, ny, cost)
# R automatically wraps xmat as a SEXP; nrows()/ncols() recover shape inside C.
```

- **C/C++ Equivalent (.C):**

```c
/*
 * .C entry-point: xmat2 becomes a flat double * buffer; its dimensions
 * are passed as explicit int * scalars n_obs (rows) and n_var (columns).
 * nrows() and ncols() are completely removed.
 */
void rpart_c(const int    *ncat,
             const int    *method,
             const double *opt,
             const double *parms,
             const int    *xvals,
             const int    *xgrp,
             const double *ymat,
             const double *xmat,    /* flat column-major matrix */
             const int    *n_obs,   /* was: nrows(xmat2) — number of rows */
             const int    *n_var,   /* was: ncols(xmat2) — number of columns */
             const double *wt,
             const int    *ny,
             const double *cost
             /* ... output pointer arguments ... */)
{
    int n    = *n_obs;   /* replaces: rp.n    = nrows(xmat2); n = rp.n; */
    int nvar = *n_var;   /* replaces: rp.nvar = ncols(xmat2) */

    /* Reconstruct column pointers over the flat column-major buffer.
     * The per-column stride is n (number of rows), identical to the
     * original dptr += n loop. Memory is pre-allocated on the R side. */
    double **xdata = (double **) R_alloc(nvar, sizeof(double *));
    const double *dptr = xmat;
    for (int i = 0; i < nvar; i++) {
        xdata[i] = (double *) dptr;   /* cast away const for internal use */
        dptr += n;                    /* same stride logic as original */
    }
    /* ... rest of function uses n and nvar in place of rp.n and rp.nvar ... */
}
```

Corresponding R-side call:

```r
n_obs <- nrow(xmat)          # replaces nrows() inside C
n_var <- ncol(xmat)          # replaces ncols() inside C

result <- .C("rpart_c",
             ncat   = as.integer(ncat),
             method = as.integer(method),
             opt    = as.double(opt),
             parms  = as.double(parms),
             xvals  = as.integer(xvals),
             xgrp   = as.integer(xgrp),
             ymat   = as.double(ymat),
             xmat   = as.double(xmat),    # matrix coerced to flat double vector (column-major)
             n_obs  = as.integer(n_obs),  # explicit row count
             n_var  = as.integer(n_var),  # explicit column count
             wt     = as.double(wt),
             ny     = as.integer(ny),
             cost   = as.double(cost)
             # ... output arguments pre-allocated here ...
             )
```

- **Explanation:**
  - `nrows(xmat2)` is replaced by `*n_obs`, a single-element `int *` array (the
    `.C` convention for scalar integers). It is immediately dereferenced into the
    local variable `n` to preserve the original coding style (`n = rp.n` alias).
  - On the R side, `nrow(xmat)` is called before the `.C` dispatch and passed as
    `as.integer(n_obs)`. When `xmat` is passed as `as.double(xmat)`, R flattens
    the matrix to a column-major `double` vector, preserving the same memory layout
    that `REAL(xmat2)` exposes under `.Call`.
  - The ragged-array setup loop (`xdata[i] = dptr; dptr += n`) is structurally
    unchanged; only the source of `n` changes from an `nrows` introspection call to
    a dereferenced `int *` parameter.
  - `nrows` and `ncols` must be converted together, because both dimensions are
    required simultaneously to interpret the flat column-major buffer correctly.
    The two new parameters (`n_obs` and `n_var`) should be placed adjacent to the
    `xmat` argument in the function signature to keep the data-and-dimensions
    pairing visually clear.
  - No `PROTECT`/`UNPROTECT` or `REAL()`/`INTEGER()` unwrapping is needed inside
    the `.C` function because all data arrives as plain C pointers.
  - Any downstream code that uses `n` as an allocation size (e.g., for output
    vectors) must pre-allocate those buffers on the R side and pass them as
    additional `int *` or `double *` output arguments, since `allocVector` is also
    unavailable under the `.C` API (see `allocVector.md`).
