# Fake Header Implementation Guide: `INTSXP`

---

### 1. Overview of `INTSXP` in R API

`INTSXP` is an integer constant with value `13` that serves as the `SEXPTYPE` tag for integer vector objects in R's C API. It is defined in `Rinternals.h` as part of the `SEXPTYPE` type — either as a `#define` macro (`#define INTSXP 13`) or as an enum member (`INTSXP = 13`) depending on whether `enum_SEXPTYPE` is defined at compile time. `INTSXP` is used exclusively as the first argument to allocation functions such as `allocVector(INTSXP, n)` and `allocMatrix(INTSXP, nrow, ncol)`, instructing R to allocate a `SEXPREC` node whose `data` field will hold `n` (or `nrow * ncol`) contiguous `int` values. The accessor macro `INTEGER(sexp)` casts `sexp->data` to `int *` and is the canonical way to read and write the elements of an `INTSXP` vector after allocation.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `pred_rpart.c` | 139 | `SEXP where = PROTECT(allocVector(INTSXP, n));` |
| `rpart.c` | 194 | `which3 = PROTECT(allocVector(INTSXP, n));` |
| `rpart.c` | 278 | `inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));` |
| `rpart.c` | 285 | `isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));` |
| `rpart.c` | 293 | `csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));` |
| `rpartexp2.c` | 47 | `SEXP keep = PROTECT(allocVector(INTSXP, n));` |

**Argument and return types observed.**

In every occurrence, `INTSXP` is passed as the first argument to either `allocVector` or `allocMatrix`, both of which are declared in `Rinternals.h`:

```c
SEXP Rf_allocVector(SEXPTYPE type, R_xlen_t length);
SEXP Rf_allocMatrix(SEXPTYPE type, int nrow, int ncol);
```

`INTSXP` is of type `SEXPTYPE` (defined as `unsigned int` in the non-enum branch of `Rinternals.h`). The return value in each case is a `SEXP` (`SEXPREC *`), which is immediately passed to `PROTECT` and, once populated, accessed through `INTEGER(sexp)` which returns `int *`.

**Co-occurring R API items.**

- `PROTECT` / `UNPROTECT` — every allocation site wraps the result in `PROTECT`. In the fake runtime these are no-ops.
- `INTEGER(sexp)` — used directly after allocation to obtain the `int *` data pointer from the returned SEXP, then written through that pointer to populate the array.
- `REAL(sexp)`, `allocMatrix(REALSXP, ...)` — appear interleaved at nearby lines in `rpart.c`, confirming the pattern: the type tag determines which accessor (`INTEGER` vs. `REAL`) is used on the returned SEXP.
- `ALLOC` — used in the same function bodies for non-SEXP scratch arrays (arena-allocated via `R_alloc`); does not interact with `INTSXP` directly.
- `LENGTH(sexp)` — used in `rpartexp2.c` at line 46 (`int n = LENGTH(dtimes)`) to compute the allocation size.

**Distinct usage patterns.**

Two structural patterns appear across the six CSV rows:

1. **1-D integer vector allocation** (`allocVector(INTSXP, n)`) — rows from `pred_rpart.c:139`, `rpart.c:194`, and `rpartexp2.c:47`. The returned SEXP holds a flat `int[n]` array. `INTEGER(sexp)` is used to get a writeable `int *`.
2. **2-D integer matrix allocation** (`allocMatrix(INTSXP, nrow, ncol)`) — rows from `rpart.c:278`, `rpart.c:285`, and `rpart.c:293`. The returned SEXP holds a flat `int[nrow * ncol]` array stored in column-major order. `INTEGER(sexp)` is used identically; the caller manages column pointers via `iptr += nrow` arithmetic.

Both patterns share the same fake strategy: `INTSXP` is the type tag constant `13`; the actual allocation and `INTEGER` accessor behavior are provided by the `allocVector`, `allocMatrix`, and `INTEGER` fakes. `INTSXP` itself requires no implementation logic — it is a pure compile-time constant.

---

### 3. Fake C++ Implementation Strategy

**Category: A — Type or Enum Constant.**

`INTSXP` is a named integer constant used solely as a tag value. Its fake implementation is a single `#define` macro (or an enum member, depending on whether the surrounding `SEXPTYPE` is faked as a `typedef unsigned int` or as a `typedef enum`).

