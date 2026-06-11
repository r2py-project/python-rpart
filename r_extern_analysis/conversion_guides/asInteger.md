# Conversion Guide: `asInteger`

## 1. Overview of `asInteger` in R API

`asInteger` is a macro defined in `Rinternals.h` as `#define asInteger Rf_asInteger`, where `Rf_asInteger` has the C signature `int Rf_asInteger(SEXP x)`. It accepts any scalar-compatible `SEXP` (most commonly a length-1 integer or numeric vector) and returns its value coerced to a plain C `int`, applying R's standard scalar coercion rules (truncation for doubles, `NA` propagation). Its sole purpose in `.Call/.External` code is to unpack a single-element R object passed as a `SEXP` argument into a bare C integer for immediate use in arithmetic, comparisons, or struct-field assignments. Under the `.C/.Fortran` API, `asInteger` is entirely absent: R's `.C` dispatcher passes each `integer(1)` R value directly as a single-element `int *`, so the scalar is obtained by dereferencing the pointer (`arg[0]` or `*arg`) without any `SEXP` involvement.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `pred_rpart.c` | 138 | `int n = asInteger(dimx);` |
| `pred_rpart.c` | 140 | `pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit), …);` |
| `rpart.c` | 77 | `xvals = asInteger(xvals2);` |
| `rpart.c` | 83 | `if (asInteger(method2) <= NUM_METHODS) {` |
| `rpart.c` | 84 | `i = asInteger(method2) - 1;` |
| `rpart.c` | 89 | `rp.num_y = asInteger(ny2);` |
| `rpart_callback.c` | 54 | `ysave = asInteger(ny);` |
| `rpart_callback.c` | 55 | `rsave = asInteger(nr);` |
| `xpred.c` | 71 | `xvals = asInteger(xvals2);` |
| `xpred.c` | 81 | `if (asInteger(method2) <= NUM_METHODS) {` |
| `xpred.c` | 82 | `i = asInteger(method2) - 1;` |
| `xpred.c` | 87 | `rp.num_y = asInteger(ny2);` |
| `xpred.c` | 114 | `rp.num_resp = asInteger(nresp2);` |
| `xpred.c` | 205 | `if (asInteger(all2) == 1)` |

### Data types involved

In every occurrence, the `SEXP` argument is a length-1 integer or numeric scalar supplied by the R caller. The receiving C-side destinations are:

- **Local `int` variable:** `int n = asInteger(dimx)` (`pred_rpart.c:138`); `xvals = asInteger(xvals2)` where `xvals` is `int` (`rpart.c:77`, `xpred.c:71`); `i = asInteger(method2) - 1` where `i` is `int` (`rpart.c:84`, `xpred.c:82`).
- **Struct field `int`:** `rp.num_y = asInteger(ny2)` where `rp.num_y` is declared `int` in `rpart.h:59` (`rpart.c:89`, `xpred.c:87`); `rp.num_resp = asInteger(nresp2)` where `rp.num_resp` is `int` in `rpart.h:67` (`xpred.c:114`).
- **Static module-level `int`:** `ysave = asInteger(ny)` and `rsave = asInteger(nr)` where `ysave` and `rsave` are static module-level integers in `rpart_callback.c:54-55`.
- **Inline in conditional expression:** `if (asInteger(method2) <= NUM_METHODS)` (`rpart.c:83`, `xpred.c:81`) and `if (asInteger(all2) == 1)` (`xpred.c:205`).
- **Inline as function argument:** `asInteger(nnode)` and `asInteger(nsplit)` passed directly to `pred_rpart0()` (`pred_rpart.c:140`).

### Memory management context

`asInteger` is not associated with any memory allocation or garbage-collector protection. It performs a pure extraction of a scalar integer value from a `SEXP` and returns it by value. No `PROTECT`/`UNPROTECT` pairing is required. The function does not allocate any R-managed memory.

### Distinct implementation patterns

