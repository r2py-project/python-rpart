# Conversion Guide: `FALSE`

## 1. Overview of `FALSE` in R API

`FALSE` is one of two named integer constants (`FALSE = 0`, `TRUE = 1`) exported
by `R_ext/Boolean.h` (included transitively through `R.h` and `Rinternals.h`).
It is defined as a member of the `Rboolean` enumeration
(`typedef enum { FALSE = 0, TRUE } Rboolean;`), which uses `int` as its
underlying type on all platforms that R supports. In R's C API, `FALSE` is used
wherever a boolean flag argument is required — most commonly as the `inherits`
argument to `R_getVar` (controlling whether variable lookup should search parent
environments) and as the `value` argument to `R_useDynamicSymbols` / `R_forceSymbols`
(controlling shared-library registration policy at DLL load time). It carries no
heap-allocated memory, requires no `PROTECT`/`UNPROTECT` treatment, and imposes no
GC interaction.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `init.c` | 26 | `R_useDynamicSymbols(dll, FALSE);` |
| `rpart_callback.c` | 59 | `stemp = R_getVar(install("yback"), rho, FALSE);` |
| `rpart_callback.c` | 62 | `stemp = R_getVar(install("wback"), rho, FALSE);` |
| `rpart_callback.c` | 65 | `stemp = R_getVar(install("xback"), rho, FALSE);` |
| `rpart_callback.c` | 68 | `stemp = R_getVar(install("nback"), rho, FALSE);` |

### Pattern A — DLL registration flag (`init.c` line 26)

`R_useDynamicSymbols(dll, FALSE)` is called inside the package's
`R_init_rpart` entry point, which is invoked automatically by R when the shared
library is loaded via `library()`. The second argument is a `Rboolean` that
tells R whether unregistered symbols should be resolvable by `.Call` by name.
Passing `FALSE` locks the package to its explicit `R_CallMethodDef` table, which
is a security and performance best practice. The surrounding block also calls
`R_forceSymbols(dll, TRUE)` (compiled only on R >= 2.16.0), which enforces that
`.Call` must always use the registered `R_CallMethodDef` objects rather than
character symbol lookup.

This use of `FALSE` is entirely within DLL registration infrastructure — a concern
of the `.Call` layer's initialization pathway. It does not appear inside any
computational kernel and does not migrate into `.C`-callable code.

### Pattern B — Variable lookup flag (`rpart_callback.c` lines 59, 62, 65, 68)

All four occurrences follow the same idiom:

```c
stemp = R_getVar(install("<name>"), rho, FALSE);
```

`R_getVar` (declared in `Rinternals.h` as
`SEXP R_getVar(SEXP sym, SEXP rho, Rboolean inherits)`) looks up a symbol in an
R environment. When `inherits = FALSE`, the search is restricted to the
frame `rho` itself (equivalent to `findVarInFrame`), without traversing parent
environments. The returned `SEXP` is then immediately unwrapped into a raw C
pointer via `REAL()` or `INTEGER()`:

```c
stemp = R_getVar(install("yback"), rho, FALSE);   /* double[] */
ydata = REAL(stemp);

stemp = R_getVar(install("wback"), rho, FALSE);   /* double[] */
wdata = REAL(stemp);

stemp = R_getVar(install("xback"), rho, FALSE);   /* double[] */
xdata = REAL(stemp);

stemp = R_getVar(install("nback"), rho, FALSE);   /* int[] */
ndata = INTEGER(stemp);
```

The file also contains a backward-compatibility shim (lines 19–28, compiled only
for `R_VERSION < R_Version(4, 5, 0)`) that re-implements `R_getVar` using the
older `findVar`/`findVarInFrame` pair, with `Rboolean inherits` as its third
parameter (covered in the companion guide `Rboolean.md`).

### Key observations

- `FALSE` is used purely as a **compile-time integer literal** (value `0`) passed
  as a flag argument. It is never stored in a `SEXP`, never allocated on the R
  heap, and never garbage-collected.
- Both call sites (`R_useDynamicSymbols`, `R_getVar`) are `.Call`-layer
  functions — they require `SEXP` or `DllInfo *` arguments that do not exist in
  the `.C` API.
- The semantic role of `FALSE` in `R_getVar` (frame-only lookup) is replaced
  under `.C` by the complete elimination of environment lookup — the data is
  passed directly as pre-allocated C arrays.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Under the `.C` API, R passes data as pre-allocated vectors of basic C types
(`int *`, `double *`, `char **`, `int *` for logicals). The `.C` API does not
provide access to R environments, symbol tables, or `SEXP` objects at all.
Consequently:

