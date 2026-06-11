# Conversion Guide: `REALSXP`

## 1. Overview of `REALSXP` in R API

`REALSXP` is the integer constant `14` of type `SEXPTYPE`, defined in
`Rinternals.h`. It is the type tag that identifies an R numeric (double-precision
floating-point) vector (`typeof(x) == "double"`) inside R's internal `SEXPREC`
representation. It is passed as the first argument to `allocVector(REALSXP, n)`
or `allocMatrix(REALSXP, nrow, ncol)` to request a freshly heap-allocated,
GC-managed block of `double` values of length `n` (or `nrow * ncol`); the
returned `SEXP` is then unwrapped to a raw `double *` via `REAL(sexp)`. Under
the `.C` API, `REALSXP` appears in `R_NativePrimitiveArgType[]` arrays to
declare that a given `.C` argument carries a `double *` pointer.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 241 | `cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));` |
| `rpart.c` | 261 | `dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));` |
| `rpart.c` | 269 | `dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));` |
| `xpred.c` | 209 | `predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));` |

### Data types and memory management

- In every case `REALSXP` is the type selector passed to `allocVector` or
  `allocMatrix`; it is never used in isolation.
- `PROTECT` / `UNPROTECT` wrap every allocation to pin the resulting `SEXP`
  against the garbage collector for the lifetime of the enclosing `.Call`
  function.
- `REAL(sexp)` immediately follows each allocation to obtain the underlying
  `double *` that is then used for all subsequent read/write access. In
  `rpart.c` the local variable `dptr` (of type `double *`) is assigned from
  `REAL(sexp)` and then incremented to set up ragged-array column pointers
  (`ddnode[]`, `ddsplit[]`). In `xpred.c` the variable `predict` is assigned
  directly and used as a flat 3-D array indexed by `j * ncp * nresp`.

### Distinct implementation patterns

1. **Conditionally-sized 2-D real matrix** (`allocMatrix(REALSXP, expr ? r1 : r2, ncols)`) —
   `rpart.c` line 241: the row count is `xvals > 1 ? 5 : 3` and the column
   count is `rp.num_unique_cp`. Immediately after, `REAL(cptable3)` is assigned
   to `dptr` and the table is filled in a loop that increments `dptr` by
   individual element (`dptr[i++]`), walking the flat column-major buffer.

2. **Variable-column 2-D real matrix** (`allocMatrix(REALSXP, nrow, expr)`) —
   `rpart.c` line 261: dimensions are `nodecount` rows and `(3 + rp.num_resp)`
   columns, where `rp.num_resp` is known only at runtime. After allocation,
   `REAL(dnode3)` is used to build a ragged-array index `ddnode[]` of
   `double *` column pointers.

3. **Fixed-column 2-D real matrix** (`allocMatrix(REALSXP, nrow, 3)`) —
   `rpart.c` line 269: dimensions are `splitcount` rows and a fixed 3 columns.
   After allocation, `REAL(dsplit3)` is used to build `ddsplit[]` column
   pointers, and each column is explicitly zero-initialised.

4. **1-D real vector from a product of dimensions** (`allocVector(REALSXP, n * ncp * nresp)`) —
   `xpred.c` line 209: a flat buffer of `double` whose length is the product of
   three runtime scalars. After allocation, `predict = REAL(predict2)` is used as
   a flat 3-D array indexed as `predict + j * ncp * nresp` per observation.

### Role of the `REAL()` accessor

After allocation, `REAL(sexp)` returns the `double *` base pointer of the
underlying data array. All C-level arithmetic operates on that pointer, not on
the `SEXP` wrapper. The `.Call`-to-`.C` migration therefore consists primarily
of removing the allocation and `PROTECT` machinery and replacing the `SEXP`
variable with a pre-allocated `double *` argument supplied by the R caller.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under `.Call`, the C function allocates its output `double` storage internally
via `allocVector`/`allocMatrix`, protects it from the GC with `PROTECT`, and
returns it (or places it into a named list) as a `SEXP`. The `.C` API forbids
`SEXP` arguments and return values entirely: the C function must be
`void`-returning and must accept only basic C pointer types (`double *`,
`int *`, etc.).

