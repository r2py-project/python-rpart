# Conversion Guide: `LENGTH`

## 1. Overview of `LENGTH` in R API

`LENGTH` is a C API function declared in `Rinternals.h` as `int (LENGTH)(SEXP x)`.
It is a thin wrapper around `Rf_length(SEXP)` (which returns `R_len_t`, a
`typedef` for `int`) and returns the number of elements in any R vector,
matrix, or list object regardless of its `SEXPTYPE`. It accepts a single
argument — any `SEXP` — and returns an `int` representing the element count;
for matrices this is the total element count (`nrow * ncol`), not a per-axis
dimension. In the `.Call/.External` API, `LENGTH` is the canonical way to
discover how many elements a caller-supplied or freshly allocated `SEXP` holds;
under the `.C` API the size information must be communicated through a dedicated
scalar `int *` argument because no `SEXP` objects exist.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart_callback.c` | 115 | `if (LENGTH(value) != (1 + rsave))` |
| `rpart_callback.c` | 149 | `j = LENGTH(goodness);` |
| `rpartexp2.c` | 46 | `int n = LENGTH(dtimes);` |
| `xpred.c` | 74 | `ncp = LENGTH(cp2);` |

### Data types involved

In all four occurrences `LENGTH` is applied to a `SEXP` that wraps a numeric
(`REALSXP`) or integer (`INTSXP`) R vector arriving from an R caller via the
`.Call` dispatch mechanism:

- `value` (`rpart_callback.c:115`) — a `SEXP` returned by `eval(expr2, rho)`,
  expected to be a real vector of length `1 + rsave`.
- `goodness` (`rpart_callback.c:149`) — a `SEXP` returned by `eval(expr1, rho)`,
  expected to be a real vector of length `2*(n-1)` or a related categorical
  length.
- `dtimes` (`rpartexp2.c:46`) — a `SEXP` argument of type `REALSXP` containing
  sorted death times; `LENGTH(dtimes)` gives the number of observations `n`.
- `cp2` (`xpred.c:74`) — a `SEXP` argument containing the complexity-parameter
  vector; `LENGTH(cp2)` gives `ncp`, the number of cp cut-points.

### Memory management macros used alongside `LENGTH`

`LENGTH` itself does not allocate memory and requires no `PROTECT`/`UNPROTECT`
pairing. In all observed cases `LENGTH` is called purely to read the size of an
already-existing `SEXP` before the result is used in arithmetic, loop bounds, or
validation checks.

### Distinct implementation patterns

1. **Validation guard** — `LENGTH` result compared against an expected value;
   an error is raised on mismatch (`rpart_callback.c:115`).
2. **Loop-bound extraction from a callback result** — `LENGTH` result assigned
   to an `int` variable that then drives a copy loop (`rpart_callback.c:149`).
3. **Size extraction from a function argument** — `LENGTH` result used to
   derive `n` (observation count) for the enclosing function's logic and
   downstream allocation (`rpartexp2.c:46`).
4. **Size extraction for a scalar count variable** — `LENGTH` result stored in
   a dedicated integer (`ncp`) used throughout the rest of the function
   (`xpred.c:74`).

Patterns 3 and 4 are structurally identical (assign the count once, use it
throughout); they are presented together. Pattern 1 is a specialisation of
pattern 3 where the count is only used for a single comparison.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under the `.Call` API, the size of every `SEXP` object can be queried at any
point inside the C function with `LENGTH(x)`. Under the `.C` API there are no
`SEXP` objects: every argument is a raw C pointer to a pre-allocated buffer, and
the pointer itself carries no length metadata. The size must therefore be
**passed explicitly as an additional `int *` scalar argument** alongside the
data pointer.

The required transformation for `LENGTH` is:

1. **Replace `LENGTH(sexp_arg)` with `*n_arg`**, where `n_arg` is a new `int *`
   parameter added to the C function signature.
2. **Add a matching `as.integer(length(x))` argument** on the R side before the
   `.C(…)` call so that the value is passed in.
3. **For validation patterns** (`rpart_callback.c:115`): the `eval()` result is
   an intermediate `SEXP` produced inside the `.Call` wrapper, not a direct
   `.C` argument. The validation logic itself lives in the `.Call` wrapper and
   does not migrate to the `.C` inner function; only the scalar that was derived
   from `LENGTH` (e.g., the loop bound `j`) is forwarded through the `.C`
   boundary as an `int *` argument.
4. **Do not use `XLENGTH`** as a substitute. `XLENGTH` returns `R_xlen_t`
   (a `ptrdiff_t` / `long` on 64-bit platforms), which is not a valid `.C`
   argument type. All sizes must be `int`.

This approach is fully `.C` compatible because `.C` exclusively communicates
through basic C pointer types; no `SEXP` introspection functions are callable
inside a function reached via `.C`.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Size Extraction from a Function Argument

- **Locations:** `rpartexp2.c` line 46; `xpred.c` line 74

- **Original Context (.Call):**

```c
/* rpartexp2.c:43-51 */
SEXP rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);                      /* derive size from SEXP */
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);
    return keep;
}

