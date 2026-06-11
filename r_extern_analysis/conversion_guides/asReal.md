# Conversion Guide: `asReal`

## 1. Overview of `asReal` in R API

`asReal` is a macro defined in `Rinternals.h` as `#define asReal Rf_asReal`, where `Rf_asReal` has the C signature `double Rf_asReal(SEXP x)`. It accepts any scalar-compatible `SEXP` (most commonly a length-1 numeric or integer vector) and returns its value coerced to a plain C `double`, applying R's standard scalar coercion rules (integer-to-double promotion, `NA` propagation). Its sole purpose in `.Call/.External` code is to unpack a single-element R object passed as a `SEXP` argument into a bare C `double` for immediate use in arithmetic or as a function argument. Under the `.C/.Fortran` API, `asReal` is entirely absent: R's `.C` dispatcher passes each `numeric(1)` R value directly as a single-element `double *`, so the scalar is obtained by dereferencing the pointer (`arg[0]` or `*arg`) without any `SEXP` involvement.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpartexp2.c` | 48 | `Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));` |
| `xpred.c` | 76 | `toprisk = asReal(toprisk2);` |

### Data types involved

In both occurrences the `SEXP` argument is a length-1 numeric (double) scalar supplied by the R caller. The receiving C-side destinations are:

- **Inline as a function argument** (`rpartexp2.c:48`): `asReal(eps)` is passed directly to the internal worker `Rpartexp2` as its third argument, which is declared `double eps` in the static function signature at line 14. No intermediate C variable is introduced; the `double` value flows straight into the call.
- **Local `double` variable** (`xpred.c:76`): `toprisk = asReal(toprisk2)` stores the extracted scalar into the local variable `double toprisk` declared at line 48. This variable is used later in the cross-validation loop to represent the risk of the top node of the tree.

### Memory management context

`asReal` is not associated with any memory allocation or garbage-collector protection. It performs a pure extraction of a scalar double value from a `SEXP` and returns it by value. No `PROTECT`/`UNPROTECT` pairing is required. The function does not allocate any R-managed memory.

In `rpartexp2.c`, the call to `asReal(eps)` appears inside the `.Call`-registered wrapper `rpartexp2`, which also contains a `PROTECT(allocVector(INTSXP, n))` / `UNPROTECT(1)` pair for the integer output buffer `keep`. The `asReal` call itself is entirely independent of that protection: it does not allocate memory and does not require protection. See the `PROTECT`, `allocVector`, `INTSXP`, and `REAL` conversion guides for the handling of the surrounding buffer management.

### Distinct implementation patterns

1. **Inline scalar extraction as a function argument** — `asReal(eps)` appears directly inside a function call's argument list without an intermediate assignment (`rpartexp2.c:48`).
2. **Scalar extraction into a local `double` variable** — the result is assigned to a named `double` variable and used in subsequent logic (`xpred.c:76`).

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under `.Call`, `asReal(sexp)` is the standard gate for extracting a single C `double` from a `SEXP` argument. Under `.C`, this gate is unnecessary: R's `.C` dispatcher coerces each `numeric(1)` R argument to a single-element `double *` before entering C, so the scalar double value is retrieved by dereferencing the pointer — `arg[0]` or equivalently `*arg`.

The complete transformation is:

1. **Replace each `SEXP` scalar parameter with `const double *`.** An input argument that was received as `SEXP x` and then used only via `asReal(x)` becomes `const double *x` in the `.C` signature. The `const` qualifier reflects that the value is read-only input data.

2. **Replace every `asReal(sexp)` call with `sexp[0]` (or `*sexp`).** The dereference is the direct, zero-overhead equivalent. For example:
   - `toprisk = asReal(toprisk2)` becomes `toprisk = toprisk2[0]` (or simply `*toprisk2`).
   - `asReal(eps)` passed inline as a function argument becomes `eps[0]` (or `*eps`).

3. **No length information change is required.** Unlike `REAL(sexp)` applied to multi-element vectors, `asReal` is only ever called on length-1 objects. A single-element `double *` argument under `.C` is sufficient; no extra length parameter needs to be added.

4. **Remove `SEXP` from the function signature.** Each `SEXP` argument whose only use was `asReal(arg)` is replaced entirely by `const double *arg`.

5. **Register each scalar argument as `REALSXP` in `R_NativePrimitiveArgType[]`.** This allows R's `.C` dispatcher to coerce and type-check the argument automatically. The R caller passes the value as `as.double(scalar_value)` or `numeric(1L)`.

This approach is fully `.C`-compatible because after the transformation every scalar double argument is a plain `const double *` known at call time; no R object introspection or garbage-collector interaction is required inside C.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Inline Scalar Extraction as a Function Argument

- **Locations:** `rpartexp2.c` line 48

- **Original Context (.Call):**

```c
/* rpartexp2.c:13-51 — static worker and .Call wrapper */