1. **Pattern A (`R_useDynamicSymbols`)** — This call lives in `R_init_<pkg>`,
   which is a DLL-registration hook executed by R's dynamic loader, not by any
   user-callable `.C` or `.Call` function. It is not migrated. When a package
   migrates its computational kernels from `.Call` to `.C`, the `R_init_<pkg>`
   function and its `R_useDynamicSymbols(dll, FALSE)` line remain unchanged
   (or are updated to register `.C` methods in the `R_CMethodDef` table instead
   of `.Call` methods in `R_CallMethodDef`).

2. **Pattern B (`R_getVar(..., FALSE)`)** — The entire environment-lookup idiom
   is eliminated. The C function no longer searches for named variables in an R
   frame; instead, the R calling code passes the underlying data directly as
   typed pointer arguments. The `FALSE` flag, the `install()` call, the `SEXP`
   intermediate `stemp`, `REAL()`, and `INTEGER()` unwrapping are all removed.

### Type mapping

| `.Call` construct | Role of `FALSE` | `.C` equivalent |
|---|---|---|
| `R_useDynamicSymbols(dll, FALSE)` | Disables dynamic symbol resolution | Not migrated; stays in `R_init_<pkg>` |
| `R_getVar(sym, rho, FALSE)` | Frame-only lookup (`inherits = 0`) | Eliminated; data passed as `double *` / `int *` argument |
| `Rboolean` local flag set to `FALSE` | Internal C boolean | `int` flag initialized to `0`, or `bool` from `<stdbool.h>` |

The `.C` documentation states: _"Logical values are sent as `0` (`FALSE`), `1`
(`TRUE`) or `INT_MIN` (NA)"_ and the C type for a logical argument is `int *`.
Therefore, wherever `FALSE` must survive as a passable value in a `.C`-compatible
interface (e.g., an `int *` logical flag sent from R), it maps directly to the
integer value `0`.

---

## 4. Step-by-Step Conversion Examples

### Pattern 1: DLL Registration Flag (`R_useDynamicSymbols`)

- **Locations:** `init.c` line 26

- **Original Context (.Call):**

```c
/* init.c — R_init_rpart, the DLL load hook */
#include <Rversion.h>

void R_init_rpart(DllInfo *dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);   /* FALSE: lock to registered symbols only */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

- **C/C++ Equivalent (.C):**

When migrating computational kernels to `.C`, the DLL registration hook is
updated to register the new `.C` methods in the `R_CMethodDef` table. The
`R_useDynamicSymbols(dll, FALSE)` call is **retained as-is** — it is not part
of any `.C` function signature, and `FALSE` here is simply the integer `0`
passed to an R internal API. No source change is required for this line itself.

```c
/* init.c — updated to register .C methods alongside (or instead of) .Call */
#include <Rversion.h>

/* .C method table — replace or augment CallEntries as needed */
static const R_CMethodDef CEntries[] = {
    {"init_rpcallback_c", (DL_FUNC) &init_rpcallback_c, 6},
    /* ... other .C routines ... */
    {NULL, NULL, 0}
};

void R_init_rpart(DllInfo *dll)
{
    /* First argument: CEntries (.C); second: CallEntries (.Call), etc. */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);   /* unchanged: still 0 / FALSE */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

- **Explanation:**
  - `FALSE` in `R_useDynamicSymbols(dll, FALSE)` is a `Rboolean` enum value
    that resolves to the integer `0`. The function is part of R's shared-library
    API (`R_ext/Rdynload.h`), not of any `.Call`/`.C` computational interface.
  - Migrating kernels to `.C` does not require touching this line. If `FALSE`
    were to be replaced for complete header independence, `0` is the exact
    substitute — but in practice this file always includes R headers, so `FALSE`
    is always available.
  - The only meaningful change when adopting `.C` is replacing `R_CallMethodDef`
    with `R_CMethodDef` for the newly ported functions and passing the table to
    the first (`.C`) slot of `R_registerRoutines`.

---

### Pattern 2: Frame-Only Variable Lookup (`R_getVar(..., FALSE)`)

- **Locations:** `rpart_callback.c` lines 59, 62, 65, 68

- **Original Context (.Call):**

```c
/* rpart_callback.c:47-71 — .Call-layer initialization function */
SEXP
init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x)
{
    SEXP stemp;

    rho   = rhox;
    ysave = asInteger(ny);
    rsave = asInteger(nr);
    expr1 = expr1x;
    expr2 = expr2x;

    /* FALSE = frame-only lookup; no parent-environment search */
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

The `FALSE` flag tells `R_getVar` to perform a frame-local lookup only
(`findVarInFrame` semantics). The result is immediately stripped of its `SEXP`
wrapper via `REAL()` or `INTEGER()` and stored as a raw pointer.

- **C/C++ Equivalent (.C):**

```c
/*
 * .C-compatible replacement for init_rpcallback.
 *
 * The four environment variables (yback, wback, xback, nback) are passed
 * directly as typed pointers from R. R_getVar, install(), REAL(),
 * INTEGER(), and FALSE are eliminated entirely from this interface.
 *
 * Signature designed for use with .C("init_rpcallback_c", ...) in R.
 */