1. **Scalar extraction into a local `int` variable** — the result is assigned to a local `int` and used in subsequent logic (`pred_rpart.c:138`; `rpart.c:77,84`; `xpred.c:71,82`).
2. **Scalar extraction into a struct field** — the result is written directly into a member of the global `rp` struct (`rpart.c:89`; `xpred.c:87,114`).
3. **Inline scalar extraction in a conditional** — `asInteger(sexp)` used directly inside an `if` condition without an intermediate variable (`rpart.c:83`; `xpred.c:81,205`).
4. **Inline scalar extraction as a function argument** — `asInteger(sexp)` used directly in a function call's argument list (`pred_rpart.c:140`).
5. **Scalar extraction into a static module-level `int` (callback context)** — `asInteger` used inside a `.Call`-registered callback initialisation function that also stores R environments; this pattern depends on the `.Call` infrastructure (`rpart_callback.c:54-55`).

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under `.Call`, `asInteger(sexp)` is the standard gate for extracting a single C `int` from a `SEXP` argument. Under `.C`, this gate is unnecessary: R's `.C` dispatcher coerces each `integer(1)` R argument to a single-element `int *` before entering C, so the scalar integer value is retrieved by dereferencing the pointer — `arg[0]` or equivalently `*arg`.

The complete transformation is:

1. **Replace each `SEXP` scalar parameter with `const int *`.** An input argument that was received as `SEXP x` and then used only via `asInteger(x)` becomes `const int *x` in the `.C` signature. The `const` qualifier reflects that the value is read-only input data.

2. **Replace every `asInteger(sexp)` call with `sexp[0]` (or `*sexp`).** The dereference `sexp[0]` is the direct, zero-overhead equivalent. For example:
   - `int n = asInteger(dimx)` becomes `int n = dimx[0]` (or simply use `*dimx` everywhere `n` was used).
   - `rp.num_y = asInteger(ny2)` becomes `rp.num_y = ny2[0]`.
   - `if (asInteger(method2) <= NUM_METHODS)` becomes `if (method2[0] <= NUM_METHODS)`.
   - `asInteger(nnode)` passed inline as a function argument becomes `nnode[0]`.

3. **No length information change is required.** Unlike `INTEGER(sexp)` or `REAL(sexp)` applied to multi-element vectors, `asInteger` is only ever called on length-1 objects. A single-element `int *` argument under `.C` is sufficient; no extra length parameter needs to be added.

4. **Remove `SEXP` from the function signature.** Each `SEXP` argument whose only use was `asInteger(arg)` is replaced entirely by `const int *arg`.

5. **Register each scalar argument as `INTSXP` in `R_NativePrimitiveArgType[]`.** This allows R's `.C` dispatcher to coerce and type-check the argument automatically. The R caller passes the value as `as.integer(scalar_value)` or `integer(1L)`.

6. **The `rpart_callback.c` pattern is not directly portable.** `asInteger(ny)` and `asInteger(nr)` at lines 54–55 appear inside `init_rpcallback`, which also stores an R environment (`SEXP rho`) and two R expressions (`SEXP expr1`, `SEXP expr2`) in static module-level state for use by later callback invocations. This function is registered under `.Call` and depends on capabilities — environment handles, deferred expression evaluation — that have no `.C` equivalent. The `asInteger` calls themselves are mechanically convertible, but the surrounding function must remain under `.Call` or be restructured (see Pattern 5 below).

This approach is fully `.C`-compatible because after the transformation every scalar integer argument is a plain `const int *` known at call time; no R object introspection or garbage-collector interaction is required inside C.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Scalar Extraction into a Local `int` Variable

- **Locations:** `pred_rpart.c` line 138; `rpart.c` line 77, line 84; `xpred.c` line 71, line 82

- **Original Context (.Call):**

```c
/* pred_rpart.c:133-144 */
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc, ...)
{
    int n = asInteger(dimx);       /* scalar extraction into local int */
    SEXP where = PROTECT(allocVector(INTSXP, n));
    pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit), ...);
    UNPROTECT(1);
    return where;
}

/* rpart.c:41-91 */
SEXP rpart(SEXP ncat2, SEXP method2, SEXP opt2, ..., SEXP xvals2, ..., SEXP ny2, ...)
{
    int xvals;
    int i;
    xvals = asInteger(xvals2);          /* scalar into local int */
    if (asInteger(method2) <= NUM_METHODS) {
        i = asInteger(method2) - 1;     /* scalar into local int, with arithmetic */
        ...
        rp.num_y = asInteger(ny2);
    }
}
```

- **C/C++ Equivalent (.C):**