/* Static inner function — already uses raw C types; unchanged by conversion */
static void
Rpartexp2(int n, double *y, double eps, int *keep)
{
    double delta;
    int i, j;
    double lasty;

    i = n / 4;
    j = (3 * n) / 4;
    delta = eps * (y[j] - y[i]);

    lasty = y[0];
    keep[0] = 1;
    for (i = 1; i < n; i++) {
        if ((y[i] - lasty) <= delta)
            keep[i] = 0;
        else {
            keep[i] = 1;
            lasty = y[i];
        }
    }
}

/* .Call wrapper — the target of conversion */
SEXP
rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    /*                         ^^^^^^^^^^^
     *  asReal(eps) extracts the scalar double from the length-1 SEXP eps
     *  and passes it directly to Rpartexp2 as the third argument (double eps).
     */
    UNPROTECT(1);
    return keep;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The .Call wrapper rpartexp2 is replaced by a void .C entry point.
 *
 * Changes:
 *   - SEXP dtimes  -> const double *dtimes  (pointer passed directly)
 *   - SEXP eps     -> const double *eps     (length-1; asReal(eps) -> eps[0] or *eps)
 *   - LENGTH(dtimes) cannot be derived in .C; becomes explicit const int *n_arg
 *   - SEXP keep = PROTECT(allocVector(INTSXP, n)) -> int *keep  (pre-allocated by R)
 *   - REAL(dtimes) -> dtimes  (pointer passed directly)
 *   - asReal(eps)  -> eps[0]  (or *eps)
 *   - INTEGER(keep) -> keep   (pointer passed directly)
 *   - PROTECT / UNPROTECT removed
 *   - Return type void; output recovered from .C result list in R
 *
 * The inner static function Rpartexp2 is unchanged.
 */
void rpartexp2_c(const double *dtimes,    /* was: SEXP dtimes -> REAL(dtimes)       */
                 const int    *n_arg,     /* was: LENGTH(dtimes); must be explicit   */
                 const double *eps,       /* was: SEXP eps     -> asReal(eps)        */
                 int          *keep)      /* was: SEXP keep = PROTECT(allocVector(INTSXP, n)) */
{
    Rpartexp2(*n_arg,           /* was: n = LENGTH(dtimes)      */
              (double *) dtimes, /* was: REAL(dtimes)             */
              eps[0],            /* was: asReal(eps)              */
              keep);             /* was: INTEGER(keep)            */
    /* No UNPROTECT; no return value */
}
```

- **R-side call:**

```r
n_val  <- as.integer(length(dtimes))
result <- .C("rpartexp2_c",
             dtimes = as.double(dtimes),    # was: SEXP dtimes
             n_arg  = n_val,                # was: LENGTH(dtimes) computed in C
             eps    = as.double(eps),       # was: SEXP eps; length-1 scalar
             keep   = integer(n_val))       # pre-allocated; was: PROTECT(allocVector(INTSXP, n))
