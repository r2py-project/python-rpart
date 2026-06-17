# Fake Header Implementation Guide: `REALSXP`

---

### 1. Overview of `REALSXP` in R API

`REALSXP` is an integer constant with value `14` that serves as the `SEXPTYPE` tag for real (double-precision floating-point) vector objects in R's C API. It is defined in `Rinternals.h` as part of the `SEXPTYPE` type — either as `#define REALSXP 14` or as an enum member `REALSXP = 14` depending on whether `enum_SEXPTYPE` is active at compile time. `REALSXP` is used exclusively as the first argument to allocation functions such as `allocVector(REALSXP, n)` and `allocMatrix(REALSXP, nrow, ncol)`, instructing R to allocate a `SEXPREC` node whose `data` field will hold `n` (or `nrow * ncol`) contiguous `double` values. The canonical accessor `REAL(sexp)` casts `sexp->data` to `double *` and is used immediately after allocation to read and write the elements of a `REALSXP` object.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `rpart.c` | 241 | `cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));` |
| `rpart.c` | 261 | `dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));` |
| `rpart.c` | 269 | `dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));` |
| `xpred.c` | 209 | `predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));` |

**Argument and return types observed.**

In every occurrence, `REALSXP` is passed as the first argument to either `allocVector` or `allocMatrix`, both declared in `Rinternals.h`:

```c
SEXP Rf_allocVector(SEXPTYPE type, R_xlen_t length);
SEXP Rf_allocMatrix(SEXPTYPE type, int nrow, int ncol);
```

`REALSXP` is of type `SEXPTYPE` (defined as `typedef unsigned int SEXPTYPE` in the non-enum branch). The return value in each case is a `SEXP` (`SEXPREC *`), which is immediately passed to `PROTECT` and then accessed via `REAL(sexp)` — which returns `double *`.

**Co-occurring R API items.**

- `PROTECT` / `UNPROTECT` — every allocation site wraps the result in `PROTECT`. In the fake runtime these are no-ops.
- `REAL(sexp)` — used directly after each allocation to obtain the writable `double *` data pointer. In `rpart.c:243` the pattern is `dptr = REAL(cptable3)`, and in `xpred.c:210` it is `predict = REAL(predict2)`.
- `allocMatrix` — three of the four rows use `allocMatrix(REALSXP, nrow, ncol)` to create column-major 2-D real matrices.
- `allocVector` — one row (`xpred.c:209`) uses `allocVector(REALSXP, n * ncp * nresp)` to create a flat 1-D real vector.
- `ALLOC` / `R_alloc` — used in the same function bodies for scratch arrays (arena-managed, independent of the SEXP allocations).
- `INTEGER(sexp)` — used in the same function body for `INTSXP` objects; `REAL` and `INTEGER` coexist in the rpart return-value construction block.

**Distinct usage patterns.**

Two structural patterns appear across the four CSV rows:

1. **2-D real matrix allocation** (`allocMatrix(REALSXP, nrow, ncol)`) — `rpart.c:241`, `rpart.c:261`, `rpart.c:269`. The returned SEXP holds a flat `double[nrow * ncol]` buffer in column-major order. `REAL(sexp)` is used to obtain the writable `double *`; column-pointer arithmetic (`dptr += nrow`) is performed by the caller.
2. **1-D real vector allocation** (`allocVector(REALSXP, n)`) — `xpred.c:209`. The returned SEXP holds a flat `double[n]` buffer. `REAL(sexp)` provides the `double *` that is indexed directly.

Both patterns share the same fake strategy: `REALSXP` is the type-tag constant `14`; the actual allocation and `REAL` accessor behavior are provided by the `allocVector`, `allocMatrix`, and `REAL` fakes. `REALSXP` itself requires no implementation logic — it is a pure compile-time constant.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`REALSXP` is a named integer constant used solely as a tag value passed to allocation functions. Its fake implementation is a single `#define` macro (or an enum member if `SEXPTYPE` is faked as an enum, which it is not — see the `INTSXP` guide for the rationale).

