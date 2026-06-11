# Conversion Guide: `findVarInFrame`

## 1. Overview of `findVarInFrame` in R API

`findVarInFrame` is a macro defined in `Rinternals.h` as `#define findVarInFrame Rf_findVarInFrame`, aliasing the C function declared as `SEXP Rf_findVarInFrame(SEXP rho, SEXP sym)`. It accepts an R environment (`SEXP` of type `ENVSXP`) as its first argument and an R symbol (`SEXP` of type `SYMSXP`, typically produced by `install("name")`) as its second, searches exclusively the immediate frame of `rho` without ascending to any parent environments, and returns the `SEXP` value to which `sym` is bound. If no binding exists in that single frame it returns the global sentinel `R_UnboundValue`; the caller is responsible for testing this condition and raising an error. It is the frame-restricted counterpart of `findVar(SEXP sym, SEXP rho)`, which traverses the full enclosing environment chain. Under the `.C/.Fortran` API, `findVarInFrame` is entirely inapplicable: `.C` functions communicate exclusively through basic C pointer types and have no mechanism to accept, store, or search R environments or R symbols.

---

## 2. Contextual Usage Analysis

### Source location

| File | Line | Category | Context |
|------|------|----------|---------|
| `rpart_callback.c` | 22 | function | `SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);` |

### 31-line window (lines 7–37 of `rpart_callback.c`)

```c
#include <Rinternals.h>
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

static int ysave;               /* number of columns of y  */
static int rsave;               /* the length of the returned "mean" from the
                                 * user's eval routine */
static SEXP expr1;              /* the evaluation expression for splits */
static SEXP expr2;              /* the evaluation expression for values */
static SEXP rho;

static double *ydata;           /* pointer to the data portion of yback */
```

### Structural role

`findVarInFrame` appears at line 22 inside the `static` helper function `compat_getVar` (lines 20–26), which is wrapped in a preprocessor guard `#if R_VERSION < R_Version(4, 5, 0)`. This guard exists because R 4.5.0 introduced the public API function `R_getVar` (`SEXP R_getVar(SEXP sym, SEXP rho, Rboolean inherits)`), which internalises the unbound-value check. On R versions prior to 4.5.0, that function was not available in the public header, so `compat_getVar` reimplements its full semantics:

1. When `inherits` is `TRUE`, `findVar(sym, rho)` is called — it searches `rho` and all parent environments.
2. When `inherits` is `FALSE`, `findVarInFrame(rho, sym)` is called — it searches only the immediate frame of `rho`.
3. Both functions return `R_UnboundValue` when the symbol is absent. The comparison `val == R_UnboundValue` detects this failure and triggers `error(...)`, using `CHAR(PRINTNAME(sym))` to recover the symbol name string for the message.
4. On success, the resolved `SEXP val` is returned to the caller.

The macro `#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)` makes the shim transparent to the rest of the file, which calls `R_getVar` uniformly regardless of R version.

The four call sites that ultimately reach `findVarInFrame` (via `R_getVar`) are in `init_rpcallback` (lines 59–69), all with `inherits = FALSE`, which means every lookup at runtime routes exclusively through `findVarInFrame`:

| Line | Call | Resolved pointer |
|------|------|-----------------|
| 59 | `R_getVar(install("yback"), rho, FALSE)` | `double *ydata` via `REAL()` |
| 62 | `R_getVar(install("wback"), rho, FALSE)` | `double *wdata` via `REAL()` |
| 65 | `R_getVar(install("xback"), rho, FALSE)` | `double *xdata` via `REAL()` |
| 68 | `R_getVar(install("nback"), rho, FALSE)` | `int    *ndata` via `INTEGER()` |

### Data types involved

| Symbol | Type | Role |
|--------|------|------|
| `rho` | `SEXP` (`ENVSXP`) | R environment passed in as a function argument and retained as a module-level static |
| `sym` | `SEXP` (`SYMSXP`) | interned R symbol, produced by `install("name")` |
| `inherits` | `Rboolean` | selects `findVar` (full chain, `TRUE`) vs. `findVarInFrame` (frame only, `FALSE`) |
| `val` | `SEXP` | receives the bound value, or `R_UnboundValue` on miss |
| `R_UnboundValue` | `SEXP` (global singleton) | sentinel pointer indicating a failed lookup |

