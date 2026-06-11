# Conversion Guide: `TRUE`

## 1. Overview of `TRUE` in R API

`TRUE` is a named integer constant with value `1`, defined as a member of the
`Rboolean` enumeration in `R_ext/Boolean.h`:

```c
typedef enum { FALSE = 0, TRUE } Rboolean;
```

The header is included transitively by `R.h` and `Rinternals.h`. On compilers
that support a fixed enum base type (`HAVE_ENUM_BASE_TYPE` defined), the
underlying type is explicitly `int`; on all standard C99+ platforms the base
type resolves to `int` by default. `TRUE` is used wherever a `Rboolean`-typed
boolean flag argument is required by R's C API — most commonly as the `value`
argument to `R_forceSymbols` and `R_useDynamicSymbols` (shared-library
registration policy) and as the `inherits` argument to `R_getVar` (controlling
whether an environment lookup should search parent frames). It carries no
heap-allocated memory, requires no `PROTECT`/`UNPROTECT` treatment, and
imposes no GC interaction.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `init.c` | 28 | `R_forceSymbols(dll, TRUE);` |

### 31-line window analysis (`init.c`, lines 13–30)

The full `init.c` file is 30 lines. The complete listing around the target line:

```c
#include "rpart.h"
#include "R_ext/Rdynload.h"
#include "node.h"
#include "rpartproto.h"

SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x);
SEXP rpartexp2(SEXP dtimes, SEXP seps);
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
        SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
        SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2);

static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart",           (DL_FUNC) &rpart,            11},
    {"xpred",           (DL_FUNC) &xpred,            15},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,          2},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,        12},
    {NULL, NULL, 0}
};

#include <Rversion.h>
void
R_init_rpart(DllInfo * dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);           /* line 26 */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);                 /* line 28 — target */
#endif
}
```

### Pattern — DLL registration flag (`init.c` line 28)

`R_forceSymbols(dll, TRUE)` is called inside the package's `R_init_rpart`
entry point, which R invokes automatically when the shared library is loaded
via `library()`. The function is declared in `R_ext/Rdynload.h` as:

```c
Rboolean R_forceSymbols(DllInfo *info, Rboolean value);
```

Passing `TRUE` (value `1`) instructs R to require that every `.Call` or
`.C` invocation targeting this package must use the registered
`R_CallMethodDef` / `R_CMethodDef` objects (i.e., `PACKAGE = "rpart"` with
an object handle), rather than a plain character string for symbol lookup.
This is a security and correctness best practice that prevents dynamic
symbol resolution by name.

The `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` guard
wrapping the call means it is compiled only on R 2.16.0 and later, where
`R_forceSymbols` exists in the API.

The companion call on the immediately preceding line is:
```c
R_useDynamicSymbols(dll, FALSE);
```
which disables resolution of unregistered symbols. Together, these two calls
enforce strict symbol-registration policy for the package DLL.

### Key observations

- `TRUE` is used purely as a **compile-time integer literal** (value `1`)
  passed as a flag argument to an R infrastructure API function. It is never
  stored in a `SEXP`, never allocated on the R heap, and never
  garbage-collected.
- The call site (`R_forceSymbols`) is a DLL-registration function, not a
  computational kernel. It is part of the `.Call`-layer initialization pathway
  and does not appear inside any function body that would be migrated to the
  `.C` API.
- The return value of `R_forceSymbols` (a `Rboolean`) is discarded here, as
  is conventional for this registration idiom.