**Chosen mechanism.** Following the pattern established in the `INTSXP` guide, the fake header defines `SEXPTYPE` as `typedef unsigned int SEXPTYPE` and provides each type tag as a `#define` macro. `REALSXP` is defined as `#define REALSXP 14`. This is consistent with the non-`enum_SEXPTYPE` branch of the real `Rinternals.h`.

The `REALSXP` constant coexists in the same `SEXPTYPE` block already defined for `INTSXP`. No separate block is required; `#define REALSXP 14` is simply one line within the block already established by the `INTSXP` guide.

**Relationship to `SEXP` / `SEXPREC`.**
`REALSXP` is meaningful only in the presence of the `SEXPREC` struct and the `SEXP` typedef. The `allocVector` and `allocMatrix` fakes set `sexp->type = REALSXP` when called with `REALSXP` as the type argument. The `REAL(sexp)` accessor casts `sexp->data` to `double *`.

**`#define` aliases that must be preserved.**
The original `Rinternals.h` defines `REALSXP` via `#define REALSXP 14`. This exact macro must be replicated. No function-style aliases wrap `REALSXP` directly.

**Invariant applicability.**
- Invariant 1 (error/warning style): not directly triggered by `REALSXP` itself. However, `allocVector` and `allocMatrix` (which consume `REALSXP`) must throw `RError` on allocation failure. Documented in the pattern examples below.
- Invariant 2 (arena memory): not triggered by `REALSXP` itself. The memory implications belong to `allocVector` and `allocMatrix`. `SEXP` nodes and their data buffers are heap-allocated, not arena-allocated. `ALLOC`/`R_alloc` scratch arrays in the same function bodies are arena-allocated.
- Invariant 3 (interpreter items): not triggered. `REALSXP` is a compile-time integer constant; no running interpreter is required.

---

### 4. Fake Implementation Examples

#### Pattern: Allocate 2-D Real Matrix

- **Locations:** `rpart.c:241`, `rpart.c:261`, `rpart.c:269`

- **Original R API Usage:**

