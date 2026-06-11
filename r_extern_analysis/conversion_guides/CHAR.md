# Conversion Guide: `CHAR`

## 1. Overview of `CHAR` in R API

`CHAR` is a macro defined in `Rinternals.h` as `#define CHAR(x) R_CHAR(x)`, where `R_CHAR` is declared as `const char *(R_CHAR)(SEXP x)`. It accepts a `SEXP` of internal type `CHARSXP` (type code 9, the scalar string type used internally by R) and returns a read-only `const char *` pointer to the null-terminated UTF-8 (or native-encoded) C string stored inside that object. In the `.Call/.External` API it is the standard way to extract a C string from any R character object: the typical idiom is to first obtain a `CHARSXP` via `PRINTNAME(sym)` (for symbol names) or `STRING_ELT(strvec, i)` (for elements of a character vector), then call `CHAR()` on that `CHARSXP` to get the raw `const char *`. Under the `.C/.Fortran` API `CHAR` is entirely absent: character data must be pre-extracted in R and passed as `char **` or represented numerically, because `.C` functions cannot receive or manipulate `SEXP` objects.

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

`CHAR` appears at line 24 inside `compat_getVar`, a `static` helper wrapped in a `#if R_VERSION < R_Version(4, 5, 0)` preprocessor guard. The complete call chain at that line is:

```
CHAR( PRINTNAME( sym ) )
```

- `sym` — a `SEXP` of type `SYMSXP` (type code 1). It is an R symbol object created upstream by `install("varname")`.
- `PRINTNAME(sym)` — declared at line 364 of `Rinternals.h` as `SEXP (PRINTNAME)(SEXP x)`. It extracts the name field of a `SYMSXP` and returns a `SEXP` of type `CHARSXP`. This is R's internal scalar string type (type code 9), distinct from `STRSXP` (character vectors). `CHARSXP` objects are interned and read-only.
- `CHAR(...)` — accepts that `CHARSXP` and returns `const char *`, the null-terminated C string of the symbol's printed name.

The `const char *` result is used directly as the `%s` argument in an `error()` call to form a human-readable error message, e.g. `"variable 'yback' not found"`. No allocation, copying, or mutation is performed on the returned pointer.

### Data types involved

| Symbol | Type | Role |
|--------|------|------|
| `sym` | `SEXP` (`SYMSXP`) | R symbol whose name is being extracted |
| `PRINTNAME(sym)` | `SEXP` (`CHARSXP`) | internal scalar string holding the symbol's name |
| `CHAR(PRINTNAME(sym))` | `const char *` | null-terminated C string of the symbol name; passed to `error()` |

### Memory-management macros

`CHAR` does not allocate memory and does not interact with `PROTECT`/`UNPROTECT`. The `const char *` it returns points into R's internal string-interning cache and must never be freed or stored beyond the lifetime of the surrounding `.Call` frame.

### Distinct implementation patterns

There is exactly one usage pattern in this codebase: **extracting a symbol's printed name as a C string for use in a diagnostic error message**. The nested idiom `CHAR(PRINTNAME(sym))` is the canonical way to render an R symbol's name as a `const char *` inside a `.Call` C function.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under the `.C` API, a C function has no access to `SEXP` objects, `CHARSXP` values, or R's symbol table. Consequently, the full `CHAR(PRINTNAME(sym))` idiom is inapplicable because:

1. `sym` is a `SEXP` (a `SYMSXP`): `.C` functions cannot receive or hold `SEXP` arguments.
2. `PRINTNAME` is a `SEXP`-to-`SEXP` accessor from `Rinternals.h`: not available in `.C` code.
3. `CHAR` itself requires a `CHARSXP` argument: not available in `.C` code.
4. `error()` (R's C-level error reporter) is technically callable from `.C` code via `<R.h>`, but the entire surrounding function `compat_getVar` — which performs `findVar`/`findVarInFrame` against an R environment — is fundamentally incompatible with `.C` for the reasons documented in `R_UnboundValue.md`.

The conversion strategy is therefore **complete removal with uplift to R**: the `compat_getVar` shim, the `R_UnboundValue` sentinel comparison, the `CHAR(PRINTNAME(sym))` extraction, and the `error()` call are all deleted from C. The symbol-name lookup and error reporting are moved entirely to the R caller, which can access symbol names natively as R character strings.

If a `.C` function independently needs to receive a symbol name as a string (outside the context of environment lookup), the correct approach is for the R caller to pass the name as a `character(1)` argument, which `.C` delivers as `char **` with a single element. The C code then accesses the string directly as `name[0]`, requiring no `CHAR`, `PRINTNAME`, or `CHARSXP`.

### Why this ensures `.C` compatibility

The `.C` dispatcher communicates exclusively via basic C pointer types: `int *`, `double *`, `char **`, and their `const`-qualified variants. `CHAR` and `PRINTNAME` both require `SEXP` arguments, which are pointer types that live inside R's garbage-collected heap. Making those types available inside a `.C` function would require including `Rinternals.h` and calling R's object introspection API — which is permitted only in `.Call/.External` functions. Removing `CHAR(PRINTNAME(sym))` and shifting the string to the R caller as a `character(1)` argument is the only approach consistent with the `.C` API contract.

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
    /* CHAR(PRINTNAME(sym)) extracts the symbol's printed name
     * as a const char * from the CHARSXP returned by PRINTNAME */
    error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
  return val;
}
#define R_getVar(sym, rho, inherits) compat_getVar(sym, rho, inherits)
#endif

