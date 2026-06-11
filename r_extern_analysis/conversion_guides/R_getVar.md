# Conversion Guide: `R_getVar`

## 1. Overview of `R_getVar` in R API

`R_getVar` is declared in `Rinternals.h` as `SEXP R_getVar(SEXP sym, SEXP rho, Rboolean inherits)`. It takes a symbol `SEXP` (typically produced by `install("name")`) and an environment `SEXP`, looks up the named binding in that environment (and, when `inherits` is `TRUE`, through its enclosing environments), and returns the bound value as a `SEXP`. If no binding is found it raises an R-level error rather than returning `R_UnboundValue`, distinguishing it from the lower-level `findVar`/`findVarInFrame` functions that return the sentinel and let the caller handle the miss. In R < 4.5.0, `R_getVar` does not exist in the public API; the rpart source provides a compatibility shim (defined at `rpart_callback.c` lines 20–27) that emulates the identical behaviour using `findVar` or `findVarInFrame` plus an explicit `R_UnboundValue` check.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart_callback.c` | 59 | `stemp = R_getVar(install("yback"), rho, FALSE);` |
| `rpart_callback.c` | 62 | `stemp = R_getVar(install("wback"), rho, FALSE);` |
| `rpart_callback.c` | 65 | `stemp = R_getVar(install("xback"), rho, FALSE);` |
| `rpart_callback.c` | 68 | `stemp = R_getVar(install("nback"), rho, FALSE);` |

All four calls reside inside the single function `init_rpcallback` (lines 47–72).

### Types and variables involved

- **`sym` argument** — `install("yback")` etc. returns a `SEXP` of type `SYMSXP` (an interned R symbol). `install` maps a C string to a unique, GC-protected symbol object. It has no equivalent in the `.C` API.
- **`rho` argument** — a `static SEXP rho` module-level variable, set at line 53 from the `SEXP rhox` parameter of `init_rpcallback`. It is an R environment (`ENVSXP`) passed in by the R caller and retained across multiple C function calls.
- **`inherits` argument** — `FALSE` in every call, meaning the lookup is confined to the immediate frame of `rho` (equivalent to `findVarInFrame(rho, sym)`).
- **`stemp` variable** — a local `SEXP`, used only to hold the result long enough to call `REAL(stemp)` (lines 60, 63, 66) or `INTEGER(stemp)` (line 69) and extract the underlying data pointer. The retrieved data is stored in module-level pointers:
  - `double *ydata` ← `REAL(stemp)` from `"yback"`
  - `double *wdata` ← `REAL(stemp)` from `"wback"`
  - `double *xdata` ← `REAL(stemp)` from `"xback"`
  - `int    *ndata` ← `INTEGER(stemp)` from `"nback"`

### Compatibility shim (R < 4.5.0)

`rpart_callback.c` lines 19–28 define:

```c
#if R_VERSION < R_Version(4, 5, 0)
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
  if (val == R_UnboundValue)
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif
```

This reveals the full semantics: with `inherits = FALSE`, `R_getVar` is a thin error-checking wrapper around `findVarInFrame(rho, sym)`.

### Distinct implementation patterns

There is only one functional pattern in the CSV data:

**Pattern: Look up a named variable in an R environment, extract its data pointer, and store that pointer in a module-level static C variable.**

The four calls are structurally identical; they differ only in the variable name string and the accessor macro applied to the result (`REAL` for three of them, `INTEGER` for `"nback"`).

---

## 3. Pure C/C++ Conversion Strategy

### Why direct `.C` conversion is not possible

`R_getVar` depends on three `.Call`-only mechanisms, none of which are available under the `.C` API:

1. **`SEXP rho` (environment handle)** — an R environment object. The `.C` API communicates exclusively through basic C pointer types (`int *`, `double *`, `char **`). There is no C type that represents an R environment, so `rho` cannot be passed into or stored by a `.C` function.

2. **`install("name")` (symbol interning)** — produces a `SEXP` of type `SYMSXP`. Under `.C` there are no `SEXP` values of any kind.

3. **Dynamic variable lookup at runtime** — `R_getVar` traverses R's internal environment chain at the time of the call. The `.C` API has no mechanism to reach into a live R environment from within a C function.

### Equivalent `.C`-compatible approach

The R-level environment lookup must be lifted entirely out of C and performed on the R side before the `.C` call is made. The R code pre-extracts the numeric vectors from the environment and passes them as typed pointer arguments. The C function receives the pre-resolved data pointers directly, eliminating every `R_getVar`, `install`, `REAL(stemp)`, and `INTEGER(stemp)` call.

Concretely, the R caller replaces:

```r
.Call("init_rpcallback", rho, ny, nr, expr1, expr2)
```

with code that first retrieves the four backing vectors from `rho` explicitly:

```r
yback <- get("yback", envir = rho, inherits = FALSE)
wback <- get("wback", envir = rho, inherits = FALSE)
xback <- get("xback", envir = rho, inherits = FALSE)
nback <- get("nback", envir = rho, inherits = FALSE)
.C("init_rpcallback_c",
   yback = as.double(yback),
   wback = as.double(wback),
   xback = as.double(xback),
   nback = as.integer(nback),
   ny    = as.integer(ny),
   nr    = as.integer(nr))
