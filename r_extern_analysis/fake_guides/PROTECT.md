# Fake Header Implementation Guide: `PROTECT`

---

### 1. Overview of `PROTECT` in R API

`PROTECT` is a macro defined in `Rinternals.h` as `#define PROTECT(s) Rf_protect(s)`. Its role in R's C API is to register a `SEXP` object with R's garbage collector (GC) so that the object is not collected while the current C stack frame holds a reference to it. `PROTECT` takes a single `SEXP` argument, pushes it onto R's internal protection stack, and returns the same `SEXP` unchanged — it is purely an identity function with a side effect on the GC protection stack. In the fake runtime there is no garbage collector, so `PROTECT` reduces to a pure identity inline function, and its companions `UNPROTECT`, `UNPROTECT_PTR`, `PROTECT_WITH_INDEX`, and `REPROTECT` reduce to no-ops.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `pred_rpart.c` | 139 | `SEXP where = PROTECT(allocVector(INTSXP, n));` — only `PROTECT` call in function; matching `UNPROTECT(1)` at line 145 before return |
| `rpart.c` | 194 | `which3 = PROTECT(allocVector(INTSXP, n));` — first of seven PROTECT calls in `rpart()`; wraps `allocVector` result assigned to a local SEXP variable |
| `rpart.c` | 241 | `cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));` — wraps `allocMatrix` with conditional row count |
| `rpart.c` | 261 | `dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));` — wraps `allocMatrix` |
| `rpart.c` | 269 | `dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));` — wraps `allocMatrix` |
| `rpart.c` | 278 | `inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));` — wraps `allocMatrix` |
| `rpart.c` | 285 | `isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));` — wraps `allocMatrix` |
| `rpart.c` | 293 | `csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));` — conditional PROTECT inside `if (catcount > 0)` block |
| `rpart.c` | 327 | `SEXP rlist = PROTECT(allocVector(VECSXP, nout));` — wraps `allocVector` for output list; matching `UNPROTECT(1 + nout)` at line 347 |
| `rpartexp2.c` | 47 | `SEXP keep = PROTECT(allocVector(INTSXP, n));` — only `PROTECT` call in function; matching `UNPROTECT(1)` at line 49 |
| `xpred.c` | 209 | `predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));` — wraps `allocVector` for a large real output buffer |

**C types observed.**

- `PROTECT(s)` argument: always `SEXP` (the return value of `allocVector` or `allocMatrix`).
- `PROTECT(s)` return value: `SEXP` — used directly as an rvalue assigned to a `SEXP` local variable.
- `UNPROTECT(n)` argument: always a literal integer (`1`, `1 + nout`) indicating how many stack frames to pop; return value `void`.

**Co-occurring R API items.**

Every `PROTECT` occurrence in the CSV is immediately wrapped around one of the two allocation functions:
- `allocVector(SEXPTYPE, int length)` — 1-D vector allocation
- `allocMatrix(SEXPTYPE, int nrow, int ncol)` — 2-D matrix allocation

In `rpart.c`, these allocation calls are interleaved with `ALLOC(...)` (arena-backed scratch allocations, not SEXP allocations). Immediately after the PROTECT call, the allocated SEXP is accessed via `REAL(sexp)` or `INTEGER(sexp)` to obtain a raw pointer into the data buffer.

Every PROTECT in `pred_rpart.c`, `rpartexp2.c`, and `xpred.c` has a matching `UNPROTECT(1)` in the same function scope before the return. In `rpart.c`, there are up to 7 conditional PROTECTs with a final `UNPROTECT(1 + nout)` (where `nout` is 6 or 7 depending on `catcount > 0`) at line 347.

**Distinct implementation patterns.**

Two patterns are present, differing only in which allocation function is wrapped:

| Pattern | CSV rows | Allocation wrapped |
|---|---|---|
| Pattern 1: Protect result of `allocVector` (1-D vector) | `pred_rpart.c:139`, `rpart.c:194`, `rpart.c:327`, `rpartexp2.c:47`, `xpred.c:209` | `allocVector(SEXPTYPE, int)` |
| Pattern 2: Protect result of `allocMatrix` (2-D matrix) | `rpart.c:241`, `rpart.c:261`, `rpart.c:269`, `rpart.c:278`, `rpart.c:285`, `rpart.c:293` | `allocMatrix(SEXPTYPE, int, int)` |

