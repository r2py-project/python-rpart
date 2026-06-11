# Conversion Guide: `R_UnboundValue`

## 1. Overview of `R_UnboundValue` in R API

`R_UnboundValue` is a globally pre-allocated `SEXP` sentinel object declared in `Rinternals.h` as `LibExtern SEXP R_UnboundValue; /* Unbound marker */`. It is the canonical out-of-band return value that R's environment-lookup functions (`findVar`, `findVarInFrame`, `findVarInFrame3`) return when a symbol cannot be resolved in the searched environment chain, i.e., the symbol is not bound to any value. In the `.Call/.External` API it is used exclusively as a pointer-comparison sentinel: the calling C code tests `val == R_UnboundValue` to detect lookup failure and take an appropriate action (typically calling `error()`), and its result is never unwrapped or passed back to R. Under the `.C/.Fortran` API, `R_UnboundValue` along with the entire environment-lookup machinery it guards is inapplicable because `.C` functions cannot interact with R environments or R symbols at all.

---

## 2. Contextual Usage Analysis

### Source location

| File | Line | Category | Context |
|------|------|----------|---------|
| `rpart_callback.c` | 23 | sentinel comparison | `if (val == R_UnboundValue)` |

### 31-line window (lines 8–38 of `rpart_callback.c`)

```c
#include <Rversion.h>
/* don't include rpart.h: it conflicts */

#ifdef ENABLE_NLS
#include <libintl.h>
#define _(String) dgettext ("rpart", String)
#else
#define _(String) (String)
#endif

/* compatibility shim for R < 4.5.0 */
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

static int ysave;
static int rsave;
static SEXP expr1;
static SEXP expr2;
static SEXP rho;

static double *ydata;
static double *xdata;
static double *wdata;
static int *ndata;
```

### Structural role

`R_UnboundValue` appears inside `compat_getVar`, a `static` helper function that is wrapped in an `#if R_VERSION < R_Version(4, 5, 0)` preprocessor guard. This guard exists because R 4.5.0 introduced the public API function `R_getVar` (declared at line 537 of `Rinternals.h` as `SEXP R_getVar(SEXP, SEXP, Rboolean)`), which already performs the unbound-check internally. On R versions prior to 4.5.0 that function did not exist, so `compat_getVar` reimplements it:

1. It calls `findVar(sym, rho)` (which searches `rho` and its parent environments) or `findVarInFrame(rho, sym)` (which searches only `rho`) depending on the `inherits` flag.
2. Both lookup functions return `R_UnboundValue` when the symbol is absent.
3. The test `val == R_UnboundValue` detects that failure and calls `error(...)` with a formatted message using `CHAR(PRINTNAME(sym))` to extract the symbol's name string.
4. If the lookup succeeded, the resolved `SEXP val` is returned to the caller.

The macro `#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)` makes `compat_getVar` available under the same name as the native R 4.5.0 API, so the rest of the file uses `R_getVar` uniformly.

### Data types involved

| Symbol | Type | Role |
|--------|------|------|
| `val` | `SEXP` | receives return value of `findVar` / `findVarInFrame` |
| `R_UnboundValue` | `SEXP` (global singleton) | sentinel pointer for "not found" |
| `sym` | `SEXP` | an R symbol object created by `install(...)` |
| `rho` | `SEXP` | an R environment object |
| `inherits` | `Rboolean` | controls whether parent environments are searched |

### Memory-management macros

`R_UnboundValue` is never passed to `PROTECT` or `UNPROTECT`, and no allocation is involved. It is used purely as an opaque pointer for identity comparison (`==`).

### Distinct implementation patterns

There is exactly one usage pattern in this codebase: **sentinel comparison after environment variable lookup**. `R_UnboundValue` is compared with `==` against the return value of `findVar` / `findVarInFrame` to detect a failed symbol resolution in a given R environment.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under the `.C` API, the C function has no access to R environments, R symbols, or R's evaluator. All data that the function needs must be pre-extracted in R and passed in as basic C pointer arguments (`int *`, `double *`, `char **`). As a direct consequence:

- `findVar` and `findVarInFrame` cannot be called from a `.C` function.
- `R_UnboundValue` (the sentinel that guards those lookup results) becomes unreachable.
- `compat_getVar` / `R_getVar` (the lookup wrapper that uses `R_UnboundValue`) is entirely irrelevant to `.C` functions.
- The four variables whose pointers are resolved by `R_getVar` in `init_rpcallback` (`ydata`, `wdata`, `xdata`, `ndata`) must instead be received as pre-extracted `double *` / `int *` arguments from the R caller.

The sole conversion strategy is therefore **complete removal**: the `compat_getVar` helper, the `R_UnboundValue` comparison, and every `R_getVar` call site are all deleted from the C source, and the data they formerly resolved is supplied by the R caller as plain pointer arguments.

### Why this ensures `.C` compatibility

The `.C` dispatcher communicates exclusively via basic C pointer types. It provides no mechanism to pass or return `SEXP` objects, call R's symbol-resolution machinery, or raise R-level errors with `error()`. Any C code that touches `R_UnboundValue` necessarily also touches at least one of `findVar`, `findVarInFrame`, `SEXP`, `PRINTNAME`, `CHAR`, or `error()` — all of which belong exclusively to the `.Call/.External` world. Removing the entire lookup block and shifting variable resolution to the R side is the only approach that keeps the C code within the `.C` API contract.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Sentinel Comparison After Environment Variable Lookup

