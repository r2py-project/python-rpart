# Fake Header Implementation Guide: `allocVector`

---

### 1. Overview of `allocVector` in R API

`allocVector` is a C API function declared in `Rinternals.h` as `SEXP Rf_allocVector(SEXPTYPE type, R_xlen_t length)` and exposed to package source via the macro alias `#define allocVector Rf_allocVector`. It allocates a one-dimensional R vector object: a heap-managed `SEXPREC` node whose `data` field points to a flat, contiguous buffer of `length` elements of the scalar type indicated by `type` (`INTSXP` for `int`, `REALSXP` for `double`, `STRSXP` for `SEXP[]` string slots, `VECSXP` for `SEXP[]` list slots). The returned `SEXP` is the canonical 1-D R vector; accessor functions `INTEGER(s)`, `REAL(s)`, `STRING_ELT(s,i)`, and `VECTOR_ELT(s,i)` provide typed access to its elements. In the fake runtime, `allocVector` is an `inline` C++ function that allocates the `SEXPREC` node and element data buffer via `std::malloc`, zero-initializes the data, sets `s->type`, `s->length`, `s->nrow`, and `s->ncol`, and returns the pointer; no garbage collector, no R runtime, and no `libR.so` are involved.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context window read | Usage |
|---|---|---|---|
| `pred_rpart.c` | 139 | Lines 124–155 | `SEXP where = PROTECT(allocVector(INTSXP, n));` — sole allocation in function; result passed to `INTEGER(where)`, returned directly |
| `rpart.c` | 194 | Lines 179–210 | `which3 = PROTECT(allocVector(INTSXP, n));` — first allocation in `rpart()`; result accessed via `INTEGER(which3)` |
| `rpart.c` | 327 | Lines 312–349 | `SEXP rlist = PROTECT(allocVector(VECSXP, nout));` — output container list; nout is 6 or 7 |
| `rpart.c` | 328 | Lines 312–349 | `SEXP rname = allocVector(STRSXP, nout);` — names string vector; not wrapped in PROTECT |
| `rpartexp2.c` | 47 | Lines 32–51 | `SEXP keep = PROTECT(allocVector(INTSXP, n));` — sole allocation; result passed to `INTEGER(keep)`, returned directly |
| `xpred.c` | 209 | Lines 194–225 | `predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));` — large real output buffer; accessed via `REAL(predict2)` |

**C types of arguments and return values.**

- `type` (first argument): `SEXPTYPE` (defined as `typedef unsigned int SEXPTYPE`). Values used across the CSV: `INTSXP` (13), `REALSXP` (14), `STRSXP` (16), `VECSXP` (19).
- `length` (second argument): `R_xlen_t` in the real API (treated as `int` in rpart, which is 32-bit safe). Values are runtime-computed integers: `n`, `n * ncp * nresp`, `nout`.
- Return value: `SEXP` (`SEXPREC *`). Always assigned to a local `SEXP` variable, usually (but not always) wrapped in `PROTECT`.

**Co-occurring R API items.**

- `PROTECT` / `UNPROTECT` — five of the six `allocVector` calls are wrapped in `PROTECT`. The single unprotected call is `rpart.c:328` (`rname = allocVector(STRSXP, nout)`), which is immediately passed to `setAttrib` and then populated slot-by-slot via `SET_STRING_ELT`. In the fake runtime, `PROTECT` is a no-op identity (see `PROTECT.md`).
- `INTEGER(sexp)` — applied to every `INTSXP` result (`where`, `which3`, `keep`) to obtain a writable `int *` into the data buffer.
- `REAL(sexp)` — applied to the `REALSXP` result (`predict2`) to obtain a `double *` into the data buffer.
- `VECTOR_ELT` / `SET_VECTOR_ELT` — used on the `VECSXP` result (`rlist`) to read and write child SEXP slots.
- `SET_STRING_ELT` / `mkChar` — used on the `STRSXP` result (`rname`) to assign CHARSXP elements.
- `setAttrib(rlist, R_NamesSymbol, rname)` — attaches `rname` as the `names` attribute of `rlist`. In the fake runtime this is a no-op.
- `ALLOC` / `R_alloc` — used in the same function bodies (`rpart.c`, `xpred.c`) for arena-backed scratch arrays; independent of SEXP allocations.
- `allocMatrix` — a thin wrapper over `allocVector` that sets `nrow` and `ncol` in addition to `length`; defined in `allocMatrix.md`.
- `LENGTH(sexp)` — used in `rpartexp2.c:46` to compute `n` before calling `allocVector`.
- `asReal(eps)`, `asInteger(dimx)` — scalar extraction from SEXP parameters, used in the same function bodies as `allocVector`.

