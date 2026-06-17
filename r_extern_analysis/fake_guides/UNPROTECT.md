# Fake Header Implementation Guide: `UNPROTECT`

---

### 1. Overview of `UNPROTECT` in R API

`UNPROTECT` is a macro defined in `Rinternals.h` as `#define UNPROTECT(n) Rf_unprotect(n)`. Its role in R's C API is to pop `n` entries from the GC protection stack that was grown by prior `PROTECT` (i.e., `Rf_protect`) calls within the same C stack frame, signalling to R's garbage collector that those `SEXP` objects no longer need to be kept alive through the current scope. `UNPROTECT` takes a single `int` argument (which may be an integer literal such as `1` or an integer expression such as `1 + nout`) and returns `void`; it is always called immediately before a `return` statement or at the point where the protected objects can safely be collected. In the fake runtime there is no garbage collector, so `UNPROTECT` reduces to a pure no-op `inline void` function, exactly mirroring the complementary `PROTECT` no-op documented in `PROTECT.md`.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `pred_rpart.c` | 145 | `UNPROTECT(1);` — single unprotect matching the single `PROTECT(allocVector(INTSXP, n))` at line 139; immediately precedes `return where;` |
| `rpart.c` | 347 | `UNPROTECT(1 + nout);` — integer-expression argument; `nout` is `catcount > 0 ? 7 : 6` (set at line 326), so the argument is 7 or 8; matches 6 or 7 conditional `PROTECT(allocMatrix/allocVector)` calls plus the unconditional `PROTECT(allocVector(VECSXP, nout))` at line 327; immediately precedes `return rlist;` |
| `rpartexp2.c` | 49 | `UNPROTECT(1);` — single unprotect matching the single `PROTECT(allocVector(INTSXP, n))` at line 47; immediately precedes `return keep;` |
| `xpred.c` | 294 | `UNPROTECT(1);` — single unprotect matching the single `PROTECT(allocVector(REALSXP, n * ncp * nresp))` at line 209; immediately precedes `return predict2;` |

**C types observed.**

- `UNPROTECT(n)` argument: always `int` — either a literal integer (`1`) or an `int` expression (`1 + nout` where `nout` is declared `int` at `rpart.c:326`).
- `UNPROTECT(n)` return value: `void` in every occurrence.
- The official signature from `Rinternals.h` line 599 is `void Rf_unprotect(int);`.

**Co-occurring R API items.**

Every `UNPROTECT` occurrence is paired with a corresponding set of `PROTECT` calls earlier in the same function:
- `pred_rpart.c:145` — matches `PROTECT(allocVector(INTSXP, n))` at line 139.
- `rpart.c:347` — matches `PROTECT(allocVector(INTSXP, n))` at line 194, `PROTECT(allocMatrix(...))` at lines 241, 261, 269, 278, 285, and conditionally at 293, plus `PROTECT(allocVector(VECSXP, nout))` at line 327.
- `rpartexp2.c:49` — matches `PROTECT(allocVector(INTSXP, n))` at line 47.
- `xpred.c:294` — matches `PROTECT(allocVector(REALSXP, n * ncp * nresp))` at line 209.

In all four files, `UNPROTECT` is the last R API call before the `return` statement; no SEXP accessors (`INTEGER`, `REAL`, etc.) appear between `UNPROTECT` and `return`.

**Distinct implementation patterns.**

Two patterns are present, differing only in the form of the integer argument:

| Pattern | CSV rows | Argument form |
|---|---|---|
| Pattern 1: Literal-integer argument `UNPROTECT(1)` | `pred_rpart.c:145`, `rpartexp2.c:49`, `xpred.c:294` | Compile-time constant `1` |
| Pattern 2: Integer-expression argument `UNPROTECT(1 + nout)` | `rpart.c:347` | Runtime `int` expression involving a local variable |

Both patterns share an identical fake strategy: `Rf_unprotect(int)` is an empty inline function that accepts any `int` argument. The `#define UNPROTECT(n) Rf_unprotect(n)` alias passes the argument through regardless of whether it is a literal or an expression.

---

### 3. Fake C++ Implementation Strategy

**Category: C — Allocation or Memory Function.**