The required transformation is:

1. **Remove `allocVector(REALSXP, …)` and `allocMatrix(REALSXP, …, …)`.**
   Every such allocation becomes a pre-allocated `double *` argument supplied
   by the R caller with `numeric(n)` before the `.C(…)` call. The length `n`
   equals `nrow * ncol` for matrices (stored column-major in R).
2. **Remove `PROTECT(…)` / `UNPROTECT(n)`.** R's garbage collector protects
   the caller-allocated `numeric()` vector for the duration of the `.C` call
   automatically — no explicit protection is needed in C.
3. **Remove `REAL(sexp)` unwrapping calls.** The `double *` pointer arrives
   directly as a function argument; there is no `SEXP` wrapper to strip.
4. **Declare the argument type** as `REALSXP` in the corresponding
   `R_NativePrimitiveArgType[]` array so that R's `.C` dispatcher performs
   type coercion automatically.
5. **R-side allocation.** The calling R code creates the output buffer with
   `numeric(n)` (for a vector or a flattened matrix). After the `.C` call, the
   R code can apply `dim()` or `matrix()` to recover the 2-D structure.
6. **Dimension scalars.** Any dimension expression that was computed inside C
   (e.g. `xvals > 1 ? 5 : 3`, `3 + rp.num_resp`) must be pre-computed in R
   and passed as an `integer *` argument (or inferred from other arguments
   already present), so the C function can verify or use them without
   re-evaluating the expression.

This approach is fully `.C` compatible because `.C` communicates exclusively
through raw C pointers; `REALSXP` in C source is only needed as a type tag in
the `R_NativePrimitiveArgType` registration array.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Conditionally-Sized 2-D Real Matrix

- **Locations:** `rpart.c` line 241

- **Original Context (.Call):**

```c
/* rpart.c:239-252 */
scale = 1 / tree->risk;
i = 0;
cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3,
                               rp.num_unique_cp));
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
 * cptable_out: pre-allocated flat double buffer of length nrow_cp * num_unique_cp,
 *              where nrow_cp = (xvals > 1 ? 5 : 3), passed from R as numeric().
 * nrow_cp and num_unique_cp are passed as scalar int * arguments.
 */
void rpart_c(/* ... other args ... */,
             const int    *xvals_arg,        /* scalar: number of cross-validations */
             const int    *nrow_cp_arg,      /* scalar: 5 if xvals>1, else 3        */
             const int    *num_unique_cp_arg,/* scalar: rp.num_unique_cp            */
             double       *cptable_out,      /* pre-allocated: numeric(nrow_cp * num_unique_cp) */
             /* ... */)
{
    int xvals       = *xvals_arg;
    int nrow_cp     = *nrow_cp_arg;       /* caller ensures: xvals > 1 ? 5 : 3  */
    double scale    = 1.0 / tree->risk;
    int i = 0;
    double *dptr = cptable_out;           /* was: REAL(cptable3) after allocMatrix */

    for (CpTable cp = cptable; cp; cp = cp->forward) {
        dptr[i++] = cp->cp    * scale;
        dptr[i++] = cp->nsplit;
        dptr[i++] = cp->risk  * scale;
        if (xvals > 1) {
            dptr[i++] = cp->xrisk * scale;
            dptr[i++] = cp->xstd  * scale;
        }
    }
    /* No UNPROTECT needed */
}
```

Corresponding R-side call:

```r
nrow_cp     <- if (xvals > 1L) 5L else 3L
num_ucp     <- rp_num_unique_cp          # integer scalar known from R

result <- .C("rpart_c",
             # ... other args ...
             xvals_arg        = as.integer(xvals),
             nrow_cp_arg      = nrow_cp,
             num_unique_cp_arg = num_ucp,
             cptable_out      = numeric(nrow_cp * num_ucp),
             # ...)

# Recover as proper R matrix (column-major, same layout as allocMatrix)
cptable_mat <- matrix(result$cptable_out, nrow = nrow_cp, ncol = num_ucp)
```

