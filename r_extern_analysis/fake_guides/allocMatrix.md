# Fake Header Implementation Guide: `allocMatrix`

---

### 1. Overview of `allocMatrix` in R API

`allocMatrix` is a C API function declared in `Rinternals.h` as `SEXP Rf_allocMatrix(SEXPTYPE type, int nrow, int ncol)` and exposed to package source via the macro alias `#define allocMatrix Rf_allocMatrix`. It allocates a two-dimensional R matrix object: a heap-managed `SEXPREC` node whose `data` field points to a flat, column-major buffer of `nrow * ncol` elements of the scalar type indicated by `type` (`REALSXP` for `double`, `INTSXP` for `int`). The returned `SEXP` is the canonical R matrix: R's `dim` attribute records `c(nrow, ncol)`, and accessor functions `nrows(s)` / `ncols(s)` return those dimensions. In the fake runtime, `allocMatrix` is a thin inline wrapper over `allocVector` that additionally sets `s->nrow` and `s->ncol` on the returned `SEXPREC` node; no garbage collector, no attribute list, and no `dim` SEXP are involved.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `rpart.c` | 241 | `cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));` |
| `rpart.c` | 261 | `dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));` |
| `rpart.c` | 269 | `dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));` |
| `rpart.c` | 278 | `inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));` |
| `rpart.c` | 285 | `isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));` |
| `rpart.c` | 293 | `csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));` |

All six call sites are located in the return-value construction block of `rpart()` (lines 239–305), which assembles the output list that is ultimately returned to R/Python. The function signature of `rpart()` is:

```c
SEXP rpart(SEXP ncat2, SEXP method2, SEXP opt2,
           SEXP parms2, SEXP xvals2, SEXP xgrp2,
           SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2)
```

**C types of arguments and return values.**

- `type` (first argument): `SEXPTYPE` (defined as `typedef unsigned int SEXPTYPE`). Values used: `REALSXP` (14) and `INTSXP` (13).
- `nrow` (second argument): `int`. Values are runtime-computed quantities: `xvals > 1 ? 5 : 3`, `nodecount`, `splitcount`, `catcount`.
- `ncol` (third argument): `int`. Values are runtime-computed quantities: `rp.num_unique_cp`, `3 + rp.num_resp`, `3`, `6`, `3`, `maxcat`.
- Return value: `SEXP` (`SEXPREC *`). Immediately wrapped in `PROTECT` and assigned to a local `SEXP` variable declared at the top of `rpart()` (`rpart.c:64-65`).

**Co-occurring R API items.**

- `PROTECT` / `UNPROTECT` — every `allocMatrix` call site wraps the result in `PROTECT`. In the fake runtime these are no-ops (see `PROTECT.md`). The matching `UNPROTECT(1 + nout)` at `rpart.c:347` is also a no-op.
- `REAL(sexp)` — applied immediately after each `REALSXP` allocation to obtain a `double *` into the data buffer. Used in column-pointer setup: `dptr = REAL(dnode3); for (i = 0; i < ncol; i++) { ddnode[i] = dptr; dptr += nrow; }`.
- `INTEGER(sexp)` — applied immediately after each `INTSXP` allocation to obtain an `int *`. Used analogously for column-pointer setup.
- `ALLOC(n, size)` — the arena-backed scratch allocator, defined in `rpart.h` as `R_alloc(n, size)`. Interleaved with `allocMatrix` calls for scratch pointer arrays (`ddnode`, `ddsplit`, `iinode`, `iisplit`, `ccsplit`). These arena allocations are entirely independent of the heap-based SEXP allocations.
- `SET_VECTOR_ELT(rlist, i, sexp)` — used downstream (lines 329–346) to pack all allocated SEXPs into the output VECSXP list returned to R/Python.

**Distinct implementation patterns.**

| Pattern | CSV rows | Element type | Buffer type | Accessor |
|---|---|---|---|---|
| Pattern 1: 2-D REALSXP matrix | `rpart.c:241`, `rpart.c:261`, `rpart.c:269` | `double` | `double[nrow * ncol]` | `REAL(s)` returns `double *` |
| Pattern 2: 2-D INTSXP matrix | `rpart.c:278`, `rpart.c:285`, `rpart.c:293` | `int` | `int[nrow * ncol]` | `INTEGER(s)` returns `int *` |

