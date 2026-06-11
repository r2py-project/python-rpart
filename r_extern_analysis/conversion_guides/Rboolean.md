# Conversion Guide: `Rboolean`

## 1. Overview of `Rboolean` in R API

`Rboolean` is a C enumeration type defined in `R_ext/Boolean.h` (included
transitively by `R.h`) as `typedef enum { FALSE = 0, TRUE } Rboolean;`. On
platforms whose C compiler supports a fixed enum base type (i.e. where
`HAVE_ENUM_BASE_TYPE` is defined), the underlying type is explicitly `int`; on
all other standard C99+ platforms the base type resolves to `int` by default
because `stdbool.h` is included and the enum values are within `int` range. Its
role is to express a two-valued boolean flag (no `NA`) in `.Call`/`.External`
function signatures, replacing raw `int` flags with a self-documenting type that
R's C API uses pervasively — for example as the `inherits` parameter to
`R_getVar`, the `from_last` parameter to `Rf_any_duplicated`, and the argument
type of many `Rf_is*` predicate functions declared in `Rinternals.h`.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart_callback.c` | 20 | `static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)` |

### How `Rboolean` is used in this file

The single occurrence is the parameter type for `inherits` in the static
compatibility shim `compat_getVar`, which is compiled only when
`R_VERSION < R_Version(4, 5, 0)` (i.e., before `R_getVar` was added to the
public API in R 4.5.0). At line 22 the parameter is used as a C boolean
expression in a ternary:

```c
SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
```

Callers pass the R-level constants `FALSE` and `TRUE` (e.g.,
`R_getVar(install("yback"), rho, FALSE)` at line 59), which after macro
expansion become the `Rboolean` enum values `0` and `1`.

### Key observations

- `Rboolean` is used exclusively as a **function parameter type** — it is never
  allocated, stored in a `SEXP`, or returned from a function in this file.
- Its underlying storage type is `int` on all practically relevant platforms,
  meaning it is ABI-compatible with `int`.
- The entire function that uses `Rboolean` (`compat_getVar`) is itself part of
  the `.Call` infrastructure: it operates on `SEXP` arguments and returns a
  `SEXP`. It is not directly callable from `.C`.
- The function is conditionally compiled — it exists only as a backward-compat
  shim for R < 4.5.0; on R >= 4.5.0 the built-in `R_getVar` (declared in
  `Rinternals.h` as `SEXP R_getVar(SEXP, SEXP, Rboolean)`) is used instead.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

The `.C` API accepts only basic C pointer types. `Rboolean` itself is not a
`.C`-compatible type by name, but because its underlying representation is
`int`, a `Rboolean`-typed parameter maps directly to an `int *` (scalar passed
by pointer) under `.C`. The R documentation states: _"logical values are sent as
`0` (`FALSE`) or `1` (`TRUE`)"_ and the corresponding C type for an R `logical`
vector is `int *`.

There are two distinct conversion scenarios:

1. **The entire enclosing `.Call` function is being rewritten as a `.C`
   function.** In that case, any `Rboolean` parameter is replaced by `int *`
   (a scalar pointer), the `SEXP` arguments are removed, and the function
   becomes `void`-returning.

2. **`Rboolean` appears only in an internal helper called from the `.Call`
   layer.** The helper can be rewritten with a plain `int` (or `int *`) flag,
   keeping the same logic but removing all R-API-specific types. This is the
   correct strategy for `compat_getVar` in `rpart_callback.c`: because the
   function also takes `SEXP` arguments (`sym`, `rho`) and calls `findVar` /
   `findVarInFrame`, a full `.C` migration requires replacing the entire
   environment-lookup idiom with pre-computed data passed in as raw C arrays,
   not just substituting `Rboolean` for `int`.

### Type mapping

| `.Call` type | `.C` C type | R-side type |
|---|---|---|
| `Rboolean` (parameter) | `int *` (scalar pointer) | `logical(1)` |
| `Rboolean` (local flag) | `int` | n/a (internal only) |

The C constants `FALSE` and `TRUE` (from `<stdbool.h>` / `Boolean.h`) are
replaced by the integer literals `0` and `1`, or by `false` / `true` from
standard C99 `<stdbool.h>` without any R headers.

---

## 4. Step-by-Step Conversion Examples

### Pattern: `Rboolean` as a Function Parameter in a `.Call` Helper

- **Locations:** `rpart_callback.c` line 20

- **Original Context (.Call):**

```c
/* rpart_callback.c:18-28 — compiled only for R < 4.5.0 */
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