### Memory-management macros

`findVarInFrame` does not allocate new memory; it returns a pointer to an existing binding within R's internal environment structure. The returned `SEXP` is not passed to `PROTECT` because it is already protected by its presence in the environment frame. No `PROTECT`/`UNPROTECT` calls surround this function.

### Argument order distinction from `findVar`

Note the reversed argument order compared to `findVar`:

| Function | Signature |
|----------|-----------|
| `findVar` | `SEXP Rf_findVar(SEXP sym, SEXP rho)` — symbol first, environment second |
| `findVarInFrame` | `SEXP Rf_findVarInFrame(SEXP rho, SEXP sym)` — environment first, symbol second |

This distinction is visible directly at line 22: `findVar(sym, rho)` vs. `findVarInFrame(rho, sym)`. Both return `R_UnboundValue` on a miss, but only `findVarInFrame` restricts the search to the single specified frame.

### Related conversion guides

- `findVar.md` — covers the full-chain counterpart `findVar(sym, rho)`, which appears in the same ternary expression at line 22. The conversion strategy is identical for both functions.
- `R_getVar.md` — covers the high-level wrapper `R_getVar(sym, rho, inherits)` that delegates to `findVarInFrame` (when `inherits = FALSE`) or `findVar` (when `inherits = TRUE`), and the four concrete call sites in `init_rpcallback`.
- `R_UnboundValue.md` — covers the sentinel comparison `val == R_UnboundValue` that guards the return value of `findVarInFrame`.
- `PRINTNAME.md` — covers `CHAR(PRINTNAME(sym))`, used in the error message that fires when `findVarInFrame` returns `R_UnboundValue`.
- `SEXP.md` — covers the broader consequences of removing all `SEXP` usage throughout the codebase.
- `eval.md` — covers the `eval(expr, rho)` callback pattern in the same file, which constitutes a separate hard blocker for full `.C` migration.

### Distinct implementation patterns

There is exactly one functional pattern in the CSV data:

**Pattern: Frame-restricted environment variable lookup — `findVarInFrame(rho, sym)` used as the `FALSE`-branch of a ternary controlled by an `inherits` flag, followed by an `R_UnboundValue` guard and an error call.**

In practice every call site in this codebase passes `inherits = FALSE`, so `findVarInFrame` is the only branch ever executed at runtime.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

The `.C` API communicates exclusively through basic C pointer types (`int *`, `double *`, `char **`). It provides no mechanism to:

- Accept or store an R environment handle (`SEXP rho`).
- Accept or create an R symbol object (`SEXP sym` / `install("name")`).
- Restrict or perform a lookup within a single R environment frame at runtime.
- Compare against the `R_UnboundValue` sentinel.
- Call `error()` with a formatted symbol-name message using `CHAR(PRINTNAME(sym))`.

As a consequence, `findVarInFrame`, its argument `install("name")`, the `compat_getVar` shim, and the entire `#if R_VERSION` guard are entirely unportable to the `.C` API. The **only compatible strategy** is to lift every variable lookup out of C and perform it on the R side before the `.C` call is made.

### Type mapping

| `.Call` construct | `.C` equivalent |
|-------------------|-----------------|
| `findVarInFrame(rho, sym)` | `get("name", envir = rho, inherits = FALSE)` on the R side; result passed as typed pointer |
| `findVar(sym, rho)` | `get("name", envir = rho, inherits = TRUE)` on the R side; result passed as typed pointer |
| `install("name")` | disappears; the name string is used only in the R-side `get()` call |
| `SEXP val` (lookup result) | disappears; the R caller passes the already-extracted data array |
| `val == R_UnboundValue` + `error(...)` | replaced automatically by R's own error from `get()` when the name is absent |
| `REAL(stemp)` | `as.double(val)` in R; arrives as `double *` in C |
| `INTEGER(stemp)` | `as.integer(val)` in R; arrives as `int *` in C |

### Why this ensures `.C` compatibility