- **Locations:** `rpart_callback.c`, line 23 (inside `compat_getVar`, lines 19–28)

- **Original Context (.Call):**

```c
/* rpart_callback.c:18-28 — compatibility shim for R < 4.5.0 */
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

/* rpart_callback.c:59-69 — R_getVar call sites that trigger the lookup */
SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;

    rho   = rhox;
    ysave = asInteger(ny);
    rsave = asInteger(nr);
    expr1 = expr1x;
    expr2 = expr2x;

    stemp = R_getVar(install("yback"), rho, FALSE);  /* lookup + unbound check */
    ydata = REAL(stemp);

    stemp = R_getVar(install("wback"), rho, FALSE);
    wdata = REAL(stemp);

    stemp = R_getVar(install("xback"), rho, FALSE);
    xdata = REAL(stemp);

    stemp = R_getVar(install("nback"), rho, FALSE);
    ndata = INTEGER(stemp);

    return R_NilValue;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The entire compat_getVar shim and R_getVar macro are deleted.
 * R_UnboundValue is never referenced.
 *
 * init_rpcallback_c receives the four data arrays directly from the
 * R caller.  The R caller is responsible for extracting "yback",
 * "wback", "xback", and "nback" from the evaluation frame (rho) before
 * making the .C call, eliminating the need for environment lookup in C.
 *
 * The function is void; no SEXP objects are involved anywhere.
 */

/* Module-level storage — still plain C pointers, unchanged */
static int    ysave;
static int    rsave;
static double *ydata;
static double *wdata;
static double *xdata;
static int    *ndata;

void init_rpcallback_c(const double *yback,   /* was: R_getVar("yback", rho, FALSE) -> REAL() */
                       const double *wback,   /* was: R_getVar("wback", rho, FALSE) -> REAL() */
                       const double *xback,   /* was: R_getVar("xback", rho, FALSE) -> REAL() */
                       const int    *nback,   /* was: R_getVar("nback", rho, FALSE) -> INTEGER() */
                       const int    *ny,      /* was: asInteger(ny) */
                       const int    *nr)      /* was: asInteger(nr) */
{
    ysave = ny[0];
    rsave = nr[0];
    ydata = yback;   /* R guarantees the buffer stays live for the duration of .C */
    wdata = wback;
    xdata = xback;
    ndata = nback;
    /* function is void; no return statement needed */
}
```

- R-side call:

```r
# Before (.Call) — R_getVar resolved "yback" etc. inside C using the rho frame
.Call("init_rpcallback", rho, ny, nr, expr1, expr2)

# After (.C) — R resolves the variables from rho before the call
.C("init_rpcallback_c",
   yback = as.double(get("yback", envir = rho, inherits = FALSE)),
   wback = as.double(get("wback", envir = rho, inherits = FALSE)),
   xback = as.double(get("xback", envir = rho, inherits = FALSE)),
   nback = as.integer(get("nback", envir = rho, inherits = FALSE)),
   ny    = as.integer(ny),
   nr    = as.integer(nr))
# return value is the argument list; discarded (side-effect-only call)
```

- **Explanation:**

  - `R_UnboundValue` and `compat_getVar` are completely removed. They existed solely to detect a failed `findVar` / `findVarInFrame` call; since those lookup functions cannot be called from `.C` code, the sentinel becomes irrelevant.

  - `findVar(sym, rho)` and `findVarInFrame(rho, sym)` (the two functions that can return `R_UnboundValue`) are both removed from the C source. Their job is moved to the R caller, which uses `get("varname", envir = rho, inherits = FALSE)` — an R-level call that raises an R error automatically if the name is missing, replicating the `error(...)` that `compat_getVar` performed on `val == R_UnboundValue`.

  - `REAL(stemp)` and `INTEGER(stemp)` (which unwrapped the found `SEXP` to a C pointer) disappear. The R caller passes the numeric vectors directly; the C function receives them as typed `double *` / `int *` arguments.

  - The version guard `#if R_VERSION < R_Version(4, 5, 0)` and the `#define R_getVar` macro are both deleted. Under `.C` there is no concept of API-version-dependent symbol lookup; the R-level `get()` call works uniformly across all R versions.

  - The `error(...)` call inside `compat_getVar` is also removed. The equivalent error is now raised on the R side: `get()` signals a standard R error with a descriptive message if the variable does not exist in `rho`.

  - The registration table entry moves from `R_CallMethodDef` to `R_CMethodDef` with an `R_NativePrimitiveArgType[]` array:

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

  - Note that `expr1`, `expr2`, and `rho` (which stored R language objects for `eval()` calls in the callback functions `rpart_callback1` and `rpart_callback2`) are omitted from the `.C` signature because those callbacks cannot be converted to `.C` at all — they depend on `eval()`, which requires `SEXP` and is part of the `.Call` API only. See the `SEXP.md` conversion guide for the full treatment of that blocker.