/* xpred.c:73-76 */
SEXP xpred(SEXP ncat2, SEXP method2, SEXP opt2,
           SEXP parms2, SEXP xvals2, SEXP xgrp2,
           SEXP ymat2, SEXP xmat2, SEXP wt2,
           SEXP ny2, SEXP cost2, SEXP all2, SEXP cp2, SEXP toprisk2, SEXP nresp2)
{
    int ncp;
    double *cp;
    /* ... */
    ncp = LENGTH(cp2);                           /* derive size from SEXP */
    cp  = REAL(cp2);
    /* ... ncp used throughout the rest of the function ... */
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * rpartexp2: dtimes length is now passed as a separate int * argument.
 * The inner worker Rpartexp2 is unchanged.
 */
void rpartexp2_c(const double *dtimes,
                 const int    *n,        /* was: int n = LENGTH(dtimes) */
                 const double *eps,
                 int          *keep)     /* pre-allocated: integer(*n) on R side */
{
    Rpartexp2(*n, dtimes, *eps, keep);
    /* No PROTECT/UNPROTECT, no LENGTH call needed */
}

/*
 * xpred: cp vector length is now passed as a separate int * argument.
 */
void xpred_c(const int    *ncat,
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
             const int    *all,
             const double *cp,
             const int    *ncp,          /* was: ncp = LENGTH(cp2) */
             const double *toprisk,
             const int    *nresp,
             /* ... output args ... */)
{
    /* ncp is now *ncp — use it directly without LENGTH */
    for (int i = 0; i < *ncp; i++) {
        /* use cp[i] and *ncp in downstream logic */
    }
}
```

Corresponding R-side calls:

```r
# rpartexp2
n      <- length(dtimes)
result <- .C("rpartexp2_c",
             dtimes = as.double(dtimes),
             n      = as.integer(n),         # explicit length argument
             eps    = as.double(eps),
             keep   = integer(n))$keep        # pre-allocated output

# xpred
result <- .C("xpred_c",
             ncat     = as.integer(ncat),
             method   = as.integer(method),
             # ... other arguments ...
             cp       = as.double(cp),
             ncp      = as.integer(length(cp)),  # explicit length argument
             toprisk  = as.double(toprisk),
             nresp    = as.integer(nresp),
             # ... output args ... )
```

- **Explanation:**
  - `LENGTH(dtimes)` and `LENGTH(cp2)` are replaced by `*n` and `*ncp`
    respectively, which arrive as `int *` scalar arguments (single-element
    arrays) under the `.C` convention.
  - On the R side, `as.integer(length(x))` is passed immediately before or
    after the corresponding data vector argument to keep the pairing visually
    clear.
  - No `PROTECT`/`UNPROTECT` or `REAL()`/`INTEGER()` unwrapping is needed
    inside the `.C` function because all data arrives as plain C pointers.
  - Scalar `int *` arguments under `.C` are dereferenced with `*n` in
    arithmetic contexts (e.g., loop bounds) and passed on to inner helpers
    by value with `*n`.

---

### Pattern: Validation Guard

- **Locations:** `rpart_callback.c` line 115

- **Original Context (.Call):**

```c
/* rpart_callback.c:111-119 */
/* no need to protect as no memory allocation (or error) below */
value = eval(expr2, rho);
if (!isReal(value))
    error(_("return value not a vector"));
if (LENGTH(value) != (1 + rsave))            /* guard: check returned length */
    error(_("returned value is the wrong length"));
dptr = REAL(value);
for (i = 0; i <= rsave; i++)
    z[i] = dptr[i];
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The eval()/SEXP validation block cannot migrate into a .C function.
 * It belongs in the .Call wrapper that calls the R expression and then
 * passes the validated result to an inner .C helper.
 *
 * .Call wrapper (keeps SEXP logic + validation):
 */
SEXP rpart_eval_wrapper(SEXP expr2, SEXP rho, SEXP rsave2)
{
    int rsave = asInteger(rsave2);
    SEXP value = eval(expr2, rho);

    if (!isReal(value))
        error(_("return value not a vector"));
    if (LENGTH(value) != (1 + rsave))
        error(_("returned value is the wrong length"));

    /* Pass validated data to .C inner function via a direct C call,
     * or return value to R for a subsequent .C dispatch */
    return value;   /* caller extracts REAL(value) and passes as double * */
}

/*
 * .C inner function: receives the pre-validated, pre-extracted array.
 * LENGTH is no longer needed here — the size is passed as *n_z.
 */
void rpart_callback1_c(const double *z_in,
                        const int    *n_z,    /* == 1 + rsave, already validated */
                        double       *z_out)
{
    for (int i = 0; i < *n_z; i++)
        z_out[i] = z_in[i];
}
```

Corresponding R-side wrappers:

```r
# Step 1: evaluate and validate in .Call (SEXP-aware)
value <- .Call("rpart_eval_wrapper", expr2, rho, rsave)

# Step 2: pass plain numeric data to .C inner function
n_z    <- 1L + rsave
result <- .C("rpart_callback1_c",
             z_in  = as.double(value),
             n_z   = n_z,
             z_out = double(n_z))$z_out
```

- **Explanation:**
  - The `eval()` call and `LENGTH`-based guard cannot be expressed inside a
    `.C` function because they operate on `SEXP` objects. The pattern splits
    cleanly into a thin `.Call` wrapper that owns all `SEXP`-level logic
    (including the `LENGTH` check) and a `.C` inner function that receives only
    plain C pointers to already-validated data.
  - The validated length (`1 + rsave`) is passed as an explicit `int *` scalar
    to the inner `.C` function, replacing any need to re-call `LENGTH` there.
  - This two-layer approach is the standard idiom for migrating `.Call` routines
    that mix `SEXP` introspection (type checks, `LENGTH`, `eval`) with
    numerical computation: keep the introspection in `.Call`, delegate the
    computation to `.C`.

---

### Pattern: Loop-Bound Extraction from a Callback Result

- **Locations:** `rpart_callback.c` line 149

- **Original Context (.Call):**

```c
/* rpart_callback.c:145-162 */
/* no need to protect as no memory allocation (or error) below */
goodness = eval(expr1, rho);
if (!isReal(goodness))
    error(_("the expression expr1 did not return a vector!"));
j = LENGTH(goodness);               /* extract length as loop bound */
dptr = REAL(goodness);

if (ncat == 0) {
    if (j != 2 * (n - 1))
        error("the expression expr1 returned a list of %d elements, %d required",
              j, 2 * (n - 1));
    for (i = 0; i < j; i++)
        good[i] = dptr[i];
} else {
    /* categorical branch uses j differently */
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * As with the validation-guard pattern, the eval()/SEXP block stays in a
 * .Call wrapper.  The inner .C function receives the extracted double *
 * array and its length.
 */

/* .Call wrapper */
SEXP rpart_split_wrapper(SEXP expr1, SEXP rho, SEXP n2, SEXP ncat2)
{
    int n    = asInteger(n2);
    int ncat = asInteger(ncat2);

    SEXP goodness = eval(expr1, rho);
    if (!isReal(goodness))
        error(_("the expression expr1 did not return a vector!"));

    int j    = LENGTH(goodness);     /* LENGTH still used in .Call wrapper */
    double *dptr = REAL(goodness);

    if (ncat == 0 && j != 2 * (n - 1))
        error("the expression expr1 returned a list of %d elements, %d required",
              j, 2 * (n - 1));

    /* Pack j and data into an R list or pass directly to inner .C */
    SEXP result = PROTECT(allocVector(REALSXP, j));
    memcpy(REAL(result), dptr, j * sizeof(double));
    UNPROTECT(1);
    return result;
}

/* .C inner function: loop bound j arrives as an int * scalar */
void rpart_callback2_c(const double *good_in,
                        const int    *j,         /* was: j = LENGTH(goodness) */
                        const int    *ncat,
                        double       *good_out)
{
    for (int i = 0; i < *j; i++)
        good_out[i] = good_in[i];
    /* categorical branch logic follows, guarded by *ncat */
}
```

Corresponding R-side call:

```r
# Step 1: evaluate, validate, and extract in .Call
good_vec <- .Call("rpart_split_wrapper", expr1, rho, n, ncat)

# Step 2: dispatch inner computation via .C
j      <- length(good_vec)
result <- .C("rpart_callback2_c",
             good_in  = as.double(good_vec),
             j        = as.integer(j),       # was LENGTH(goodness)
             ncat     = as.integer(ncat),
             good_out = double(j))$good_out
```

- **Explanation:**
  - `j = LENGTH(goodness)` is computed in the `.Call` wrapper immediately after
    `eval()` returns the `SEXP`. The validated integer `j` is then communicated
    to the `.C` inner function as an explicit `int *` scalar parameter.
  - Inside the `.C` function, `*j` directly replaces every former occurrence of
    the `LENGTH`-derived variable `j`; no other arithmetic changes are needed.
  - The second validation (`j != 2*(n-1)`) is also kept in the `.Call` wrapper
    because it compares against `SEXP`-derived metadata; the `.C` function
    assumes the data has already been validated by the time it is called.
