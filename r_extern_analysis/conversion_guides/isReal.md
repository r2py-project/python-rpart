# Conversion Guide: `isReal`

## 1. Overview of `isReal` in R API

`isReal` is a C API function declared in `Rinternals.h` as `Rboolean (Rf_isReal)(SEXP s)`, exposed as the macro `#define isReal Rf_isReal`. It takes a single `SEXP` argument and returns an `Rboolean` (`TRUE` or `FALSE`) indicating whether that object's internal type code is `REALSXP` (14), i.e., whether the object is an R double-precision numeric vector or matrix. In the `.Call/.External` API, `isReal` is used as a runtime type-guard: it is called immediately after receiving a `SEXP` from an untrusted source (typically a user-supplied R callback expression evaluated via `eval()`) and before unwrapping the object with `REAL()`, allowing the C code to emit a meaningful error instead of crashing on a type mismatch. Under the `.C/.Fortran` API, `isReal` is entirely absent: no `SEXP` objects exist, and type safety is enforced at the R level by the `.C` dispatcher before the C function is ever entered.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart_callback.c` | 113 | `if (!isReal(value))` |
| `rpart_callback.c` | 147 | `if (!isReal(goodness))` |

Both occurrences are in `rpart_callback.c`, the dedicated module that implements user-supplied split-function callbacks via R's `eval()` mechanism. No other source file in the rpart package uses `isReal`.

### Data types involved

**Occurrence 1 — line 113, function `rpart_callback1`:**

- Enclosing function signature: `void rpart_callback1(int n, double *y[], double *wt, double *z)` — a `.C`-registered void callback.
- The `SEXP value` local variable (declared at line 92) receives the result of `eval(expr2, rho)` at line 112. `expr2` is a module-level `static SEXP` storing an unevaluated R language object (the "node value / deviance" expression). `rho` is a `static SEXP` R environment holding the shared data channel between C and the user's R expression.
- `isReal(value)` at line 113 checks that the result is a double-precision vector before the `REAL(value)` call at line 117 extracts the `double *` data pointer.
- The surrounding validation block (lines 113–116) also calls `LENGTH(value)` to confirm that the vector has exactly `1 + rsave` elements. The actual data copy into the output buffer `z[]` follows at lines 118–119.
- The source comment at line 111 notes: "no need to protect as no memory allocation (or error) below", confirming that `value` is not `PROTECT`ed because no GC-triggering allocation occurs between the `eval` call and the end of the function.

**Occurrence 2 — line 147, function `rpart_callback2`:**

- Enclosing function signature: `void rpart_callback2(int n, int ncat, double *y[], double *wt, double *x, double *good)` — also `.C`-registered.
- The `SEXP goodness` local variable (declared at line 131) receives the result of `eval(expr1, rho)` at line 146. `expr1` stores the "goodness of split" expression.
- `isReal(goodness)` at line 147 checks the type before `REAL(goodness)` at line 150 extracts the data pointer.
- `LENGTH(goodness)` at line 149 stores the element count in `j`, which is then validated against `2*(n-1)` (continuous splits) or the categorical length formula before being copied into `good[]`.

### Memory management context

Neither `value` nor `goodness` is `PROTECT`ed. Both are the direct return values of `eval()`, and the source explicitly documents that protection is unnecessary because no GC-triggering allocation follows. `isReal` itself allocates nothing and triggers no GC activity.

### Distinct usage patterns

There is exactly one functional pattern across both occurrences: **runtime type validation of a `SEXP` returned by `eval()` before extracting its `double *` data via `REAL()`**. The full pattern in both locations is:

```
SEXP result = eval(expr, rho);
if (!isReal(result)) error(…);
/* optional: if (LENGTH(result) != expected) error(…); */
double *dptr = REAL(result);
/* use dptr */
```

The two occurrences differ only in the expression evaluated (`expr1` vs. `expr2`), the error message string, the expected length, and the output buffer (`good[]` vs. `z[]`).

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under `.Call`, `isReal(sexp)` is a runtime introspection call: it queries the internal type tag of a live R heap object to confirm it is `REALSXP` before the data pointer is extracted. This guard is necessary because the `SEXP` was produced by `eval()` and its type is unknown at compile time.