`UNPROTECT` is classified as Category C because it is the deallocation side of R's GC protection protocol. Although `UNPROTECT` performs no deallocation itself (it merely decrements a GC protection counter in the real runtime), it is inseparable from `PROTECT` and `allocVector`/`allocMatrix` in the object lifecycle: every allocation that is registered with `PROTECT` is eventually deregistered with `UNPROTECT`. The `PROTECT.md` guide establishes the complete protection family (including `UNPROTECT`) in the same fake header section; this guide documents `UNPROTECT` specifically in isolation because it appears in a separate CSV extraction.

**Chosen mechanism.**

In the real R runtime, `Rf_unprotect(int n)` pops `n` entries from the thread-local LIFO protection stack inside R's GC. In the fake runtime, the GC does not exist and SEXP objects are heap-allocated, so there is no protection stack and no counter to decrement. `Rf_unprotect` is therefore an `inline void` function with an empty body. It accepts an `int` parameter (which may be any value, including a runtime expression such as `1 + nout`) and does nothing.

The `#define` alias from `Rinternals.h` line 389 must be preserved verbatim:

```c
#define UNPROTECT(n)    Rf_unprotect(n)
```

Additionally, the companion alias for the pointer-based variant at line 390 must also be reproduced:

```c
#define UNPROTECT_PTR(s)    Rf_unprotect_ptr(s)
```

And the lower-case alias from `Rinternals.h` line 1065-1066 (the R_ext compatibility block) must also be included:

```c
#define unprotect       Rf_unprotect
#define unprotect_ptr   Rf_unprotect_ptr
```

**Relationship to arena and heap memory.**

`UNPROTECT` operates on the GC protection stack, not on any memory allocator. In the fake runtime:
- SEXP objects produced by `allocVector` and `allocMatrix` are **heap-allocated** via `std::malloc` and are not freed by `UNPROTECT`. They survive until the Python caller invokes `free_sexp()` after data extraction.
- The `ArenaFrame` / `gArenaStack` infrastructure from `fake_arena.hpp` (Invariant 2) governs `R_alloc`/`ALLOC` scratch arrays, which are completely independent of the PROTECT/UNPROTECT mechanism.
- `UNPROTECT` has no interaction with either the heap allocator or the arena allocator in the fake runtime.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `UNPROTECT`. The function is a no-op; it cannot fail and emits no diagnostics.
- Invariant 2 (arena memory): not triggered by `UNPROTECT`. The function is a no-op with no allocator interaction.
- Invariant 3 (R Interpreter Items): `UNPROTECT` is not an R Interpreter Item. No function pointer bridge is required.

**Consistency with PROTECT.md.**

`PROTECT.md` already specifies the complete set of GC protection no-ops in its Section 3 and Section 4. This guide is fully consistent with those definitions: `PROTECT.md` defines `Rf_unprotect` as a no-op as part of the same fake header block, and this guide documents the specific rpart CSV rows where `UNPROTECT` appears. The actual C++ code presented here is the same code specified in `PROTECT.md`; the purpose of this guide is to document the usage patterns and design rationale for `UNPROTECT` specifically.

---

### 4. Fake Implementation Examples

#### Pattern 1: Literal-Integer Argument `UNPROTECT(1)`

- **Locations:** `pred_rpart.c:145`, `rpartexp2.c:49`, `xpred.c:294`

- **Original R API Usage:**