- The companion guides `FALSE.md`, `Rboolean.md`, and `DllInfo.md` cover the
  surrounding constructs (`R_useDynamicSymbols`, `Rboolean`, and `DllInfo *`)
  in detail.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_forceSymbols(dll, TRUE)` lives in `R_init_<pkg>`, which is a DLL-
registration hook executed by R's dynamic loader — not by any user-callable
`.C` or `.Call` function. Consequently:

1. **This call is not migrated.** When a package migrates its computational
   kernels from `.Call` to `.C`, the `R_init_<pkg>` function and its
   `R_forceSymbols(dll, TRUE)` line remain **unchanged**. The only required
   change in `R_init_rpart` is replacing the `R_CallMethodDef` registration
   table with an `R_CMethodDef` table (see the `DllInfo.md` and
   `R_CallMethodDef.md` companion guides).

2. **`TRUE` as a general internal C boolean.** If `TRUE` appears in a purely
   computational C function that is being ported away from all R headers, the
   symbol is no longer in scope (because `Boolean.h` is no longer included).
   The direct replacement is the integer literal `1`, or `true` from standard
   C99 `<stdbool.h>`. The `.C` API specification states: _"logical values are
   sent as `0` (`FALSE`) or `1` (`TRUE`)"_ — so the integer `1` is the exact,
   zero-dependency representation for a true logical value crossing the `.C`
   boundary.

### Type mapping

| `.Call` construct | Role of `TRUE` | `.C` equivalent |
|---|---|---|
| `R_forceSymbols(dll, TRUE)` | Enforces registered-symbol-only lookup | Not migrated; stays verbatim in `R_init_<pkg>` |
| `R_useDynamicSymbols(dll, TRUE)` | Enables dynamic symbol resolution (hypothetical) | Not migrated; stays verbatim in `R_init_<pkg>` |
| `R_getVar(sym, rho, TRUE)` | Inheriting environment lookup | Eliminated; data passed as `double *` / `int *` argument |
| `Rboolean` local flag set to `TRUE` | Internal C boolean | `int` initialized to `1`, or `true` from `<stdbool.h>` |

---

## 4. Step-by-Step Conversion Examples

### Pattern: DLL Registration Flag (`R_forceSymbols`)

- **Locations:** `init.c` line 28

- **Original Context (.Call):**

```c
/* init.c — R_init_rpart, the DLL load hook */
#include "R_ext/Rdynload.h"
#include <Rversion.h>

static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart",           (DL_FUNC) &rpart,            11},
    {"xpred",           (DL_FUNC) &xpred,            15},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,          2},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,        12},
    {NULL, NULL, 0}
};

void
R_init_rpart(DllInfo * dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);    /* TRUE: forbid character-name symbol lookup */
#endif
}
```

- **C/C++ Equivalent (.C):**

When migrating computational kernels to `.C`, the DLL registration hook is
updated to register the new `.C` methods in an `R_CMethodDef` table. The
`R_forceSymbols(dll, TRUE)` call is **retained as-is** — it is not part of
any `.C` function signature, and `TRUE` here is simply the integer `1` passed
to an R internal API function that is agnostic to `.Call` vs. `.C`.

```c
/* init.c — updated to register .C methods alongside (or instead of) .Call */
#include "R_ext/Rdynload.h"
#include <Rversion.h>

/*
 * .C method table — replaces (or augments) CallEntries.
 * Each entry lists: name, function pointer, argument count, type array.
 * Pass NULL for the types field to skip per-argument type checking.
 */
static const R_CMethodDef CEntries[] = {
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c,  6, NULL},
    {"rpart_c",           (DL_FUNC) &rpart_c,            11, NULL},
    {"xpred_c",           (DL_FUNC) &xpred_c,            15, NULL},
    {"rpartexp2_c",       (DL_FUNC) &rpartexp2_c,         4, NULL},
    {"pred_rpart_c",      (DL_FUNC) &pred_rpart_c,       13, NULL},
    {NULL, NULL, 0, NULL}
};

void
R_init_rpart(DllInfo * dll)
{
    /* .C table in first slot (croutines); .Call slot is now NULL */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);          /* unchanged */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);               /* unchanged: still 1 / TRUE */
#endif
}
```

- **Explanation:**
  - `TRUE` in `R_forceSymbols(dll, TRUE)` is a `Rboolean` enum value that
    resolves to the integer `1`. The function is part of R's shared-library
    infrastructure API (`R_ext/Rdynload.h`), not of any `.Call`/`.C`
    computational interface.
  - Migrating kernels to `.C` does not require touching this line. The call
    enforces registered-symbol-only lookup regardless of whether the registered
    routines use `.Call` or `.C` — the flag is API-agnostic.
  - If `TRUE` were to be replaced for complete header independence in this
    file, `1` is the exact integer substitute. In practice `init.c` always
    includes R headers (`R_ext/Rdynload.h` pulls in `Boolean.h`), so `TRUE`
    is always available and should be kept for readability.
  - The only meaningful change when adopting `.C` is replacing
    `R_CallMethodDef` with `R_CMethodDef` for the newly ported functions and
    passing the new table to the first (`.C`) slot of `R_registerRoutines`.
    See the companion guides `DllInfo.md` and `R_CallMethodDef.md` for the
    complete registration-table migration.

---

### Pattern: `TRUE` as a Plain Integer Literal in Internal C Logic

This pattern applies when `TRUE` appears as a local variable value or a
conditional operand inside a C function that will be fully ported to `.C` and
stripped of all R headers.

- **Locations:** Not present in the CSV (the single CSV occurrence falls into
  the DLL Registration pattern above), but documented here as the general case.

- **Original Context (.Call):**

```c
#include <Rinternals.h>   /* provides TRUE, FALSE via Boolean.h */