The `.C` dispatcher type-checks and passes each argument as a raw C pointer. No `SEXP` objects enter or leave the C function. The R-level `get(..., inherits = FALSE)` call precisely mirrors the frame-restricted semantics of `findVarInFrame`: it searches only the immediate environment `rho` without ascending to parent frames. When the named variable is absent, `get()` raises a standard R error automatically, reproducing the `R_UnboundValue` check that `compat_getVar` performed explicitly. The `compat_getVar` function, the `R_getVar` macro, and the `#if R_VERSION` preprocessor guard are all rendered unnecessary and deleted in their entirety.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Frame-Restricted Environment Variable Lookup (`findVarInFrame`)

- **Locations:** `rpart_callback.c`, line 22 (inside `compat_getVar`, which is the body of the `R_getVar` shim used at lines 59, 62, 65, 68)

- **Original Context (.Call):**

```c
/* rpart_callback.c:18-28 — compatibility shim where findVarInFrame is called */
#if R_VERSION < R_Version(4, 5, 0)
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
  /* findVar   searches rho AND parent environments (inherits = TRUE).
   * findVarInFrame searches only the immediate frame of rho (inherits = FALSE).
   * Note the reversed argument order: findVar(sym, rho) vs findVarInFrame(rho, sym). */
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
  if (val == R_UnboundValue)
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif

/* rpart_callback.c:47-72 — the four call sites that resolve to findVarInFrame */
SEXP
init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;

    rho   = rhox;
    ysave = asInteger(ny);
    rsave = asInteger(nr);
    expr1 = expr1x;
    expr2 = expr2x;

    stemp = R_getVar(install("yback"), rho, FALSE); /* → findVarInFrame(rho, "yback") */
    ydata = REAL(stemp);                            /* line 60 */

    stemp = R_getVar(install("wback"), rho, FALSE); /* → findVarInFrame(rho, "wback") */
    wdata = REAL(stemp);                            /* line 63 */

    stemp = R_getVar(install("xback"), rho, FALSE); /* → findVarInFrame(rho, "xback") */
    xdata = REAL(stemp);                            /* line 66 */

    stemp = R_getVar(install("nback"), rho, FALSE); /* → findVarInFrame(rho, "nback") */
    ndata = INTEGER(stemp);                         /* line 69 */

    return R_NilValue;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The entire compat_getVar shim, the #if R_VERSION guard, and the R_getVar macro
 * are deleted. findVarInFrame, install(), R_UnboundValue, PRINTNAME, CHAR, REAL,
 * INTEGER, and the SEXP rho/sym/val types are all removed from the C translation unit.
 *
 * The four backing arrays formerly resolved by findVarInFrame inside C are now
 * received as pre-extracted typed pointer arguments from the R caller.
 *
 * Note: expr1, expr2, and rho (the eval()-based callback machinery) cannot be
 * ported to .C at all; they must remain in a separate .Call-registered function.
 * Only the data-pointer initialisation portion of init_rpcallback is shown here.
 */

static double *ydata;
static double *wdata;
static double *xdata;
static int    *ndata;
static int     ysave;
static int     rsave;

void init_rpcallback_c(
    double *yback,  /* R: as.double(get("yback", envir=rho, inherits=FALSE)) */
    double *wback,  /* R: as.double(get("wback", envir=rho, inherits=FALSE)) */
    double *xback,  /* R: as.double(get("xback", envir=rho, inherits=FALSE)) */
    int    *nback,  /* R: as.integer(get("nback", envir=rho, inherits=FALSE)) */
    int    *ny,     /* R: as.integer(ny) */
    int    *nr      /* R: as.integer(nr) */
)
{
    /* Assign pre-extracted data pointers to module-level statics.
     * The .C dispatcher guarantees the caller's vectors are protected for
     * the duration of the call, so no PROTECT/UNPROTECT is needed. */
    ydata = yback;  /* was: ydata = REAL(findVarInFrame(rho, install("yback"))) */
    wdata = wback;  /* was: wdata = REAL(findVarInFrame(rho, install("wback"))) */
    xdata = xback;  /* was: xdata = REAL(findVarInFrame(rho, install("xback"))) */
    ndata = nback;  /* was: ndata = INTEGER(findVarInFrame(rho, install("nback"))) */
    ysave = *ny;    /* was: ysave = asInteger(ny) */
    rsave = *nr;    /* was: rsave = asInteger(nr) */

    /* void return; no R_NilValue */
}
```

- **R-side call:**

