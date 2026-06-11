# Conversion Guide: `install`

## 1. Overview of `install` in R API

`install` is a macro defined in `Rinternals.h` as `#define install Rf_install`, aliasing the C function declared as `SEXP Rf_install(const char *name)`. It accepts a null-terminated C string and looks up or creates a unique, garbage-collector-protected symbol object (`SEXP` of type `SYMSXP`, type code 1) in R's global symbol table (the symbol interning table). Because the table is deduplicated, calling `install("yback")` any number of times always returns the same `SEXP` pointer for the lifetime of the R session, making the result safe to store and compare by identity. The returned `SYMSXP` is the canonical input to environment-lookup functions such as `findVarInFrame`, `findVar`, and `R_getVar`, which use it to identify a named binding within an R environment. Under the `.C/.Fortran` API, `install` is entirely inapplicable: `.C` functions have no access to `SEXP` objects of any kind, and every use of `install` must be eliminated by moving the string-to-symbol conversion (i.e., the variable name lookup) to the R caller.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart_callback.c` | 59 | `stemp = R_getVar(install("yback"), rho, FALSE);` |
| `rpart_callback.c` | 62 | `stemp = R_getVar(install("wback"), rho, FALSE);` |
| `rpart_callback.c` | 65 | `stemp = R_getVar(install("xback"), rho, FALSE);` |
| `rpart_callback.c` | 68 | `stemp = R_getVar(install("nback"), rho, FALSE);` |

All four calls reside inside the single function `init_rpcallback` (lines 47–72 of `rpart_callback.c`).

### 31-line window (lines 44–74 of `rpart_callback.c`)

```c
 *   of the evaluation frame and the 2 expressions to be computed within it,
 *   and away the memory location of the 4 "callback" objects.
 */
SEXP
init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;

    rho   = rhox;
    ysave = asInteger(ny);
    rsave = asInteger(nr);
    expr1 = expr1x;
    expr2 = expr2x;

    stemp = R_getVar(install("yback"), rho, FALSE);
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

### Types and variables involved

| Symbol | Type | Role |
|--------|------|------|
| `"yback"`, `"wback"`, `"xback"`, `"nback"` | `const char *` | Literal C strings passed as the sole argument to `install` |
| `install("yback")` etc. | `SEXP` (`SYMSXP`, type code 1) | Interned R symbol; used as the lookup key for `R_getVar` |
| `rho` | `SEXP` (`ENVSXP`) | Module-level static R environment; target of the symbol lookup |
| `stemp` | `SEXP` | Local temporary holding the found R object before pointer extraction |
| `ydata`, `wdata`, `xdata` | `double *` | Module-level statics; receive `REAL(stemp)` for three of the four lookups |
| `ndata` | `int *` | Module-level static; receives `INTEGER(stemp)` for the `"nback"` lookup |

### Compatibility shim interaction

`rpart_callback.c` lines 19–28 define a compatibility shim for R < 4.5.0. The shim makes `R_getVar` available on older R versions by routing through `findVarInFrame(rho, sym)`, where `sym` is the `SYMSXP` produced by `install`. When the lookup fails, `CHAR(PRINTNAME(sym))` recovers the original name string from the symbol for the error message:

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

This reveals the full operational role of `install`: it converts a plain C string into the interned `SYMSXP` that both `R_getVar` (R >= 4.5.0) and `findVarInFrame` (via the shim on older R) require as their lookup key. `CHAR(PRINTNAME(sym))` performs the reverse conversion — recovering the C string from the symbol — for diagnostic purposes.

### Memory management

`install` does not allocate a new `SEXP` on every call. It returns a pointer to a pre-existing, interned symbol in R's global symbol table. Interned symbols are permanently rooted and are never garbage-collected. No `PROTECT`/`UNPROTECT` calls are needed around `install`'s return value.

### Distinct implementation patterns

There is exactly one functional pattern in the CSV data:

**Pattern: Convert a literal C string to an interned R symbol (`SYMSXP`) for immediate use as the lookup key in `R_getVar`.**

All four calls are structurally identical; they differ only in the string literal passed (`"yback"`, `"wback"`, `"xback"`, `"nback"`) and in the downstream accessor applied to the found `SEXP` (`REAL` for three, `INTEGER` for one).

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`install` serves exclusively as a bridge from a C string to the `SEXP`-typed symbol that R's environment-lookup functions require. Under the `.C` API:

1. **No `SEXP` arguments or return values.** The `.C` dispatcher communicates exclusively through basic C pointer types (`int *`, `double *`, `char **`). A `SYMSXP` produced by `install` cannot be passed to or from a `.C` function.

2. **No runtime environment lookup from C.** `R_getVar`, `findVarInFrame`, and `findVar` — the only consumers of the `SYMSXP` that `install` produces — all require an `SEXP` environment handle (`rho`) which is equally unavailable under `.C`.

3. **`install` has no `.C`-compatible equivalent.** The function's sole purpose is to produce a `SYMSXP` for R's internal environment machinery. Once that machinery is removed, `install` itself has nothing to do.

### Conversion strategy: lift all lookups to R

The entire chain `install("name") → R_getVar(...) → REAL/INTEGER(stemp)` is replaced by performing the environment lookup in R **before** the `.C` call. The R caller uses `get("name", envir = rho, inherits = FALSE)` — which maps precisely to `findVarInFrame(rho, install("name"))` — to retrieve each backing vector and passes the resulting typed array as a plain C pointer argument. The C function receives pre-extracted `double *` or `int *` values directly, with no `install`, no symbol table, and no `SEXP` of any kind.

### Type mapping

| `.Call` construct | `.C` equivalent |
|-------------------|-----------------|
| `install("yback")` | Eliminated; name string used only in R-side `get("yback", ...)` |
| `R_getVar(install("yback"), rho, FALSE)` | `get("yback", envir = rho, inherits = FALSE)` on R side |
| `SEXP stemp` (temporary result holder) | Eliminated; result flows directly into `as.double()`/`as.integer()` in R |
| `REAL(stemp)` | `as.double(...)` in R; arrives in C as `double *` |
| `INTEGER(stemp)` | `as.integer(...)` in R; arrives in C as `int *` |
| `static SEXP rho` (module-level environment) | Eliminated; lookup performed in R before the `.C` call |
| Error via `CHAR(PRINTNAME(sym))` | Superseded by `get()`'s built-in error when name is absent |

This approach is fully `.C`-compatible because it removes every `SEXP`-typed object from the C translation unit. The string-to-symbol conversion that `install` performs is implicitly handled on the R side by `get()`, which takes a plain character string as its first argument.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Convert C String to R Symbol as Environment-Lookup Key

- **Locations:** `rpart_callback.c` lines 59, 62, 65, 68

- **Original Context (.Call):**

```c
/* rpart_callback.c:47-72
 *
 * install("name") converts a C string literal to an interned SYMSXP.
 * That SYMSXP is the required argument type for R_getVar and findVarInFrame.
 * Without install(), there is no way to identify the binding to look up.
 */