```c
/* Each SEXP scalar argument becomes const int *.
 * asInteger(arg) is replaced by arg[0]. */

void pred_rpart_c(const int    *n,          /* was: SEXP dimx, then asInteger(dimx) */
                  const int    *dimx,       /* was: INTEGER(dimx) contents          */
                  const int    *nnode,      /* was: asInteger(nnode) — scalar       */
                  const int    *nsplit,     /* was: asInteger(nsplit) — scalar      */
                  const int    *dimc,
                  ...
                  int          *where)      /* pre-allocated output: integer(n[0])  */
{
    /* n[0] replaces asInteger(dimx); no intermediate variable needed */
    pred_rpart0(dimx, nnode[0], nsplit[0], dimc, ..., where);
}

void rpart_c(const int *ncat, const int *method, ...,
             const int *xvals_arg, ..., const int *ny, ...)
{
    int xvals = xvals_arg[0];          /* was: xvals = asInteger(xvals2)     */
    int i;
    if (method[0] <= NUM_METHODS) {    /* was: asInteger(method2) <= ...     */
        i = method[0] - 1;             /* was: i = asInteger(method2) - 1    */
        ...
        rp.num_y = ny[0];              /* was: rp.num_y = asInteger(ny2)     */
    }
}
```

- **R-side call:**

```r
result <- .C("pred_rpart_c",
             n       = as.integer(dimx[1]),   # scalar: first element of dimx
             dimx    = as.integer(dimx),
             nnode   = as.integer(nnode),
             nsplit  = as.integer(nsplit),
             dimc    = as.integer(dimc),
             # ... other args ...
             where   = integer(dimx[1]))       # pre-allocated output
where_vec <- result$where

result <- .C("rpart_c",
             ncat    = as.integer(ncat_vec),
             method  = as.integer(method_val),  # length-1 integer
             xvals   = as.integer(xvals_val),   # length-1 integer
             ny      = as.integer(ny_val),       # length-1 integer
             # ... other args ...
             )
```

- **Explanation:**
  - `SEXP dimx` is split into two arguments: `const int *n` carrying the scalar (`asInteger(dimx)` became `n[0]`) and `const int *dimx` carrying the full integer array for the `INTEGER(dimx)` use inside `pred_rpart0`.
  - For arguments used exclusively via `asInteger` (e.g., `method2`, `xvals2`, `ny2`, `nsplit`, `nnode`), the `SEXP` collapses to a single `const int *` and every `asInteger(arg)` call becomes `arg[0]`.
  - No length parameter is needed because these are guaranteed length-1 scalars.
  - The arithmetic `asInteger(method2) - 1` becomes `method[0] - 1` with no further change.

---

### Pattern: Scalar Extraction into a Struct Field

- **Locations:** `rpart.c` line 89; `xpred.c` lines 87, 114

- **Original Context (.Call):**

```c
/* rpart.c:83-89 */
if (asInteger(method2) <= NUM_METHODS) {
    i = asInteger(method2) - 1;
    rp_init   = func_table[i].init_split;
    rp_choose = func_table[i].choose_split;
    rp_eval   = func_table[i].eval;
    rp_error  = func_table[i].error;
    rp.num_y  = asInteger(ny2);     /* SEXP scalar -> struct field */
}

/* xpred.c:81-114 */
if (asInteger(method2) <= NUM_METHODS) {
    ...
    rp.num_y   = asInteger(ny2);     /* struct field */
}
rp.num_resp = asInteger(nresp2);     /* struct field */
```

- **C/C++ Equivalent (.C):**

```c
/* rp.num_y and rp.num_resp are struct fields declared as int in rpart.h. */
void rpart_c(const int *method, const int *ny, ...)
{
    if (method[0] <= NUM_METHODS) {
        int i = method[0] - 1;
        rp_init   = func_table[i].init_split;
        ...
        rp.num_y  = ny[0];      /* was: rp.num_y = asInteger(ny2) */
    }
}

void xpred_c(const int *method, const int *ny, const int *nresp, ...)
{
    if (method[0] <= NUM_METHODS) {
        ...
        rp.num_y   = ny[0];       /* was: rp.num_y = asInteger(ny2)    */
    }
    rp.num_resp = nresp[0];       /* was: rp.num_resp = asInteger(nresp2) */
}
```

- **R-side call:**

```r
result <- .C("xpred_c",
             method = as.integer(method_val),
             ny     = as.integer(ny_val),
             nresp  = as.integer(nresp_val),
             # ... other args ...
             )
```