**Chosen mechanism.** Following the pattern established in `Rinternals.h` (the non-`enum_SEXPTYPE` branch), the fake header defines `SEXPTYPE` as `typedef unsigned int SEXPTYPE` and provides each type tag as a `#define` macro. This approach:

- Is fully compatible with both C and C++ compilation units, since `unsigned int` is unambiguous in both languages.
- Avoids enum-value conflicts: the real `Rinternals.h` uses numeric gaps (11 and 12 are unassigned), which are valid in an enum but can cause surprises; `#define` constants are independently scoped.
- Allows `switch(sexp->type)` statements in the package source to compile without a `default:` warning, since the type is `unsigned int` rather than a scoped enum.

The complete `SEXPTYPE` block that must appear in the fake `Rinternals.h` replacement is:

```cpp
typedef unsigned int SEXPTYPE;

#define NILSXP       0   /* nil = NULL */
#define SYMSXP       1   /* symbols */
#define LISTSXP      2   /* lists of dotted pairs */
#define CLOSXP       3   /* closures */
#define ENVSXP       4   /* environments */
#define PROMSXP      5   /* promises */
#define LANGSXP      6   /* language constructs */
#define SPECIALSXP   7   /* special forms */
#define BUILTINSXP   8   /* builtin non-special forms */
#define CHARSXP      9   /* scalar string (internal only) */
#define LGLSXP      10   /* logical vectors */
/* 11 and 12 were factors in the 1990s — intentionally unassigned */
#define INTSXP      13   /* integer vectors */
#define REALSXP     14   /* real (double) variables */
#define CPLXSXP     15   /* complex variables */
#define STRSXP      16   /* string vectors */
#define DOTSXP      17   /* dot-dot-dot object */
#define ANYSXP      18   /* any-type marker */
#define VECSXP      19   /* generic vectors (lists) */
#define EXPRSXP     20   /* expression vectors */
#define BCODESXP    21   /* byte code */
#define EXTPTRSXP   22   /* external pointer */
#define WEAKREFSXP  23   /* weak reference */
#define RAWSXP      24   /* raw bytes */
#define OBJSXP      25   /* S4 non-vector */
#define S4SXP       25   /* alias for OBJSXP */
#define NEWSXP      30   /* fresh GC node */
#define FREESXP     31   /* released GC node */
#define FUNSXP      99   /* Closure or Builtin or Special */
```

**Relationship to `SEXP` / `SEXPREC`.**
`INTSXP` is meaningful only in the presence of the `SEXPREC` struct and the `SEXP` typedef. The `SEXPREC` fake must include a `SEXPTYPE type` field that stores the tag. The `allocVector` and `allocMatrix` fakes set `sexp->type = INTSXP` when called with `INTSXP` as the type argument. The `INTEGER(sexp)` accessor then casts `sexp->data` to `int *`.

**`#define` aliases that must be preserved.**
The original `Rinternals.h` defines `INTSXP` via `#define INTSXP 13` (in the non-enum branch, which is the active branch by default when `enum_SEXPTYPE` is not defined). This exact macro must be replicated. No function-style aliases wrap `INTSXP`.

**Invariant applicability.**
- Invariant 1 (error/warning style): not directly triggered by `INTSXP` itself. However, `allocVector` and `allocMatrix` (which consume `INTSXP`) must throw `RError` on allocation failure. This is documented in the `allocVector` and `allocMatrix` guides.
- Invariant 2 (arena memory): not triggered by `INTSXP` itself. The memory implications belong to `allocVector` and `allocMatrix`. See Arena/Memory Notes in the pattern examples below.
- Invariant 3 (interpreter items): not triggered. `INTSXP` is a compile-time integer constant; no running interpreter is required.

---

### 4. Fake Implementation Examples

#### Pattern: Allocate 1-D Integer Vector

- **Locations:** `pred_rpart.c:139`, `rpart.c:194`, `rpartexp2.c:47`

- **Original R API Usage:**

