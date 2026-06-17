# Fake Header Implementation Guide: `SEXP`

---

### 1. Overview of `SEXP` in R API

`SEXP` is the foundational pointer type of R's C API, defined in `Rinternals.h` as `typedef struct SEXPREC *SEXP`. Every R object — integer vectors, real matrices, character strings, generic lists, language expressions, environments, and `NULL` — is represented at the C level as a `SEXP`, which is a pointer to an opaque `SEXPREC` node managed by R's garbage collector. `SEXP` is the parameter type and return type of every `.Call`-registered C function in rpart; it carries the type tag (`SEXPTYPE`), the object's length, and a pointer to the element data. In the fake runtime, `SEXPREC` is redefined as a minimal C++ struct with fields `type`, `length`, `nrow`, `ncol`, and `data`; the GC is absent, and all lifetime management is explicit.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines | Context |
|---|---|---|
| `init.c` | 6–10 | Forward declarations of three `.Call` entry points: `init_rpcallback`, `rpartexp2`, `pred_rpart` |
| `rpart.c` | 40–65 | Entry-point signature of `rpart()`; local `SEXP` variable block (7 output SEXPs) |
| `rpart.c` | 327–328 | Allocation of `VECSXP` output list (`rlist`) and `STRSXP` name vector (`rname`) |
| `pred_rpart.c` | 133–147 | Entry-point signature and body of `pred_rpart()`; one `INTSXP` allocation |
| `rpart_callback.c` | 20, 33–35, 47–71 | Static SEXP globals (`expr1`, `expr2`, `rho`); entry-point `init_rpcallback()`; local `SEXP stemp` |
| `rpart_callback.c` | 92, 131 | Local `SEXP value`, `SEXP goodness` in callback bodies |
| `rpartexp2.c` | 43–51 | Entry-point `rpartexp2()`; one `INTSXP` allocation |
| `rpartproto.h` | 39, 57 | Prototype declarations for `rpart()` and `xpred()` |
| `xpred.c` | 33–63 | Entry-point signature of `xpred()`; local `SEXP predict2` |

**Argument and return types observed.**

`SEXP` appears in four distinct syntactic roles across the CSV:

1. **Parameter type in `.Call` function signatures.** Every rpart entry point takes only `SEXP` parameters and returns `SEXP`. The real `Rinternals.h` signatures (from `pred_rpart.c:134`, `rpart.c:41`, etc.) confirm this pattern.

2. **Local variable declaration for SEXP objects that are heap-allocated during the function body.** Examples: `SEXP which3, cptable3, ...` in `rpart.c:64`; `SEXP rlist` in `rpart.c:327`; `SEXP predict2` in `xpred.c:63`; `SEXP keep` in `rpartexp2.c:47`; `SEXP where` in `pred_rpart.c:139`.

3. **Static module-level SEXP variables** that persist across `.Call` invocations. Examples: `static SEXP expr1; static SEXP expr2; static SEXP rho;` in `rpart_callback.c:33–35`. These hold references to R language objects (expressions and an environment) passed in by `init_rpcallback` and later consumed by `eval()`.

4. **Local temporary SEXP variables** in internal (non-entry-point) C functions. Examples: `SEXP stemp` at `rpart_callback.c:51`; `SEXP value` at `rpart_callback.c:92`; `SEXP goodness` at `rpart_callback.c:131`. These hold results of `eval()` calls.

**Co-occurring R API items in context windows.**

- `PROTECT` / `UNPROTECT` — wrap every allocation result at `rpart.c:194`, `rpart.c:327`, `pred_rpart.c:139`, `rpartexp2.c:47`. In the fake runtime these are identity no-ops.
- `allocVector(INTSXP, n)`, `allocVector(VECSXP, nout)`, `allocVector(STRSXP, nout)`, `allocMatrix(REALSXP, ...)`, `allocMatrix(INTSXP, ...)` — every SEXP local variable is populated by one of these. Documented in `INTSXP.md` and `REALSXP.md`.
- `INTEGER(sexp)`, `REAL(sexp)`, `asInteger(sexp)`, `asReal(sexp)` — accessors applied to `SEXP` parameters immediately after receipt. Return `int *`, `double *`, `int`, and `double` respectively.
- `LENGTH(sexp)` — used in `rpartexp2.c:46` and `rpart_callback.c:115,149` to read the element count from a SEXP parameter.
- `eval(expr, rho)` — used in `rpart_callback.c:112,146` on the static `expr1`, `expr2` SEXPs; an R Interpreter Item (Category E). Documented separately.
- `isReal(value)` — checks whether a SEXP result from `eval()` is a real vector (`rpart_callback.c:113`).
- `SET_VECTOR_ELT`, `SET_STRING_ELT`, `mkChar`, `setAttrib` — used in `rpart.c:329–345` to populate the output list SEXP.
- `R_NilValue` — the nil singleton SEXP; assigned to `csplit3` as a safe default before conditional allocation (`rpart.c:64`).

**Distinct implementation patterns.**