- **Explanation:**
  - `rp.num_y = asInteger(ny2)` becomes `rp.num_y = ny[0]`. The struct assignment itself is unchanged; only the right-hand side loses its `SEXP` wrapper.
  - `rp.num_resp = asInteger(nresp2)` becomes `rp.num_resp = nresp[0]`.
  - Both `rp.num_y` and `rp.num_resp` are declared `int` in `rpart.h` (lines 59 and 67), so no type conversion is needed.
  - The `.C` dispatcher ensures the R-side `as.integer(ny_val)` value arrives as a properly coerced `int *` at the C boundary.

---

### Pattern: Inline Scalar Extraction in a Conditional Expression

- **Locations:** `rpart.c` line 83; `xpred.c` lines 81, 205

- **Original Context (.Call):**

```c
/* rpart.c:83-84 */
if (asInteger(method2) <= NUM_METHODS) {
    i = asInteger(method2) - 1;
    ...
}

/* xpred.c:205 */
if (asInteger(all2) == 1)
    nresp = rp.num_resp;
else
    nresp = 1;
```

- **C/C++ Equivalent (.C):**

```c
/* asInteger(arg) used inline in a condition becomes arg[0]. */
void rpart_c(const int *method, ...)
{
    if (method[0] <= NUM_METHODS) {    /* was: asInteger(method2) <= NUM_METHODS */
        int i = method[0] - 1;         /* was: asInteger(method2) - 1            */
        ...
    }
}

void xpred_c(const int *all, ...)
{
    int nresp;
    if (all[0] == 1)                   /* was: asInteger(all2) == 1 */
        nresp = rp.num_resp;
    else
        nresp = 1;
    ...
}
```

- **R-side call:**

```r
result <- .C("xpred_c",
             all    = as.integer(all_flag),   # length-1 flag: 1L or 0L
             # ... other args ...
             )
```

- **Explanation:**
  - `asInteger(method2)` and `asInteger(all2)` used directly inside `if` conditions become `method[0]` and `all[0]`.
  - The conditional logic, comparison operators, and arithmetic (`- 1`) are unchanged.
  - Where `asInteger` is called twice on the same `SEXP` argument within a short scope (lines 83–84 in both `rpart.c` and `xpred.c`), the `.C` version reads `method[0]` twice, which is equally efficient — no caching is necessary.

---

### Pattern: Inline Scalar Extraction as a Function Argument

- **Locations:** `pred_rpart.c` line 140

- **Original Context (.Call):**

```c
/* pred_rpart.c:140-144 */
pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit),
            INTEGER(dimc), INTEGER(nnum), INTEGER(nodes2),
            INTEGER(vnum), REAL(split2), INTEGER(csplit2),
            INTEGER(usesur), REAL(xdata2), INTEGER(xmiss2),
            INTEGER(where));
```

- **C/C++ Equivalent (.C):**

```c
/* asInteger(arg) used inline in a function call becomes arg[0].
 * INTEGER(arg) used inline becomes the arg pointer directly. */

void pred_rpart_c(const int    *n,
                  const int    *dimx,
                  const int    *nnode,
                  const int    *nsplit,
                  const int    *dimc,
                  const int    *nnum,
                  const int    *nodes2,
                  const int    *vnum,
                  const double *split2,
                  const int    *csplit2,
                  const int    *usesur,
                  const double *xdata2,
                  const int    *xmiss2,
                  int          *where)
{
    pred_rpart0(dimx,       /* was: INTEGER(dimx)      */
                nnode[0],   /* was: asInteger(nnode)   */
                nsplit[0],  /* was: asInteger(nsplit)  */
                dimc,       /* was: INTEGER(dimc)      */
                nnum,       /* was: INTEGER(nnum)      */
                nodes2,     /* was: INTEGER(nodes2)    */
                vnum,       /* was: INTEGER(vnum)      */
                split2,     /* was: REAL(split2)       */
                csplit2,    /* was: INTEGER(csplit2)   */
                usesur,     /* was: INTEGER(usesur)    */
                xdata2,     /* was: REAL(xdata2)       */
                xmiss2,     /* was: INTEGER(xmiss2)    */
                where);     /* was: INTEGER(where)     */
}
```

- **R-side call:**

```r
n_val <- as.integer(dimx[1])
result <- .C("pred_rpart_c",
             n       = n_val,
             dimx    = as.integer(dimx),
             nnode   = as.integer(nnode),    # length-1 scalar
             nsplit  = as.integer(nsplit),   # length-1 scalar
             dimc    = as.integer(dimc),
             nnum    = as.integer(nnum),
             nodes2  = as.integer(nodes2),
             vnum    = as.integer(vnum),
             split2  = as.double(split2),
             csplit2 = as.integer(csplit2),
             usesur  = as.integer(usesur),
             xdata2  = as.double(xdata2),
             xmiss2  = as.integer(xmiss2),
             where   = integer(n_val))
where_vec <- result$where
```