```c
/* pred_rpart.c:139 */
SEXP where = PROTECT(allocVector(INTSXP, n));
pred_rpart0(INTEGER(dimx), ..., INTEGER(where));
UNPROTECT(1);
return where;

/* rpart.c:194 */
which3 = PROTECT(allocVector(INTSXP, n));
rp.which = INTEGER(which3);

/* rpartexp2.c:47 */
SEXP keep = PROTECT(allocVector(INTSXP, n));
Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
UNPROTECT(1);
return keep;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — SEXPTYPE block and INTSXP)
// -----------------------------------------------------------------------
// SEXPTYPE: unsigned int tag identifying the content type of a SEXPREC node.
// INTSXP = 13 is the tag for integer vectors.
// -----------------------------------------------------------------------

#pragma once
#ifndef FAKE_RINTERNALS_H
#define FAKE_RINTERNALS_H

#include <cstdlib>    // std::malloc, std::free
#include <cstring>    // std::memset
#include <stdexcept>  // std::runtime_error
#include "fake_arena.hpp"   // ArenaFrame, arena_alloc, arena_calloc

// -----------------------------------------------------------------------
// RError — C++ exception replacing Rf_error / longjmp.
// Must be defined before any fake that can throw.
// -----------------------------------------------------------------------
struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

// -----------------------------------------------------------------------
// SEXPTYPE: tag values — reproduced from Rinternals.h (non-enum_SEXPTYPE branch)
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
#define REALSXP     14
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
// SEXPREC and SEXP — minimal fake matching the observable C API contract.
// heap-allocated; not garbage-collected in the fake runtime.
// -----------------------------------------------------------------------
struct SEXPREC {
    SEXPTYPE  type;    // one of the INTSXP / REALSXP / ... tags above
    int       length;  // number of elements (used by LENGTH())
    int       nrow;    // row count for matrices (used by nrows())
    int       ncol;    // column count for matrices (used by ncols())
    void     *data;    // pointer to the element buffer (heap-allocated)
};

typedef SEXPREC *SEXP;

// -----------------------------------------------------------------------
// Element size helper — returns sizeof(element) for each SEXPTYPE.
// Used by allocVector and allocMatrix to size the data buffer.
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
// allocVector — allocates a 1-D SEXP of the requested type and length.
// The SEXP node itself is heap-allocated (std::malloc); the data buffer
// inside it is also heap-allocated.  Neither participates in the arena:
// SEXP objects returned from .Call functions are owned by the Python
// caller, which is responsible for calling free_sexp() on them.
//
// When INTSXP is the type tag, data holds int[length].
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
// PROTECT / UNPROTECT — no-ops in the fake runtime (no garbage collector).
// The macros are defined to evaluate their argument so that PROTECT(expr)
// still returns the SEXP produced by expr, exactly as the real PROTECT does.
// -----------------------------------------------------------------------
inline SEXP Rf_protect(SEXP s) { return s; }
inline void Rf_unprotect(int /*n*/) {}
inline void Rf_unprotect_ptr(SEXP /*s*/) {}

#define PROTECT(s)            Rf_protect(s)
#define UNPROTECT(n)          Rf_unprotect(n)
#define UNPROTECT_PTR(s)      Rf_unprotect_ptr(s)
#define PROTECT_WITH_INDEX(s, i) Rf_protect(s)
#define REPROTECT(s, i)       Rf_protect(s)

// -----------------------------------------------------------------------
// INTEGER accessor — casts sexp->data to int *.
// Used immediately after allocVector(INTSXP, n) to obtain the writable
// int array that the package populates.
// -----------------------------------------------------------------------
inline int *INTEGER(SEXP s) {
    return static_cast<int *>(s->data);
}

// -----------------------------------------------------------------------
// LENGTH — returns the element count of the SEXP.
// -----------------------------------------------------------------------
inline int LENGTH(SEXP s) { return s->length; }

// -----------------------------------------------------------------------
// .Call entry point boundary pattern (illustration for pred_rpart):
// The ArenaFrame guard must be declared at the top of every .Call wrapper.
// SEXP-returning functions do NOT need an ArenaFrame unless they also call
// ALLOC / R_alloc internally — those scratch allocations DO use the arena.
// The returned SEXP is heap-allocated and must be kept alive until Python
// extracts the data from it.
// -----------------------------------------------------------------------
//
//  extern "C" SEXP pred_rpart_entry(SEXP dimx, ...) {
//      ArenaFrame _frame;      // frees all R_alloc scratch at function exit
//      try {
//          return pred_rpart(dimx, ...);
//      } catch (const RError &e) {
//          // translate to Python exception via your ctypes error flag mechanism
//          set_python_error(e.what());
//          return nullptr;
//      }
//  }

#endif // FAKE_RINTERNALS_H
```