static SEXP rho;            /* module-level R environment (ENVSXP) */
static double *ydata;
static double *wdata;
static double *xdata;
static int    *ndata;

SEXP
init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;

    rho   = rhox;
    ysave = asInteger(ny);
    rsave = asInteger(nr);
    expr1 = expr1x;
    expr2 = expr2x;

    /* install("yback") → SYMSXP lookup key
     * R_getVar(sym, rho, FALSE) → findVarInFrame(rho, sym) + error on miss
     * REAL(stemp) → double * data pointer */
    stemp = R_getVar(install("yback"), rho, FALSE);
    ydata = REAL(stemp);                            /* line 60 */

    stemp = R_getVar(install("wback"), rho, FALSE);
    wdata = REAL(stemp);                            /* line 63 */

    stemp = R_getVar(install("xback"), rho, FALSE);
    xdata = REAL(stemp);                            /* line 66 */

    /* "nback" holds an integer vector: INTEGER() instead of REAL() */
    stemp = R_getVar(install("nback"), rho, FALSE);
    ndata = INTEGER(stemp);                         /* line 69 */

    return R_NilValue;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * install(), R_getVar(), REAL(), INTEGER(), the SEXP stemp intermediate,
 * and the static SEXP rho environment handle are all removed.
 *
 * The four backing arrays are received as typed pointer arguments.
 * The R caller performs the environment lookups using get() before
 * invoking .C, so no string-to-symbol conversion is needed in C.
 *
 * Note: expr1, expr2, rho, and the eval()-based callbacks
 * (rpart_callback1, rpart_callback2) cannot be ported to .C.
 * Those must remain as separate .Call-registered functions.
 */

static double *ydata;
static double *wdata;
static double *xdata;
static int    *ndata;
static int     ysave;
static int     rsave;