| Pattern | CSV rows | Description |
|---|---|---|
| P1: `.Call` entry-point parameter/return type | `init.c:6-8`, `pred_rpart.c:133`, `rpart.c:40`, `rpart_callback.c:47`, `rpartexp2.c:43`, `rpartproto.h:39`, `rpartproto.h:57`, `xpred.c:33` | SEXP as the uniform parameter and return type of all `.Call`-registered functions. No memory; pure type. |
| P2: Local SEXP variable for allocation result | `pred_rpart.c:139`, `rpart.c:64`, `rpart.c:327-328`, `rpartexp2.c:47`, `xpred.c:63` | SEXP declared as a local C variable to receive the result of `allocVector` / `allocMatrix`. Heap-allocated; must outlive the local scope to be returned. |
| P3: Static SEXP global for interpreter objects | `rpart_callback.c:33-35` | SEXP stored in a static module-level variable to hold an R expression or environment passed in from R. Requires the fake to accept an opaque SEXP that is never dereferenced as a vector. |
| P4: Local SEXP temporary for `eval()` result | `rpart_callback.c:51`, `rpart_callback.c:92`, `rpart_callback.c:131` | SEXP declared locally to receive the return value of `eval(expr, rho)`. The result is then accessed via `REAL(value)` / `LENGTH(value)`. These paths require the R Interpreter callback (Invariant 3). |

Patterns P1 and P2 share the same fake strategy — both require only `SEXPREC` and `SEXP` to be defined. Patterns P3 and P4 compile with the same type definition but the runtime paths through `eval()` / `findVar()` require function pointer bridges (Invariant 3; those are documented in the `eval` and `findVar` guides, not here).

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`SEXP` is a type alias (`typedef struct SEXPREC *SEXP`). Its fake implementation defines the `SEXPREC` struct and the `SEXP` typedef. No runtime logic lives in `SEXP` itself; all behavior is in the functions (`allocVector`, `INTEGER`, `REAL`, etc.) that consume or produce `SEXP` values.

**Chosen mechanism.**

The real `Rinternals.h` at line 186 defines `typedef struct SEXPREC *SEXP;` where `SEXPREC` is an opaque struct whose fields are gated behind `USE_RINTERNALS`. In the fake build, `USE_RINTERNALS` is never defined (the rpart source does not define it), so the real `SEXPREC` layout is not visible to package code — meaning the fake can define any layout that satisfies the observable C API contract.

The fake `SEXPREC` is a plain C++ struct with five fields:

```
SEXPTYPE  type;    // the SEXPTYPE tag (INTSXP=13, REALSXP=14, etc.)
int       length;  // total element count (returned by LENGTH())
int       nrow;    // row count for matrices (returned by nrows())
int       ncol;    // column count for matrices (returned by ncols())
void     *data;    // pointer to the flat element buffer (heap-allocated)
```

This layout is sufficient for every SEXP accessor used by rpart:

- `INTEGER(s)` and `REAL(s)` cast `s->data` to `int *` and `double *`.
- `LENGTH(s)` returns `s->length`.
- `nrows(s)` and `ncols(s)` return `s->nrow` and `s->ncol`.
- `asInteger(s)` returns `((int*)s->data)[0]`.
- `asReal(s)` returns `((double*)s->data)[0]`.
- `PROTECT(s)` is a no-op identity returning `s`.
- `UNPROTECT(n)` is a no-op.

For `STRSXP` and `VECSXP` objects (string and generic list vectors), `data` holds `SEXP[length]` — an array of child SEXP pointers. `SET_STRING_ELT` and `SET_VECTOR_ELT` write through this array; `STRING_ELT` and `VECTOR_ELT` read from it.

For `CHARSXP` objects (scalar strings created by `mkChar`), `data` holds a `char *` to a null-terminated string.

**Static SEXP globals (Pattern P3).** The three static globals `expr1`, `expr2`, and `rho` in `rpart_callback.c` receive whatever SEXP is passed in from Python and store it verbatim. In the fake runtime, these will hold either `nullptr` (initial state) or a SEXP that was passed in as a Python integer (treated as an opaque handle). Since the only code that actually dereferences these variables calls `eval(expr1, rho)` and `eval(expr2, rho)` — both of which are Category E items requiring a function pointer bridge — the SEXP type definition alone is sufficient for compilation; the interpreter paths are blocked until the `eval` bridge is registered.

**SEXP lifetime model.** In the real R runtime, `PROTECT`/`UNPROTECT` guard SEXP nodes against garbage collection. In the fake runtime:

- `SEXP` nodes returned from `.Call` entry points are heap-allocated via `std::malloc` inside `allocVector` / `allocMatrix` / `mkChar`. They survive until Python explicitly frees them (via a `free_sexp()` utility the build provides).
- `SEXP` input parameters are pointers to `SEXPREC` nodes constructed by the Python-side caller (e.g., from numpy arrays) before the `.Call` boundary. The fake entry-point wrapper constructs these nodes, passes them in, and frees them after the call returns.
- Arena memory (`R_alloc`, `ALLOC`) is completely separate from SEXP nodes. It is managed by `ArenaFrame` at the `.Call` boundary (Invariant 2).

**`#define` aliases that must be preserved.** The real `Rinternals.h` defines:

```c
#define PROTECT(s)              Rf_protect(s)
#define UNPROTECT(n)            Rf_unprotect(n)
#define UNPROTECT_PTR(s)        Rf_unprotect_ptr(s)
#define PROTECT_WITH_INDEX(x,i) R_ProtectWithIndex(x,i)
#define REPROTECT(x,i)          R_Reprotect(x,i)
#define CHAR(x)                 R_CHAR(x)
#define NA_STRING               R_NaString
```

All of these must be preserved in the fake header so that the original source files compile unchanged. The functions they expand to (`Rf_protect`, `Rf_unprotect`, etc.) are no-ops or simple inline stubs in the fake.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by the `SEXP` typedef itself. `allocVector` and `mkChar` (which produce SEXP values) throw `RError` on allocation failure. The `.Call` wrapper catches `RError`.
- Invariant 2 (arena memory): not triggered by `SEXP` nodes themselves. `SEXP` nodes and their `data` buffers are heap-allocated. The arena governs `R_alloc`/`ALLOC` scratch memory in the same function bodies.
- Invariant 3 (R Interpreter Items): partially triggered. `SEXP` as a type compiles without an interpreter. However, `rpart_callback.c` uses `SEXP` values as arguments to `eval()`, `findVar()`, `install()`, and related functions — those require function pointer bridges documented in the `eval`, `findVar`, and `install` guides.