- **Explanation:**
  - `allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp)` is replaced
    by `numeric(nrow_cp * num_ucp)` on the R side; the ternary expression is
    evaluated in R before the call.
  - `PROTECT` / `UNPROTECT` are removed; R's GC protects the `numeric()`
    vector automatically.
  - `REAL(cptable3)` becomes the function argument `cptable_out` directly —
    no unwrapping step is needed.
  - The fill loop and all index arithmetic are unchanged.
  - After the call, `matrix(result$cptable_out, nrow = nrow_cp, ncol = num_ucp)`
    restores the 2-D structure that was previously encoded in the `SEXP`'s
    `dim` attribute.

---

### Pattern: Variable-Column 2-D Real Matrix with Ragged-Array Index

- **Locations:** `rpart.c` line 261

- **Original Context (.Call):**

```c
/* rpart.c:261-267 */
dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));
ddnode = (double **) ALLOC(3 + rp.num_resp, sizeof(double *));
dptr = REAL(dnode3);
for (i = 0; i < 3 + rp.num_resp; i++) {
    ddnode[i] = dptr;
    dptr += nodecount;
}
/* later: rpmatrix(tree, …, ddnode, …) writes into the columns via ddnode[i][j] */
```

- **C/C++ Equivalent (.C):**

```c
/*
 * dnode_out: pre-allocated flat double buffer of length nodecount * ncols_dnode,
 *            where ncols_dnode = 3 + rp.num_resp.
 * nodecount and ncols_dnode are passed as scalar int * arguments.
 */
void rpart_c(/* ... other args ... */,
             const int *nodecount_arg,   /* scalar                              */
             const int *ncols_dnode_arg, /* scalar: 3 + rp.num_resp             */
             double    *dnode_out,       /* pre-allocated: numeric(nodecount * ncols_dnode) */
             /* ... */)
{
    int nodecount   = *nodecount_arg;
    int ncols_dnode = *ncols_dnode_arg;

    double **ddnode = (double **) R_alloc(ncols_dnode, sizeof(double *));
    double  *dptr   = dnode_out;          /* was: REAL(dnode3) after allocMatrix */

    for (int i = 0; i < ncols_dnode; i++) {
        ddnode[i] = dptr;
        dptr += nodecount;
    }

    /* downstream: rpmatrix(…, ddnode, …) is unchanged */
}
```

Corresponding R-side call:

```r
ncols_dnode <- 3L + rp_num_resp          # integer scalar known from R

result <- .C("rpart_c",
             # ... other args ...
             nodecount_arg   = as.integer(nodecount),
             ncols_dnode_arg = ncols_dnode,
             dnode_out       = numeric(nodecount * ncols_dnode),
             # ...)

dnode_mat <- matrix(result$dnode_out, nrow = nodecount, ncol = ncols_dnode)
```

- **Explanation:**
  - `allocMatrix(REALSXP, nodecount, 3 + rp.num_resp)` is replaced by
    `numeric(nodecount * ncols_dnode)` on the R side; the column-count
    expression `3 + rp.num_resp` is pre-evaluated in R.
  - `PROTECT` / `UNPROTECT` are removed.
  - `REAL(dnode3)` becomes the function argument `dnode_out`.
  - The ragged-array setup loop (`ddnode[i] = dptr; dptr += nodecount`) is
    preserved unchanged; R's column-major storage ensures `dptr += nodecount`
    correctly steps to the next column.
  - `R_alloc` is used for the `ddnode` pointer array (scratch memory
    automatically freed when the `.C` call returns), replacing R's `ALLOC`
    macro which is only valid inside `.Call` functions.

---

### Pattern: Fixed-Column 2-D Real Matrix with Zero-Initialisation

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
/* later: rpmatrix(tree, …, ddsplit, …) fills the columns */
```

- **C/C++ Equivalent (.C):**

```c
/*
 * dsplit_out: pre-allocated flat double buffer of length splitcount * 3.
 * splitcount is passed as a scalar int * argument.
 * The fixed column count (3) is a compile-time constant.
 */
