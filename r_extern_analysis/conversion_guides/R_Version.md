# Conversion Guide: `R_Version`

## 1. Overview of `R_Version` in R API

`R_Version(v, p, s)` is a preprocessor arithmetic macro defined in `Rversion.h`
as `(((v) * 65536) + ((p) * 256) + (s))`. It packs a major version number `v`,
minor version number `p`, and patch (sub-minor) version number `s` into a single
integer, producing the same encoding used by the companion constant `R_VERSION`.
Its sole purpose is to serve as the right-hand operand in `#if` comparisons
against `R_VERSION`, allowing a single C source tree to compile correctly against
multiple R versions by gating version-dependent code paths at compile time.
`R_Version` performs no runtime computation, involves no heap allocation, and has
no interaction with R's garbage collector or `.Call`/`.C` argument marshalling.

> **Companion constant:** `R_VERSION.md` documents the left-hand operand
> `R_VERSION`; the two macros are always used together and must be read as a
> pair.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `init.c` | 27 | `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` |
| `rpart_callback.c` | 19 | `#if R_VERSION < R_Version(4, 5, 0)` |

### Header resolution

`Rversion.h` was not accessible at the expected path
`~/.conda/envs/r-to-python/lib/R/include/Rversion.h` (permission denied) and is
not present in `rpart/src/`. The macro definition is established from the
companion guide `R_VERSION.md`, which documents the expansion as:

```c
/* Rversion.h (canonical definition) */
#define R_Version(v,p,s) (((v) * 65536) + ((p) * 256) + (s))
```

For example, `R_Version(4, 5, 0)` expands to `(4*65536 + 5*256 + 0)` = `263936`.

### 31-line window — `init.c` (lines 12–30)

```c
static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart",           (DL_FUNC) &rpart,            11},
    {"xpred",           (DL_FUNC) &xpred,            15},
    {"rpartexp2",       (DL_FUNC) &rpartexp2,         2},
    {"pred_rpart",      (DL_FUNC) &pred_rpart,       12},
    {NULL, NULL, 0}
};

#include <Rversion.h>
void
R_init_rpart(DllInfo * dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

**Pattern analysis:** The `R_Version(2, 16, 0)` call supplies the minimum version
threshold for `R_forceSymbols`, which was introduced in R 2.16.0. The combined
guard `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` is standard
defensive idiom: `defined(R_VERSION)` protects against extremely old toolchains
that lack `Rversion.h`, while `R_VERSION >= R_Version(2, 16, 0)` is the numeric
gate. The entire block is DLL-registration infrastructure inside
`R_init_rpart`; it is not part of any user-callable computation kernel.

### 31-line window — `rpart_callback.c` (lines 4–34)

```c
#include <stddef.h>
#include <R.h>
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
```

**Pattern analysis:** `R_Version(4, 5, 0)` provides the threshold below which
the native `R_getVar` function is absent from R's headers. When the guard is
satisfied (R < 4.5.0), the block injects a static shim `compat_getVar` and
overrides the `R_getVar` macro to point to it. The entire guarded region uses
exclusively `.Call`-layer constructs — `SEXP`, `findVar`, `findVarInFrame`,
`R_UnboundValue`, `Rboolean` — none of which appear in `.C` function bodies.

### Key observations

- `R_Version(v, p, s)` is a **compile-time arithmetic macro**. It is never stored
  in a variable, never passed as a function argument, and never allocated on the
  heap. It exists solely as an integer expression evaluated by the C preprocessor.
- Both occurrences pair `R_Version` with `R_VERSION` in a `#if` comparison; the
  two macros are always used together.
- Both guarded blocks contain `.Call`-layer constructs (`DllInfo`,
  `R_forceSymbols`, `SEXP`, `findVar`, etc.). No `.C`-compatible code is gated by
  either `R_Version` guard.