```c
/* pred_rpart.c:133-147 — full function showing PROTECT/UNPROTECT pair */
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
    UNPROTECT(1);   /* <-- target item */
    return where;
}

/* rpartexp2.c:43-51 */
SEXP
rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);   /* <-- target item */
    return keep;
}

/* xpred.c:205-295 (key lines only) */
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);
/* ... computation loop ... */
UNPROTECT(1);   /* <-- target item */
return predict2;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp — PROTECT / UNPROTECT section
// This block must appear after the SEXPREC / SEXP typedef block and after the
// allocVector / allocMatrix definitions (both from SEXP.md).

#pragma once

// Forward declaration — SEXP typedef must already be in scope from SEXP.md.
// typedef struct SEXPREC *SEXP;  (defined in SEXP.md, not repeated here)

// -----------------------------------------------------------------------
// PROTECT_INDEX — integer index type required by PROTECT_WITH_INDEX and
// REPROTECT.  Reproduced from Rinternals.h line 396.
// -----------------------------------------------------------------------
typedef int PROTECT_INDEX;

// -----------------------------------------------------------------------
// Rf_protect — identity function (no-op side-effect).
// In real R this pushes s onto the GC protection stack and returns s.
// In the fake runtime there is no GC; this simply returns s unchanged so
// that the pattern  SEXP x = PROTECT(allocVector(...));  compiles and
// assigns the allocated SEXP to x.
// -----------------------------------------------------------------------
inline SEXP Rf_protect(SEXP s) { return s; }

// -----------------------------------------------------------------------
// Rf_unprotect — no-op.
// In real R this pops n entries from the GC protection stack.
// In the fake runtime there is no protection stack; the function accepts
// any int (including runtime expressions such as 1 + nout) and does
// nothing.  Signature from Rinternals.h line 599:  void Rf_unprotect(int);
// -----------------------------------------------------------------------
inline void Rf_unprotect(int /*n*/) {}

// -----------------------------------------------------------------------
// Rf_unprotect_ptr — no-op.
// In real R this removes a specific SEXP from the protection stack by
// pointer comparison.  Not used in rpart CSV rows, but required so that
// any code that calls UNPROTECT_PTR compiles correctly.
// Signature from Rinternals.h line 601:  void Rf_unprotect_ptr(SEXP);
// -----------------------------------------------------------------------
inline void Rf_unprotect_ptr(SEXP /*s*/) {}

// -----------------------------------------------------------------------
// R_ProtectWithIndex — no-op.
// In real R this protects x and writes its stack index into *i.
// -----------------------------------------------------------------------
inline void R_ProtectWithIndex(SEXP /*s*/, PROTECT_INDEX * /*i*/) {}

// -----------------------------------------------------------------------
// R_Reprotect — no-op.
// In real R this replaces the protected object at stack position i with x.
// -----------------------------------------------------------------------
inline void R_Reprotect(SEXP /*s*/, PROTECT_INDEX /*i*/) {}

// -----------------------------------------------------------------------
// #define aliases — must match Rinternals.h exactly so that the original
// rpart source files compile without any modification.
// Sources: Rinternals.h lines 388-390 and 1065-1066.
// -----------------------------------------------------------------------
#define PROTECT(s)               Rf_protect(s)
#define UNPROTECT(n)             Rf_unprotect(n)
#define UNPROTECT_PTR(s)         Rf_unprotect_ptr(s)
#define PROTECT_WITH_INDEX(x,i)  R_ProtectWithIndex(x, i)
#define REPROTECT(x,i)           R_Reprotect(x, i)
// Lower-case aliases from the R_ext compatibility block (Rinternals.h:1065-1066)
#define unprotect                Rf_unprotect
#define unprotect_ptr            Rf_unprotect_ptr

// -----------------------------------------------------------------------
// .Call boundary wrapper — representative example for pred_rpart.
//
// The ArenaFrame guard at entry frees R_alloc / ALLOC scratch arrays when
// the function returns (or throws).  SEXP objects (allocVector results)
// are heap-allocated independently and survive the ArenaFrame destruction
// to be returned to Python.
//
// Example:
//
//   #include "fake_Rinternals.hpp"
//   #include "fake_arena.hpp"
//
//   extern "C" SEXP pred_rpart_wrapper(
//           SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
//           SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
//           SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2) {
//       ArenaFrame _frame;   // destroyed on exit, frees R_alloc scratch arrays
//       try {
//           return pred_rpart(dimx, nnode, nsplit, dimc, nnum, nodes2,
//                             vnum, split2, csplit2, usesur, xdata2, xmiss2);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
//
// Inside pred_rpart, the sequence expands as follows at the preprocessor:
//
//   SEXP where = PROTECT(allocVector(INTSXP, n));
//   =>  SEXP where = Rf_protect(allocVector(INTSXP, n));
//   =>  SEXP where = allocVector(INTSXP, n);   // Rf_protect is identity
//
//   UNPROTECT(1);
//   =>  Rf_unprotect(1);
//   =>  (nothing)                              // Rf_unprotect is no-op
//
//   return where;                              // where is a valid heap SEXP
// -----------------------------------------------------------------------
```

- **Arena / Memory Notes:** `UNPROTECT(1)` expands to `Rf_unprotect(1)`, which is an empty inline function. No memory is freed, allocated, or touched. The SEXP `where` / `keep` / `predict2` returned from these functions is a heap-allocated `SEXPREC` node (produced by `allocVector` inside the function). Its data buffer (`sexp->data`) remains valid after `UNPROTECT` because the fake runtime does not collect it. The caller (Python layer) is responsible for calling `free_sexp()` once data has been extracted. The `ArenaFrame` guard at the `.Call` wrapper level is completely independent of this SEXP lifetime: it frees only `R_alloc`/`ALLOC` scratch arrays, none of which appear in `pred_rpart`, `rpartexp2`, or the output-allocation section of `xpred`.