/* Called at lines 59-68 with Rboolean constant FALSE: */
stemp = R_getVar(install("yback"), rho, FALSE);
ydata = REAL(stemp);
```

The function performs an R environment lookup, which is inherently a
`.Call`-level operation: it requires `SEXP` environment objects and returns a
`SEXP`.

- **C/C++ Equivalent (.C):**

Under the `.C` API, R-level environment lookups (`findVar`, `findVarInFrame`)
are not performed inside the C code at all. The data that was retrieved from the
environment (`yback`, `wback`, `xback`, `nback`) must instead be passed as
pre-allocated raw C arrays from R. The `compat_getVar` helper and the
`Rboolean`-typed `inherits` parameter are therefore eliminated entirely.

```c
/*
 * .C-compatible replacement for init_rpcallback.
 *
 * All four environment variables (yback, wback, xback, nback) are passed
 * directly as typed pointers instead of being looked up via findVar.
 * Rboolean is not present anywhere in this interface.
 */
void init_rpcallback_c(
    const int    *ny,        /* scalar: number of y columns (was asInteger(ny))  */
    const int    *nr,        /* scalar: length of returned "mean" vector         */
    const double *yback,     /* pre-allocated double vector (was REAL(stemp))    */
    const double *wback,     /* pre-allocated double vector                      */
    const double *xback,     /* pre-allocated double vector                      */
    const int    *nback      /* pre-allocated int vector                         */
)
{
    ysave = *ny;
    rsave = *nr;

    /* Store raw pointers; no SEXP, no findVar, no Rboolean */
    ydata = (double *) yback;
    wdata = (double *) wback;
    xdata = (double *) xback;
    ndata = (int *)    nback;
}
```

Corresponding R-side call:

```r
# All data is prepared in R and passed directly — no environment lookup in C
.C("init_rpcallback_c",
   ny    = as.integer(ny),
   nr    = as.integer(nr),
   yback = as.double(yback_vec),   # length ny * nobs
   wback = as.double(wback_vec),   # length nobs
   xback = as.double(xback_vec),   # length nobs * ncols
   nback = integer(1L))            # length-1 scratch integer
```

- **Explanation:**
  - `Rboolean inherits` is eliminated completely. It was only needed to select
    between `findVar` (inheriting lookup) and `findVarInFrame` (frame-only
    lookup). Under `.C`, no environment lookup occurs in C; R passes the data
    directly, so the distinction is irrelevant.
  - `SEXP sym`, `SEXP rho`, `findVar`, `findVarInFrame`, `R_UnboundValue`,
    `CHAR(PRINTNAME(...))`, and `error(...)` are all removed — they are all
    `.Call`-layer constructs with no `.C` equivalents.
  - `Rboolean` (the type) can be replaced by `int` wherever a boolean flag must
    be kept as an internal C variable; the values `FALSE`/`TRUE` become `0`/`1`
    or standard C99 `false`/`true` from `<stdbool.h>`.
  - The `#if R_VERSION < R_Version(4, 5, 0)` compatibility guard is no longer
    needed because the `.C` interface does not call `R_getVar` at all.

---

### Pattern: `Rboolean` Replaced by `int` in an Internal-Only Flag

This pattern applies whenever `Rboolean` is used as a **local variable** or
**return type** of a purely internal C function that does not touch `SEXP`
objects and can therefore be straightforwardly ported.

- **Locations:** Not present in the CSV, but documented here as the general
  case for completeness.

- **Original Context (.Call):**

```c
#include <Rinternals.h>   /* provides Rboolean */

static Rboolean is_valid(int x)
{
    return (x > 0) ? TRUE : FALSE;
}
```

- **C/C++ Equivalent (.C):**

```c
#include <stdbool.h>  /* provides bool, true, false — no R headers needed */

/* Option A: use standard C99 bool */
static bool is_valid(int x)
{
    return x > 0;
}

/* Option B: use plain int (maximally portable, matches .C logical mapping) */
static int is_valid(int x)
{
    return x > 0;   /* 1 == TRUE, 0 == FALSE — matches .C logical convention */
}
```

- **Explanation:**
  - `Rboolean` is a typedef for `enum { FALSE = 0, TRUE }` whose base type is
    `int`. Under `.C`, R logical vectors are passed as `int *` with values `0`
    (false) and `1` (true). Both representations are identical at the bit level.
  - Option A (`bool`) is idiomatic modern C99/C11 and avoids any R headers in
    purely computational code.
  - Option B (`int`) is the safest choice when the value will ultimately be
    written into or read from a `.C` `logical` argument, because the `.C` ABI
    explicitly specifies `int *` for logical data.
  - The constants `FALSE` and `TRUE` (from `Boolean.h`) are replaced by `0`
    and `1`, or by `false` and `true` from `<stdbool.h>`, depending on which
    header set is retained after the migration.
  - No `PROTECT`/`UNPROTECT` or memory management changes are required because
    `Rboolean` itself never involves heap allocation.