---

### 4. Fake Implementation Examples

#### Pattern P1: `.Call` Entry-Point Parameter and Return Type

- **Locations:** `init.c:6`, `init.c:7`, `init.c:8`, `pred_rpart.c:133`, `rpart.c:40`, `rpart_callback.c:47`, `rpartexp2.c:43`, `rpartproto.h:39`, `rpartproto.h:57`, `xpred.c:33`

- **Original R API Usage:**

```c
/* init.c:6-10 — forward declarations */
SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x);
SEXP rpartexp2(SEXP dtimes, SEXP seps);
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
        SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
        SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2);

/* rpart.c:40-43 — entry-point definition */
SEXP
rpart(SEXP ncat2, SEXP method2, SEXP opt2,
      SEXP parms2, SEXP xvals2, SEXP xgrp2,
      SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2)
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// Drop-in replacement for Rinternals.h.
// Provides: SEXPTYPE, SEXPREC, SEXP, PROTECT/UNPROTECT, and all
// accessors used by rpart source files.
//
// Include order requirement: this file must be included before
// R_ext/Rdynload.h (i.e., before fake_Rdynload.hpp), because DL_FUNC
// and R_CallMethodDef reference SEXP indirectly through function casts.

#pragma once
#ifndef FAKE_RINTERNALS_H
#define FAKE_RINTERNALS_H

#include <cstdlib>    // std::malloc, std::free
#include <cstring>    // std::memset, std::strlen, std::strcpy
#include <stdexcept>  // std::runtime_error, std::bad_alloc
#include "fake_arena.hpp"   // ArenaFrame, gArenaStack, arena_alloc

// -----------------------------------------------------------------------
// RError — C++ exception replacing Rf_error / longjmp (Invariant 1).
// -----------------------------------------------------------------------
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

// -----------------------------------------------------------------------
// Scalar types used by the R C API
// -----------------------------------------------------------------------
typedef unsigned char  Rbyte;
typedef int            R_len_t;
typedef int            R_xlen_t;   // 64-bit R uses ptrdiff_t; rpart is 32-bit safe
#define R_LEN_T_MAX    INT_MAX

// -----------------------------------------------------------------------
// SEXPTYPE: unsigned int tag constants.
// Reproduced from the non-enum_SEXPTYPE branch of Rinternals.h.
// -----------------------------------------------------------------------
typedef unsigned int SEXPTYPE;

#define NILSXP       0    /* nil = NULL */
#define SYMSXP       1    /* symbols */
#define LISTSXP      2    /* lists of dotted pairs */
#define CLOSXP       3    /* closures */
#define ENVSXP       4    /* environments */
#define PROMSXP      5    /* promises */
#define LANGSXP      6    /* language constructs */
#define SPECIALSXP   7    /* special forms */
#define BUILTINSXP   8    /* builtin non-special forms */
#define CHARSXP      9    /* scalar string (internal only) */
#define LGLSXP      10    /* logical vectors */
/* 11 and 12 were factors in the 1990s — intentionally unassigned */
#define INTSXP      13    /* integer vectors */
#define REALSXP     14    /* real (double) vectors */
#define CPLXSXP     15    /* complex variables */
#define STRSXP      16    /* string vectors */
#define DOTSXP      17    /* dot-dot-dot object */
#define ANYSXP      18    /* any-type marker */
#define VECSXP      19    /* generic vectors (lists) */
#define EXPRSXP     20    /* expression vectors */
#define BCODESXP    21    /* byte code */
#define EXTPTRSXP   22    /* external pointer */
#define WEAKREFSXP  23    /* weak reference */
#define RAWSXP      24    /* raw bytes */
#define OBJSXP      25    /* S4 non-vector */
#define S4SXP       25    /* alias for OBJSXP */
#define NEWSXP      30    /* fresh GC node */
#define FREESXP     31    /* released GC node */
#define FUNSXP      99    /* Closure or Builtin or Special */

// -----------------------------------------------------------------------
// SEXPREC — minimal struct satisfying the observable rpart C API contract.
//
// Real SEXPREC has a 5-bit type field in a packed header word; the fake
// uses a plain int for simplicity. Package source never accesses SEXPREC
// fields directly (USE_RINTERNALS is not defined), so the internal layout
// is irrelevant — only the accessor functions matter.
//
// Heap-allocated via std::malloc; NOT garbage-collected.
// Caller is responsible for freeing via free_sexp() after use.
// -----------------------------------------------------------------------
struct SEXPREC {
    SEXPTYPE  type;    // one of the XSXP constants above
    int       length;  // element count (used by LENGTH(), XLENGTH())
    int       nrow;    // row count for matrices (used by nrows())
    int       ncol;    // column count for matrices (used by ncols())
    void     *data;    // flat element buffer (heap-allocated separately)
};

typedef SEXPREC *SEXP;

// -----------------------------------------------------------------------
// free_sexp — release a SEXP and its data buffer.
// Not part of the real R API; provided for Python-side cleanup.
// For VECSXP and STRSXP, child SEXP elements are freed recursively.
// -----------------------------------------------------------------------
inline void free_sexp(SEXP s) {
    if (!s) return;
    if (s->type == VECSXP || s->type == EXPRSXP) {
        SEXP *elems = static_cast<SEXP *>(s->data);
        for (int i = 0; i < s->length; i++)
            free_sexp(elems[i]);
    }
    std::free(s->data);
    std::free(s);
}

// -----------------------------------------------------------------------
// Element size helper — returns sizeof(element) for each SEXPTYPE.
// -----------------------------------------------------------------------
inline std::size_t sexptype_element_size(SEXPTYPE type) {
    switch (type) {
        case INTSXP:  case LGLSXP:                  return sizeof(int);
        case REALSXP:                                return sizeof(double);
        case CPLXSXP:                                return 2 * sizeof(double);
        case RAWSXP:                                 return sizeof(unsigned char);
        case STRSXP:  case VECSXP:  case EXPRSXP:   return sizeof(SEXP);
        case CHARSXP:                                return sizeof(char);
        default:                                     return sizeof(int);
    }
}

// -----------------------------------------------------------------------
// R_NilValue — the NULL singleton.
// Implemented as a static SEXPREC with type=NILSXP, length=0, data=NULL.
// The real Rinternals.h declares this as LibExtern SEXP R_NilValue.
// -----------------------------------------------------------------------
inline SEXP make_nil_value() {
    static SEXPREC nil_rec = { NILSXP, 0, 0, 0, nullptr };
    return &nil_rec;
}
// R_NilValue is used as a static-initializer-safe global.
// Translation units that include this header get a consistent singleton.
static SEXP R_NilValue = make_nil_value();

// Similarly, R_UnboundValue is used in rpart_callback.c as a sentinel.
inline SEXP make_unbound_value() {
    static SEXPREC unbound_rec = { SYMSXP, 0, 0, 0, nullptr };
    return &unbound_rec;
}
static SEXP R_UnboundValue = make_unbound_value();

#endif // FAKE_RINTERNALS_H
```