```

The `expr1`, `expr2`, and `rho` arguments are not passed at all; they belong to the `eval()`-based callback pattern, which is handled separately (see the `SEXP` and `REAL` conversion guides) and must remain as `.Call`.

This approach is fully `.C`-compatible because every datum that was previously retrieved dynamically inside C is now a plain typed pointer supplied by the caller.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Runtime Environment Variable Lookup via `R_getVar`

- **Locations:** `rpart_callback.c` lines 59, 62, 65, 68

- **Original Context (.Call):**

```c
/* rpart_callback.c:47-72 */
static SEXP rho;            /* module-level R environment handle */
static double *ydata;       /* extracted pointers stored across calls */
static double *wdata;
static double *xdata;
static int    *ndata;

SEXP
init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;

    rho   = rhox;                    /* store environment SEXP for later eval() */
    ysave = asInteger(ny);
    rsave = asInteger(nr);
    expr1 = expr1x;
    expr2 = expr2x;

    /* Look up each backing vector by name in rho, extract its data pointer */
    stemp = R_getVar(install("yback"), rho, FALSE);
    ydata = REAL(stemp);             /* line 60 */

    stemp = R_getVar(install("wback"), rho, FALSE);
    wdata = REAL(stemp);             /* line 63 */

    stemp = R_getVar(install("xback"), rho, FALSE);
    xdata = REAL(stemp);             /* line 66 */

    stemp = R_getVar(install("nback"), rho, FALSE);
    ndata = INTEGER(stemp);          /* line 69 */

    return R_NilValue;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * R_getVar, install, REAL, INTEGER, and the SEXP rho handle are all removed.
 * The four backing arrays are received as typed C pointer arguments.
 * The function is void-returning.
 *
 * Note: expr1, expr2, and rho are NOT included here. The eval()-based
 * callbacks (rpart_callback1, rpart_callback2) depend on R's evaluator
 * and must remain as separate .Call functions. Only the data-pointer
 * initialisation portion is ported to .C.
 */

static double *ydata;
static double *wdata;
static double *xdata;
static int    *ndata;
static int     ysave;
static int     rsave;