- No data types, memory management macros, or heap allocations are associated with
  `R_Version` in any observed usage.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_Version(v, p, s)` is a preprocessor macro, not a runtime function. It
requires no API-level conversion. The correct migration action is determined
entirely by what the gated code block contains:

1. **Pattern A — DLL registration gate (`init.c` line 27):** The `R_Version`
   threshold guards a call to `R_forceSymbols`, which is DLL-initialization
   infrastructure that applies equally to `.C` and `.Call` registrations. When
   porting computational kernels to `.C`, `R_init_<pkg>` is updated to register
   the new `.C` methods in an `R_CMethodDef` table, but the `R_VERSION >=
   R_Version(2, 16, 0)` block is **retained unchanged**. `R_forceSymbols`
   controls symbol-resolution policy for the whole DLL regardless of the calling
   convention used by individual functions.

2. **Pattern B — backward-compatibility shim (`rpart_callback.c` line 19):** The
   `R_Version(4, 5, 0)` threshold guards a shim that polyfills `R_getVar` on
   older R builds. Because `R_getVar`, `SEXP`, `findVar`, and all related
   constructs are exclusive to the `.Call` API, the entire block — both the shim
   and the version gate itself — becomes **dead code** in a `.C`-only
   implementation and must be removed.

### Type mapping

| Construct | Nature | `.C` migration action |
|---|---|---|
| `R_Version(v, p, s)` | Preprocessor arithmetic macro | Retained in DLL init alongside `R_VERSION`; removed from `.C` function source files |
| `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` | Compile-time gate for `R_forceSymbols` | Retained unchanged in `R_init_<pkg>` |
| `#if R_VERSION < R_Version(4, 5, 0)` | Compile-time gate for `.Call`-layer shim | Entire block eliminated; shim contains no `.C`-compatible constructs |
| `#include <Rversion.h>` | Header providing both macros | Retained in files that still contain DLL registration code; removed from pure `.C` source files |

### Why this approach ensures `.C` compatibility

The `.C` API requires function bodies to contain no R-API constructs: no `SEXP`,
no `PROTECT`, no `eval`, no `findVar`, no `R_getVar`. `R_Version` itself imposes
none of those; it is a bare compile-time integer expression. The version-gated
code in `rpart_callback.c` does use `.Call`-layer constructs, but those
constructs are removed during the `.C` migration regardless of the version gate —
making the `#if R_Version` block redundant in the converted code. In `init.c` the
guarded code (`R_forceSymbols`) is DLL infrastructure orthogonal to whether the
registered methods are `.Call` or `.C`.

---

## 4. Step-by-Step Conversion Examples

### Pattern A: Compile-Time Version Gate in DLL Registration

- **Locations:** `init.c` line 27

- **Original Context (.Call):**

```c
/* init.c — full R_init_rpart, .Call-era version */
#include <Rversion.h>

void
R_init_rpart(DllInfo *dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);   /* available since R 2.16.0 */
#endif
}
```

- **C/C++ Equivalent (.C):**