- **Arena / Memory Notes:**

  `INTSXP` itself allocates nothing; the memory concern belongs to `allocVector`. The `SEXPREC` node and its `data` buffer are both heap-allocated via `std::malloc`. They are **not** arena-managed, because the returned SEXP must outlive the function frame (it is the `.Call` return value consumed by Python). The arena (`fake_arena.hpp`) manages only scratch allocations made with `R_alloc` / `ALLOC` / `R_Calloc` within the same function frame. Those scratch arrays are freed at `ArenaFrame` destruction when the `.Call` wrapper returns.

  If allocation fails for either the `SEXPREC` node or its `data` buffer, a `RError` is thrown (Invariant 1). Python's `.Call` boundary wrapper must catch `RError` and translate it into a Python exception before the exception crosses the C/Python boundary.

- **Explanation:**

  The fake provides `#define INTSXP 13` as a plain preprocessor constant. When the original source calls `allocVector(INTSXP, n)`, the preprocessor substitutes `13`, and `allocVector` receives `(SEXPTYPE)13`. The fake `allocVector` sets `s->type = 13` (i.e., `INTSXP`) on the returned `SEXPREC`. Because `INTEGER(sexp)` simply casts `sexp->data` to `int *` — regardless of the type tag — the integer accessor works correctly for any `SEXPREC` whose `data` was allocated as `int[length]`.

  `PROTECT(expr)` expands to `Rf_protect(expr)`, which is the identity function; it returns `expr` unchanged. The surrounding code `SEXP where = PROTECT(allocVector(INTSXP, n))` therefore compiles and behaves identically to `SEXP where = allocVector(INTSXP, n)`. `UNPROTECT(1)` is a no-op call to `Rf_unprotect(1)`. Neither changes any state; they exist solely so the original source files compile without modification.

---

#### Pattern: Allocate 2-D Integer Matrix

- **Locations:** `rpart.c:278`, `rpart.c:285`, `rpart.c:293`

- **Original R API Usage:**