Both patterns share the same fake implementation mechanism: a single `allocMatrix` function that dispatches element sizing through `sexptype_element_size(type)` and delegates buffer allocation to `allocVector`. The only difference between the two patterns is the `SEXPTYPE` tag and which accessor (`REAL` vs. `INTEGER`) is applied to the result.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function.**

`allocMatrix` creates a heap-allocated `SEXPREC` node whose data buffer holds `nrow * ncol` contiguous elements of the type specified by the `SEXPTYPE` argument. It falls squarely in Category C because its primary role is to produce a heap-allocated SEXP object.

**Chosen mechanism.**

`allocMatrix` is implemented as an `inline` C++ function that:

1. Computes `length = nrow * ncol` (total element count).
2. Delegates to `allocVector(type, length)` to heap-allocate both the `SEXPREC` node and the element data buffer.
3. Overwrites `s->nrow = nrow` and `s->ncol = ncol` on the returned `SEXPREC` (because `allocVector` sets `s->nrow = length` and `s->ncol = 1` by default for 1-D vectors).
4. Returns the modified `SEXP`.

This design satisfies the invariants:

- **Invariant 1:** `allocVector` throws `RError` (a `std::runtime_error` subclass) if either `std::malloc` call fails. Since `allocMatrix` calls `allocVector`, allocation failures propagate automatically as C++ exceptions. No `longjmp`, `setjmp`, or `abort()` is used.
- **Invariant 2:** The `SEXPREC` node and its data buffer are heap-allocated via `std::malloc` (inside `allocVector`), **not** arena-allocated. This is correct because all six `allocMatrix` results in `rpart()` are output components — they are packed into the `rlist` VECSXP at lines 329–346 and returned to Python. They must outlive the `ArenaFrame` RAII guard that is pushed at the `.Call` wrapper entry and destroyed when the wrapper returns. The `ArenaFrame` governs only `ALLOC`/`R_alloc` scratch arrays; it has no effect on heap-allocated SEXPs.
- **Invariant 3:** Not applicable. `allocMatrix` is not an R Interpreter Item.

**Memory allocation summary.**

| Allocation call | Allocator | Lifetime | Freed by |
|---|---|---|---|
| `SEXPREC` node (8 bytes each) | `std::malloc` in `allocVector` | Until Python calls `free_sexp()` | `free_sexp()` in Python wrapper |
| Data buffer (`double[]` or `int[]`) | `std::malloc` in `allocVector` | Until Python calls `free_sexp()` | `free_sexp()` in Python wrapper |
| Column-pointer scratch arrays (`ddnode`, `ddsplit`, etc.) | Arena via `ALLOC`/`R_alloc` | Until `ArenaFrame` destructs | `ArenaFrame` RAII at `.Call` boundary |

**`#define` alias that must be preserved.**

The real `Rinternals.h` at line 893 defines:

```c
#define allocMatrix    Rf_allocMatrix
```

This alias must be reproduced in the fake header so that the rpart source files compile without modification. The actual implementation function must be named `Rf_allocMatrix` (or `allocMatrix` directly with no alias needed), with the macro alias mapping `allocMatrix` to `Rf_allocMatrix`. Alternatively, since the fake controls the entire header, the function can be named `allocMatrix` directly and the alias `#define allocMatrix Rf_allocMatrix` can be omitted (since the function is already named `allocMatrix`). However, to exactly mirror the real header structure and prevent symbol conflicts if any source file calls `Rf_allocMatrix` directly, the guide provides both the `inline Rf_allocMatrix` function and the `#define allocMatrix Rf_allocMatrix` alias.

**Relationship to `PROTECT` / `UNPROTECT`.**

As established in `PROTECT.md`, `PROTECT(s)` expands to `Rf_protect(s)` which is an identity inline function returning `s` unchanged. `UNPROTECT(n)` is a no-op. The six `PROTECT(allocMatrix(...))` calls in `rpart.c` are therefore identical to bare `allocMatrix(...)` calls in the fake runtime. No GC protection stack state is modified.

**ArenaFrame requirement.**