void init_rpcallback_c(
    double *yback,  /* was: REAL(R_getVar(install("yback"), rho, FALSE)) */
    double *wback,  /* was: REAL(R_getVar(install("wback"), rho, FALSE)) */
    double *xback,  /* was: REAL(R_getVar(install("xback"), rho, FALSE)) */
    int    *nback,  /* was: INTEGER(R_getVar(install("nback"), rho, FALSE)) */
    int    *ny,     /* was: asInteger(ny)  — scalar as single-element int * */
    int    *nr      /* was: asInteger(nr)  — scalar as single-element int * */
)
{
    /* Assign pre-extracted pointers to module-level statics.
     * No install(), no R_getVar(), no SEXP of any kind. */
    ydata = yback;
    wdata = wback;
    xdata = xback;
    ndata = nback;
    ysave = *ny;    /* scalar int: dereference the single-element array */
    rsave = *nr;

    /* void return; no R_NilValue */
}
```

- **R-side call:**

```r
## The R caller performs the environment lookups that install() + R_getVar()
## previously performed inside C.
##
## get("yback", envir = rho, inherits = FALSE) is semantically identical to
## findVarInFrame(rho, install("yback")):
##   - searches only the immediate frame of rho (inherits = FALSE)
##   - raises a standard R error if "yback" is absent
##     (equivalent to the CHAR(PRINTNAME(sym)) error in compat_getVar)
##
## as.double() / as.integer() replaces REAL(stemp) / INTEGER(stemp).

invisible(.C("init_rpcallback_c",
             yback = as.double (get("yback", envir = rho, inherits = FALSE)),
             wback = as.double (get("wback", envir = rho, inherits = FALSE)),
             xback = as.double (get("xback", envir = rho, inherits = FALSE)),
             nback = as.integer(get("nback", envir = rho, inherits = FALSE)),
             ny    = as.integer(ny),
             nr    = as.integer(nr)))
```

- **Registration entry:**

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
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c, 6,
     init_rpcallback_c_types},
    {NULL, NULL, 0, NULL}
};
```

- **Explanation:**

  - `install("yback")` (declared in `Rinternals.h` as `SEXP Rf_install(const char *)`) converts the C string `"yback"` to an interned `SYMSXP` — R's internal, GC-rooted symbol object. This symbol is the mandatory argument type for `R_getVar`, `findVarInFrame`, and `findVar`. Under the `.C` API there are no `SEXP` arguments of any kind, so the `SYMSXP` produced by `install` has no place in the function's argument list. `install` is therefore removed entirely.

  - The role that `install("name")` served — identifying which binding to retrieve — is taken over by the plain string literal `"name"` in the R-side `get("name", envir = rho, inherits = FALSE)` call. R's `get` function accepts a `character(1)` string directly without requiring a pre-interned symbol object.

  - `R_getVar(install("yback"), rho, FALSE)` is precisely equivalent (including on R < 4.5.0 via the compat shim) to `findVarInFrame(rho, install("yback"))` — a frame-only lookup that raises an error on miss. The R-side `get("yback", envir = rho, inherits = FALSE)` replicates the same semantics: it searches only the immediate frame of `rho` and raises a standard R error (`object 'yback' not found`) when the variable is absent, superseding the explicit `CHAR(PRINTNAME(sym))` error message from the C shim.

  - `SEXP stemp` — the local temporary that held the `SEXP` returned by `R_getVar` before it was unwrapped by `REAL(stemp)` or `INTEGER(stemp)` — disappears entirely. Under `.C`, `as.double()` and `as.integer()` perform the type coercion on the R side, and the resulting typed arrays are delivered directly as `double *` and `int *` arguments.

  - `static SEXP rho` — the module-level environment handle — is not passed to the `.C` function. All four lookups that required `rho` are performed in R before the call, so C never needs to hold a reference to the environment.

  - The `#if R_VERSION < R_Version(4, 5, 0)` preprocessor guard, the `compat_getVar` static function, and the `#define R_getVar` macro shim are deleted in their entirety. The R-side `get(..., inherits = FALSE)` function works identically across all R versions; no version-conditional branch is needed under the `.C` API.

  - `asInteger(ny)` and `asInteger(nr)` become `*ny` and `*nr` because under `.C` scalar integers arrive as single-element `int *` arrays; the scalar value is obtained by dereferencing the pointer.

  - The function return type changes from `SEXP` (returning `R_NilValue`) to `void`. The `.C` API does not support return values; the R caller receives the modified argument list instead. `invisible()` suppresses the printing of that list.

  - No `PROTECT`/`UNPROTECT` calls are needed. `install` never required protection (interned symbols are permanently rooted), and the `.C` dispatcher automatically protects all caller-supplied vectors for the duration of the call.

---

### Note on the Compatibility Shim

For projects that must support R < 4.5.0, the compat shim at `rpart_callback.c` lines 19–27 shows that `install("name")` is used solely to produce the `SYMSXP` key for `findVarInFrame` or `findVar`. On R >= 4.5.0, `R_getVar` accepts the same `SYMSXP` from `install` directly. In both cases, `install` plays an identical role: C-string to SYMSXP conversion. The `.C` migration eliminates this conversion in both R version ranges by moving it to the R side, where `get("name", envir = rho, inherits = FALSE)` takes a plain string argument and no symbol-interning step is exposed to the caller.