Under `.C`, this entire construct — `eval()`, `isReal()`, `REAL()`, and the `SEXP` variables themselves — becomes inapplicable for two independent reasons:

1. **`eval()` is unavailable under `.C`.** The `.C` API provides no access to R's evaluator, R environment handles, or unevaluated R language objects. The `SEXP result = eval(expr, rho)` step that produces the object to be inspected by `isReal` cannot exist in a `.C` function. Since there is no `SEXP` to test, `isReal` has nothing to operate on.

2. **Type safety is enforced by the `.C` dispatcher, not by C code.** When a `.C`-registered function is called from R, the `.C` dispatcher coerces each argument to the declared `R_NativePrimitiveArgType` before the C function receives it. An argument declared as `REALSXP` will always arrive as a `double *`; no runtime type check is needed or possible inside C.

The conversion strategy is therefore not a mechanical translation of `isReal` to a C equivalent. Instead, `isReal` — together with `eval()`, `LENGTH()`, and `REAL()` — must be removed from C entirely, and the validation responsibility must be relocated:

- **If the callback subsystem remains under `.Call`:** The `rpart_callback1` and `rpart_callback2` functions already have `.C`-style signatures (they return `void` and accept raw C pointer arguments). They are registered as `.C` entry points, but they call `eval()` internally via the module-level `static SEXP` state set up by `init_rpcallback` (a `.Call` function). This hybrid pattern — a `.C`-registered function that internally uses `.Call`-only mechanisms — is allowed by R only because the `static SEXP` globals are initialised by a prior `.Call` call before any `.C` callback fires. In this scenario, `isReal` remains in C unchanged and no conversion is required.

- **If the callback subsystem is migrated to pure `.C`:** `eval()` must be moved to R. The R wrapper that invokes the user's expression must validate the result type in R (e.g., `if (!is.double(result)) stop(…)`) before passing it down to C as a pre-filled `double *` argument. The `isReal` call in C is removed entirely; the argument arrives typed by construction.

### Type mapping

| `.Call` construct | `.C` equivalent |
|---|---|
| `SEXP value = eval(expr2, rho)` | result computed in R; passed as `const double *value_out` argument |
| `if (!isReal(value)) error(…)` | `if (!is.double(result)) stop(…)` in R before the `.C` call |
| `if (LENGTH(value) != expected) error(…)` | `if (length(result) != expected) stop(…)` in R |
| `double *dptr = REAL(value)` | `value_out` is already `double *`; no unwrap needed |

---

## 4. Step-by-Step Conversion Examples

### Pattern: Runtime Type Guard on an `eval()` Result Before `REAL()` Extraction

- **Locations:** `rpart_callback.c` lines 113 and 147

- **Original Context (.Call):**