Because `rpart()` interleaves `allocMatrix` (heap) calls with `ALLOC` (arena) calls, the `.Call` wrapper for `rpart()` must declare an `ArenaFrame` at entry:

```cpp
extern "C" SEXP rpart_wrapper(
        SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2,
        SEXP xvals2, SEXP xgrp2, SEXP ymat2, SEXP xmat2,
        SEXP wt2, SEXP ny2, SEXP cost2) {
    ArenaFrame _frame;   // governs all ALLOC / R_alloc scratch allocations
    try {
        return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                     ymat2, xmat2, wt2, ny2, cost2);
    } catch (const RError &e) {
        set_python_error(e.what());
        return R_NilValue;
    }
}
```

When `_frame` destructs at wrapper return, all `ALLOC`-managed scratch arrays are freed. The heap-allocated SEXP nodes (including all six `allocMatrix` results) are unaffected.

---

### 4. Fake Implementation Examples

#### Pattern 1: Allocate 2-D REALSXP Matrix

- **Locations:** `rpart.c:241`, `rpart.c:261`, `rpart.c:269`

- **Original R API Usage:**

```c
/* rpart.c:239-276 — assembling the cp table and node/split double matrices */

scale = 1 / tree->risk;
i = 0;
cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3,
                               rp.num_unique_cp));
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

rpcountup(tree, &nodecount, &splitcount, &catcount);
dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));
ddnode = (double **) ALLOC(3 + rp.num_resp, sizeof(double *));
dptr = REAL(dnode3);
for (i = 0; i < 3 + rp.num_resp; i++) {
    ddnode[i] = dptr;
    dptr += nodecount;   /* column-major: advance one column */
}

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
// fake_Rinternals.hpp  — allocMatrix definition (REALSXP path)
// Prerequisite: SEXPREC, SEXP, SEXPTYPE, REALSXP, RError, allocVector,
//               PROTECT, REAL, ALLOC, ArenaFrame are already defined
//               in the same fake_Rinternals.hpp / fake_arena.hpp.

// -----------------------------------------------------------------------
// sexptype_element_size — maps SEXPTYPE to sizeof(element).
// Used by allocVector to compute the data buffer size.
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
// allocVector — heap-allocates a 1-D SEXP of the given type and length.
// Both the SEXPREC node and the data buffer are heap-allocated via
// std::malloc.  Neither participates in the arena: SEXP objects returned
// from .Call functions are owned by the Python caller, which calls
// free_sexp() after extracting the data.
//
// Throws RError on allocation failure (Invariant 1).
// -----------------------------------------------------------------------
inline SEXP allocVector(SEXPTYPE type, int length) {
    SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!s) throw RError("allocVector: out of memory allocating SEXPREC");
    s->type   = type;
    s->length = length;
    s->nrow   = length;  // default for 1-D; overwritten by allocMatrix
    s->ncol   = 1;
    std::size_t bytes = static_cast<std::size_t>(length)
                        * sexptype_element_size(type);
    if (bytes == 0) bytes = 1;  // std::malloc(0) is implementation-defined
    s->data = std::malloc(bytes);
    if (!s->data) {
        std::free(s);
        throw RError("allocVector: out of memory allocating data buffer");
    }
    std::memset(s->data, 0, bytes);  // zero-initialize (matches R semantics)
    return s;
}

// -----------------------------------------------------------------------
// Rf_allocMatrix — thin wrapper over allocVector; sets nrow and ncol.
//
// For REALSXP:
//   s->type   = REALSXP (14)
//   s->length = nrow * ncol
//   s->nrow   = nrow
//   s->ncol   = ncol
//   s->data   = double[nrow * ncol], zero-initialized, column-major layout
//
// REAL(s) returns (double *)s->data.
// Column j starts at REAL(s) + j * nrow.
//
// Throws RError on allocation failure (propagated from allocVector).
// -----------------------------------------------------------------------
inline SEXP Rf_allocMatrix(SEXPTYPE type, int nrow, int ncol) {
    SEXP s = allocVector(type, nrow * ncol);
    s->nrow = nrow;
    s->ncol = ncol;
    return s;
}

// Macro alias matching real Rinternals.h line 893.
#define allocMatrix    Rf_allocMatrix

// -----------------------------------------------------------------------
// REAL accessor — casts sexp->data to double *.
// Used immediately after allocMatrix(REALSXP, ...) to obtain the
// writable column-major double buffer.
// -----------------------------------------------------------------------
inline double *REAL(SEXP s) {
    return static_cast<double *>(s->data);
}

// -----------------------------------------------------------------------
// .Call boundary wrapper for rpart() — REALSXP allocMatrix context.
// ArenaFrame _frame governs all ALLOC / R_alloc scratch allocations.
// SEXP matrix objects (cptable3, dnode3, dsplit3) are heap-allocated and
// survive ArenaFrame destruction; Python frees them via free_sexp().
// -----------------------------------------------------------------------
extern "C" SEXP rpart_wrapper(
        SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2,
        SEXP xvals2, SEXP xgrp2, SEXP ymat2, SEXP xmat2,
        SEXP wt2, SEXP ny2, SEXP cost2) {
    ArenaFrame _frame;   // frees ddnode, ddsplit, savesort, etc. on exit
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

  All three REALSXP matrices (`cptable3`, `dnode3`, `dsplit3`) are heap-allocated via `std::malloc` inside `allocVector`. They are **not** arena-managed. They must outlive the `ArenaFrame` guard because they are the output data returned to Python (packed into `rlist` via `SET_VECTOR_ELT` at lines 329–346).

  The `ALLOC(3 + rp.num_resp, sizeof(double *))` call at `rpart.c:262` (which produces `ddnode`, a scratch `double **` column-pointer array) **does** go to the arena via the `R_alloc`/`ALLOC` fake. When `ArenaFrame _frame` destructs at `rpart_wrapper` return, `ddnode` and all other ALLOC-managed scratch arrays are freed. The `double[]` data buffers that `ddnode[i]` point into are part of `dnode3->data` — a heap allocation — and are unaffected by arena destruction.

  If `std::malloc` fails inside `allocVector`, `RError` is thrown. The `rpart_wrapper` `catch` block intercepts it, stores the message via `set_python_error`, and returns `R_NilValue` as a sentinel. No partial SEXP objects remain: `allocVector` frees the `SEXPREC` node before throwing if the data buffer allocation fails.

  If `splitcount` or `nodecount` is zero, `allocMatrix(REALSXP, 0, ncol)` calls `allocVector(REALSXP, 0)`, which allocates a zero-length data buffer (handled by the `if (bytes == 0) bytes = 1` guard). This is safe because the caller never writes through a zero-row matrix.

- **Explanation:**

  `allocMatrix(REALSXP, nrow, ncol)` expands via `#define allocMatrix Rf_allocMatrix` to `Rf_allocMatrix(REALSXP, nrow, ncol)`. The fake `Rf_allocMatrix` calls `allocVector(REALSXP, nrow * ncol)`, which sets `s->type = REALSXP`, `s->length = nrow * ncol`, `s->nrow = nrow * ncol`, `s->ncol = 1`, allocates `sizeof(double) * nrow * ncol` bytes for `s->data`, and zero-initializes the buffer. `Rf_allocMatrix` then overwrites `s->nrow = nrow` and `s->ncol = ncol` to record the true matrix shape. The returned `SEXP` is passed through `PROTECT` (which is `Rf_protect`, the identity function) and assigned to the local `SEXP` variable. No source file modification is required.

  Column-major layout is implicit: `REAL(dnode3)` returns `(double *)dnode3->data`, and the subsequent `dptr += nodecount` arithmetic correctly advances one full column of `nodecount` doubles. The data buffer is contiguous and unstructured from the fake runtime's perspective; all column-pointer setup is performed by the calling code.