```c
/* rpart.c:241-252 — cp table, 3 or 5 rows x num_unique_cp columns */
cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));
dptr = REAL(cptable3);
for (cp = cptable; cp; cp = cp->forward) {
    dptr[i++] = cp->cp * scale;
    dptr[i++] = cp->nsplit;
    dptr[i++] = cp->risk * scale;
    if (xvals > 1) {
        dptr[i++] = cp->xrisk * scale;
        dptr[i++] = cp->xstd * scale;
    }
}

/* rpart.c:261-267 — node table, nodecount rows x (3+num_resp) columns */
dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));
ddnode = (double **) ALLOC(3 + rp.num_resp, sizeof(double *));
dptr = REAL(dnode3);
for (i = 0; i < 3 + rp.num_resp; i++) {
    ddnode[i] = dptr;
    dptr += nodecount;      /* column-major: advance one column */
}

/* rpart.c:269-276 — split table, splitcount rows x 3 columns */
dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));
dptr = REAL(dsplit3);
for (i = 0; i < 3; i++) {
    ddsplit[i] = dptr;
    dptr += splitcount;
    for (j = 0; j < splitcount; j++)
        ddsplit[i][j] = 0.0;
}
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — REALSXP definition and REAL accessor)
// -----------------------------------------------------------------------
// SEXPTYPE block — must appear once in fake_Rinternals.hpp.
// REALSXP = 14 is the tag for real (double) vector/matrix objects.
// This block already contains INTSXP = 13 (see INTSXP guide).
// -----------------------------------------------------------------------

#pragma once
#ifndef FAKE_RINTERNALS_H
#define FAKE_RINTERNALS_H

#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include "fake_arena.hpp"   // ArenaFrame, arena_alloc

// -----------------------------------------------------------------------
// RError — C++ exception replacing Rf_error / longjmp (Invariant 1).
// -----------------------------------------------------------------------
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

// -----------------------------------------------------------------------
// SEXPTYPE tag constants — non-enum_SEXPTYPE branch of Rinternals.h.
// -----------------------------------------------------------------------
typedef unsigned int SEXPTYPE;

#define NILSXP       0
#define SYMSXP       1
#define LISTSXP      2
#define CLOSXP       3
#define ENVSXP       4
#define PROMSXP      5
#define LANGSXP      6
#define SPECIALSXP   7
#define BUILTINSXP   8
#define CHARSXP      9
#define LGLSXP      10
/* 11 and 12 intentionally unassigned */
#define INTSXP      13   /* integer vectors */
#define REALSXP     14   /* real (double) vectors and matrices */
#define CPLXSXP     15
#define STRSXP      16
#define DOTSXP      17
#define ANYSXP      18
#define VECSXP      19
#define EXPRSXP     20
#define BCODESXP    21
#define EXTPTRSXP   22
#define WEAKREFSXP  23
#define RAWSXP      24
#define OBJSXP      25
#define S4SXP       25
#define NEWSXP      30
#define FREESXP     31
#define FUNSXP      99

// -----------------------------------------------------------------------
// SEXPREC and SEXP — minimal struct matching the observable C API contract.
// Heap-allocated; not garbage-collected in the fake runtime.
// -----------------------------------------------------------------------
struct SEXPREC {
    SEXPTYPE  type;    // INTSXP, REALSXP, etc.
    int       length;  // total element count (used by LENGTH())
    int       nrow;    // row count for matrices (used by nrows())
    int       ncol;    // column count for matrices (used by ncols())
    void     *data;    // pointer to element buffer (heap-allocated)
};
typedef SEXPREC *SEXP;

// -----------------------------------------------------------------------
// Element size helper.
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
// allocVector — heap-allocates a 1-D SEXP of the requested type and length.
// Throws RError on allocation failure (Invariant 1).
// -----------------------------------------------------------------------
inline SEXP allocVector(SEXPTYPE type, int length) {
    SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!s) throw RError("allocVector: out of memory allocating SEXPREC");
    s->type   = type;
    s->length = length;
    s->nrow   = length;
    s->ncol   = 1;
    std::size_t bytes = static_cast<std::size_t>(length)
                        * sexptype_element_size(type);
    s->data = std::malloc(bytes);
    if (!s->data) {
        std::free(s);
        throw RError("allocVector: out of memory allocating data buffer");
    }
    std::memset(s->data, 0, bytes);
    return s;
}

// -----------------------------------------------------------------------
// allocMatrix — thin wrapper over allocVector; sets nrow and ncol.
// allocMatrix(REALSXP, nrow, ncol) produces a SEXP with:
//   s->type   = REALSXP (14)
//   s->length = nrow * ncol
//   s->nrow   = nrow
//   s->ncol   = ncol
//   s->data   = double[nrow * ncol], zero-initialized, column-major layout
// -----------------------------------------------------------------------
inline SEXP allocMatrix(SEXPTYPE type, int nrow, int ncol) {
    SEXP s = allocVector(type, nrow * ncol);
    s->nrow = nrow;
    s->ncol = ncol;
    return s;
}

// -----------------------------------------------------------------------
// REAL accessor — casts sexp->data to double *.
// Used immediately after allocVector/allocMatrix with REALSXP to obtain
// the writable double array that the package populates.
// -----------------------------------------------------------------------
inline double *REAL(SEXP s) {
    return static_cast<double *>(s->data);
}

// -----------------------------------------------------------------------
// INTEGER accessor — casts sexp->data to int *.
// -----------------------------------------------------------------------
inline int *INTEGER(SEXP s) {
    return static_cast<int *>(s->data);
}

// -----------------------------------------------------------------------
// LENGTH / nrows / ncols accessors.
// -----------------------------------------------------------------------
inline int LENGTH(SEXP s)     { return s->length; }
inline int Rf_nrows(SEXP s)   { return s->nrow; }
inline int Rf_ncols(SEXP s)   { return s->ncol; }
#define nrows(x) Rf_nrows(x)
#define ncols(x) Rf_ncols(x)

// -----------------------------------------------------------------------
// PROTECT / UNPROTECT — no-ops in the fake runtime (no garbage collector).
// PROTECT(expr) must evaluate and return expr unchanged.
// -----------------------------------------------------------------------
inline SEXP Rf_protect(SEXP s)      { return s; }
inline void Rf_unprotect(int /*n*/) {}
inline void Rf_unprotect_ptr(SEXP /*s*/) {}

#define PROTECT(s)               Rf_protect(s)
#define UNPROTECT(n)             Rf_unprotect(n)
#define UNPROTECT_PTR(s)         Rf_unprotect_ptr(s)
#define PROTECT_WITH_INDEX(s, i) Rf_protect(s)
#define REPROTECT(s, i)          Rf_protect(s)

// -----------------------------------------------------------------------
// .Call entry point boundary for rpart() — illustration.
// ArenaFrame is required because rpart() mixes SEXP allocations (heap)
// with ALLOC / R_alloc scratch allocations (arena) in the same body.
//
//  extern "C" SEXP rpart_entry(SEXP ncat, SEXP method, ...) {
//      ArenaFrame _frame;   // frees all R_alloc scratch on exit
//      try {
//          return rpart(ncat, method, ...);
//      } catch (const RError &e) {
//          set_python_error(e.what());
//          return nullptr;
//      }
//  }
// -----------------------------------------------------------------------

#endif // FAKE_RINTERNALS_H
```

