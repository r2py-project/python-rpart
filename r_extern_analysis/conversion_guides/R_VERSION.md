# Conversion Guide: `R_VERSION`

## 1. Overview of `R_VERSION` in R API

`R_VERSION` is a preprocessor integer constant defined in `Rversion.h` as
`#define R_VERSION 263427` (the exact numeric value changes with each R release).
It encodes the running R build's version as a single integer computed by the
companion macro `R_Version(v, p, s)` — defined as `(((v) * 65536) + ((p) * 256) + (s))` — so that the major, minor, and patch components can be packed into one
value and compared with a single `>=` or `<` operator. `R_VERSION` is exclusively
a compile-time constant; it plays no runtime role, carries no heap allocation,
and has no interaction with R's garbage collector or `.Call`/`.C` argument
marshalling. Its sole purpose is to gate version-dependent code paths through
`#if`/`#ifdef` preprocessor directives so that a single source tree can compile
correctly against multiple R versions.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `init.c` | 27 | `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` |
| `rpart_callback.c` | 19 | `#if R_VERSION < R_Version(4, 5, 0)` |

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

**Pattern analysis:** The `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)`
guard is a two-part check: the `defined(R_VERSION)` half ensures the header is
present (defensive coding for very old toolchains that might lack `Rversion.h`),
and `R_VERSION >= R_Version(2, 16, 0)` numerically requires at least R 2.16.0.
Inside the guarded block, `R_forceSymbols(dll, TRUE)` is called — a function
introduced in R 2.16.0 that makes `.Call` require registered `R_CallMethodDef`
objects rather than character-string symbol lookup. This block is exclusively
DLL-registration infrastructure; it lives entirely within `R_init_rpart`, which
is invoked by R's dynamic loader, not from any user-callable function.

### 31-line window — `rpart_callback.c` (lines 8–34)

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
```

**Pattern analysis:** This `#if R_VERSION < R_Version(4, 5, 0)` block is a
backward-compatibility shim. The function `R_getVar` (which takes a `Rboolean
inherits` third argument) was introduced in R 4.5.0. On older R builds the
symbol `R_getVar` does not exist in the headers, so the block provides a local
static replacement and redefines the macro `R_getVar` to point to it. On R
4.5.0 and above the block is compiled out entirely and the native `R_getVar`
from `Rinternals.h` is used. The entire guarded region — both the shim function
and the macro override — belongs to the `.Call` layer: it uses `SEXP`, `findVar`,
`findVarInFrame`, and `R_UnboundValue`, none of which exist in `.C` functions.

### Key observations

- `R_VERSION` is a **preprocessor-only artifact**. It is never stored in a
  variable, never passed as a function argument, and never allocated on the heap.
  It exists solely as a `#define` integer literal evaluated at compile time.
- Both occurrences in the codebase guard `.Call`-layer infrastructure: DLL
  registration (`init.c`) and an environment-lookup compatibility shim
  (`rpart_callback.c`). Neither affects any `.C`-compatible computational kernel.
- The companion macro `R_Version(v, p, s)` is also defined in `Rversion.h`; it
  is used as the right-hand operand in every `R_VERSION` comparison. The two
  macros are always used together.
- No data types, memory management macros, or output allocations are involved.
  `R_VERSION` comparisons are not connected to `PROTECT`/`UNPROTECT` or
  `allocVector` in any of the observed usages.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Because `R_VERSION` is a compile-time preprocessor constant rather than a
runtime value, it requires no API-level conversion at all. It is not part of any
function signature, not passed through `.Call` or `.C`, and not involved in
memory management. The correct migration approach differs by pattern:

1. **Pattern A (DLL registration gate, `init.c`):** The `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` guard and the `R_forceSymbols` call inside it are
   DLL-initialization logic that must remain in `R_init_<pkg>`. When migrating
   computational kernels from `.Call` to `.C`, `R_init_<pkg>` is updated to
   register the new `.C` methods in an `R_CMethodDef` table, but the
   `R_VERSION`-gated `R_forceSymbols` block is **retained unchanged** because it
   controls symbol-resolution policy for the entire DLL, including any `.C`
   entries.

2. **Pattern B (backward-compatibility shim, `rpart_callback.c`):** The
   `#if R_VERSION < R_Version(4, 5, 0)` block defines a shim for `R_getVar` on
   older R versions. Since `R_getVar`, `findVar`, `findVarInFrame`, `SEXP`, and
   `R_UnboundValue` are all `.Call`-layer constructs that do not exist in `.C`
   functions, this entire block — both when the shim is compiled in and when it
   is compiled out — is **irrelevant to any `.C` migration**. A `.C`-compatible
   function never calls `R_getVar` regardless of the R version, so the version
   gate becomes dead code in a fully ported implementation.

### Type mapping

| Construct | Nature | `.C` migration action |
|---|---|---|
| `R_VERSION` | Preprocessor `#define` integer | Retained as-is in DLL init; eliminated from `.C` function bodies |
| `R_Version(v, p, s)` | Preprocessor arithmetic macro | Same as `R_VERSION`; retained alongside it |
| `#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)` | Compile-time gate for `R_forceSymbols` | Retained unchanged in `R_init_<pkg>` |
| `#if R_VERSION < R_Version(4, 5, 0)` | Compile-time gate for `.Call`-layer shim | Eliminated; the shim guards `.Call` constructs with no `.C` equivalent |

### Why this approach ensures `.C` compatibility