- **Explanation:**
  - Each `asInteger(arg)` in the inline argument list is replaced by `arg[0]`, passing the scalar `int` value to `pred_rpart0` exactly as before.
  - Each `INTEGER(arg)` in the same list is replaced by `arg` (the pointer itself), since the argument is already `int *` under `.C`.
  - `REAL(arg)` similarly becomes the pointer `arg` of type `double *`.
  - The function signature of `pred_rpart0` (the lower-level non-`.Call` worker) is unchanged; only the arguments passed to it change from SEXP-derived expressions to plain pointer/scalar expressions.

---

### Pattern: Scalar Extraction in a Callback Initialisation Function (Not Directly Portable to `.C`)

- **Locations:** `rpart_callback.c` lines 54–55

- **Original Context (.Call):**

```c
/* rpart_callback.c:47-72 */
static SEXP rho;
static SEXP expr1, expr2;
static int ysave, rsave;

SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    rho   = rhox;
    ysave = asInteger(ny);    /* line 54: scalar SEXP -> static int */
    rsave = asInteger(nr);    /* line 55: scalar SEXP -> static int */
    expr1 = expr1x;
    expr2 = expr2x;
    /* ... R_getVar calls to retrieve environment variables ... */
    return R_NilValue;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Direct .C conversion of init_rpcallback is NOT possible.
 *
 * The asInteger calls at lines 54-55 are mechanically convertible (ny[0],
 * nr[0]), but the surrounding function has three hard dependencies on
 * .Call-only capabilities:
 *
 *   1. static SEXP rho — persists an R environment handle between calls;
 *      R environments cannot be passed through the .C interface.
 *   2. static SEXP expr1, expr2 — persist unevaluated R language objects;
 *      there is no .C equivalent for storing R expressions.
 *   3. R_getVar(install("yback"), rho, FALSE) — looks up a variable by name
 *      in a live R environment; this operation requires a SEXP environment
 *      handle and has no counterpart in the .C API.
 *
 * Recommended migration strategies:
 *
 *   Option A — Keep init_rpcallback as a .Call function.
 *     Register only init_rpcallback and the callback invocation routines
 *     under .Call.  The main rpart computation loop, which does not use
 *     eval(), can be ported to .C independently with asInteger(ny) and
 *     asInteger(nr) replaced by ny[0] and nr[0] where they appear as
 *     direct scalar inputs to a .C function.
 *
 *   Option B — Move environment lookups and expression evaluation to R.
 *     Pre-extract yback, wback, xback, nback from the environment in R
 *     before calling .C, and pass them as explicit integer() / double()
 *     vectors.  Pass ny and nr as as.integer() scalars.  The C function
 *     stores raw pointers rather than SEXP handles:
 *
 *       void init_rpcallback_c(const int *ny,    // was: asInteger(ny)
 *                              const int *nr,    // was: asInteger(nr)
 *                              const double *yback,
 *                              const int    *n_yback,
 *                              const double *wback,
 *                              const double *xback,
 *                              const int    *nback,
 *                              const int    *n_nback)
 *       {
 *           ysave = ny[0];      // was: ysave = asInteger(ny)
 *           rsave = nr[0];      // was: rsave = asInteger(nr)
 *           ydata = yback;
 *           wdata = wback;
 *           xdata = xback;
 *           ndata = nback;
 *           // expr1/expr2/rho cannot be initialised this way
 *       }
 *
 *     The eval(expr1/expr2, rho) callback invocations still require
 *     restructuring at the algorithm level (Option A is preferred for
 *     the callback subsystem).
 */
```

- **Explanation:**
  - `ysave = asInteger(ny)` and `rsave = asInteger(nr)` are individually convertible to `ysave = ny[0]` and `rsave = nr[0]`; the `asInteger` macro itself is not the blocker.
  - The blocker is the three `static SEXP` module-level variables (`rho`, `expr1`, `expr2`) and the `R_getVar`/`install` calls that depend on a live R environment handle. None of these constructs exist in the `.C` API.
  - This is the only pattern in the CSV where a complete `.C` migration requires architectural restructuring beyond a mechanical substitution.