- **Arena / Memory Notes:**

  `REALSXP` itself allocates nothing. The memory concern belongs to `allocMatrix`. Each call to `allocMatrix(REALSXP, nrow, ncol)` heap-allocates (via `std::malloc`) both the `SEXPREC` node and a `double[nrow * ncol]` data buffer. These allocations are **not** arena-managed because the returned SEXPs (`cptable3`, `dnode3`, `dsplit3`) are part of the `.Call` return list and must outlive the function frame. The Python-side wrapper is responsible for extracting the data (e.g., into `numpy` arrays) and then freeing the `SEXPREC` nodes.

  The `ALLOC(...)` calls that immediately follow the `allocMatrix` calls in `rpart.c` (e.g., `ddnode = (double **) ALLOC(3 + rp.num_resp, sizeof(double *))` at line 262) are scratch pointer arrays that **do** go to the arena via the `R_alloc`/`ALLOC` fake. Those are freed automatically when the `ArenaFrame` destructs at `.Call` boundary return. The matrix `SEXP` data buffers they point into are unaffected.

  If allocation fails for either the `SEXPREC` node or its `double` data buffer, `allocVector` throws `RError` (Invariant 1). The `.Call` boundary wrapper catches this and translates it to a Python exception.

- **Explanation:**

  The fake provides `#define REALSXP 14` as a plain preprocessor constant. When the original source calls `allocMatrix(REALSXP, nrow, ncol)`, the preprocessor substitutes `14`, and `allocMatrix` receives `(SEXPTYPE)14`. The fake sets `s->type = 14` on the returned `SEXPREC`. The `REAL(sexp)` accessor then casts `sexp->data` to `double *` — regardless of how the type tag was recorded — giving the caller the writable column-major buffer.

  `PROTECT(expr)` expands to `Rf_protect(expr)`, which is the identity function. The assignment `cptable3 = PROTECT(allocMatrix(REALSXP, ...))` is therefore identical to `cptable3 = allocMatrix(REALSXP, ...)`. Multiple `PROTECT` calls within rpart's return-value construction block (lines 241–303) accumulate no state changes in the fake runtime.

  Column-major indexing is handled entirely by the caller: `dptr += nodecount` advances the pointer by one full column of `nodecount` doubles. The fake data buffer is a flat `double[nrow * ncol]` allocation, which is exactly what this pointer arithmetic requires.

---

#### Pattern: Allocate 1-D Real Vector

- **Locations:** `xpred.c:209`

- **Original R API Usage:**