- **Arena / Memory Notes:** Not applicable for Pattern P1. `SEXP` as a parameter type allocates nothing. The SEXP nodes that appear as parameters to `.Call` entry points are pre-constructed by the Python-side caller before the call boundary. See Pattern P2 for the allocation of SEXP nodes that are returned.

- **Explanation:**

  The fake defines `struct SEXPREC` with five public fields and `typedef SEXPREC *SEXP`. Every rpart source file that `#include <Rinternals.h>` (directly or through `rpart.h`) will see this definition instead of the real opaque `SEXPREC`. Because none of the rpart source files define `USE_RINTERNALS`, they never access `SEXPREC` fields directly — all field access goes through accessor functions (`INTEGER`, `REAL`, `LENGTH`, etc.), which are defined in the same fake header.

  The `SEXPTYPE` block and tag constants (`INTSXP`, `REALSXP`, `VECSXP`, `STRSXP`, etc.) are defined in the same file. They are already documented in `INTSXP.md` and `REALSXP.md`; they are reproduced here because `SEXP.md` is the authoritative source for the complete `fake_Rinternals.hpp`.

  `R_NilValue` is assigned to `csplit3` as a default value in `rpart.c:64` (`csplit3 = R_NilValue`) and returned from `init_rpcallback` (`return R_NilValue;` at line 71). The fake provides it as a pointer to a static `SEXPREC` with `type=NILSXP`. Since it is a static local, it is initialized once and the same address is returned on every call.

---

#### Pattern P2: Local SEXP Variable for Allocation Result

- **Locations:** `pred_rpart.c:139`, `rpart.c:64`, `rpart.c:327`, `rpart.c:328`, `rpartexp2.c:47`, `xpred.c:63`

- **Original R API Usage:**