```c
/* rpart.c:278-290 */
inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));
iptr = INTEGER(inode3);
for (i = 0; i < 6; i++) {
    iinode[i] = iptr;
    iptr += nodecount;      /* advance by one column (column-major) */
}

isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));
iptr = INTEGER(isplit3);
for (i = 0; i < 3; i++) {
    iisplit[i] = iptr;
    iptr += splitcount;
}

/* rpart.c:293 — conditionally allocated */
if (catcount > 0) {
    csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));
    ccsplit = (int **) ALLOC(maxcat, sizeof(int *));
    iptr = INTEGER(csplit3);
    for (i = 0; i < maxcat; i++) {
        ccsplit[i] = iptr;
        iptr += catcount;
        for (j = 0; j < catcount; j++)
            ccsplit[i][j] = 0;
    }
}
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — allocMatrix)
// -----------------------------------------------------------------------
// allocMatrix — allocates a 2-D SEXP stored as a flat column-major array.
// allocMatrix(INTSXP, nrow, ncol) produces a SEXP with:
//   s->type   = INTSXP (13)
//   s->length = nrow * ncol
//   s->nrow   = nrow
//   s->ncol   = ncol
//   s->data   = int[nrow * ncol], zero-initialized, column-major layout
//
// INTEGER(s) returns int * to the flat buffer.
// Column j starts at INTEGER(s) + j * nrow.
// -----------------------------------------------------------------------
inline SEXP allocMatrix(SEXPTYPE type, int nrow, int ncol) {
    int length = nrow * ncol;
    SEXP s = allocVector(type, length);  // reuse allocVector
    s->nrow = nrow;
    s->ncol = ncol;
    return s;
}

// -----------------------------------------------------------------------
// nrows / ncols accessors — return the stored matrix dimensions.
// The real R API provides these as Rf_nrows / Rf_ncols (declared in
// Rinternals.h and defined in matrix.c).  The #define aliases below
// match the names used by the rpart source.
// -----------------------------------------------------------------------
inline int Rf_nrows(SEXP s) { return s->nrow; }
inline int Rf_ncols(SEXP s) { return s->ncol; }
#define nrows(x) Rf_nrows(x)
#define ncols(x) Rf_ncols(x)

// -----------------------------------------------------------------------
// .Call entry point boundary for rpart() (the main tree-building function):
//
//  extern "C" SEXP rpart_entry(SEXP ncat, SEXP method, ...) {
//      ArenaFrame _frame;   // frees R_alloc / ALLOC scratch on exit
//      try {
//          return rpart(ncat, method, ...);
//      } catch (const RError &e) {
//          set_python_error(e.what());
//          return nullptr;
//      }
//  }
//
// The ArenaFrame is essential here: rpart() calls ALLOC (which is
// R_alloc) extensively for scratch arrays (rp.csplit, rp.lwt, etc.).
// Those arena-allocated blocks are released when _frame is destroyed.
// The SEXP return values (inode3, isplit3, csplit3, etc.) are
// heap-allocated and survive the ArenaFrame destruction.
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:**

  `allocMatrix` delegates to `allocVector`, which heap-allocates both the `SEXPREC` node and its `int[nrow * ncol]` data buffer via `std::malloc`. These allocations are **not** arena-managed. The matrix SEXPs (`inode3`, `isplit3`, `csplit3`) must survive until Python reads their contents; they are freed by the Python-side wrapper after the data has been copied out (e.g., into a `numpy` array).

  The `ALLOC(maxcat, sizeof(int *))` call on line 294 of `rpart.c` is a separate scratch allocation that **does** go to the arena. `ALLOC` is a macro that expands to `R_alloc(n, size)`, and the arena-backed `R_alloc` fake allocates from `gArenaStack.back()`. That scratch memory is freed automatically when the `ArenaFrame` guard in the `.Call` wrapper destructs. The matrix SEXP itself (the `csplit3` node) is not affected by this distinction.

  If `catcount == 0`, the `csplit3 = PROTECT(allocMatrix(...))` branch is skipped entirely. No conditional logic is needed in the fake — the allocation simply does not occur.

- **Explanation:**

  `allocMatrix(INTSXP, nrow, ncol)` is implemented as a thin wrapper over `allocVector`: it calls `allocVector(INTSXP, nrow * ncol)` and then overwrites `s->nrow = nrow; s->ncol = ncol`. The `length` field stores the total element count, which is what `LENGTH(sexp)` returns and what determines the `data` buffer size.

  The column-major indexing performed by the rpart source (`iptr += nodecount` to advance one column) is correct for a flat `int[nrow * ncol]` buffer: column `j` occupies elements `[j * nrow, (j+1) * nrow)`. No special handling is required in the fake — the buffer is flat and the calling code performs all the index arithmetic.

  `PROTECT` and `UNPROTECT` remain no-ops. The multiple `PROTECT` calls in rpart's return-value construction block (lines 241–303) introduce no state changes in the fake runtime.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP` / `SEXPREC` (no separate guide exists yet; must be in the same fake `Rinternals.h`) | The `SEXPREC` struct with fields `type` (SEXPTYPE), `length` (int), `nrow` (int), `ncol` (int), and `data` (void *). `INTSXP` is stored in `s->type` by `allocVector`; `INTEGER(s)` casts `s->data` to `int *`. |
| `fake_arena.hpp` | The `ArenaFrame` RAII guard, `gArenaStack`, `arena_alloc`, and `arena_calloc`. Required by the `.Call` entry-point wrappers for rpart functions that also call `R_alloc` / `ALLOC` in the same function body. `INTSXP` itself does not use the arena, but the functions that use `INTSXP` allocations also perform arena allocations. |
| `RError` (defined in same `fake_Rinternals.hpp` or in a separate `fake_error.hpp`) | `struct RError : public std::runtime_error`. Required by `allocVector` and `allocMatrix` to signal allocation failure via C++ exception rather than `longjmp` (Invariant 1). |
| `DL_FUNC.md` / `DllInfo.md` / `fake_Rdynload.hpp` | Already generated. `fake_Rdynload.hpp` must be included after `fake_Rinternals.hpp` in the shadow include tree, because `init.c` includes `rpart.h` (which pulls in `Rinternals.h`) before it includes `R_ext/Rdynload.h`, and the `R_CallMethodDef` struct references `DL_FUNC` while the cast targets reference `SEXP`. |