```c
/* xpred.c:205-210 */
if (asInteger(all2) == 1)
    nresp = rp.num_resp;
else
    nresp = 1;
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — allocVector with REALSXP, REAL accessor)
// The same allocVector and REAL inline functions shown in the matrix
// pattern above handle this case without any additional code.
//
// allocVector(REALSXP, n * ncp * nresp) produces:
//   s->type   = REALSXP (14)
//   s->length = n * ncp * nresp
//   s->nrow   = n * ncp * nresp  (treated as a 1-D vector; ncol = 1)
//   s->ncol   = 1
//   s->data   = double[n * ncp * nresp], zero-initialized
//
// predict = REAL(predict2) then gives a double * into that buffer.
// The caller indexes it directly: predict[k++] = value;

// -----------------------------------------------------------------------
// .Call entry point boundary for xpred():
//
//  extern "C" SEXP xpred_entry(SEXP ncat, SEXP method, ...) {
//      ArenaFrame _frame;   // frees R_alloc scratch (rp.csplit, etc.)
//      try {
//          return xpred(ncat, method, ...);
//      } catch (const RError &e) {
//          set_python_error(e.what());
//          return nullptr;
//      }
//  }
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:**

  `allocVector(REALSXP, n * ncp * nresp)` heap-allocates a `SEXPREC` node and a `double[n * ncp * nresp]` data buffer. The allocation is **not** arena-managed: `predict2` is the return value of `xpred()` and must survive until Python extracts the prediction matrix. The Python wrapper copies the `double *` data into a `numpy` array and then calls `free_sexp(predict2)` to release both the data buffer and the `SEXPREC` node.

  As with `rpart.c`, `xpred.c` also calls `ALLOC`/`R_alloc` for scratch arrays (e.g., sorting arrays, node arrays). Those go to the arena and are freed when the `ArenaFrame` in the `xpred_entry` wrapper destructs.

  If `n * ncp * nresp` is zero, `allocVector` still allocates a zero-length buffer (a valid `std::malloc(0)` call on most platforms, or one element of zero padding). The caller never writes to a zero-length buffer, so this is safe.

- **Explanation:**

  The single `#define REALSXP 14` handles both matrix and vector patterns — there is no distinction in the type tag between a 1-D vector and a 2-D matrix in R's type system. The distinction exists only in `s->nrow` and `s->ncol`. For `allocVector`, `nrow = length` and `ncol = 1`; for `allocMatrix`, `nrow` and `ncol` are set to the caller-supplied values. The `REAL(sexp)` accessor does not inspect `nrow` or `ncol`; it always returns `sexp->data` cast to `double *`, which is correct for both layouts.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `INTSXP` guide (`INTSXP.md`) | The complete `SEXPTYPE` block and `#define INTSXP 13` that also includes `#define REALSXP 14`. `REALSXP` must be placed in the same block to avoid redefinition conflicts. The `SEXPREC` struct (`type`, `length`, `nrow`, `ncol`, `data`) defined there is reused unchanged. |
| `fake_arena.hpp` | The `ArenaFrame` RAII guard, `gArenaStack`, `arena_alloc`, and `arena_calloc`. Required by the `.Call` entry-point wrappers for `rpart()` and `xpred()`, both of which mix SEXP (heap) allocations with `R_alloc`/`ALLOC` (arena) allocations in the same function body. `REALSXP` itself does not use the arena. |
| `RError` (same `fake_Rinternals.hpp` or separate `fake_error.hpp`) | `struct RError : public std::runtime_error`. Required by `allocVector` and `allocMatrix` to signal allocation failure via C++ exception rather than `longjmp` (Invariant 1). |
| `DL_FUNC.md` / `DllInfo.md` / `fake_Rdynload.hpp` | Already generated. Must be included after `fake_Rinternals.hpp` in the shadow include tree, because `init.c` includes `rpart.h` (which pulls in `Rinternals.h` and therefore `SEXP`) before it includes `R_ext/Rdynload.h` (which references `DL_FUNC`). |