```c
/* init.c — updated to register .C methods; R_Version gate preserved unchanged */
#include <Rversion.h>
#include <R_ext/Rdynload.h>

/* Type descriptor arrays for each .C-registered function */
static R_NativePrimitiveArgType rpart_c_types[] = {
    INTSXP,  /* ncat   */
    INTSXP,  /* method */
    REALSXP, /* opt    */
    /* ... remaining argument types ... */
};

static const R_CMethodDef CEntries[] = {
    {"rpart_c",      (DL_FUNC) &rpart_c,      N_RPART_ARGS,      rpart_c_types},
    {"xpred_c",      (DL_FUNC) &xpred_c,      N_XPRED_ARGS,      NULL},
    {"pred_rpart_c", (DL_FUNC) &pred_rpart_c,  N_PRED_RPART_ARGS, NULL},
    {NULL, NULL, 0, NULL}
};

void
R_init_rpart(DllInfo *dll)
{
    /*
     * Pass CEntries as the first (.C) argument.
     * CallEntries is set to NULL once all kernels are ported to .C.
     */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);

    /*
     * The R_Version gate is retained exactly as-is.
     * R_forceSymbols applies to all registered symbols in the DLL,
     * including .C entries, and is unaffected by the .Call-to-.C migration.
     */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

- **Explanation:**
  - `R_Version(2, 16, 0)` expands to the integer `131584` at compile time. It is
    not a function call and produces no object code.
  - The `defined(R_VERSION)` half of the combined guard is a historical defensive
    check from the era when `Rversion.h` was not universally available. It is
    harmless on any modern R installation and is kept for portability.
  - The only structural changes in `R_init_rpart` are: (a) replacing
    `R_CallMethodDef CallEntries` with `R_CMethodDef CEntries`, and (b) passing
    `CEntries` as the first (`.C`) slot rather than the second (`.Call`) slot of
    `R_registerRoutines`. The `R_Version`-gated block is untouched.
  - `R_forceSymbols(dll, TRUE)` prevents lookup by character string for all
    methods in the DLL, both `.C` and `.Call`. It is equally desirable after the
    migration and must not be removed.

---

### Pattern B: Compile-Time Version Gate for a `.Call`-Layer Compatibility Shim

- **Locations:** `rpart_callback.c` line 19

- **Original Context (.Call):**

```c
/* rpart_callback.c — backward-compat shim for R < 4.5.0 */
#include <Rversion.h>

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
```

The `R_Version(4, 5, 0)` threshold is the point at which R's public API gained
the native `R_getVar` function. On older builds the block injects a static
replacement; on newer builds it is compiled out entirely.

- **C/C++ Equivalent (.C):**

```c
/*
 * In a .C-compatible implementation the entire version-gated block is removed.
 *
 * Reason: the block guards code that uses SEXP, Rboolean, findVar,
 * findVarInFrame, R_UnboundValue, and CHAR(PRINTNAME(...)). Every one of those
 * constructs is exclusive to the .Call API. A .C function never performs
 * R-environment lookup of any kind, so neither the native R_getVar nor the
 * compat_getVar shim is relevant.
 *
 * The data that was previously retrieved from an R environment via R_getVar is
 * instead passed directly as typed C pointer arguments by the R caller:
 */

/* No #include <Rversion.h> required in a pure .C source file. */

void init_rpcallback_c(
    const int    *ny,    /* scalar: number of y columns         */
    const int    *nr,    /* scalar: length of per-node result   */
    const double *yback, /* was: R_getVar("yback", rho, FALSE)  */
    const double *wback, /* was: R_getVar("wback", rho, FALSE)  */
    const double *xdata, /* was: R_getVar("xback", rho, FALSE)  */
    const int    *nback  /* was: R_getVar("nback", rho, FALSE)  */
)
{
    /*
     * No version gate, no SEXP, no findVar / R_getVar, no R_UnboundValue.
     * Data arrives directly as typed pointers from the R caller.
     */
    ysave = *ny;
    rsave = *nr;
    /* assign module-level pointers used by the callback machinery */
    ydata = (double *) yback;
    wdata = (double *) wback;
    xptr  = (double *) xdata;
    ndata = (int *)    nback;
}
```

Corresponding R-side call:

```r
# The R caller already holds yback, wback, xback, nback as R vectors.
# It passes them directly; no environment lookup occurs on the C side.
# The R_Version version gate is irrelevant from the R side as well.
.C("init_rpcallback_c",
   ny    = as.integer(ny),
   nr    = as.integer(nr),
   yback = as.double(yback_vec),
   wback = as.double(wback_vec),
   xdata = as.double(xback_vec),
   nback = integer(1L))
```

- **Explanation:**
  - The `#if R_VERSION < R_Version(4, 5, 0)` block is removed in its entirety.
    The threshold it encodes — whether the build is older or newer than R 4.5.0 —
    is meaningless to a `.C` function that never calls `R_getVar`.
  - The `#include <Rversion.h>` directive can be removed from any C source file
    that, after porting, contains only `.C`-compatible functions. If the same
    file also retains `.Call` functions or DLL-registration code, the include and
    any `R_VERSION`/`R_Version` guards within those sections remain.
  - Environment lookup (`findVar`, `findVarInFrame`, `R_getVar`) is replaced by
    the architectural shift fundamental to `.C`: data is pre-computed on the R
    side and passed as raw typed pointers. The `inherits = FALSE` semantics of the
    original `R_getVar` call (frame-only lookup, no parent-environment search) are
    reproduced trivially because no lookup occurs at all.
  - See `R_UnboundValue.md`, `FALSE.md`, and `Rboolean.md` for treatment of the
    other `.Call`-layer constructs that appeared inside this version-gated block.