void rpart_c(/* ... other args ... */,
             const int *splitcount_arg,  /* scalar */
             double    *dsplit_out,      /* pre-allocated: numeric(splitcount * 3) */
             /* ... */)
{
    int     splitcount = *splitcount_arg;
    double *ddsplit[3];
    double *dptr = dsplit_out;            /* was: REAL(dsplit3) after allocMatrix */

    for (int i = 0; i < 3; i++) {
        ddsplit[i] = dptr;
        dptr += splitcount;
        for (int j = 0; j < splitcount; j++)
            ddsplit[i][j] = 0.0;          /* explicit zero-fill preserved */
    }

    /* downstream: rpmatrix(…, ddsplit, …) is unchanged */
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
  - `allocMatrix(REALSXP, splitcount, 3)` is replaced by
    `numeric(splitcount * 3L)` on the R side. R's `numeric(n)` initialises all
    elements to `0.0`, but the explicit C-level zero-fill loop is preserved for
    clarity and correctness.
  - `PROTECT` / `UNPROTECT` are removed.
  - `REAL(dsplit3)` becomes the function argument `dsplit_out`.
  - The ragged-array setup and fill logic are unchanged.
  - The fixed column count `3` remains a compile-time constant; no extra scalar
    argument is needed to convey it.

---

### Pattern: 1-D Real Vector from a Product of Dimensions

- **Locations:** `xpred.c` line 209

- **Original Context (.Call):**

```c
/* xpred.c:205-210 */
if (asInteger(all2) == 1)
    nresp = rp.num_resp;     /* number of response values returned */
else
    nresp = 1;
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);

/* later, per observation: */
rundown2(xtree, j, cp, (predict + j * ncp * nresp), nresp);

/* ... */
UNPROTECT(1);
return predict2;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * predict_out: pre-allocated flat double buffer of length n * ncp * nresp.
 * n, ncp, and nresp are passed as scalar int * arguments (nresp pre-computed
 * by the R caller based on the "all" flag).
 */
void xpred_c(/* ... other args ... */,
             const int *n_arg,     /* scalar: number of observations          */
             const int *ncp_arg,   /* scalar: number of cp cutpoints          */
             const int *nresp_arg, /* scalar: 1 or rp.num_resp (from R "all") */
             double    *predict_out /* pre-allocated: numeric(n * ncp * nresp) */
             /* ... */)
{
    int     n     = *n_arg;
    int     ncp   = *ncp_arg;
    int     nresp = *nresp_arg;
    double *predict = predict_out;    /* was: REAL(predict2) after allocVector  */

    /* ... cross-validation loop unchanged ... */
    for (int xgroup = 0; xgroup < xvals; xgroup++) {
        /* ... */
        for (int i = k; i < rp.n; i++) {
            int j = rp.sorts[0][i];
            rundown2(xtree, j, cp, (predict + j * ncp * nresp), nresp);
        }
        /* ... */
    }
    /* No UNPROTECT needed */
}
```

Corresponding R-side call:

```r
nresp <- if (all_flag == 1L) rp_num_resp else 1L

result <- .C("xpred_c",
             # ... other args ...
             n_arg        = as.integer(n),
             ncp_arg      = as.integer(ncp),
             nresp_arg    = nresp,
             predict_out  = numeric(n * ncp * nresp),
             # ...)

# The output is a flat vector; reshape as needed in R
predict_arr <- result$predict_out   # length n * ncp * nresp
```

- **Explanation:**
  - `allocVector(REALSXP, n * ncp * nresp)` is replaced by
    `numeric(n * ncp * nresp)` on the R side. The length expression is
    fully computable in R because `n`, `ncp`, and `nresp` are all known
    before the call.
  - The conditional `nresp = rp.num_resp` vs. `nresp = 1` is evaluated in R
    using the `all` flag and the known `rp.num_resp` value; the result is
    passed in as the scalar `nresp_arg`.
  - `PROTECT` / `UNPROTECT(1)` are removed.
  - `REAL(predict2)` is replaced by the direct pointer argument `predict_out`;
    the assignment `predict = predict_out` mirrors the original
    `predict = REAL(predict2)` but requires no SEXP unwrapping.
  - The 3-D indexing expression `predict + j * ncp * nresp` is unchanged
    because it operates purely on pointer arithmetic over the flat buffer.
  - The function changes its return type from `SEXP` to `void`; the filled
    `predict_out` array is returned to R through the `.C` list as
    `result$predict_out`.