Both patterns share an identical fake strategy: `PROTECT` is a pure identity function that returns its argument unchanged, and `UNPROTECT` is a no-op.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function.**

`PROTECT` is classified as Category C because it is an integral part of R's GC protection protocol, which governs the lifetime of heap-allocated SEXP objects. Although it performs no allocation itself, it is always paired with allocation functions (`allocVector`, `allocMatrix`) and with the deallocation-side `UNPROTECT`.

**Chosen mechanism.**

In the real R runtime, `Rf_protect(SEXP s)` pushes `s` onto a thread-local LIFO protection stack inside R's GC, increments a counter, and returns `s`. `Rf_unprotect(int n)` pops `n` entries from that stack. This machinery is entirely absent from the fake runtime because there is no garbage collector. Therefore:

- `Rf_protect(SEXP s)` is an `inline` C++ function that returns `s` unchanged.
- `Rf_unprotect(int n)` is an `inline` C++ function with an empty body.
- `Rf_unprotect_ptr(SEXP s)` is an `inline` C++ function with an empty body.
- `R_ProtectWithIndex(SEXP s, PROTECT_INDEX *i)` is an `inline` no-op.
- `R_Reprotect(SEXP s, PROTECT_INDEX i)` is an `inline` no-op.

The original `#define` aliases from `Rinternals.h` must be preserved verbatim so that the original source files compile unchanged without any modification:

```c
#define PROTECT(s)               Rf_protect(s)
#define UNPROTECT(n)             Rf_unprotect(n)
#define UNPROTECT_PTR(s)         Rf_unprotect_ptr(s)
#define PROTECT_WITH_INDEX(x,i)  R_ProtectWithIndex(x, i)
#define REPROTECT(x,i)           R_Reprotect(x, i)
```

The `typedef int PROTECT_INDEX;` from `Rinternals.h` line 396 must also be reproduced in the fake header so that `PROTECT_WITH_INDEX` and `REPROTECT` compile correctly (they take a `PROTECT_INDEX *` argument). Even though these macros are not used in rpart's CSV rows, they appear in `Rinternals.h` and may be referenced by transitively included headers.

**Relationship to arena and heap memory.**

`PROTECT` operates exclusively on SEXP objects. SEXP objects in the fake runtime are **heap-allocated** (via `std::malloc` inside `allocVector` and `allocMatrix`) — they are never arena-allocated. This means:

- `PROTECT` has no interaction with the `ArenaFrame` / `gArenaStack` infrastructure from `fake_arena.hpp`.
- The `ArenaFrame` RAII guard at the entry of each `.Call` wrapper function governs only the `R_alloc`/`ALLOC` scratch arrays, not the SEXP objects produced by `allocVector`/`allocMatrix`.
- The SEXP objects returned from the `.Call` entry points (`rpart`, `xpred`, `pred_rpart`, `rpartexp2`) must survive past `ArenaFrame` destruction — they are heap-allocated and caller-owned. Python reads their data and then calls `free_sexp()` to release them.

Concretely, the SEXP lifetime model is: `allocVector`/`allocMatrix` allocate SEXP nodes and data buffers via `std::malloc`, `PROTECT` passes them through unchanged, `UNPROTECT` does nothing, and Python eventually frees them via `free_sexp()`. The arena is a completely separate subsystem governing scratch arrays that are intentionally discarded at the `.Call` boundary.

The implementations of `allocVector` and `allocMatrix` are documented in `SEXP.md` (which serves as the authoritative `fake_Rinternals.hpp`) since standalone `allocVector.md` and `allocMatrix.md` guides have not been generated separately — those functions are defined within the SEXP guide's Pattern P2 section.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `PROTECT` itself. `allocVector` and `allocMatrix` (the functions always wrapped by `PROTECT`) throw `RError` on allocation failure; `PROTECT` propagates the thrown exception unchanged since `Rf_protect` is called with the result of those functions. The `.Call` wrapper's `try/catch` block at the `.Call` boundary catches `RError` from either source.
- Invariant 2 (arena memory): not triggered by `PROTECT`. SEXP objects are heap-allocated, not arena-allocated. The arena governs only `R_alloc`/`ALLOC` scratch memory.
- Invariant 3 (R Interpreter Items): `PROTECT` is not an R Interpreter Item. No function pointer bridge is required.

---