keep_vec <- result$keep
```

- **Explanation:**
  - `asReal(eps)` in the inline argument list is replaced by `eps[0]` (equivalently `*eps`), passing the scalar `double` value to `Rpartexp2` exactly as before. The third parameter of `Rpartexp2` is `double eps` — a pass-by-value scalar — so `eps[0]` dereferences the single-element `double *` to produce that value.
  - `SEXP eps` in the outer wrapper collapses to `const double *eps` in the `.C` signature.
  - `LENGTH(dtimes)` is not available inside a `.C` function because there is no `SEXP` from which to read the length attribute; it must be passed as the explicit scalar `const int *n_arg` from R using `as.integer(length(dtimes))`.
  - `REAL(dtimes)` inline in the argument list becomes `dtimes` directly (a `const double *` already). A `(double *)` cast is applied when passing to `Rpartexp2` whose parameter is `double *y`, since `const` is not in its original signature (the static worker predates this conversion).
  - `PROTECT(allocVector(INTSXP, n))`, `UNPROTECT(1)`, and `return keep` are removed entirely; the R caller supplies `integer(n_val)` and retrieves `result$keep`.

---

### Pattern: Scalar Extraction into a Local `double` Variable

- **Locations:** `xpred.c` line 76

- **Original Context (.Call):**

```c
/* xpred.c:33-76 — function signature and scalar extraction */
SEXP
xpred(SEXP ncat2, SEXP method2, SEXP opt2,
      SEXP parms2, SEXP xvals2, SEXP xgrp2,
      SEXP ymat2, SEXP xmat2, SEXP wt2,
      SEXP ny2, SEXP cost2, SEXP all2, SEXP cp2, SEXP toprisk2, SEXP nresp2)
{
    /* ... */
    double toprisk;       /* local variable receiving the extracted scalar */
    /* ... */
    ncat     = INTEGER(ncat2);
    xgrp     = INTEGER(xgrp2);
    xvals    = asInteger(xvals2);
    wt       = REAL(wt2);
    parms    = REAL(parms2);
    ncp      = LENGTH(cp2);
    cp       = REAL(cp2);
    toprisk  = asReal(toprisk2);   /* line 76: SEXP scalar -> local double */
    /* ... toprisk is used later in the cross-validation loop ... */
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * SEXP toprisk2 becomes const double *toprisk_arg (length-1).
 * asReal(toprisk2) becomes toprisk_arg[0] (or *toprisk_arg).
 * The local variable toprisk receives the dereferenced value as before.
 */
void xpred_c(const int    *ncat,
             const int    *method,
             const double *opt,
             const double *parms,
             const int    *xvals_arg,
             const int    *xgrp,
             const double *ymat,
             const double *xmat,
             const double *wt,
             const int    *ny,
             const double *cost,
             const int    *all,
             const double *cp,
             const int    *ncp_arg,      /* was: LENGTH(cp2); must be explicit */
             const double *toprisk_arg,  /* was: SEXP toprisk2 -> asReal(toprisk2) */
             const int    *nresp,
             /* ... output args ... */)
{
    double toprisk = toprisk_arg[0];   /* was: toprisk = asReal(toprisk2) */

    /* All subsequent uses of toprisk are unchanged */
}
```

- **R-side call:**

```r
result <- .C("xpred_c",
             ncat        = as.integer(ncat_vec),
             method      = as.integer(method_val),
             opt         = as.double(opt_vec),
             parms       = as.double(parms_vec),
             xvals_arg   = as.integer(xvals_val),
             xgrp        = as.integer(xgrp_vec),
             ymat        = as.double(ymat_mat),
             xmat        = as.double(xmat_mat),
             wt          = as.double(wt_vec),
             ny          = as.integer(ny_val),
             cost        = as.double(cost_vec),
             all         = as.integer(all_flag),
             cp          = as.double(cp_vec),
             ncp_arg     = as.integer(length(cp_vec)),  # was: LENGTH(cp2) in C
             toprisk_arg = as.double(toprisk_val),      # was: SEXP toprisk2; length-1 scalar
             nresp       = as.integer(nresp_val),
             # ... output args ...
             )
```

- **Explanation:**
  - `SEXP toprisk2` is replaced by `const double *toprisk_arg`; `toprisk = asReal(toprisk2)` becomes `toprisk = toprisk_arg[0]`. The local `double toprisk` variable is retained because it is read multiple times later in the function body; caching it avoids repeated pointer dereferences and preserves the original code structure.
  - `LENGTH(cp2)` is not available in a `.C` function for the same reason as `LENGTH(dtimes)` above (no `SEXP` attribute access); it is passed as the explicit scalar `const int *ncp_arg`.
  - The remaining `SEXP` parameters (`ncat2`, `method2`, etc.) are converted to their corresponding pointer types following the `asInteger`, `INTEGER`, and `REAL` conversion guides.
  - The local variable assignment `double toprisk = toprisk_arg[0]` is semantically identical to the original `toprisk = asReal(toprisk2)`; no arithmetic or type coercion changes are needed beyond the dereference.
  - `as.double(toprisk_val)` on the R side ensures the dispatcher passes a properly typed `double *` even if the R object is stored as integer — mirroring the coercion that `asReal` previously applied inside C.