```c
/* pred_rpart.c:139 — INTSXP allocation, used as return value */
SEXP where = PROTECT(allocVector(INTSXP, n));
pred_rpart0(INTEGER(dimx), ..., INTEGER(where));
UNPROTECT(1);
return where;

/* rpart.c:64 — multiple SEXP locals, some conditionally allocated */
SEXP which3, cptable3, dsplit3, isplit3, csplit3 = R_NilValue,
    dnode3, inode3;
/* ... then at rpart.c:194: */
which3 = PROTECT(allocVector(INTSXP, n));

/* rpart.c:327-328 — VECSXP output list and STRSXP name vector */
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);
SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));
...
UNPROTECT(1 + nout);
return rlist;

/* rpartexp2.c:47 — INTSXP allocation, returned directly */
SEXP keep = PROTECT(allocVector(INTSXP, n));
Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
UNPROTECT(1);
return keep;

/* xpred.c:63 — REALSXP allocation used as return value */
SEXP predict2;
/* ... then at xpred.c:209: */
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp (continued — allocation, accessors, PROTECT/UNPROTECT)
// These definitions follow the SEXPREC/SEXP typedef block above.

// -----------------------------------------------------------------------
// allocVector — heap-allocates a 1-D SEXP of the requested type and length.
// Both the SEXPREC node and the data buffer use std::malloc (NOT the arena).
// SEXP objects returned from .Call are owned by the Python caller and must
// be freed via free_sexp() after data extraction.
// Throws RError on allocation failure (Invariant 1).
// -----------------------------------------------------------------------
inline SEXP allocVector(SEXPTYPE type, int length) {
    SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!s) throw RError("allocVector: out of memory (SEXPREC)");
    s->type   = type;
    s->length = length;
    s->nrow   = length;
    s->ncol   = 1;
    std::size_t bytes = static_cast<std::size_t>(length)
                        * sexptype_element_size(type);
    if (bytes == 0) bytes = 1;  // std::malloc(0) is implementation-defined
    s->data = std::malloc(bytes);
    if (!s->data) { std::free(s); throw RError("allocVector: out of memory (data)"); }
    std::memset(s->data, 0, bytes);
    return s;
}

// -----------------------------------------------------------------------
// allocMatrix — thin wrapper over allocVector; sets nrow and ncol.
// allocMatrix(REALSXP, nrow, ncol) =>
//   s->type=REALSXP, s->length=nrow*ncol, s->nrow=nrow, s->ncol=ncol
//   s->data = double[nrow*ncol], zero-initialized, column-major layout.
// -----------------------------------------------------------------------
inline SEXP allocMatrix(SEXPTYPE type, int nrow, int ncol) {
    SEXP s = allocVector(type, nrow * ncol);
    s->nrow = nrow;
    s->ncol = ncol;
    return s;
}

// -----------------------------------------------------------------------
// mkChar — creates a CHARSXP from a null-terminated C string.
// Used in rpart.c:331 etc. as SET_STRING_ELT(rname, i, mkChar("which")).
// -----------------------------------------------------------------------
inline SEXP mkChar(const char *str) {
    std::size_t len = std::strlen(str);
    SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!s) throw RError("mkChar: out of memory (SEXPREC)");
    s->type   = CHARSXP;
    s->length = static_cast<int>(len);
    s->nrow   = static_cast<int>(len);
    s->ncol   = 1;
    s->data   = std::malloc(len + 1);
    if (!s->data) { std::free(s); throw RError("mkChar: out of memory (data)"); }
    std::strcpy(static_cast<char *>(s->data), str);
    return s;
}

// -----------------------------------------------------------------------
// PROTECT / UNPROTECT — no-ops in the fake runtime (no GC).
// PROTECT(expr) must evaluate and RETURN expr unchanged (it is an lvalue
// in constructs like `SEXP x = PROTECT(allocVector(...))`).
// UNPROTECT(n) and UNPROTECT_PTR(s) do nothing.
// -----------------------------------------------------------------------
inline SEXP       Rf_protect(SEXP s)          { return s; }
inline void       Rf_unprotect(int /*n*/)     {}
inline void       Rf_unprotect_ptr(SEXP /*s*/) {}
inline void       R_ProtectWithIndex(SEXP /*s*/, int * /*i*/) {}
inline void       R_Reprotect(SEXP /*s*/, int /*i*/) {}

#define PROTECT(s)               Rf_protect(s)
#define UNPROTECT(n)             Rf_unprotect(n)
#define UNPROTECT_PTR(s)         Rf_unprotect_ptr(s)
#define PROTECT_WITH_INDEX(x,i)  R_ProtectWithIndex(x, i)
#define REPROTECT(x,i)           R_Reprotect(x, i)

// -----------------------------------------------------------------------
// Accessor functions — cast sexp->data to the appropriate pointer type.
// -----------------------------------------------------------------------
inline int    *INTEGER(SEXP s) { return static_cast<int    *>(s->data); }
inline int    *LOGICAL(SEXP s) { return static_cast<int    *>(s->data); }
inline double *REAL(SEXP s)    { return static_cast<double *>(s->data); }
inline Rbyte  *RAW(SEXP s)     { return static_cast<Rbyte  *>(s->data); }

// CHAR / R_CHAR — returns the char* stored in a CHARSXP.
inline const char *R_CHAR(SEXP s) { return static_cast<const char *>(s->data); }
#define CHAR(x) R_CHAR(x)

// -----------------------------------------------------------------------
// Scalar coercion — reads element [0] of the data buffer.
// -----------------------------------------------------------------------
inline int    asInteger(SEXP s) { return static_cast<int    *>(s->data)[0]; }
inline double asReal(SEXP s)    { return static_cast<double *>(s->data)[0]; }
inline int    asLogical(SEXP s) { return static_cast<int    *>(s->data)[0]; }

// -----------------------------------------------------------------------
// Length and shape accessors.
// -----------------------------------------------------------------------
inline int LENGTH(SEXP s)      { return s->length; }
inline int XLENGTH(SEXP s)     { return s->length; }
inline int Rf_nrows(SEXP s)    { return s->nrow; }
inline int Rf_ncols(SEXP s)    { return s->ncol; }
#define nrows(x) Rf_nrows(x)
#define ncols(x) Rf_ncols(x)

// -----------------------------------------------------------------------
// TYPEOF — returns the SEXPTYPE tag of a SEXP.
// -----------------------------------------------------------------------
inline int TYPEOF(SEXP s) { return static_cast<int>(s->type); }

// -----------------------------------------------------------------------
// Type predicate helpers (used in rpart_callback.c).
// -----------------------------------------------------------------------
inline int isReal(SEXP s)    { return s->type == REALSXP; }
inline int isInteger(SEXP s) { return s->type == INTSXP; }
inline int isNull(SEXP s)    { return s->type == NILSXP; }

// Rf_* aliases matching Rinternals.h declarations.
inline int Rf_isReal(SEXP s)    { return isReal(s); }
inline int Rf_isInteger(SEXP s) { return isInteger(s); }
inline int Rf_isNull(SEXP s)    { return isNull(s); }

// -----------------------------------------------------------------------
// VECSXP / STRSXP element accessors.
// VECTOR_ELT(x, i) reads element i from a generic vector (VECSXP).
// SET_VECTOR_ELT(x, i, v) writes element i.
// STRING_ELT / SET_STRING_ELT work analogously on STRSXP.
// -----------------------------------------------------------------------
inline SEXP VECTOR_ELT(SEXP s, int i) {
    return static_cast<SEXP *>(s->data)[i];
}
inline SEXP SET_VECTOR_ELT(SEXP s, int i, SEXP v) {
    static_cast<SEXP *>(s->data)[i] = v;
    return v;
}
inline SEXP STRING_ELT(SEXP s, int i) {
    return static_cast<SEXP *>(s->data)[i];
}
inline void SET_STRING_ELT(SEXP s, int i, SEXP v) {
    static_cast<SEXP *>(s->data)[i] = v;
}

// -----------------------------------------------------------------------
// setAttrib / R_NamesSymbol — used in rpart.c:329 to attach a names
// attribute to the output list.  In the fake runtime, attributes are
// not tracked; setAttrib is a no-op that is sufficient because Python
// reads the named elements by position, not by name lookup.
// R_NamesSymbol is a sentinel SEXP; its specific value is irrelevant
// as long as it is a stable non-null pointer.
// -----------------------------------------------------------------------
inline void setAttrib(SEXP /*x*/, SEXP /*name*/, SEXP /*val*/) {}
inline SEXP getAttrib(SEXP /*x*/, SEXP /*name*/) { return R_NilValue; }

inline SEXP make_names_symbol() {
    static SEXPREC sym = { SYMSXP, 0, 0, 0, nullptr };
    return &sym;
}
static SEXP R_NamesSymbol = make_names_symbol();

// -----------------------------------------------------------------------
// PRINTNAME — returns the symbol-name SEXP for a SYMSXP.
// Used in rpart_callback.c:24: CHAR(PRINTNAME(sym)).
// In the fake, if sym->data is a SEXP* pointing to a CHARSXP, return it;
// otherwise return sym itself.  For correctly constructed fake symbols
// (e.g., from the install() fake), sym->data points to the CHARSXP.
// -----------------------------------------------------------------------
inline SEXP PRINTNAME(SEXP s) {
    if (s->type == SYMSXP && s->data)
        return static_cast<SEXP>(s->data);
    return s;
}

// -----------------------------------------------------------------------
// .Call boundary wrapper pattern — required for ALL rpart entry points.
//
// Every function in the rpart .Call table (rpart, xpred, pred_rpart,
// rpartexp2, init_rpcallback) mixes:
//   - SEXP allocations (heap, not arena): allocVector / allocMatrix / mkChar
//   - Scratch allocations via R_alloc / ALLOC (arena, freed at frame exit)
//
// The ArenaFrame RAII guard at entry handles the scratch allocations.
// The returned SEXP is heap-allocated and must outlive the ArenaFrame.
//
// Template (for pred_rpart as a representative example):
//
//   extern "C" SEXP pred_rpart_wrapper(
//           SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
//           SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
//           SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2) {
//       ArenaFrame _frame;   // frees R_alloc scratch allocations on exit
//       try {
//           return pred_rpart(dimx, nnode, nsplit, dimc, nnum, nodes2,
//                             vnum, split2, csplit2, usesur, xdata2, xmiss2);
//       } catch (const RError &e) {
//           set_python_error(e.what());  // store message for Python to read
//           return R_NilValue;           // signal failure to caller
//       }
//   }
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:**

  `SEXP` nodes and their `data` buffers are **heap-allocated** via `std::malloc`. They are not arena-managed. The reason is that the SEXP objects produced inside `rpart()`, `xpred()`, `pred_rpart()`, and `rpartexp2()` are the return values of those functions and must outlive the function frame. If they were arena-allocated, they would be destroyed when `ArenaFrame` destructs at the `.Call` boundary — before Python reads the data.

  The arena (`fake_arena.hpp`) exclusively governs memory allocated by `R_alloc(n, size)` and the `ALLOC(a,b)` macro (defined in `rpart.h` as `R_alloc(a,b)`). In `rpart.c` these scratch arrays include `rp.ydata`, `rp.xdata`, `rp.sorts`, `rp.lwt`, `rp.rwt`, `savesort`, and many others. They are allocated during the body of `rpart()` and are not returned; they are safe to free at `ArenaFrame` destruction.

  The interleaving in `rpart.c` is: `allocMatrix(REALSXP, ...)` (heap, SEXP) followed immediately by `ALLOC(n, sizeof(...))` (arena, scratch). These two allocators are completely independent; destroying the arena does not affect heap-allocated SEXPs.

  If either `std::malloc` call inside `allocVector` fails, a `RError` is thrown. The `.Call` boundary wrapper catches it, stores the error message where Python can read it, and returns `R_NilValue` as a sentinel.

- **Explanation:**

  For `rpart.c:64`, the declaration `SEXP which3, cptable3, ..., csplit3 = R_NilValue, dnode3, inode3;` initializes `csplit3` to the nil singleton (a valid `SEXP` pointer to the static `SEXPREC` with `type=NILSXP`) and leaves the others uninitialized. The fake does not change this — the original initialization `= R_NilValue` compiles correctly because `R_NilValue` is a `SEXP` (pointer) value in the fake, not a macro or integer. The subsequent conditional `if (catcount > 0) { csplit3 = PROTECT(allocMatrix(INTSXP, ...)); }` then overwrites `csplit3` with a real allocation or leaves it as `R_NilValue`.

  For `rpart.c:327-328`, the `VECSXP` list `rlist` and `STRSXP` name vector `rname` are allocated by `allocVector(VECSXP, nout)` and `allocVector(STRSXP, nout)`. Both produce a `SEXPREC` whose `data` field is `SEXP[nout]` (a `void *` pointing to `nout` SEXP slots, initialized to `nullptr`). `SET_VECTOR_ELT(rlist, i, child)` writes `child` into slot `i`. `SET_STRING_ELT(rname, i, mkChar("name"))` writes a `CHARSXP` into slot `i`. The Python-side caller reads `VECTOR_ELT(rlist, i)` to extract each component SEXP.

  `PROTECT(allocVector(...))` expands to `Rf_protect(allocVector(...))` which is the identity function — it returns the `SEXP` produced by `allocVector` unchanged. The surrounding `SEXP x = PROTECT(allocVector(...))` is equivalent to `SEXP x = allocVector(...)` in the fake runtime.

---

#### Pattern P3: Static SEXP Global for Interpreter Objects

- **Locations:** `rpart_callback.c:33`, `rpart_callback.c:34`, `rpart_callback.c:35`

- **Original R API Usage:**

```c
/* rpart_callback.c:33-35 */
static SEXP expr1;   /* the evaluation expression for splits */
static SEXP expr2;   /* the evaluation expression for values */
static SEXP rho;     /* the environment in which to evaluate */