---

#### Pattern 2: Allocate 2-D INTSXP Matrix

- **Locations:** `rpart.c:278`, `rpart.c:285`, `rpart.c:293`

- **Original R API Usage:**

```c
/* rpart.c:278-303 — integer node, split, and categorical split matrices */

inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));
iptr = INTEGER(inode3);
for (i = 0; i < 6; i++) {
    iinode[i] = iptr;
    iptr += nodecount;   /* column-major: advance one column */
}

isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));
iptr = INTEGER(isplit3);
for (i = 0; i < 3; i++) {
    iisplit[i] = iptr;
    iptr += splitcount;
}

if (catcount > 0) {
    csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));
    ccsplit = (int **) ALLOC(maxcat, sizeof(int *));
    iptr = INTEGER(csplit3);
    for (i = 0; i < maxcat; i++) {
        ccsplit[i] = iptr;
        iptr += catcount;
        for (j = 0; j < catcount; j++)
            ccsplit[i][j] = 0;   /* redundant zero-fill (already zero from malloc) */
    }
} else
    ccsplit = NULL;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  — allocMatrix definition (INTSXP path)
// No additional code is required beyond what Pattern 1 defines.
// The same Rf_allocMatrix function handles INTSXP via the type dispatch
// in sexptype_element_size: INTSXP maps to sizeof(int).

// -----------------------------------------------------------------------
// Rf_allocMatrix (repeated for clarity — defined once in the header):
//
// For INTSXP:
//   s->type   = INTSXP (13)
//   s->length = nrow * ncol
//   s->nrow   = nrow
//   s->ncol   = ncol
//   s->data   = int[nrow * ncol], zero-initialized, column-major layout
//
// INTEGER(s) returns (int *)s->data.
// Column j starts at INTEGER(s) + j * nrow.
// -----------------------------------------------------------------------
// inline SEXP Rf_allocMatrix(SEXPTYPE type, int nrow, int ncol) {
//     SEXP s = allocVector(type, nrow * ncol);   // type = INTSXP => int[nrow*ncol]
//     s->nrow = nrow;
//     s->ncol = ncol;
//     return s;
// }
// #define allocMatrix    Rf_allocMatrix           // alias preserved from Rinternals.h

// -----------------------------------------------------------------------
// INTEGER accessor — casts sexp->data to int *.
// Used immediately after allocMatrix(INTSXP, ...) to obtain the writable
// column-major int buffer for node, split, and categorical split data.
// -----------------------------------------------------------------------
inline int *INTEGER(SEXP s) {
    return static_cast<int *>(s->data);
}

// -----------------------------------------------------------------------
// Conditional PROTECT pattern (rpart.c:292-301):
// csplit3 is declared with = R_NilValue at line 64 and conditionally
// re-assigned inside if (catcount > 0).  In the fake runtime:
//   - PROTECT(allocMatrix(INTSXP, catcount, maxcat)) returns the SEXP
//     produced by allocMatrix, unchanged (PROTECT is the identity).
//   - csplit3 is then a valid SEXPREC* pointing to a catcount x maxcat
//     int matrix.
//   - ALLOC(maxcat, sizeof(int *)) allocates ccsplit from the arena.
//   - If catcount == 0, no allocMatrix call occurs; csplit3 remains
//     R_NilValue (the nil sentinel).
//
// The nout count passed to UNPROTECT(1 + nout) at line 347 is either 6
// (if catcount == 0, csplit3 not PROTECTed) or 7 (if catcount > 0).
// In the fake runtime UNPROTECT is a no-op for any integer argument.
// -----------------------------------------------------------------------
//
// .Call boundary wrapper (same as Pattern 1):
//
//   extern "C" SEXP rpart_wrapper(
//           SEXP ncat2, ..., SEXP cost2) {
//       ArenaFrame _frame;
//       try {
//           return rpart(ncat2, ..., cost2);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
```