/* Downstream call site in init_rpcallback (line ~67): */
stemp = R_getVar(install("yback"), rho, FALSE);
ydata = REAL(stemp);
```

- **C/C++ Equivalent (.C):**

```c
/* The entire compat_getVar function, the R_UnboundValue comparison,
 * CHAR(PRINTNAME(sym)), and error() are all removed from C.
 *
 * No .C-compatible replacement for CHAR or PRINTNAME exists inside C.
 * The variable name string is never needed inside the C function;
 * it existed only to format a diagnostic error message.  That error
 * is now raised on the R side by get(), which produces an equivalent
 * message automatically.
 *
 * If a .C function independently needs a symbol name as a plain string
 * (not in the context of environment lookup), the R caller passes it as
 * a character(1) and the C function receives it as char **:
 */

/* Example: .C function that receives a name for logging purposes */
void example_c_func(const char **var_name,   /* character(1) from R */
                    const double *data,
                    const int    *n)
{
    /* Access the string directly — no CHAR, no PRINTNAME, no SEXP */
    const char *name = var_name[0];

    /* Use name as a plain C string */
    if (n[0] <= 0)
        /* error() from <R.h> is callable from .C, but the name string
         * is now simply a char * argument, not extracted via CHAR/PRINTNAME */
        error("variable '%s': n must be positive", name);

    /* ... rest of computation ... */
}
```

- R-side call (replacing `.Call("init_rpcallback", ...)`):

```r
# Before (.Call) — symbol lookup and error reporting happened inside C
# via findVar / R_UnboundValue / CHAR(PRINTNAME(sym)) / error()
.Call("init_rpcallback", rho, ny, nr, expr1, expr2)

# After (.C) — R performs the lookup; get() raises an R error automatically
# if the variable is absent, reproducing the original CHAR(PRINTNAME(sym))
# error message at the R level without any C-side SEXP manipulation
.C("init_rpcallback_c",
   yback = as.double(get("yback", envir = rho, inherits = FALSE)),
   wback = as.double(get("wback", envir = rho, inherits = FALSE)),
   xback = as.double(get("xback", envir = rho, inherits = FALSE)),
   nback = as.integer(get("nback", envir = rho, inherits = FALSE)),
   ny    = as.integer(ny),
   nr    = as.integer(nr))
# If "yback" (or any other variable) does not exist in rho, get() throws:
#   Error in get("yback", envir = rho, inherits = FALSE) :
#     object 'yback' not found
# — equivalent to the original error("variable '%s' not found", CHAR(PRINTNAME(sym)))

# If a .C function genuinely needs a name string as input, pass it directly:
.C("example_c_func",
   var_name = "yback",          # character(1) -> char ** in C
   data     = as.double(data),
   n        = as.integer(n))
```

- **Explanation:**

  - `CHAR(PRINTNAME(sym))` is a two-step SEXP-to-C-string conversion that requires `Rinternals.h` types (`SEXP`, `CHARSXP`) unavailable in `.C` functions. Both steps are eliminated.

  - `PRINTNAME(sym)` (line 364 of `Rinternals.h`: `SEXP (PRINTNAME)(SEXP x)`) takes a `SYMSXP` and returns the `CHARSXP` holding its printed name. This accessor has no equivalent in the `.C` world; it is replaced by R-level string handling.

  - `CHAR(charsxp)` (macro expanding to `R_CHAR(charsxp)`, declared as `const char *(R_CHAR)(SEXP x)`) unwraps a `CHARSXP` to `const char *`. Under `.C`, character data is already a `char **` argument; no unwrapping macro is needed.

  - The `error()` call that consumed the `const char *` is removed from C. The R-level `get()` function raises a standard R error with a comparable message when the variable is absent, providing equivalent user-facing diagnostics without any C involvement.

  - The `compat_getVar` compatibility shim and its `#if R_VERSION < R_Version(4, 5, 0)` guard are deleted in their entirety. The version-conditional logic was needed only because `R_getVar` (which encapsulates `findVar` + `R_UnboundValue` + the name-extraction error) was not yet public API before R 4.5.0. Under `.C`, none of that machinery exists at all.

  - If a `.C` function independently requires access to a variable name string (e.g., for logging, not for environment lookup), the R caller passes `as.character(name)` and the `.C` dispatcher delivers it as `char **name`; the C code reads `name[0]` directly — with no `CHAR`, `PRINTNAME`, `CHARSXP`, or `SEXP` involved.

  - No `PROTECT`/`UNPROTECT` changes are required because `CHAR` never allocated memory; this removal is purely a type-level transformation.