The `.C` API requires that function bodies contain no R-API constructs: no
`SEXP`, no `PROTECT`, no `eval`, no `findVar`, no `R_getVar`. `R_VERSION` itself
imposes none of those; it is a bare integer constant. The version-gated code it
guards in `rpart_callback.c` does use `.Call`-layer constructs, but those
constructs are removed in the `.C` migration regardless of the version guard —
making the `#if R_VERSION` block redundant in the converted code. In `init.c`
the guarded code (`R_forceSymbols`) is DLL infrastructure that is orthogonal to
whether the registered methods are `.Call` or `.C`.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Compile-Time Version Gate in DLL Registration (`init.c`)

- **Locations:** `init.c` line 27

- **Original Context (.Call):**

```c
/* init.c — full R_init_rpart function */
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
/* init.c — updated to register .C methods; version gate preserved unchanged */
#include <Rversion.h>
#include <R_ext/Rdynload.h>

/* .C method type arrays (one per registered function) */
static R_NativePrimitiveArgType rpart_c_types[] = {
    INTSXP,  /* ncat    */
    INTSXP,  /* method  */
    REALSXP, /* opt     */
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
     * First argument: CEntries (.C methods).
     * CallEntries is removed or set to NULL once all kernels are ported.
     */
    R_registerRoutines(dll, CEntries, NULL, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
    /*
     * The R_VERSION gate is retained exactly as-is.
     * R_forceSymbols controls symbol-resolution policy for the whole DLL
     * (including .C entries) and is not affected by the .Call-to-.C migration.
     */
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
```

- **Explanation:**
  - `R_VERSION` and `R_Version(v, p, s)` are preprocessor macros from `Rversion.h`
    that evaluate at compile time to a single integer. They require no source
    change when porting computational code from `.Call` to `.C`.
  - The `defined(R_VERSION)` guard is a defensive check inherited from the era
    when `Rversion.h` was not universally available. In any R version capable of
    building this package today, `R_VERSION` is always defined, but the guard is
    harmless and is kept for clarity.
  - The only structural changes in `R_init_rpart` are: (a) replacing
    `R_CallMethodDef CallEntries` with `R_CMethodDef CEntries`, and (b) passing
    `CEntries` as the first (`.C`) argument rather than the second (`.Call`)
    argument to `R_registerRoutines`. The `R_VERSION`-gated block is untouched.

---

### Pattern: Compile-Time Version Gate for a `.Call`-Layer Compatibility Shim (`rpart_callback.c`)

- **Locations:** `rpart_callback.c` line 19

- **Original Context (.Call):**

```c
/* rpart_callback.c:8-28 — backward-compat shim for R < 4.5.0 */
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

The `R_VERSION < R_Version(4, 5, 0)` guard enables the shim on R builds that
predate the introduction of the native `R_getVar` API function. On R 4.5.0+
the entire block is compiled out and `R_getVar` from `Rinternals.h` is used
directly.

- **C/C++ Equivalent (.C):**

```c
/*
 * In a .C-compatible implementation, the entire version-gated block is
 * removed. The .C API provides no access to R environments (SEXP rho),
 * R symbols (install/PRINTNAME), or environment lookup functions
 * (findVar, findVarInFrame, R_getVar). None of these constructs appear
 * in .C function bodies regardless of the R version.
 *
 * The data that R_getVar retrieved by name from an R environment is instead
 * passed directly as typed C pointer arguments by the R caller:
 */

/* No #include <Rversion.h> needed if the file contains only .C functions.
 * No R_VERSION guard needed: the shim and the native R_getVar are equally
 * irrelevant to .C code. */

void init_rpcallback_c(
    const int    *ny,    /* scalar: number of y columns          */
    const int    *nr,    /* scalar: length of per-node result    */
    const double *yback, /* was: R_getVar("yback", rho, FALSE)   */
    const double *wback, /* was: R_getVar("wback", rho, FALSE)   */
    const double *xback, /* was: R_getVar("xback", rho, FALSE)   */
    const int    *nback  /* was: R_getVar("nback", rho, FALSE)   */
)
{
    /*
     * No version gate, no SEXP, no findVar / R_getVar, no R_UnboundValue.
     * Data arrives directly as typed pointers; no lookup is necessary.
     */
    ysave = *ny;
    rsave = *nr;
    ydata = (double *) yback;
    wdata = (double *) wback;
    xdata = (double *) xback;
    ndata = (int *)    nback;
}
```

Corresponding R-side call:

```r
# The R caller already holds yback, wback, xback, nback as R vectors.
# It passes them directly instead of storing them in an environment
# for C-side lookup. The R_VERSION version gate becomes irrelevant.
.C("init_rpcallback_c",
   ny    = as.integer(ny),
   nr    = as.integer(nr),
   yback = as.double(yback_vec),
   wback = as.double(wback_vec),
   xback = as.double(xback_vec),
   nback = integer(1L))
```

- **Explanation:**
  - The `#if R_VERSION < R_Version(4, 5, 0)` block guards code that uses
    `SEXP`, `findVar`, `findVarInFrame`, `R_UnboundValue`, `Rboolean`, and
    `CHAR(PRINTNAME(...))`. Every one of these constructs is exclusive to the
    `.Call` API and has no presence in `.C` function bodies.
  - When porting to `.C`, the question "does this R version have `R_getVar`?"
    becomes moot: neither the native `R_getVar` nor the shim `compat_getVar`
    is called, because environment lookup is eliminated from the C side entirely.
  - The `#include <Rversion.h>` directive can be removed from any C source file
    that, after porting, contains only `.C`-compatible functions. If the file
    also retains `.Call` functions or DLL-registration code, the include and any
    `R_VERSION` guards within those sections remain.
  - The semantic effect of the `FALSE` flag to `R_getVar` (frame-only lookup,
    not inheriting) is reproduced on the R side simply by the calling code
    passing the objects it already holds — no inheritance question arises because
    there is no environment search at all. (See also `FALSE.md` and
    `R_UnboundValue.md` for full treatment of the related constructs.)