- **Explanation:** The preprocessor expands `UNPROTECT(1)` to `Rf_unprotect(1)`. The fake `Rf_unprotect` is declared `inline void Rf_unprotect(int)` with an empty body. Because the body is empty, the compiler can — and will — eliminate the call entirely after inlining; the generated machine code contains no instruction corresponding to `UNPROTECT(1)`. The original source files require no modification: the `#define UNPROTECT(n) Rf_unprotect(n)` alias is preserved verbatim from `Rinternals.h`, so every occurrence of `UNPROTECT(...)` in the rpart C sources continues to compile as written.

---

#### Pattern 2: Integer-Expression Argument `UNPROTECT(1 + nout)`

- **Locations:** `rpart.c:347`

- **Original R API Usage:**

```c
/* rpart.c:325-349 — output list construction and UNPROTECT */

/* nout is set at line 326: number of output list elements (6 or 7) */
int nout = catcount > 0 ? 7 : 6;

/* One unconditional PROTECT for the output list itself */
SEXP rlist = PROTECT(allocVector(VECSXP, nout));
SEXP rname = allocVector(STRSXP, nout);   /* not protected */
setAttrib(rlist, R_NamesSymbol, rname);

/* Fill rlist with SET_VECTOR_ELT, SET_STRING_ELT (lines 330-344) */
SET_VECTOR_ELT(rlist, 0, which3);
SET_STRING_ELT(rname, 0, mkChar("which"));
SET_VECTOR_ELT(rlist, 1, cptable3);
SET_STRING_ELT(rname, 1, mkChar("cptable"));
/* ... 4 more unconditional slots ... */
if (catcount > 0) {
    SET_VECTOR_ELT(rlist, 6, csplit3);
    SET_STRING_ELT(rname, 6, mkChar("csplit"));
}

/*
 * UNPROTECT(1 + nout):
 *   - 1  matches the PROTECT(allocVector(VECSXP, nout)) at line 327
 *   - nout (6 or 7) matches the nout earlier PROTECTs:
 *       which3    (line 194)
 *       cptable3  (line 241)
 *       dnode3    (line 261)
 *       dsplit3   (line 269)
 *       inode3    (line 278)
 *       isplit3   (line 285)
 *       csplit3   (line 293, conditional: only when catcount > 0)
 */
UNPROTECT(1 + nout);   /* <-- target item; argument is a runtime int expr */
return rlist;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp — no additional code is required for Pattern 2.
// The same Rf_unprotect(int) no-op and the same
//   #define UNPROTECT(n)  Rf_unprotect(n)
// alias defined for Pattern 1 handle this case identically.
//
// The preprocessor expands:
//
//   UNPROTECT(1 + nout);
//   =>  Rf_unprotect(1 + nout);
//
// The argument expression  1 + nout  is evaluated as a standard C int
// expression (nout is declared int at rpart.c:326) and the result is
// passed to Rf_unprotect(int).  The function body is empty, so the
// expression is evaluated for side effects only (there are none) and
// the call is eliminated by the compiler after inlining.
//
// The .Call wrapper for rpart illustrates the full boundary:
//
//   #include "fake_Rinternals.hpp"
//   #include "fake_arena.hpp"
//
//   extern "C" SEXP rpart_wrapper(
//           SEXP ncat2, SEXP method2, SEXP opt2, SEXP parms2,
//           SEXP xvals2, SEXP xgrp2, SEXP ymat2, SEXP xmat2,
//           SEXP wt2, SEXP ny2, SEXP cost2) {
//       ArenaFrame _frame;   // frees ALLOC scratch arrays (ddnode, etc.)
//       try {
//           return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
//                        ymat2, xmat2, wt2, ny2, cost2);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return R_NilValue;
//       }
//   }
//
// Inside rpart(), the PROTECT/UNPROTECT calls expand as:
//
//   which3 = PROTECT(allocVector(INTSXP, n));
//   =>  which3 = Rf_protect(allocVector(INTSXP, n));
//   =>  which3 = allocVector(INTSXP, n);      // Rf_protect is identity
//
//   UNPROTECT(1 + nout);
//   =>  Rf_unprotect(1 + nout);
//   =>  (nothing — empty body, expression has no side effects)
//
//   return rlist;   // rlist is a valid heap-allocated VECSXP
```