- **Arena / Memory Notes:**

  The three INTSXP matrices (`inode3`, `isplit3`, `csplit3`) are heap-allocated via `std::malloc` inside `allocVector`, exactly as the REALSXP matrices. They are **not** arena-managed and survive `ArenaFrame` destruction.

  The `ALLOC(maxcat, sizeof(int *))` call at `rpart.c:294` (which produces `ccsplit`, a scratch `int **` column-pointer array) **does** go to the arena. When `ArenaFrame _frame` destructs, `ccsplit` is freed along with all other ALLOC-managed scratch arrays. The `int[]` data that `ccsplit[i]` point into is part of `csplit3->data` — a heap allocation — and is not affected.

  The conditional allocation at `rpart.c:293` — inside `if (catcount > 0)` — is handled naturally: if `catcount == 0`, `allocMatrix` is never called, `csplit3` retains its initial value of `R_NilValue`, and no corresponding arena allocation for `ccsplit` is made (`ccsplit = NULL` at line 303). If `catcount > 0`, `allocMatrix(INTSXP, catcount, maxcat)` allocates `catcount * maxcat * sizeof(int)` bytes on the heap. The zero-fill loop at lines 299-300 is redundant with `allocVector`'s `std::memset(s->data, 0, bytes)`, but it compiles and runs correctly — writing zeros into an already-zeroed buffer is harmless.

  If `std::malloc` fails for either the `SEXPREC` node or the `int[]` buffer, `RError` is thrown and the `rpart_wrapper` catch block handles it.