```r
## The frame-restricted environment lookups are performed in R,
## replacing findVarInFrame inside C.
## get(..., inherits = FALSE) mirrors findVarInFrame exactly:
## it searches only the immediate frame of rho, not parent environments.
## If the name is absent, get() raises a standard R error automatically,
## reproducing the R_UnboundValue guard that compat_getVar performed.

invisible(.C("init_rpcallback_c",
             yback = as.double (get("yback", envir = rho, inherits = FALSE)),
             wback = as.double (get("wback", envir = rho, inherits = FALSE)),
             xback = as.double (get("xback", envir = rho, inherits = FALSE)),
             nback = as.integer(get("nback", envir = rho, inherits = FALSE)),
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

  - `findVarInFrame(rho, sym)` — searches only the immediate frame of `rho`, returning `R_UnboundValue` if the symbol is absent. Under `.C`, replaced by `get("name", envir = rho, inherits = FALSE)` on the R side. The `inherits = FALSE` parameter maps directly to the frame-only restriction of `findVarInFrame`; no parent-environment traversal occurs in either case.

  - Argument order: `findVarInFrame` takes `(rho, sym)` — environment first, symbol second — the reverse of `findVar(sym, rho)`. This difference has no bearing on the `.C` conversion since both are replaced by `get("name", envir = rho, inherits = <bool>)`, but it is important to note when reading the original ternary `inherits ? findVar(sym, rho) : findVarInFrame(rho, sym)` to understand that both branches perform the same conceptual lookup under different scope rules.

  - `install("name")` — produces a `SEXP` of type `SYMSXP` used as the lookup key. Under `.C`, this call disappears completely; the name string is used only in the R-side `get()` call as a plain character literal.

  - `val == R_UnboundValue` — the failure sentinel check. Under `.C`, `get()` raises a standard R error automatically when the named variable is absent from the environment (or its parents, when `inherits = TRUE`), providing equivalent behavior without any C-level sentinel comparison.

  - `CHAR(PRINTNAME(sym))` — extracts the symbol's name string for the error message. Under `.C`, this is also removed: `get()` produces its own descriptive error message including the variable name, so the custom `error(_("variable '%s' not found"), ...)` call is superseded.

  - `REAL(stemp)` and `INTEGER(stemp)` — unwrap the found `SEXP` to a `double *` or `int *`. Under `.C`, the R caller applies `as.double()` or `as.integer()` before the call; the C function receives the correctly typed pointer directly, with no `SEXP stemp` intermediate.

  - The `#if R_VERSION < R_Version(4, 5, 0)` preprocessor guard, the `compat_getVar` static function, and the `#define R_getVar` macro are all deleted. The R-level `get()` function works identically across all R versions; there is no version-dependent branch under the `.C` API.

  - The function signature changes from `SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)` to `void init_rpcallback_c(double *yback, double *wback, double *xback, int *nback, int *ny, int *nr)`. The `rho`, `expr1`, and `expr2` `SEXP` arguments are omitted entirely because the `eval()`-based callbacks (`rpart_callback1`, `rpart_callback2`) that depend on them cannot be ported to `.C`; those functions must remain registered under `.Call`. See `eval.md` and `SEXP.md` for the detailed treatment of that constraint.

  - Scalar integer arguments `ny` and `nr` change from `asInteger(sexp)` to `*ny` / `*nr` because under `.C` every scalar integer arrives as a single-element `int *` array.

  - No `PROTECT` or `UNPROTECT` calls are needed: the `.C` dispatcher automatically protects all caller-supplied vectors for the duration of the call.

---

### Note on the Compatibility Shim and Version Guard

For projects that must support R < 4.5.0, the compat shim at `rpart_callback.c` lines 19–27 shows that `findVarInFrame(rho, sym)` is semantically equivalent to:

```r
get("name", envir = rho, inherits = FALSE)
```

on the R side. On R >= 4.5.0, `R_getVar(sym, rho, FALSE)` is available in the public API and calls `findVarInFrame` internally with the same frame-only restriction. Neither the pre-4.5.0 form (explicit `findVarInFrame` + `R_UnboundValue` check) nor the post-4.5.0 form (`R_getVar`) can be expressed under the `.C` API. The migration strategy — lifting the lookup to R via `get(..., inherits = FALSE)` — applies equally to both R version ranges and eliminates the need for the version guard entirely.