### 4. Fake Implementation Examples

#### Pattern 1: Protect Result of `allocVector` (1-D Vector)

- **Locations:** `pred_rpart.c:139`, `rpart.c:194`, `rpart.c:327`, `rpartexp2.c:47`, `xpred.c:209`

- **Original R API Usage:**

```c
/* pred_rpart.c:133-147 — INTSXP, returned directly */
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

/* rpartexp2.c:43-51 — INTSXP, returned directly */
SEXP
rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);
    return keep;
}

/* rpart.c:327 — VECSXP output list */
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
/* ... fill rlist with SET_VECTOR_ELT ... */
UNPROTECT(1 + nout);
return rlist;

/* xpred.c:209 — REALSXP large buffer */
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp — PROTECT / UNPROTECT section
// (This section belongs inside fake_Rinternals.hpp, after the SEXPREC/SEXP
// typedef block and the allocVector/allocMatrix definitions from SEXP.md.)

#pragma once
// ... (SEXPREC, SEXP, SEXPTYPE, allocVector, allocMatrix defined above) ...

// -----------------------------------------------------------------------
// PROTECT_INDEX — integer index type for PROTECT_WITH_INDEX / REPROTECT.
// Reproduced from Rinternals.h line 396.
// -----------------------------------------------------------------------
typedef int PROTECT_INDEX;

// -----------------------------------------------------------------------
// Rf_protect — identity function.  In real R this pushes s onto the GC
// protection stack.  In the fake runtime there is no GC, so it returns s
// unchanged.  The return type is SEXP so that the idiom
//
//     SEXP x = PROTECT(allocVector(INTSXP, n));
//
// compiles and works correctly: PROTECT(allocVector(...)) expands to
// Rf_protect(allocVector(...)), which returns the SEXP produced by
// allocVector unchanged.
// -----------------------------------------------------------------------
inline SEXP Rf_protect(SEXP s) { return s; }

// -----------------------------------------------------------------------
// Rf_unprotect — no-op.  In real R this pops n entries from the GC
// protection stack.  In the fake runtime, SEXP objects are heap-allocated
// and not GC-managed, so there is nothing to pop.
// -----------------------------------------------------------------------
inline void Rf_unprotect(int /*n*/) {}

// -----------------------------------------------------------------------
// Rf_unprotect_ptr — no-op.  In real R this removes a specific SEXP from
// the protection stack by pointer comparison.
// -----------------------------------------------------------------------
inline void Rf_unprotect_ptr(SEXP /*s*/) {}

// -----------------------------------------------------------------------
// R_ProtectWithIndex — no-op.  In real R this protects x and stores its
// stack index in *i so that REPROTECT can replace it later.
// -----------------------------------------------------------------------
inline void R_ProtectWithIndex(SEXP /*s*/, PROTECT_INDEX * /*i*/) {}

// -----------------------------------------------------------------------
// R_Reprotect — no-op.  In real R this replaces the protected object at
// stack index i with x.
// -----------------------------------------------------------------------
inline void R_Reprotect(SEXP /*s*/, PROTECT_INDEX /*i*/) {}

// -----------------------------------------------------------------------
// #define aliases — must match Rinternals.h exactly so that the original
// rpart source files compile without modification.
// -----------------------------------------------------------------------
#define PROTECT(s)               Rf_protect(s)
#define UNPROTECT(n)             Rf_unprotect(n)
#define UNPROTECT_PTR(s)         Rf_unprotect_ptr(s)
#define PROTECT_WITH_INDEX(x,i)  R_ProtectWithIndex(x, i)
#define REPROTECT(x,i)           R_Reprotect(x, i)

// -----------------------------------------------------------------------
// .Call boundary wrapper pattern — required for ALL rpart entry points.
//
// The ArenaFrame guard frees R_alloc/ALLOC scratch arrays on exit.
// SEXP objects (allocVector / allocMatrix results) are heap-allocated and
// must outlive the ArenaFrame; they are returned to Python and freed by
// free_sexp() after data extraction.
//
// Pattern for pred_rpart (representative):
//
//   #include "fake_Rinternals.hpp"
//   #include "fake_arena.hpp"
//
//   extern "C" SEXP pred_rpart_wrapper(
//           SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
//           SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
//           SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2) {
//       ArenaFrame _frame;   // frees R_alloc scratch arrays on exit
//       try {
//           return pred_rpart(dimx, nnode, nsplit, dimc, nnum, nodes2,
//                             vnum, split2, csplit2, usesur, xdata2, xmiss2);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
//
// Inside pred_rpart, the sequence:
//   SEXP where = PROTECT(allocVector(INTSXP, n));
// expands to:
//   SEXP where = Rf_protect(allocVector(INTSXP, n));
// which is functionally identical to:
//   SEXP where = allocVector(INTSXP, n);
// in the fake runtime.
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:** The SEXP objects allocated by `allocVector` are **heap-allocated** via `std::malloc` inside `allocVector`. `PROTECT` is a pure identity function and performs no allocation of its own. `UNPROTECT(n)` is a no-op. The SEXP node and its data buffer survive until `free_sexp()` is called by the Python caller after data extraction. The `ArenaFrame` guard at the `.Call` boundary frees only the `R_alloc`/`ALLOC` scratch arrays — it has no effect on heap-allocated SEXP nodes. If `allocVector` fails to obtain memory, it throws `RError`; `PROTECT` (being a pure call-through) propagates this exception to the `.Call` boundary `try/catch`.

- **Explanation:** The macro `PROTECT(s)` expands to `Rf_protect(s)`. The fake `Rf_protect` is an `inline SEXP` function returning its argument. This means every source statement of the form `SEXP x = PROTECT(allocVector(...))` compiles identically under the fake headers: the `allocVector` call is evaluated first, its `SEXP` result is passed to `Rf_protect`, which returns it unchanged, and the result is assigned to `x`. The original source files require no modification. `UNPROTECT(n)` expands to `Rf_unprotect(n)` which is an empty inline function — valid for any integer argument, including the `1 + nout` expression in `rpart.c:347`.

---

#### Pattern 2: Protect Result of `allocMatrix` (2-D Matrix)

- **Locations:** `rpart.c:241`, `rpart.c:261`, `rpart.c:269`, `rpart.c:278`, `rpart.c:285`, `rpart.c:293`

- **Original R API Usage:**

```c
/* rpart.c:241-252 — REALSXP matrix with conditional row count */
cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));
dptr = REAL(cptable3);