- **Explanation:**

  The same single `Rf_allocMatrix` function handles both `REALSXP` and `INTSXP` via `sexptype_element_size(type)`, which maps `INTSXP` to `sizeof(int)` and `REALSXP` to `sizeof(double)`. The type tag stored in `s->type` correctly identifies the element type so that `INTEGER(s)` casts `s->data` to `int *` and `REAL(s)` casts to `double *`.

  Column-major access for INTSXP matrices follows the same pointer arithmetic as for REALSXP: `INTEGER(inode3)` returns `(int *)inode3->data`, and `iptr += nodecount` advances one full column of `nodecount` ints. No special handling is required in the fake.

  `PROTECT(allocMatrix(INTSXP, nodecount, 6))` expands to `Rf_protect(Rf_allocMatrix(INTSXP, nodecount, 6))`. `Rf_allocMatrix` returns a heap-allocated `SEXP`. `Rf_protect` returns it unchanged. The assignment `inode3 = PROTECT(...)` stores the pointer. `UNPROTECT(1 + nout)` at line 347 calls `Rf_unprotect(1 + nout)` which is an empty inline function. None of these calls modify any global state in the fake runtime.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Authoritative source for `fake_Rinternals.hpp`. Provides the `SEXPREC` struct definition (fields: `type`, `length`, `nrow`, `ncol`, `data`) and the `SEXP` typedef (`typedef SEXPREC *SEXP`). `Rf_allocMatrix` stores `nrow` and `ncol` in `s->nrow` and `s->ncol` respectively; these fields must be present in `SEXPREC`. Also provides `free_sexp()`, `R_NilValue`, `sexptype_element_size()`, and the `allocVector` implementation that `allocMatrix` delegates to. |
| `INTSXP.md` | Provides `#define INTSXP 13` within the `SEXPTYPE` constant block in `fake_Rinternals.hpp`. Three of the six `allocMatrix` call sites pass `INTSXP` as the type argument; `sexptype_element_size(INTSXP)` must return `sizeof(int)`. |
| `REALSXP.md` | Provides `#define REALSXP 14` within the same `SEXPTYPE` block. Three of the six `allocMatrix` call sites pass `REALSXP` as the type argument; `sexptype_element_size(REALSXP)` must return `sizeof(double)`. |
| `PROTECT.md` | Establishes that `PROTECT(s)` expands to `Rf_protect(s)` (identity inline function) and `UNPROTECT(n)` expands to `Rf_unprotect(n)` (no-op). Every `allocMatrix` call site in the CSV is wrapped in `PROTECT`; the fake PROTECT definitions must be in scope for the rpart source to compile. |
| `fake_arena.hpp` (canonical definition referenced in `SEXP.md` / Invariant 2) | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, and `arena_calloc`. Required by the `.Call` wrapper for `rpart()` because `rpart()` interleaves `allocMatrix` (heap) calls with `ALLOC`/`R_alloc` (arena) calls. The `ArenaFrame _frame` declared at the wrapper entry frees all arena scratch arrays on exit, independently of the heap-allocated SEXP matrices. |
| `allocVector.md` (if generated as a standalone guide; otherwise see `SEXP.md` Pattern P2) | `allocMatrix` is implemented as a thin wrapper over `allocVector`. The `allocVector` definition — including the `std::malloc` allocation of `SEXPREC` and the element data buffer, the `std::memset` zero-initialization, and the `RError` throw on failure — must be present in `fake_Rinternals.hpp` before `Rf_allocMatrix` is defined. |