void init_rpcallback_c(double *yback,   /* pre-extracted from rho: as.double(get("yback", envir=rho)) */
                       double *wback,   /* pre-extracted from rho: as.double(get("wback", envir=rho)) */
                       double *xback,   /* pre-extracted from rho: as.double(get("xback", envir=rho)) */
                       int    *nback,   /* pre-extracted from rho: as.integer(get("nback", envir=rho)) */
                       int    *ny,      /* scalar: number of y columns */
                       int    *nr)      /* scalar: length of eval return */
{
    /* Store the data pointers for use by subsequent callback invocations */
    ydata = yback;     /* was: ydata = REAL(R_getVar(install("yback"), rho, FALSE)) */
    wdata = wback;     /* was: wdata = REAL(R_getVar(install("wback"), rho, FALSE)) */
    xdata = xback;     /* was: xdata = REAL(R_getVar(install("xback"), rho, FALSE)) */
    ndata = nback;     /* was: ndata = INTEGER(R_getVar(install("nback"), rho, FALSE)) */
    ysave = *ny;       /* was: ysave = asInteger(ny) */
    rsave = *nr;       /* was: rsave = asInteger(nr) */

    /* No return value; no R_NilValue; no PROTECT/UNPROTECT */
}
```

- **R-side call:**

```r
## Perform the environment lookups on the R side (replaces R_getVar inside C)
yback <- get("yback", envir = rho, inherits = FALSE)
wback <- get("wback", envir = rho, inherits = FALSE)
xback <- get("xback", envir = rho, inherits = FALSE)
nback <- get("nback", envir = rho, inherits = FALSE)

invisible(.C("init_rpcallback_c",
             yback = as.double(yback),
             wback = as.double(wback),
             xback = as.double(xback),
             nback = as.integer(nback),
             ny    = as.integer(ny),
             nr    = as.integer(nr)))
```

Registration entry:

```c
static R_NativePrimitiveArgType init_rpcallback_c_types[] = {
    REALSXP,  /* yback */
    REALSXP,  /* wback */
    REALSXP,  /* xback */
    INTSXP,   /* nback */
    INTSXP,   /* ny    */
    INTSXP    /* nr    */
};

static const R_CMethodDef CEntries[] = {
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c, 6, init_rpcallback_c_types},
    {NULL, NULL, 0, NULL}
};
```

- **Explanation:**
  - `R_getVar(install("yback"), rho, FALSE)` retrieves the R object named `"yback"` from environment `rho` without searching parent frames (`inherits = FALSE`). This is exactly equivalent to `get("yback", envir = rho, inherits = FALSE)` on the R side. The four `R_getVar` calls are replaced by four `get()` calls in R, one for each variable name.
  - `REAL(stemp)` and `INTEGER(stemp)` are removed because there is no `SEXP stemp` under `.C`. The R-side `as.double()` and `as.integer()` conversions ensure each argument arrives in the correct C type. The resulting `double *` and `int *` arguments are assigned directly to the module-level static pointers.
  - `install("name")` (symbol interning) is a `.Call`-only operation and disappears entirely; the name string is used only in the R-side `get()` call.
  - `static SEXP rho` is not carried into the `.C` function. Environment lookup is lifted to R completely. The `expr1`, `expr2`, and `rho` SEXP state required by `rpart_callback1` and `rpart_callback2` must remain managed by a separate `.Call`-registered initialisation function; those callbacks rely on `eval(expr, rho)` which cannot be ported to `.C`.
  - The function return type changes from `SEXP` (returning `R_NilValue`) to `void`. `.C` functions do not return values; the R caller receives the modified argument list instead.
  - `asInteger(ny)` / `asInteger(nr)` become `*ny` / `*nr` because under `.C` scalar integers arrive as single-element `int *` arrays.
  - The `.C` dispatcher protects all caller-supplied vectors for the duration of the call, so no explicit `PROTECT`/`UNPROTECT` is needed.

---

### Note on the Compatibility Shim

For projects that must support R < 4.5.0, the compat shim at `rpart_callback.c` lines 19–27 shows that `R_getVar(sym, rho, FALSE)` is semantically identical to:

```c
SEXP val = findVarInFrame(rho, sym);
if (val == R_UnboundValue)
    error("variable '%s' not found", CHAR(PRINTNAME(sym)));
```

Both `findVarInFrame` and `R_getVar` are `.Call`-only operations. The shim does not change the `.C` portability assessment — neither the pre-4.5.0 nor the post-4.5.0 form of this lookup can be expressed under the `.C` API. The migration strategy (lifting the lookup to R via `get()`) applies equally to both R version ranges.