**Distinct implementation patterns across CSV rows.**

| Pattern | CSV rows | SEXPTYPE | Length expression | Accessor | PROTECT? |
|---|---|---|---|---|---|
| P1: 1-D INTSXP vector | `pred_rpart.c:139`, `rpart.c:194`, `rpartexp2.c:47` | `INTSXP` (13) | `n` | `INTEGER(s)` | Yes |
| P2: 1-D REALSXP vector | `xpred.c:209` | `REALSXP` (14) | `n * ncp * nresp` | `REAL(s)` | Yes |
| P3: 1-D VECSXP list | `rpart.c:327` | `VECSXP` (19) | `nout` (6 or 7) | `SET_VECTOR_ELT` / `VECTOR_ELT` | Yes |
| P4: 1-D STRSXP vector (no PROTECT) | `rpart.c:328` | `STRSXP` (16) | `nout` (6 or 7) | `SET_STRING_ELT` / `STRING_ELT` | No |

All four patterns share an identical fake mechanism: a single `allocVector` inline function dispatches element sizing through `sexptype_element_size(type)` and allocates both the `SEXPREC` node and the element data buffer via `std::malloc`. The patterns differ only in the SEXPTYPE tag and which accessor is subsequently applied to the result.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function.**

`allocVector` creates a heap-allocated `SEXPREC` node whose data buffer holds `length` contiguous elements of the type specified by the `SEXPTYPE` argument. It falls squarely in Category C because its primary role is to produce a heap-allocated SEXP object with an element data buffer.

**Chosen mechanism.**

`allocVector` is implemented as an `inline` C++ function (`Rf_allocVector`) that:

1. Allocates the `SEXPREC` node via `std::malloc(sizeof(SEXPREC))`.
2. Sets `s->type = type`, `s->length = length`, `s->nrow = length`, `s->ncol = 1`.
3. Computes the data buffer size as `length * sexptype_element_size(type)`.
4. Allocates the data buffer via `std::malloc(bytes)`.
5. Zero-initializes the data buffer with `std::memset(s->data, 0, bytes)` (matching R's semantics).
6. Returns the `SEXP`.

The `#define allocVector Rf_allocVector` alias from `Rinternals.h` line 896 is reproduced in the fake header so that all six call sites in the rpart source files compile without modification.

**Memory allocation model.**

Both the `SEXPREC` node and the element data buffer are **heap-allocated** via `std::malloc` — they are **not** arena-allocated. This is correct because every `allocVector` result in the rpart source is either:
- A return value from a `.Call` entry point (`where`, `keep`, `predict2`, `rlist`), which must outlive the `.Call` frame and be consumed by Python after the function returns, or
- A component packed into the returned VECSXP list (`which3`, `rname`, and all `allocMatrix` results), which must likewise outlive the frame.

If any SEXP were arena-allocated, it would be destroyed when the `ArenaFrame` RAII guard destructs at the `.Call` wrapper boundary — before Python has read the data. The arena (`fake_arena.hpp`) exclusively governs memory allocated by `R_alloc`/`ALLOC` scratch arrays in the same function bodies; it has no interaction with heap-allocated SEXP nodes.

**Failure handling (Invariant 1).**

If either `std::malloc` call inside `Rf_allocVector` returns `nullptr`, a `RError` exception is thrown — a subclass of `std::runtime_error`. No `longjmp`, `setjmp`, `abort()`, or `Rf_error`/`error()` is used. The `.Call` boundary wrapper catches `RError` and communicates the failure to Python. Before throwing on data-buffer failure, the already-allocated `SEXPREC` node is freed to prevent a memory leak.

**ArenaFrame requirement (Invariant 2).**

Because all four entry points that call `allocVector` (`pred_rpart`, `rpart`, `rpartexp2`, `xpred`) also call `ALLOC`/`R_alloc` for scratch arrays, the `.Call` wrapper for each must declare an `ArenaFrame` guard at entry. The guard frees scratch arrays on exit. It does not affect heap-allocated SEXP nodes.

**`#define` alias that must be preserved.**

The real `Rinternals.h` at line 896 defines:

```c
#define allocVector    Rf_allocVector
```

This alias must be reproduced in the fake header. Every call site in the rpart source files spells the function as `allocVector` (not `Rf_allocVector`), so the alias is required for unchanged compilation.

---

### 4. Fake Implementation Examples

#### Pattern P1: Allocate 1-D INTSXP Vector

- **Locations:** `pred_rpart.c:139`, `rpart.c:194`, `rpartexp2.c:47`

- **Original R API Usage:**

```c
/* pred_rpart.c:133-147 */
SEXP
pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
           SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
           SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2)
{
    int n = asInteger(dimx);
    SEXP where = PROTECT(allocVector(INTSXP, n));
    pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit),
                INTEGER(dimc), INTEGER(nnum), INTEGER(nodes2),
                INTEGER(vnum), REAL(split2), INTEGER(csplit2),
                INTEGER(usesur), REAL(xdata2), INTEGER(xmiss2),
                INTEGER(where));
    UNPROTECT(1);
    return where;
}

/* rpart.c:194-195 */
which3 = PROTECT(allocVector(INTSXP, n));
rp.which = INTEGER(which3);

/* rpartexp2.c:43-51 */
SEXP
rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);
    return keep;
}
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp — allocVector definition
// Prerequisites: SEXPREC, SEXP, SEXPTYPE, INTSXP, RError,
//                sexptype_element_size, and fake_arena.hpp must be defined
//                before this section (all established in SEXP.md).

#include <cstdlib>    // std::malloc, std::free
#include <cstring>    // std::memset
#include <stdexcept>  // std::runtime_error (base of RError)
#include "fake_arena.hpp"   // ArenaFrame — governs R_alloc/ALLOC scratch arrays

// -----------------------------------------------------------------------
// RError — C++ exception replacing Rf_error / longjmp (Invariant 1).
// Defined once in fake_Rinternals.hpp; shown here for reference.
// -----------------------------------------------------------------------
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

// -----------------------------------------------------------------------
// sexptype_element_size — maps SEXPTYPE to sizeof(element).
// Used by Rf_allocVector to compute the data buffer byte count.
// Defined once in fake_Rinternals.hpp; reproduced here for clarity.
// -----------------------------------------------------------------------
inline std::size_t sexptype_element_size(SEXPTYPE type) {
    switch (type) {
        case INTSXP:  case LGLSXP:                  return sizeof(int);
        case REALSXP:                                return sizeof(double);
        case CPLXSXP:                                return 2 * sizeof(double);
        case RAWSXP:                                 return sizeof(unsigned char);
        case STRSXP:  case VECSXP:  case EXPRSXP:   return sizeof(SEXP);
        default:                                     return sizeof(int);
    }
}

// -----------------------------------------------------------------------
// Rf_allocVector — heap-allocates a 1-D SEXP of the given type and length.
//
// For INTSXP (used in Pattern P1):
//   s->type   = INTSXP (13)
//   s->length = n
//   s->nrow   = n      (default for 1-D vectors; overwritten by allocMatrix)
//   s->ncol   = 1
//   s->data   = int[n], zero-initialized via std::memset
//
// INTEGER(s) returns (int *)s->data.
//
// Both the SEXPREC node and the int[] data buffer are heap-allocated via
// std::malloc.  Neither participates in the arena: SEXP objects returned
// from .Call functions are owned by the Python caller, which calls
// free_sexp() after extracting the data.
//
// Throws RError on allocation failure (Invariant 1).
// No longjmp, setjmp, abort(), or Rf_error() is used.
// -----------------------------------------------------------------------
inline SEXP Rf_allocVector(SEXPTYPE type, int length) {
    SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!s) throw RError("allocVector: out of memory allocating SEXPREC");
    s->type   = type;
    s->length = length;
    s->nrow   = length;  // 1-D default; allocMatrix overwrites with true nrow
    s->ncol   = 1;
    std::size_t bytes = static_cast<std::size_t>(length)
                        * sexptype_element_size(type);
    if (bytes == 0) bytes = 1;  // std::malloc(0) is implementation-defined
    s->data = std::malloc(bytes);
    if (!s->data) {
        std::free(s);   // prevent leak before throwing
        throw RError("allocVector: out of memory allocating data buffer");
    }
    std::memset(s->data, 0, bytes);  // zero-initialize (matches R semantics)
    return s;
}

// Macro alias matching real Rinternals.h line 896.
#define allocVector    Rf_allocVector

// -----------------------------------------------------------------------
// INTEGER accessor — casts sexp->data to int *.
// Used immediately after allocVector(INTSXP, n) to obtain the writable
// int buffer.  Defined once; shown here for Pattern P1 context.
// -----------------------------------------------------------------------
inline int *INTEGER(SEXP s) {
    return static_cast<int *>(s->data);
}

// -----------------------------------------------------------------------
// .Call boundary wrapper for pred_rpart (Pattern P1 representative).
// ArenaFrame _frame governs all R_alloc / ALLOC scratch allocations inside
// pred_rpart0 and related helpers.  The heap-allocated SEXP 'where' is
// returned to Python and freed by the caller via free_sexp() after use.
// -----------------------------------------------------------------------
extern "C" SEXP pred_rpart_wrapper(
        SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
        SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
        SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2) {
    ArenaFrame _frame;   // frees R_alloc scratch arrays on exit
    try {
        return pred_rpart(dimx, nnode, nsplit, dimc, nnum, nodes2,
                          vnum, split2, csplit2, usesur, xdata2, xmiss2);
    } catch (const RError &e) {
        set_python_error(e.what());  // store message for Python to read
        return R_NilValue;           // signal failure to Python caller
    }
}

// .Call boundary wrapper for rpartexp2 (Pattern P1 representative).
extern "C" SEXP rpartexp2_wrapper(SEXP dtimes, SEXP eps) {
    ArenaFrame _frame;
    try {
        return rpartexp2(dtimes, eps);
    } catch (const RError &e) {
        set_python_error(e.what());
        return R_NilValue;
    }
}
```

- **Arena / Memory Notes:**

  The `SEXPREC` node and the `int[n]` data buffer for `where`, `which3`, and `keep` are **heap-allocated** via `std::malloc` inside `Rf_allocVector`. They are not arena-managed.

  `where` and `keep` are the return values of `pred_rpart` and `rpartexp2` respectively; they must outlive the `.Call` frame and be freed by Python via `free_sexp()` after data extraction. `which3` in `rpart.c` is packed into `rlist` via `SET_VECTOR_ELT(rlist, 0, which3)` at line 330; it is freed recursively when Python calls `free_sexp(rlist)`.

  The `ArenaFrame _frame` declared at each `.Call` wrapper entry governs only `R_alloc`/`ALLOC` scratch arrays (e.g., `rp.sorts`, `rp.csplit`, `savesort` in `rpart.c`). When `_frame` destructs at wrapper return, those scratch arrays are freed; the heap-allocated SEXP nodes are unaffected.

  If `std::malloc` fails for the `SEXPREC` node, `RError` is thrown immediately (no partial state). If it fails for the data buffer, the already-allocated `SEXPREC` is freed before throwing. The `.Call` boundary `catch (const RError &e)` block handles both cases.

- **Explanation:**

  `allocVector(INTSXP, n)` expands via `#define allocVector Rf_allocVector` to `Rf_allocVector(INTSXP, n)`. The fake `Rf_allocVector` allocates a `SEXPREC` with `type = INTSXP`, `length = n`, `nrow = n`, `ncol = 1`, and a zero-initialized `int[n]` data buffer. The returned `SEXP` is passed through `PROTECT` (which is `Rf_protect`, an identity function) and assigned to the local `SEXP` variable. `INTEGER(where)` then casts `where->data` to `int *`. `UNPROTECT(1)` calls `Rf_unprotect(1)`, an empty inline function. No source file modification is required.

---

#### Pattern P2: Allocate 1-D REALSXP Vector

- **Locations:** `xpred.c:209`

- **Original R API Usage:**

```c
/* xpred.c:63 — declaration at top of xpred() */
SEXP predict2;

/* xpred.c:205-210 — allocation after computing nresp */
if (asInteger(all2) == 1)
    nresp = rp.num_resp;
else
    nresp = 1;
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp — allocVector handles REALSXP via the same
// Rf_allocVector function defined in Pattern P1.
// No additional code is required for the REALSXP type path.
//
// For REALSXP (Pattern P2):
//   s->type   = REALSXP (14)
//   s->length = n * ncp * nresp
//   s->nrow   = n * ncp * nresp
//   s->ncol   = 1
//   s->data   = double[n * ncp * nresp], zero-initialized
//
// sexptype_element_size(REALSXP) returns sizeof(double) = 8.
// Total bytes = (n * ncp * nresp) * 8.

// -----------------------------------------------------------------------
// REAL accessor — casts sexp->data to double *.
// Used immediately after allocVector(REALSXP, ...) to obtain the writable
// double buffer.
// -----------------------------------------------------------------------
inline double *REAL(SEXP s) {
    return static_cast<double *>(s->data);
}

// -----------------------------------------------------------------------
// .Call boundary wrapper for xpred (Pattern P2 representative).
// -----------------------------------------------------------------------
extern "C" SEXP xpred_wrapper(
        SEXP ncat2, SEXP method2, SEXP opt2,
        SEXP parms2, SEXP xvals2, SEXP xgrp2,
        SEXP ymat2, SEXP xmat2, SEXP wt2,
        SEXP ny2, SEXP cost2, SEXP all2, SEXP cp2,
        SEXP toprisk2, SEXP nresp2) {
    ArenaFrame _frame;   // frees ALLOC / R_alloc scratch arrays on exit
    try {
        return xpred(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                     ymat2, xmat2, wt2, ny2, cost2, all2, cp2,
                     toprisk2, nresp2);
    } catch (const RError &e) {
        set_python_error(e.what());
        return R_NilValue;
    }
}
```

- **Arena / Memory Notes:**

  `predict2` is the return value of `xpred()`. The `SEXPREC` node and `double[n * ncp * nresp]` data buffer are **heap-allocated** via `std::malloc`. For large inputs (many cross-validation folds, many response variables), this buffer can be substantial in size; `std::malloc` is used throughout regardless of size, consistent with all other SEXP allocations.

  The `xpred()` function also uses `ALLOC`/`R_alloc` for scratch arrays (e.g., `savesort`, cp rescaling buffer). These are arena-managed and freed when `ArenaFrame _frame` destructs at `xpred_wrapper` return. The heap-allocated `predict2` SEXP is unaffected.

  If `n * ncp * nresp` overflows an `int`, the result is undefined behavior in the original C source — the fake replicates this behavior since `Rf_allocVector` takes the length as an `int` and the product is computed in the caller.

- **Explanation:**

  `allocVector(REALSXP, n * ncp * nresp)` expands to `Rf_allocVector(REALSXP, n * ncp * nresp)`. Inside `Rf_allocVector`, `sexptype_element_size(REALSXP)` returns `sizeof(double)` = 8, so `bytes = (n * ncp * nresp) * 8`. The `SEXPREC` fields are set with `type = REALSXP`, `length = n * ncp * nresp`, `nrow = n * ncp * nresp`, `ncol = 1`. `REAL(predict2)` then casts `predict2->data` to `double *`. The `PROTECT` wrapper is identity; the preceding `SEXP predict2;` declaration at `xpred.c:63` declares a local `SEXPREC *` variable that is later populated by the `allocVector` call at line 209. No source file modification is required.

---

#### Pattern P3: Allocate 1-D VECSXP Generic List

- **Locations:** `rpart.c:327`

- **Original R API Usage:**

```c
/* rpart.c:325-349 */
int nout = catcount > 0 ? 7 : 6;
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);          /* Pattern P4 — see below */
setAttrib(rlist, R_NamesSymbol, rname);
SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable"));
SET_VECTOR_ELT(rlist, 2, dsplit3);
SET_STRING_ELT(rname, 2, mkChar("dsplit"));
SET_VECTOR_ELT(rlist, 3, isplit3);
SET_STRING_ELT(rname, 3, mkChar("isplit"));
SET_VECTOR_ELT(rlist, 4, dnode3);
SET_STRING_ELT(rname, 4, mkChar("dnode"));
SET_VECTOR_ELT(rlist, 5, inode3);
SET_STRING_ELT(rname, 5, mkChar("inode"));
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
}
UNPROTECT(1 + nout);
return rlist;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp — allocVector handles VECSXP via the same
// Rf_allocVector function defined in Pattern P1.
// No additional code is required for the VECSXP type path in Rf_allocVector.
//
// For VECSXP (Pattern P3):
//   s->type   = VECSXP (19)
//   s->length = nout   (6 or 7)
//   s->nrow   = nout
//   s->ncol   = 1
//   s->data   = SEXP[nout], zero-initialized (all slots are nullptr initially)
//
// sexptype_element_size(VECSXP) returns sizeof(SEXP) = sizeof(SEXPREC *) = 8.
// Total bytes = nout * 8.
//
// SET_VECTOR_ELT(rlist, i, child_sexp) writes child_sexp into
// ((SEXP *)rlist->data)[i].
// VECTOR_ELT(rlist, i) reads that slot back.

// -----------------------------------------------------------------------
// VECTOR_ELT — reads element i from a VECSXP.
// -----------------------------------------------------------------------
inline SEXP VECTOR_ELT(SEXP s, int i) {
    return static_cast<SEXP *>(s->data)[i];
}

// -----------------------------------------------------------------------
// SET_VECTOR_ELT — writes element i of a VECSXP; returns the child SEXP.
// -----------------------------------------------------------------------
inline SEXP SET_VECTOR_ELT(SEXP s, int i, SEXP v) {
    static_cast<SEXP *>(s->data)[i] = v;
    return v;
}

// -----------------------------------------------------------------------
// setAttrib — no-op in the fake runtime.
// In real R, setAttrib(rlist, R_NamesSymbol, rname) attaches rname as
// the names attribute of rlist.  Python reads elements by position via
// VECTOR_ELT / INTEGER / REAL, not by name lookup, so attribute tracking
// is unnecessary.
// -----------------------------------------------------------------------
inline void setAttrib(SEXP /*x*/, SEXP /*name*/, SEXP /*val*/) {}

// -----------------------------------------------------------------------
// free_sexp — recursively frees a SEXP and all its child SEXPs.
// For VECSXP, each slot is freed before the parent's data buffer.
// Not part of the real R API; provided for Python-side cleanup.
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
// .Call boundary wrapper for rpart (Pattern P3 representative).
// rpart() interleaves allocVector/allocMatrix (heap) calls with
// ALLOC/R_alloc (arena) calls.  ArenaFrame _frame governs only the
// arena allocations; the heap-allocated rlist SEXP and all its children
// are unaffected by ArenaFrame destruction.
// -----------------------------------------------------------------------
extern "C" SEXP rpart_wrapper(
        SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2,
        SEXP xvals2, SEXP xgrp2, SEXP ymat2, SEXP xmat2,
        SEXP wt2, SEXP ny2, SEXP cost2) {
    ArenaFrame _frame;
    try {
        return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                     ymat2, xmat2, wt2, ny2, cost2);
    } catch (const RError &e) {
        set_python_error(e.what());
        return R_NilValue;
    }
}
```

- **Arena / Memory Notes:**

  `rlist` (the VECSXP) is **heap-allocated** via `std::malloc`. Its `data` field holds a `SEXP[nout]` array — an array of child SEXP pointers, all zero-initialized. `SET_VECTOR_ELT(rlist, i, child)` writes an already-heap-allocated child SEXP pointer into slot `i`. No additional allocation is performed by `SET_VECTOR_ELT`; the child SEXPs (`which3`, `cptable3`, `dsplit3`, `isplit3`, `dnode3`, `inode3`, `csplit3`) were independently heap-allocated earlier in `rpart()` via `allocVector` and `allocMatrix`. When Python calls `free_sexp(rlist)`, the implementation recursively frees each child SEXP before freeing the VECSXP itself.

  The `UNPROTECT(1 + nout)` at `rpart.c:347` is a no-op in the fake runtime regardless of its integer argument.

- **Explanation:**

  `allocVector(VECSXP, nout)` expands to `Rf_allocVector(VECSXP, nout)`. Inside `Rf_allocVector`, `sexptype_element_size(VECSXP)` returns `sizeof(SEXP)` = 8 bytes per slot (on a 64-bit platform), so `bytes = nout * 8`. The data buffer is zero-initialized: all `SEXP` slots start as `nullptr`. `PROTECT(allocVector(VECSXP, nout))` returns the same `SEXP` through the no-op identity `Rf_protect`. `setAttrib(rlist, R_NamesSymbol, rname)` is a no-op — Python accesses elements by position. `SET_VECTOR_ELT(rlist, i, child)` writes into `((SEXP *)rlist->data)[i]`. The returned `rlist` from `rpart()` is the sole `.Call` return value; Python reads its `length` field and each slot via the `VECTOR_ELT` accessor.

---

#### Pattern P4: Allocate 1-D STRSXP String Vector (No PROTECT)

- **Locations:** `rpart.c:328`

- **Original R API Usage:**

```c
/* rpart.c:328-344 */
SEXP rname = allocVector(STRSXP, nout);
setAttrib(rlist, R_NamesSymbol, rname);
SET_STRING_ELT(rname, 0, mkChar("which"));
SET_STRING_ELT(rname, 1, mkChar("cptable"));
SET_STRING_ELT(rname, 2, mkChar("dsplit"));
SET_STRING_ELT(rname, 3, mkChar("isplit"));
SET_STRING_ELT(rname, 4, mkChar("dnode"));
SET_STRING_ELT(rname, 5, mkChar("inode"));
if (catcount > 0)
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp — allocVector handles STRSXP via the same
// Rf_allocVector function defined in Pattern P1.
// No additional code is required for the STRSXP type path in Rf_allocVector.
//
// For STRSXP (Pattern P4):
//   s->type   = STRSXP (16)
//   s->length = nout   (6 or 7)
//   s->nrow   = nout
//   s->ncol   = 1
//   s->data   = SEXP[nout], zero-initialized (all slots are nullptr initially)
//               Each slot holds a CHARSXP created by mkChar().
//
// sexptype_element_size(STRSXP) returns sizeof(SEXP) = 8.
// Total bytes = nout * 8.

// -----------------------------------------------------------------------
// SET_STRING_ELT — writes element i of a STRSXP with a CHARSXP value v.
// Identical in implementation to SET_VECTOR_ELT; different name only.
// -----------------------------------------------------------------------
inline void SET_STRING_ELT(SEXP s, int i, SEXP v) {
    static_cast<SEXP *>(s->data)[i] = v;
}

// -----------------------------------------------------------------------
// STRING_ELT — reads element i from a STRSXP, returning a CHARSXP.
// -----------------------------------------------------------------------
inline SEXP STRING_ELT(SEXP s, int i) {
    return static_cast<SEXP *>(s->data)[i];
}

// -----------------------------------------------------------------------
// mkChar — creates a CHARSXP from a null-terminated C string.
// The CHARSXP node and its char[] data buffer are heap-allocated.
// Used as the argument to SET_STRING_ELT.
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
// R_CHAR / CHAR — returns the const char* stored in a CHARSXP.
// -----------------------------------------------------------------------
inline const char *R_CHAR(SEXP s) {
    return static_cast<const char *>(s->data);
}
#define CHAR(x) R_CHAR(x)
```

- **Arena / Memory Notes:**

  The `rname` STRSXP itself is **heap-allocated** via `std::malloc` in `Rf_allocVector`. Its `data` field holds a `SEXP[nout]` array of CHARSXP pointers. Each `mkChar("...")` call independently heap-allocates a CHARSXP node and a `char[]` buffer for the literal string. The STRSXP `rname` is not independently protected by `PROTECT` in the original source (`rpart.c:328` omits `PROTECT`). In real R, `rname` is safe from GC because it is immediately attached to `rlist` via `setAttrib`, which protects it transitively. In the fake runtime, `PROTECT` is a no-op and GC does not exist, so the omitted `PROTECT` is inconsequential. `rname` is owned indirectly: when Python calls `free_sexp(rlist)`, the `free_sexp` implementation for VECSXP does not recurse into the `names` attribute (attributes are not tracked in the fake). Therefore, `rname` and its child CHARSXPs must be freed separately by Python, or the fake `setAttrib` can be made to store `rname` inside `rlist` for joint cleanup. Since `setAttrib` is a no-op in the current fake design, Python tooling must be aware that `rname` is an independent allocation.

- **Explanation:**

  `allocVector(STRSXP, nout)` expands to `Rf_allocVector(STRSXP, nout)`. Inside `Rf_allocVector`, `sexptype_element_size(STRSXP)` returns `sizeof(SEXP)` = 8, identical to `VECSXP`. The `data` buffer is a zero-initialized `SEXP[nout]` array holding CHARSXP pointers. `SET_STRING_ELT(rname, i, mkChar("which"))` first calls `mkChar("which")` to create a heap-allocated CHARSXP containing the string `"which"`, then writes that CHARSXP pointer into `((SEXP *)rname->data)[i]`. This pattern is identical in structure to `SET_VECTOR_ELT` on a VECSXP; the different function name exists in the real R API to enforce type safety, but in the fake runtime both are implemented as the same pointer-array write. The `STRSXP` type tag (`s->type = STRSXP`) ensures that the fake `free_sexp` does not incorrectly recurse into the slots as if they were generic SEXPs (though in the current `free_sexp` implementation, `STRSXP` child slots are not freed recursively — that should be corrected; see Arena / Memory Notes above regarding `rname` lifetime).

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Authoritative source for `fake_Rinternals.hpp`. Provides the `SEXPREC` struct definition (fields: `type`, `length`, `nrow`, `ncol`, `data`), the `SEXP` typedef (`typedef SEXPREC *SEXP`), the `SEXPTYPE` unsigned int typedef, all `XSXP` tag constants (`INTSXP`, `REALSXP`, `STRSXP`, `VECSXP`, `CHARSXP`, `NILSXP`, etc.), the `free_sexp()` utility, `R_NilValue`, and `R_UnboundValue`. `Rf_allocVector` stores values in `s->type`, `s->length`, `s->nrow`, `s->ncol`, and `s->data` — all five fields must exist in `SEXPREC`. |
| `INTSXP.md` | Establishes `#define INTSXP 13` within the `SEXPTYPE` constant block. Three of the six `allocVector` call sites pass `INTSXP` as the type argument (`pred_rpart.c:139`, `rpart.c:194`, `rpartexp2.c:47`). `sexptype_element_size(INTSXP)` must return `sizeof(int)`. |
| `REALSXP.md` | Establishes `#define REALSXP 14`. Required by `allocVector(REALSXP, n * ncp * nresp)` in `xpred.c:209`. `sexptype_element_size(REALSXP)` must return `sizeof(double)`. |
| `STRSXP.md` | Establishes `#define STRSXP 16`. Required by `allocVector(STRSXP, nout)` in `rpart.c:328`. `sexptype_element_size(STRSXP)` must return `sizeof(SEXP)`. |
| `VECSXP.md` | Establishes `#define VECSXP 19`. Required by `allocVector(VECSXP, nout)` in `rpart.c:327`. `sexptype_element_size(VECSXP)` must return `sizeof(SEXP)`. |
| `PROTECT.md` | Establishes that `PROTECT(s)` expands to `Rf_protect(s)` (identity inline function) and `UNPROTECT(n)` expands to `Rf_unprotect(n)` (no-op). Five of the six `allocVector` call sites are wrapped in `PROTECT`; the alias and no-op definitions must be in scope for the rpart source to compile unchanged. |
| `allocMatrix.md` | Establishes `Rf_allocMatrix` as a thin wrapper over `Rf_allocVector` (calls `allocVector(type, nrow * ncol)` then overwrites `s->nrow` and `s->ncol`). `allocMatrix.md` depends on `allocVector` being defined first; this guide (`allocVector.md`) must therefore appear before `allocMatrix.md` in the fake header include order. |
| `fake_arena.hpp` (canonical definition from Invariant 2, referenced in `SEXP.md`) | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, and `arena_calloc`. Required by the `.Call` wrappers for all four entry points that call `allocVector` (`pred_rpart_wrapper`, `rpart_wrapper`, `rpartexp2_wrapper`, `xpred_wrapper`), because each entry point also invokes `ALLOC`/`R_alloc` scratch allocations alongside the `allocVector` SEXP allocations. `Rf_allocVector` itself does not use the arena, but the boundary wrapper function that calls it must declare `ArenaFrame _frame` before calling the C function. |