```c
/* rpart_callback.c:88-119 — rpart_callback1, checking "value" */
void
rpart_callback1(int n, double *y[], double *wt, double *z)
{
    int i, j, k;
    SEXP value;
    double *dptr;

    /* fill shared data buffers in rho (ydata, wdata, ndata) */
    for (i = 0, k = 0; i < ysave; i++)
        for (j = 0; j < n; j++)
            ydata[k++] = y[j][i];
    for (i = 0; i < n; i++)
        wdata[i] = wt[i];
    ndata[0] = n;

    /* evaluate the user-supplied R expression inside rho */
    value = eval(expr2, rho);           /* line 112 */
    if (!isReal(value))                 /* line 113: type guard */
        error(_("return value not a vector"));
    if (LENGTH(value) != (1 + rsave))  /* line 115: length guard */
        error(_("returned value is the wrong length"));
    dptr = REAL(value);                 /* line 117: extract pointer */
    for (i = 0; i <= rsave; i++)
        z[i] = dptr[i];                /* line 118-119: copy to output */
}

/* rpart_callback.c:126-162 — rpart_callback2, checking "goodness" */
void
rpart_callback2(int n, int ncat, double *y[], double *wt,
                double *x, double *good)
{
    int i, j, k;
    SEXP goodness;
    double *dptr;

    /* fill shared data buffers in rho */
    for (i = 0, k = 0; i < ysave; i++)
        for (j = 0; j < n; j++)
            ydata[k++] = y[j][i];
    for (i = 0; i < n; i++) {
        wdata[i] = wt[i];
        xdata[i] = x[i];
    }
    ndata[0] = (ncat > 0) ? -n : n;

    goodness = eval(expr1, rho);        /* line 146 */
    if (!isReal(goodness))              /* line 147: type guard */
        error(_("the expression expr1 did not return a vector!"));
    j = LENGTH(goodness);               /* line 149 */
    dptr = REAL(goodness);              /* line 150: extract pointer */
    /* ... copy dptr into good[] ... */
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Direct .C conversion of isReal is NOT possible in this context.
 *
 * Both occurrences of isReal guard a SEXP produced by eval(expr, rho).
 * The .C API provides no access to:
 *   - R's evaluator (eval)
 *   - R environment handles (SEXP rho)
 *   - SEXP type introspection (isReal, TYPEOF, LENGTH)
 *   - Raw-pointer extraction from SEXPs (REAL)
 *
 * Recommended migration: Option A — Keep hybrid .C/.Call structure (no change needed)
 *
 * rpart_callback1 and rpart_callback2 are already registered as .C entry
 * points (their signatures are void-returning with raw C pointer arguments).
 * The static SEXP state (expr1, expr2, rho) is initialised by
 * init_rpcallback, which is a .Call function. As long as init_rpcallback
 * has been called before any callback fires, the eval() + isReal() + REAL()
 * sequence inside the .C callbacks is safe. No conversion of isReal is
 * required under this option; the two callbacks remain exactly as written.
 *
 * Recommended migration: Option B — Move eval() and isReal() to R wrapper
 *
 * If the callback subsystem must be fully decoupled from SEXP, restructure
 * as follows. The isReal check becomes an R-level is.double() guard.
 */

/*
 * Option B — rpart_callback1 converted to pure .C:
 * The R wrapper evaluates expr2 in rho, checks its type and length,
 * then passes the result as a pre-filled double * argument.
 */
void rpart_callback1_c(int    *n_arg,       /* scalar: current node size          */
                        double *ydata_arg,   /* shared data buffer (ysave * n max) */
                        double *wdata_arg,   /* shared weight buffer               */
                        int    *ndata_arg,   /* shared count buffer                */
                        int    *rsave_arg,   /* scalar: length of per-node mean    */
                        double *value_out,   /* pre-filled by R: eval(expr2, rho)  */
                        double *z)           /* output: deviance + rsave means     */
{
    int n    = *n_arg;
    int rsave = *rsave_arg;

    /*
     * ydata_arg, wdata_arg, ndata_arg are already filled by the R wrapper
     * (or by a prior C step writing into shared buffers).
     *
     * value_out already holds the result of eval(expr2, rho), validated
     * in R via:
     *   if (!is.double(result)) stop("return value not a vector")
     *   if (length(result) != 1L + rsave) stop("returned value is the wrong length")
     *
     * No isReal() call needed: value_out is double * by construction.
     */
    for (int i = 0; i <= rsave; i++)
        z[i] = value_out[i];
}

/*
 * Option B — rpart_callback2 converted to pure .C:
 */
void rpart_callback2_c(int    *n_arg,
                        int    *ncat_arg,
                        double *ydata_arg,
                        double *wdata_arg,
                        double *xdata_arg,
                        int    *ndata_arg,
                        double *goodness_out, /* pre-filled by R: eval(expr1, rho) */
                        int    *goodness_len, /* scalar: length(goodness_out)      */
                        double *good)         /* output buffer                     */
{
    int n    = *n_arg;
    int ncat = *ncat_arg;
    int j    = *goodness_len;

    /*
     * goodness_out already holds the validated real vector from R:
     *   result <- eval(expr1, rho)
     *   if (!is.double(result)) stop("the expression expr1 did not return a vector!")
     *   expected <- if (ncat == 0L) 2L * (n - 1L) else ...
     *   if (length(result) != expected) stop("wrong length")
     *
     * No isReal() call needed.
     */
    if (ncat == 0) {
        for (int i = 0; i < j; i++)
            good[i] = goodness_out[i];
    } else {
        good[0] = (double)((j + 1) / 2);
        for (int i = 0; i < j; i++)
            good[i + 1] = goodness_out[i];
    }
}
```