/* rpart_callback.c:53-57 — set by init_rpcallback */
rho   = rhox;
expr1 = expr1x;
expr2 = expr2x;

/* rpart_callback.c:112 — used in callback body */
value = eval(expr2, rho);
```

- **C++ Fake Implementation:**

```cpp
// rpart_callback.c compiles without modification using fake_Rinternals.hpp.
// The static SEXP globals are declared as SEXP (i.e., SEXPREC *), which is
// a plain pointer. They are initialized to nullptr (zero-initialized static
// storage in C). The assignment rho = rhox; expr1 = expr1x; expr2 = expr2x;
// stores whatever pointer Python passed in.
//
// In the fake runtime, these variables hold either nullptr (uninitialized)
// or a pointer to a SEXPREC constructed on the Python side to represent an
// opaque R object handle.
//
// The critical point: the eval(expr1, rho) calls at lines 112 and 146 are
// NOT reached through the standard Python->rpart entry path unless the
// user-defined splitting method (method=4) is active.  eval() must be
// provided as a Category E stub.  See the 'eval' and 'findVar' fake guides.
//
// No additional fake code is needed for Pattern P3 beyond the SEXP typedef:
// static SEXP expr1;  declares a zero-initialized SEXP pointer — valid C++.
```

- **Arena / Memory Notes:** Not applicable. Static SEXP globals are pointer variables on the module's BSS segment. They point to SEXP nodes whose memory is managed by the Python caller (for input SEXPs) or the functions that produce them. No arena interaction.

- **Explanation:**

  The three static globals `expr1`, `expr2`, and `rho` are declared as `SEXP` (i.e., `SEXPREC *`). In C and C++, static variables with no explicit initializer are zero-initialized, so they start as `nullptr`. When `init_rpcallback()` is called (via Python's `ctypes`), it assigns `rho = rhox` etc., copying the SEXP pointer value. The SEXP type definition alone is sufficient for this to compile and for the assignment to work — no allocator, no accessor, and no interpreter item is required by the declaration and assignment themselves. The `eval()` call at line 112 is the only place where the interpreter is actually needed; that is a separate Category E item.

---

#### Pattern P4: Local SEXP Temporary for `eval()` Result

- **Locations:** `rpart_callback.c:51`, `rpart_callback.c:92`, `rpart_callback.c:131`

- **Original R API Usage:**

```c
/* rpart_callback.c:51 — in init_rpcallback */
SEXP stemp;
stemp = R_getVar(install("yback"), rho, FALSE);
ydata = REAL(stemp);