- **Arena / Memory Notes:** `UNPROTECT(1 + nout)` is a no-op. None of the SEXP objects in `rpart.c` — `which3`, `cptable3`, `dnode3`, `dsplit3`, `inode3`, `isplit3`, `csplit3`, `rlist`, `rname` — are freed by this call. They are all heap-allocated via `allocVector`/`allocMatrix` and will outlive the function return. The `ArenaFrame` guard at the `.Call` wrapper entry frees the `ALLOC`-allocated scratch arrays (`rp.csplit`, `rp.lwt`, `ddnode`, `ddsplit`, `iinode`, `iisplit`, `ccsplit`, and the `cptable` linked list nodes), which are interleaved with the `PROTECT(allocMatrix/allocVector)` calls in `rpart.c` but managed by a completely separate allocator. Python extracts data from `rlist` (and its child SEXPs) via `REAL`/`INTEGER` accessors on the returned SEXP, then calls `free_sexp(rlist)` to free the entire tree of SEXP nodes and their data buffers. The conditional `csplit3` allocation (line 293) and the conditional slot in `UNPROTECT(1 + nout)` (where `nout = 7` when `catcount > 0`) are both handled correctly: because `Rf_unprotect` ignores its argument, there is no mismatch risk if the protection count is wrong — the fake is unconditionally a no-op regardless of the value of `nout`.

- **Explanation:** The argument `1 + nout` is a C integer expression. The `#define UNPROTECT(n) Rf_unprotect(n)` macro substitutes `n` with the token sequence `1 + nout`, producing `Rf_unprotect(1 + nout)`. This is a valid C++ function call: `nout` is an `int` local variable in scope at `rpart.c:347` (declared at line 326), `1 + nout` evaluates to an `int`, and `Rf_unprotect(int)` accepts it. The body is empty, so the call is eliminated entirely. The original source file requires no modification. The variable-count pattern in real R (where the number of `PROTECT` calls may vary based on `catcount`) is harmless in the fake: the protection stack does not exist, so there is no stack underflow or counter mismatch to worry about.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct definition and the `SEXP` typedef (`typedef struct SEXPREC *SEXP`). `Rf_protect` returns `SEXP` and takes `SEXP`; `Rf_unprotect_ptr` takes `SEXP`. The `SEXP` type must be in scope before any of the protection inline functions are defined. `SEXP.md` also provides `allocVector` and `allocMatrix` — the functions whose results are passed through `PROTECT` and later released by `UNPROTECT`. |
| `PROTECT.md` | `UNPROTECT` is the complementary operation to `PROTECT`. Both are defined in the same fake header section. `PROTECT.md` establishes `Rf_protect`, `Rf_unprotect`, `Rf_unprotect_ptr`, `R_ProtectWithIndex`, `R_Reprotect`, `PROTECT_INDEX`, and all five `#define` aliases. This guide is fully consistent with those definitions. In the compiled fake header, the code from both guides must appear in a single block (no duplication) — the PROTECT/UNPROTECT block is defined once and shared. |
| `fake_arena.hpp` (canonical definition in Invariant 2) | Provides `ArenaFrame`, `gArenaStack`, `arena_alloc`, and `arena_calloc`. Required at the `.Call` wrapper level because all four rpart functions that contain `UNPROTECT` calls also use `ALLOC`/`R_alloc` scratch allocations (managed by `ArenaFrame`). `UNPROTECT` itself does not call any arena functions, but the same compilation units that use `UNPROTECT` also require `fake_arena.hpp` to be included. |
| `INTSXP.md` | Provides `#define INTSXP 13`. Required because the `PROTECT` calls paired with `UNPROTECT(1)` in `pred_rpart.c:139` and `rpartexp2.c:47` use `INTSXP` as the `SEXPTYPE` argument to `allocVector`. |
| `REALSXP.md` | Provides `#define REALSXP 14`. Required because the `PROTECT` call paired with `UNPROTECT(1)` in `xpred.c:209` uses `REALSXP` as the `SEXPTYPE` argument to `allocVector`. |
| `VECSXP.md` | Provides `#define VECSXP 19`. Required because the `PROTECT(allocVector(VECSXP, nout))` at `rpart.c:327` is part of the set of objects released by `UNPROTECT(1 + nout)` at `rpart.c:347`. |