/* rpart.c:261-267 — REALSXP matrix for tree node data */
dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));
ddnode = (double **) ALLOC(3 + rp.num_resp, sizeof(double *));
dptr = REAL(dnode3);
for (i = 0; i < 3 + rp.num_resp; i++) {
    ddnode[i] = dptr;
    dptr += nodecount;
}

/* rpart.c:269 — REALSXP matrix for split data */
dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));

/* rpart.c:278 — INTSXP matrix for integer node data */
inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));

/* rpart.c:285 — INTSXP matrix for integer split data */
isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));

/* rpart.c:292-301 — conditional PROTECT inside if block */
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
} else
    ccsplit = NULL;

/* rpart.c:347 — matching UNPROTECT for all protected objects in rpart() */
UNPROTECT(1 + nout);   /* nout is 6 or 7 depending on catcount > 0 */
return rlist;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp — no additional code is needed for Pattern 2.
// The same Rf_protect / Rf_unprotect / #define block from Pattern 1
// handles allocMatrix results identically to allocVector results.
//
// allocMatrix is defined in fake_Rinternals.hpp (from SEXP.md) as:
//
//   inline SEXP allocMatrix(SEXPTYPE type, int nrow, int ncol) {
//       SEXP s = allocVector(type, nrow * ncol);
//       s->nrow = nrow;
//       s->ncol = ncol;
//       return s;
//   }
//
// When the source writes:
//
//   cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3,
//                                  rp.num_unique_cp));
//
// The preprocessor expands PROTECT to Rf_protect:
//
//   cptable3 = Rf_protect(allocMatrix(REALSXP, xvals > 1 ? 5 : 3,
//                                     rp.num_unique_cp));
//
// allocMatrix allocates a SEXPREC node and a double[] buffer on the heap,
// sets s->nrow and s->ncol, and returns the SEXP.  Rf_protect returns the
// SEXP unchanged.  cptable3 now holds a valid SEXP pointer.
//
// The subsequent REAL(cptable3) call returns (double *)cptable3->data,
// which points to the zero-initialized double[nrow*ncol] buffer.
//
// For rpart.c specifically, the .Call wrapper is:
//
//   extern "C" SEXP rpart_wrapper(
//           SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2,
//           SEXP xvals2, SEXP xgrp2, SEXP ymat2, SEXP xmat2,
//           SEXP wt2, SEXP ny2, SEXP cost2) {
//       ArenaFrame _frame;   // covers all ALLOC() calls inside rpart()
//       try {
//           return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
//                        ymat2, xmat2, wt2, ny2, cost2);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
//
// Inside rpart(), the interleaving of PROTECT(allocMatrix(...)) calls and
// ALLOC(...) calls is handled by two independent subsystems:
//   - allocMatrix -> std::malloc -> heap (SEXP nodes, owned by Python)
//   - ALLOC -> arena_alloc -> ArenaFrame (scratch arrays, freed on exit)
// The two subsystems do not interact.
```

- **Arena / Memory Notes:** The SEXP objects allocated by `allocMatrix` are **heap-allocated** via `std::malloc` (through `allocVector`, which `allocMatrix` delegates to). `PROTECT` is identity; `UNPROTECT(1 + nout)` is a no-op regardless of the integer argument. All six `allocMatrix` results in `rpart.c` (lines 241, 261, 269, 278, 285, 293) are held in local `SEXP` variables (`cptable3`, `dnode3`, `dsplit3`, `inode3`, `isplit3`, `csplit3`) that are assigned into slots of the `rlist` VECSXP output list via `SET_VECTOR_ELT`. The VECSXP's `data` buffer (a `SEXP[]` array) holds pointers to these child SEXPs. When Python calls `free_sexp(rlist)`, the `free_sexp` function recursively frees all child SEXPs before freeing the parent VECSXP. The `ArenaFrame` destruction at `.Call` exit frees only the `ALLOC`-allocated scratch arrays (`ddnode`, `ddsplit`, `iinode`, `iisplit`, `ccsplit` etc.) which are interleaved with the `PROTECT(allocMatrix(...))` calls in `rpart.c` but managed by a completely separate allocator.

- **Explanation:** The fake header requires no additional code for Pattern 2 beyond what is already defined for Pattern 1. The same `Rf_protect` identity function and the same `#define PROTECT(s) Rf_protect(s)` alias handle `allocMatrix` results identically to `allocVector` results: `PROTECT(allocMatrix(...))` expands to `Rf_protect(allocMatrix(...))`, `allocMatrix` returns a heap-allocated `SEXP`, and `Rf_protect` returns it unchanged. The conditional PROTECT at `rpart.c:293` — inside `if (catcount > 0)` — compiles without any special treatment because `PROTECT` is a pure expression (no side effects in the fake). The `UNPROTECT(1 + nout)` at line 347 accepts an integer expression argument correctly because `Rf_unprotect(int)` takes any `int`.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the complete `fake_Rinternals.hpp` with the `SEXPREC` struct definition (`type`, `length`, `nrow`, `ncol`, `data` fields) and the `SEXP` typedef. `Rf_protect` returns `SEXP` and takes `SEXP`; the typedef must be in scope before the `PROTECT` inline functions are defined. Also provides `allocVector` and `allocMatrix` implementations (Pattern P2 in SEXP.md) — the functions whose results are always passed directly to `PROTECT` in the rpart source. |
| `fake_arena.hpp` (canonical definition in SEXP.md / Invariant 2) | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, and `arena_calloc`. Required at the `.Call` wrapper level: every entry point that calls `PROTECT(allocVector/allocMatrix)` also calls `ALLOC(...)` (which maps to `R_alloc`, which maps to `arena_alloc`). The `ArenaFrame` guard must be declared at the top of the `.Call` wrapper to ensure arena cleanup. `PROTECT` itself does not call arena functions, but the same compilation units that use `PROTECT` also use `ALLOC`. |
| `INTSXP.md` | Provides `#define INTSXP 13` (the `SEXPTYPE` constant). Required because six of the eleven `PROTECT` call sites in the CSV pass `INTSXP` as the first argument to `allocVector` or `allocMatrix`. |
| `REALSXP.md` | Provides `#define REALSXP 14`. Required because five `PROTECT` call sites pass `REALSXP` to `allocMatrix` or `allocVector`. |
| `VECSXP.md` | Provides `#define VECSXP 19`. Required because `rpart.c:327` calls `allocVector(VECSXP, nout)` inside a `PROTECT` call. |