/* Module-level storage (same as before, but populated by pointer copy) */
static int     ysave;
static int     rsave;
static double *ydata;
static double *wdata;
static double *xdata;
static int    *ndata;

void init_rpcallback_c(
    const int    *ny,       /* scalar: number of y columns                     */
    const int    *nr,       /* scalar: length of per-node "mean" result vector */
    const double *yback,    /* double vector, length (*ny) * n_obs             */
    const double *wback,    /* double vector, length n_obs                     */
    const double *xback,    /* double vector, length n_obs * n_xcols           */
    const int    *nback     /* int vector, length >= 1                         */
)
{
    ysave = *ny;
    rsave = *nr;

    /*
     * Store raw pointers directly. No SEXP intermediary, no R_getVar,
     * no FALSE flag, no findVar / findVarInFrame call needed.
     */
    ydata = (double *) yback;
    wdata = (double *) wback;
    xdata = (double *) xback;
    ndata = (int *)    nback;
}
```

Corresponding R-side invocation:

```r
# All four data vectors are prepared in R and passed directly to .C.
# The frame-only lookup that FALSE controlled is replaced by the caller
# simply passing the objects it already holds.
.C("init_rpcallback_c",
   ny    = as.integer(ny),
   nr    = as.integer(nr),
   yback = as.double(yback_vec),   # numeric vector of length ny * nrow(x)
   wback = as.double(wback_vec),   # numeric vector of length nrow(x)
   xback = as.double(xback_vec),   # numeric vector of length nrow(x) * ncol(x)
   nback = integer(1L))            # length-1 integer scratch buffer
```

- **Explanation:**
  - `FALSE` (value `0`) was the `inherits` flag to `R_getVar`, choosing between
    `findVarInFrame` (frame-local, `FALSE`) and `findVar` (inheriting, `TRUE`).
    Under `.C`, the entire environment-lookup mechanism is absent — R transmits
    the data values directly, making the `inherits` distinction irrelevant.
  - `R_getVar(install("yback"), rho, FALSE)` together with `REAL(stemp)` is a
    two-step operation: (1) locate the R object by name in the environment, then
    (2) extract its underlying C pointer. Under `.C`, step (1) is performed by
    the R calling code (which already has the object), and step (2) is performed
    implicitly by R's `.C` argument marshalling, which copies or passes the raw
    data buffer to the C function.
  - `SEXP stemp`, `SEXP rho`, `asInteger()`, `REAL()`, `INTEGER()`, and the
    `install()` / `R_getVar()` calls are all removed from the C side.
  - The `Rboolean` type and the `FALSE` / `TRUE` constants are no longer needed
    anywhere in the converted function. If a boolean flag is needed inside a
    purely computational `.C` function, use `int` (with values `0` and `1`) or
    `bool` from `<stdbool.h>`.
  - The R-level objects `yback`, `wback`, `xback`, `nback` must be allocated
    with the correct length before the `.C` call; the C function receives pointers
    to those pre-allocated buffers and must not exceed their bounds.

---

### Pattern 3: `FALSE` as a Plain Integer Literal in Internal C Logic

This pattern applies when `FALSE` appears as a local variable value or a
conditional operand inside a C function that will be fully ported to `.C` and
stripped of all R headers.

- **Locations:** Not present in the CSV (all CSV occurrences fall into Patterns 1
  and 2), but included here as the general case.

- **Original Context (.Call):**

```c
#include <Rinternals.h>   /* provides FALSE, TRUE via Boolean.h */

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
#include <stdbool.h>   /* C99: provides bool, false, true */

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
    int ok = 0;        /* 0 == FALSE */
    if (x > 0) ok = 1; /* 1 == TRUE  */
    return ok;
}
```

- **Explanation:**
  - `FALSE` (integer `0`) and `TRUE` (integer `1`) are replaced by `false`/`true`
    (C99 `<stdbool.h>`) or the integer literals `0`/`1`.
  - The `.C` API specification states that R logical vectors arrive in C as
    `int *` with values `0` (false), `1` (true), or `INT_MIN` (NA). Option B
    (`int` with `0`/`1`) is therefore the safest mapping for values that cross
    the `.C` boundary.
  - No `PROTECT`/`UNPROTECT` changes are needed: `FALSE`/`TRUE` are scalars with
    no heap allocation.
  - Once R headers are removed from purely computational `.C` code, the symbols
    `FALSE` and `TRUE` from `Boolean.h` are no longer in scope; using the integer
    literals `0` and `1` is the direct, zero-dependency replacement.