Corresponding R-side wrapper (Option B):

```r
# R wrapper replacing rpart_callback1 invocation (Option B)
.rpart_callback1_r <- function(n, expr2, rho, rsave, z_len) {
    # Evaluate the user expression in rho (replaces eval(expr2, rho) in C)
    result <- eval(expr2, envir = rho)

    # Type and length checks that replaced isReal() and LENGTH() in C
    if (!is.double(result))
        stop("return value not a vector")
    if (length(result) != 1L + rsave)
        stop("returned value is the wrong length")

    # Pass the validated result to the pure .C function
    out <- .C("rpart_callback1_c",
              n_arg        = as.integer(n),
              ydata_arg    = get("yback", envir = rho),
              wdata_arg    = get("wback", envir = rho),
              ndata_arg    = as.integer(n),
              rsave_arg    = as.integer(rsave),
              value_out    = as.double(result),   # formerly REAL(value)
              z            = double(z_len))
    out$z
}

# R wrapper replacing rpart_callback2 invocation (Option B)
.rpart_callback2_r <- function(n, ncat, expr1, rho, good_len) {
    result <- eval(expr1, envir = rho)

    if (!is.double(result))
        stop("the expression expr1 did not return a vector!")
    expected <- if (ncat == 0L) 2L * (n - 1L) else length(result)  # flexible
    if (length(result) != expected)
        stop(sprintf("expr1 returned %d elements, %d required",
                     length(result), expected))

    out <- .C("rpart_callback2_c",
              n_arg         = as.integer(n),
              ncat_arg      = as.integer(ncat),
              ydata_arg     = get("yback", envir = rho),
              wdata_arg     = get("wback", envir = rho),
              xdata_arg     = get("xback", envir = rho),
              ndata_arg     = as.integer(if (ncat > 0L) -n else n),
              goodness_out  = as.double(result),  # formerly REAL(goodness)
              goodness_len  = as.integer(length(result)),
              good          = double(good_len))
    out$good
}
```

- **Explanation:**
  - `isReal(value)` and `isReal(goodness)` perform `TYPEOF(sexp) == REALSXP` checks on objects returned by `eval()`. Because `eval()` cannot exist in `.C`, the `SEXP` it would return also cannot exist, and therefore `isReal` has no operand to test.
  - Under Option A (hybrid `.C/.Call`), the existing C code requires no change: the functions are already registered as `.C` entry points but internally call `.Call`-only APIs via the `static SEXP` globals set up by the `.Call` function `init_rpcallback`. This is the lowest-risk migration path for the callback subsystem.
  - Under Option B (fully decoupled `.C`), the `eval()` call moves to an R wrapper function. R's `is.double()` replaces `isReal()`, `length()` replaces `LENGTH()`, and `as.double()` replaces `REAL()`. The C function receives a pre-validated, pre-filled `double *` argument and performs no type checking.
  - `PROTECT` and `UNPROTECT` are absent from both callback functions even in the original code (as documented by the source comment at line 111); they require no removal.
  - `LENGTH(value)` and `LENGTH(goodness)` — the size checks immediately following `isReal` in the original code — must also migrate to R under Option B. The converted `.C` function receives the length as an explicit `int *goodness_len` argument.
  - No `R_NativePrimitiveArgType[]` entry for `isReal` itself is needed: `isReal` disappears entirely and does not correspond to a `.C` argument type.