static int check_flag(int x)
{
    Rboolean ok = FALSE;
    if (x > 0) ok = TRUE;
    return (int) ok;
}
```

- **C/C++ Equivalent (.C):**

```c
/* No R headers required */
#include <stdbool.h>   /* C99: provides bool, true, false */

/* Option A — standard C99 bool */
static int check_flag(int x)
{
    bool ok = false;
    if (x > 0) ok = true;
    return (int) ok;   /* 0 or 1; matches .C logical convention */
}

/* Option B — plain int, maximally portable */
static int check_flag(int x)
{
    int ok = 0;         /* 0 == FALSE */
    if (x > 0) ok = 1;  /* 1 == TRUE  */
    return ok;
}
```

- **Explanation:**
  - `TRUE` (integer `1`) and `FALSE` (integer `0`) are replaced by `true`/`false`
    (C99 `<stdbool.h>`) or the integer literals `1`/`0`.
  - The `.C` API specification states that R logical vectors arrive in C as
    `int *` with values `0` (false), `1` (true), or `INT_MIN` (NA). Option B
    (`int` with `0`/`1`) is therefore the safest mapping for values that cross
    the `.C` boundary, because the representation is explicitly specified by
    the `.C` documentation.
  - Option A (`bool`) is idiomatic modern C99/C11 and produces the same binary
    representation (`0`/`1`) when cast to `int`.
  - No `PROTECT`/`UNPROTECT` changes are needed: `TRUE`/`FALSE` are scalar
    compile-time constants with no heap allocation.
  - Once R headers are removed from purely computational `.C` code, the symbols
    `TRUE` and `FALSE` from `Boolean.h` are no longer in scope; using the
    integer literals `1` and `0` is the direct, zero-dependency replacement.

---

### Pattern: Inheriting Environment Lookup (`R_getVar(..., TRUE)`)

This pattern applies when `TRUE` is passed as the `inherits` flag to
`R_getVar`, enabling parent-frame traversal during environment lookup. While
not present in the CSV for this package, it is the principal other context
in which `TRUE` appears in R C API code and is documented here for
completeness.

- **Locations:** Not present in the CSV.

- **Original Context (.Call):**

```c
/* .Call-layer code that looks up a variable with parent-frame search */
SEXP stemp = R_getVar(install("myvar"), rho, TRUE);  /* TRUE: search parents */
double *ptr = REAL(stemp);
```

- **C/C++ Equivalent (.C):**

Under the `.C` API, R-level environment lookups are not performed inside the
C code at all. The data that was retrieved from the environment must instead
be passed as a pre-allocated raw C array from R. The `TRUE` flag, the
`install()` call, the `SEXP` intermediate, and `REAL()` unwrapping are all
eliminated.

```c
/*
 * .C-compatible replacement.
 *
 * The variable that was looked up via R_getVar(..., TRUE) is now passed
 * directly as a typed pointer. No R_getVar, no install(), no TRUE flag,
 * no REAL() unwrapping.
 */
void my_c_function(
    const double *myvar,   /* was: REAL(R_getVar(install("myvar"), rho, TRUE)) */
    const int    *n        /* length of myvar */
)
{
    /* Use myvar[0] .. myvar[*n - 1] directly */
}
```

Corresponding R-side invocation:

```r
# The object is available in R; pass it directly to .C.
# The inheriting lookup that TRUE controlled is replaced by the caller
# simply passing the object it already holds.
.C("my_c_function",
   myvar = as.double(myvar_vec),   # numeric vector pre-allocated in R
   n     = as.integer(length(myvar_vec)))
```

- **Explanation:**
  - `TRUE` (value `1`) was the `inherits` flag to `R_getVar`, selecting a
    parent-frame-traversing search (equivalent to `findVar`). Under `.C`, the
    entire environment-lookup mechanism is absent — R transmits the data values
    directly, making the `inherits` flag irrelevant and eliminating `TRUE`
    entirely from the C interface.
  - The difference between `TRUE` (inheriting search) and `FALSE` (frame-only
    search) in `R_getVar` has no analogue in the `.C` API: both are replaced
    by the same pattern of direct pointer argument passing.
  - `SEXP stemp`, `install()`, `R_getVar()`, and `REAL()` are all `.Call`-layer
    constructs with no `.C` equivalents; they are removed from the C function.
  - The `Rboolean` type and the `TRUE` / `FALSE` constants are no longer needed
    anywhere in the converted function. If a boolean flag is needed inside a
    purely computational `.C` function, use `int` (values `0` and `1`) or
    `bool` from `<stdbool.h>`.