/* rpart_callback.c:92-119 — in rpart_callback1 */
SEXP value;
value = eval(expr2, rho);
if (!isReal(value))
    error(_("return value not a vector"));
if (LENGTH(value) != (1 + rsave))
    error(_("returned value is the wrong length"));
double *dptr = REAL(value);

/* rpart_callback.c:131-150 — in rpart_callback2 */
SEXP goodness;
goodness = eval(expr1, rho);
if (!isReal(goodness))
    error(_("the expression expr1 did not return a list!"));
int j = LENGTH(goodness);
double *dptr = REAL(goodness);
```

- **C++ Fake Implementation:**

```cpp
// The SEXP declarations (SEXP stemp; SEXP value; SEXP goodness;) compile
// correctly with fake_Rinternals.hpp — they declare a SEXPREC* local
// variable initialized to an indeterminate value (not zero, since these
// are non-static locals).  No extra fake code is needed for the
// declaration itself.
//
// The runtime paths through eval() require the Category E function-pointer
// bridge.  The fake eval stub (from the 'eval' guide) is:
//
//   typedef SEXP (*eval_fn_t)(SEXP expr, SEXP rho);
//   static eval_fn_t g_eval_fn = nullptr;
//
//   extern "C" void register_eval_fn(eval_fn_t fn) { g_eval_fn = fn; }
//
//   inline SEXP eval(SEXP expr, SEXP rho) {
//       if (!g_eval_fn)
//           throw RError("eval: Python callback not registered. "
//                        "User-defined splits (method=4) require "
//                        "registration via register_eval_fn().");
//       return g_eval_fn(expr, rho);
//   }
//   #define Rf_eval eval
//
// Similarly, R_getVar / findVar / install require their own Category E
// stubs (see the 'findVar', 'findVarInFrame', 'install', and 'R_getVar'
// fake guides).
//
// The .Call entry-point wrapper for init_rpcallback must catch RError
// from the R_getVar call path if the Python pointer is not registered:
//
//   extern "C" SEXP init_rpcallback_wrapper(
//           SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x) {
//       ArenaFrame _frame;
//       try {
//           return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
```

- **Python Interop Notes:**

  The callback paths in `rpart_callback.c` (lines 92–119 for `rpart_callback1`, lines 131–172 for `rpart_callback2`) are only exercised when `method=4` (user-defined splits) is passed to `rpart()`. The standard methods (anova, poisson, class, exp) use the built-in evaluation functions in `func_table.h` and never call `eval()`. For all standard use cases, the `SEXP value` and `SEXP goodness` local variables are never assigned, and the `eval()` stub is never invoked.

  For user-defined splits, Python must register an `eval` callback before calling `rpart()` with `method=4`. The C++ stub and Python registration code are shown in the `eval` fake guide. The `SEXP` type definition documented here is a prerequisite but contains no callback-specific logic.

- **Arena / Memory Notes:** Not applicable. Local `SEXP` variables are pointer variables on the stack. Their value is a pointer to a SEXP node produced by `eval()` (heap-allocated by the Python-side callback) or by `R_getVar` (heap-allocated by the Python-side `findVar` callback). The stack slot itself requires no allocation.

- **Explanation:**

  The declarations `SEXP stemp;`, `SEXP value;`, and `SEXP goodness;` require only the `SEXP` typedef to compile. The subsequent assignments (`stemp = R_getVar(...)`, `value = eval(expr2, rho)`) require the `R_getVar` and `eval` stubs from their respective Category E guides. The downstream accessors `REAL(value)`, `LENGTH(value)`, `isReal(value)`, and `error(...)` all operate on the returned SEXP using the standard inline functions defined in `fake_Rinternals.hpp` — no special handling is needed for the SEXP type itself.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `fake_arena.hpp` (no separate guide exists; generated once as a foundation) | The `ArenaFrame` RAII struct, `gArenaStack` thread-local vector, `arena_alloc()`, and `arena_calloc()`. Required by the `.Call` entry-point wrappers for `rpart()`, `xpred()`, `pred_rpart()`, `rpartexp2()`, and `init_rpcallback()`, all of which use `ALLOC`/`R_alloc` in their function bodies. `SEXP` itself does not use the arena, but every function that accepts SEXP parameters also performs arena allocations. |
| `INTSXP.md` | Establishes the `SEXPTYPE` constant block (`#define INTSXP 13`, etc.) that is embedded in `fake_Rinternals.hpp`. The `allocVector(INTSXP, n)` pattern at `pred_rpart.c:139`, `rpart.c:194`, and `rpartexp2.c:47` requires `INTSXP=13` to be defined before `allocVector` is called. |
| `REALSXP.md` | Establishes `#define REALSXP 14` within the same `SEXPTYPE` block. Required by `allocMatrix(REALSXP, ...)` calls in `rpart.c:241`, `rpart.c:261`, `rpart.c:269`, and `allocVector(REALSXP, ...)` in `xpred.c:209`. |
| `Rboolean.md` | Establishes `typedef enum { FALSE = 0, TRUE = 1 } Rboolean` in `fake_Boolean.hpp`. Required because `rpart_callback.c` calls `R_getVar(install("yback"), rho, FALSE)` where `FALSE` is a `Rboolean`. `fake_Boolean.hpp` must be included before `fake_Rinternals.hpp` (or within it) so that `Rboolean` is defined when `Rinternals.h` function signatures that use it (e.g., `Rf_asRboolean`) are parsed. |
| `DL_FUNC.md` and `R_CallMethodDef.md` | Establish `typedef void *(*DL_FUNC)(void)` and `struct R_CallMethodDef` in `fake_Rdynload.hpp`. Required by `init.c` which includes `R_ext/Rdynload.h` and uses `DL_FUNC` casts and `R_CallMethodDef` table entries. `fake_Rdynload.hpp` must be included after `fake_Rinternals.hpp` because `R_CallMethodDef.fun` is typed `DL_FUNC` — a generic function pointer — while the cast targets in `init.c` are SEXP-bearing functions whose type is now visible through `fake_Rinternals.hpp`. |
| `DllInfo.md` | Establishes the no-op `struct DllInfo` stub in `fake_Rdynload.hpp`. Required by `R_init_rpart(DllInfo *dll)` in `init.c`. Depends on `fake_Rinternals.hpp` being present first. |
| `eval` fake guide (not yet generated — Category E) | The `eval(SEXP expr, SEXP rho)` function pointer stub. Required by `rpart_callback.c:112` and `rpart_callback.c:146`. Without it, Pattern P4 code paths at runtime throw `RError("eval: Python callback not registered")`. The `SEXP` type itself (this guide) is a prerequisite for the `eval` guide. |
| `findVar` / `findVarInFrame` fake guide (not yet generated — Category E) | Required by `compat_getVar` in `rpart_callback.c:22` (guarded by `R_VERSION < R_Version(4,5,0)`). The `Rboolean` guide already documents this dependency. Again, the `SEXP` type definition here is a prerequisite. |
| `install` fake guide (not yet generated — Category E) | Required by `install("yback")` etc. in `rpart_callback.c:59–69`. Again, `SEXP` (this guide) is a prerequisite for the `install` stub. |
| `Rversion.h` / `fake_Rversion.hpp` (not yet generated) | Required because `init.c:27` and `rpart_callback.c:8` include `<Rversion.h>` and use `R_VERSION` / `R_Version(major, minor, patch)`. The fake must define these macros such that `R_VERSION < R_Version(4, 5, 0)` evaluates to true (so the `compat_getVar` shim is compiled and `R_getVar` is defined as a macro). |
