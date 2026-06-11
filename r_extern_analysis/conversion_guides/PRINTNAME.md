# Conversion Guide: `PRINTNAME`

## 1. Overview of `PRINTNAME` in R API

`PRINTNAME` is a C-level accessor function declared in `Rinternals.h` as `SEXP (PRINTNAME)(SEXP x)`. It accepts a single `SEXP` argument of type `SYMSXP` (type code 1, an R symbol object) and returns the `CHARSXP` (type code 9, R's internal scalar string type) that holds the symbol's printed name — i.e., the human-readable identifier string such as `"yback"` or `"ncat"`. In the `.Call/.External` API, `PRINTNAME` is the canonical way to retrieve the name of an R symbol object as a `CHARSXP`; the result is immediately passed to `CHAR()` to obtain a `const char *` suitable for use in C string operations. Under the `.C/.Fortran` API, `PRINTNAME` is entirely inapplicable: `.C` functions have no access to `SEXP` objects of any kind, and the complete `CHAR(PRINTNAME(sym))` idiom must be eliminated by moving symbol-name handling to the R caller.

---

## 2. Contextual Usage Analysis

### Source location

| File | Line | Category | Context |
|------|------|----------|---------|
| `rpart_callback.c` | 24 | function | `error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));` |

### 31-line window (lines 9–39 of `rpart_callback.c`)

```c
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
static double *xdata;           /* pointer to the data portion of xback */
static double *wdata;           /* pointer to the data portion of wback */
```

### Structural role and call chain

`PRINTNAME` appears at line 24 inside `compat_getVar`, a `static` helper function wrapped in a `#if R_VERSION < R_Version(4, 5, 0)` preprocessor guard. The complete call chain at that line is:

```
CHAR( PRINTNAME( sym ) )
```

- `sym` — a `SEXP` of type `SYMSXP` (type code 1). It is an R symbol object created upstream by `install("varname")` (declared in `Rinternals.h` as `SEXP Rf_install(const char *)`). `install()` looks up or creates an interned symbol in R's global symbol table.
- `PRINTNAME(sym)` — declared at line 364 of `Rinternals.h` as `SEXP (PRINTNAME)(SEXP x)`. It accesses the name field of a `SYMSXP` and returns its `CHARSXP` — the internal, interned scalar string object (type code 9) that holds the symbol's printed name. `CHARSXP` values are read-only and interned: there is exactly one `CHARSXP` per unique string in R's string pool.
- `CHAR(PRINTNAME(sym))` — `CHAR` (a macro expanding to `R_CHAR`, declared as `const char *(R_CHAR)(SEXP x)`) accepts the `CHARSXP` and returns a `const char *` pointer to the null-terminated C string. This pointer is owned by R's internal string cache and must never be freed.

The `const char *` result is consumed directly as the `%s` argument in an `error()` call to produce a human-readable diagnostic, such as `"variable 'yback' not found"`. No allocation, copying, or mutation is performed on the returned pointer.

### Data types involved

| Symbol | Type | Role |
|--------|------|------|
| `sym` | `SEXP` (`SYMSXP`, type code 1) | R symbol whose printed name is being extracted |
| `PRINTNAME(sym)` | `SEXP` (`CHARSXP`, type code 9) | Interned scalar string holding the symbol's name |
| `CHAR(PRINTNAME(sym))` | `const char *` | Null-terminated C string of the symbol name; consumed by `error()` |

### Memory-management macros

`PRINTNAME` does not allocate memory and does not interact with `PROTECT`/`UNPROTECT`. It accesses an interned `CHARSXP` that already exists in R's string pool and is never garbage-collected as long as the corresponding symbol exists. The `const char *` returned by `CHAR()` on the result points into that pool and must not be stored beyond the lifetime of the surrounding `.Call` frame.

### Distinct implementation patterns

There is exactly one usage pattern in this codebase: **extracting an R symbol's printed name as a `const char *` for inclusion in a diagnostic error message**. The full idiom is `CHAR(PRINTNAME(sym))`, where `sym` is a `SYMSXP` created by `install()`. This pattern is part of a compatibility shim that emulates `R_getVar` (public since R 4.5.0) for older R versions.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under the `.C` API, a C function has no access to `SEXP` objects, R's symbol table, or any `Rinternals.h` types. The full `CHAR(PRINTNAME(sym))` idiom must therefore be removed entirely, for the following reasons:

1. `sym` is a `SEXP` (`SYMSXP`). The `.C` dispatcher does not accept or deliver `SEXP` arguments; only basic C pointer types (`int *`, `double *`, `char **`, etc.) are supported.
2. `PRINTNAME(sym)` is a `SEXP`-to-`SEXP` accessor from `Rinternals.h`. Including `Rinternals.h` inside a `.C` function and calling `PRINTNAME` is not a supported pattern; the entire accessor is unavailable.
3. `CHAR(charsxp)` requires a `CHARSXP` argument, which is itself a `SEXP`. With no `SEXP` available, `CHAR` cannot be called.
4. The surrounding `compat_getVar` function also calls `findVar`/`findVarInFrame` against an R environment `rho` (a `SEXP` of type `ENVSXP`) and compares the result against `R_UnboundValue` — all operations that are equally incompatible with the `.C` API (see `R_UnboundValue.md`).

The conversion strategy is **complete removal with uplift to the R caller**: the `compat_getVar` shim and everything it contains — `findVar`/`findVarInFrame`, the `R_UnboundValue` sentinel comparison, `CHAR(PRINTNAME(sym))`, and `error()` — are deleted from C. Variable existence checking and error reporting are moved to R, where `get()` natively raises an informative error when a variable is absent.

If a `.C` function independently requires a symbol name as a plain C string (in a context unrelated to environment lookup), the R caller passes the name as a `character(1)` value. The `.C` dispatcher delivers it as `char **`; the C function reads `name[0]` directly, with no `PRINTNAME`, `CHAR`, `CHARSXP`, or `SEXP` involved.

### Why this ensures `.C` compatibility

The `.C` dispatcher communicates exclusively through basic C pointer types. `PRINTNAME` requires a `SYMSXP` input and returns a `CHARSXP` — both are `SEXP` subtypes that live in R's garbage-collected heap and are manipulated through `Rinternals.h` accessors. Making those types available inside a `.C` function would require bypassing the dispatcher's type contract. Removing `PRINTNAME` and `CHAR` and shifting symbol-name information to the R caller as a `character(1)` argument is the only approach that is fully compatible with the `.C` API contract.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Symbol Name Extraction for Diagnostic Error Message

- **Locations:** `rpart_callback.c`, line 24 (inside `compat_getVar`, lines 19–28)

- **Original Context (.Call):**

```c
/* rpart_callback.c:18-28 — compatibility shim for R < 4.5.0 */
#if R_VERSION < R_Version(4, 5, 0)
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
  SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
  if (val == R_UnboundValue)
    /* PRINTNAME(sym) returns the CHARSXP holding the symbol's printed name;
     * CHAR() unwraps it to const char * for use in the error message */
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif

/* Downstream call site (rpart_callback.c ~line 67):
 * install("yback") creates a SYMSXP; compat_getVar looks it up in rho */
stemp = R_getVar(install("yback"), rho, FALSE);
ydata = REAL(stemp);
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The entire compat_getVar function — including PRINTNAME(sym),
 * CHAR(), findVar/findVarInFrame, R_UnboundValue, and error() —
 * is removed from C. No .C-compatible replacement exists for
 * PRINTNAME or CHAR inside a .C function.
 *
 * The .C function receives pre-extracted data arrays directly.
 * Variable existence is verified on the R side before the .C call.
 * No symbol name extraction is needed inside C.
 */
void rpcallback_c(const double *yback,   /* data array, pre-extracted in R */
                  const double *xback,
                  const double *wback,
                  const int    *nback,
                  const int    *ny,
                  const int    *nr)
{
    /* Work directly with the raw pointers — no SEXP, no PRINTNAME,
     * no CHAR, no findVar, no R_UnboundValue */
    ysave = ny[0];
    rsave = nr[0];
    /* ... rest of initialization ... */
}

/* If a .C function independently needs to receive a variable name
 * as a string (e.g., for logging), the R caller passes character(1)
 * and the C function accesses it via char **: */
void example_with_name(const char **var_name,  /* character(1) from R */
                       const double *data,
                       const int    *n)
{
    /* var_name[0] is the plain C string — no PRINTNAME, no CHAR, no SEXP */
    const char *name = var_name[0];
    if (n[0] <= 0)
        error("variable '%s': n must be positive", name);
    /* ... */
}
```

- R-side call replacing `.Call("init_rpcallback", ...)`:

```r
# Before (.Call): symbol lookup and error reporting happened inside C
# via install() / findVar() / CHAR(PRINTNAME(sym)) / error()
.Call("init_rpcallback", rho, ny, nr, expr1, expr2)

# After (.C): R performs the lookup with get(); if a variable is absent,
# get() raises an R error automatically — equivalent to the original
# CHAR(PRINTNAME(sym)) diagnostic — with no C-side SEXP manipulation
.C("rpcallback_c",
   yback = as.double(get("yback", envir = rho, inherits = FALSE)),
   xback = as.double(get("xback", envir = rho, inherits = FALSE)),
   wback = as.double(get("wback", envir = rho, inherits = FALSE)),
   nback = as.integer(get("nback", envir = rho, inherits = FALSE)),
   ny    = as.integer(ny),
   nr    = as.integer(nr))
# If "yback" is absent from rho, get() raises:
#   Error in get("yback", envir = rho, inherits = FALSE) :
#     object 'yback' not found
# This is equivalent to the original:
#   error("variable '%s' not found", CHAR(PRINTNAME(install("yback"))))

# If a .C function genuinely needs a symbol name string as an argument:
.C("example_with_name",
   var_name = "yback",          # character(1) -> char ** in C
   data     = as.double(data),
   n        = as.integer(length(data)))
```

- **Explanation:**

  - `PRINTNAME(sym)` (declared in `Rinternals.h` line 364 as `SEXP (PRINTNAME)(SEXP x)`) is a `SEXP`-to-`SEXP` accessor that extracts the name field from a `SYMSXP`. Because the `.C` API provides no mechanism to pass or receive `SEXP` values, `PRINTNAME` has no equivalent inside a `.C` function and is removed entirely.

  - `CHAR(PRINTNAME(sym))` is a two-step unwrapping idiom. `PRINTNAME` converts `SYMSXP` to `CHARSXP`; `CHAR` (expanding to `R_CHAR`, declared as `const char *(R_CHAR)(SEXP x)`) converts `CHARSXP` to `const char *`. Under `.C`, character data arrives already as `char **` from the R caller; neither step is needed or permissible.

  - The `compat_getVar` compatibility shim (lines 19–28) is removed in its entirety. It existed solely because `R_getVar` was not a public API before R 4.5.0. Under `.C`, the environment-lookup machinery (`findVar`, `findVarInFrame`, `R_UnboundValue`, `R_getVar`) is irrelevant; the R caller extracts data from the environment before the `.C` call using `get()`.

  - R's `get(name, envir = rho, inherits = FALSE)` produces an error message — `object 'yback' not found` — that is functionally equivalent to the original `error("variable '%s' not found", CHAR(PRINTNAME(sym)))`, preserving user-facing diagnostic quality without any C involvement.

  - When a `.C` function independently needs a variable name as a plain string (not for environment lookup), the R caller passes `as.character(name)` and the `.C` dispatcher delivers it as `char **`; the C code reads `name[0]` directly. This requires no `PRINTNAME`, `CHAR`, `CHARSXP`, or any other `SEXP`-based accessor.

  - No `PROTECT`/`UNPROTECT` adjustments are required for this conversion: `PRINTNAME` never allocated memory. The removal is a pure type-level transformation — eliminating `SEXP` accessors that have no analogue in the `.C` API.
