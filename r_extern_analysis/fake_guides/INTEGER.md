# Fake Header Implementation Guide: `INTEGER`

---

### 1. Overview of `INTEGER` in R API

`INTEGER` is a Category B accessor function in R's C API, declared in `Rinternals.h` as `int *(INTEGER)(SEXP x)`. Its sole purpose is to extract the raw `int *` data pointer from a `SEXP` object whose type tag is `INTSXP` (value `13`). The function receives one argument — a `SEXP` pointing to an integer vector or matrix — and returns a pointer to its contiguous `int` element buffer, allowing the calling C code to read and write the integer data directly without going through R's value-semantics layer. In R's real implementation the function body reaches into the internal `SEXPREC` structure; in the fake runtime it casts `sexp->data` to `int *`. `INTEGER` is not an R Interpreter Item; it requires no running R interpreter and no function-pointer bridge.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `pred_rpart.c` | 140 | `pred_rpart0(INTEGER(dimx), ..., INTEGER(where));` |
| `rpart.c` | 75 | `ncat = INTEGER(ncat2);` |
| `rpart.c` | 76 | `xgrp = INTEGER(xgrp2);` |
| `rpart.c` | 112 | `rp.numcat = INTEGER(ncat2);` |
| `rpart.c` | 195 | `rp.which = INTEGER(which3);` |
| `rpart.c` | 279 | `iptr = INTEGER(inode3);` |
| `rpart.c` | 286 | `iptr = INTEGER(isplit3);` |
| `rpart.c` | 295 | `iptr = INTEGER(csplit3);` |
| `rpart_callback.c` | 69 | `ndata = INTEGER(stemp);` |
| `rpartexp2.c` | 48 | `Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));` |
| `xpred.c` | 69 | `ncat = INTEGER(ncat2);` |
| `xpred.c` | 70 | `xgrp = INTEGER(xgrp2);` |
| `xpred.c` | 110 | `rp.numcat = INTEGER(ncat2);` |

**Argument and return types observed across all rows.**

`INTEGER` always takes a single `SEXP` argument and always returns `int *`. The receiving variable is one of:

- `int *ncat` / `int *xgrp` — module-level scratch pointers declared at the top of `rpart.c` and `xpred.c`, assigned from SEXP input parameters delivered by `.Call`.
- `int *iptr` — a local temporary pointer in `rpart.c` used to stride across the flat column-major buffer of a matrix SEXP.
- `int *` fields of the `rp` struct — specifically `rp.which` (`rpart.c:195`) and `rp.numcat` (`rpart.c:112`, `xpred.c:110`).
- `int *ndata` — a static module-level pointer in `rpart_callback.c:40` set from the result of `R_getVar`.
- An `int *` argument passed directly to an internal C function (`pred_rpart.c:140`, `rpartexp2.c:48`).

**Co-occurring R API items in context windows.**

- `allocVector(INTSXP, n)` and `allocMatrix(INTSXP, nrow, ncol)` — the source SEXP passed to `INTEGER` was produced by one of these in many cases (`rpart.c:194–195`, `rpart.c:278–279`, `rpart.c:285–286`, `rpart.c:293–295`, `pred_rpart.c:139–140`, `rpartexp2.c:47–48`). For input parameters (`rpart.c:75–76`, `xpred.c:69–70`) the SEXP was provided by the R caller.
- `PROTECT` / `UNPROTECT` — every `allocVector`/`allocMatrix` result is wrapped in `PROTECT` before `INTEGER` is applied. In the fake runtime `PROTECT` is a no-op identity, so the interleaving has no effect.
- `REAL(sexp)` — appears at the same call sites alongside `INTEGER`, accessing `double *` data from `REALSXP` SEXPs (e.g., `pred_rpart.c:140`: `REAL(split2)`, `REAL(xdata2)`).
- `asInteger(sexp)` — used at nearby lines to extract a single `int` scalar from a length-1 SEXP (e.g., `pred_rpart.c:138`, `pred_rpart.c:140`).
- `R_getVar(install("nback"), rho, FALSE)` — in `rpart_callback.c:68–69`, the SEXP passed to `INTEGER` is the return value of `R_getVar` (a Category E item). The `INTEGER` call itself is unconditional and identical to all other patterns; only the SEXP-producing call is special.
- `ALLOC` — used in `rpart.c` and `xpred.c` to allocate scratch arrays via the arena in the same function bodies, but does not interact with `INTEGER` directly.

**Distinct usage patterns.**

Three structural patterns appear across the 13 CSV rows:

| Pattern | CSV rows | Description |
|---|---|---|
| P1: Assign to a local or struct `int *` pointer from an input SEXP parameter | `rpart.c:75`, `rpart.c:76`, `rpart.c:112`, `xpred.c:69`, `xpred.c:70`, `xpred.c:110` | `INTEGER` is applied to a SEXP received as a `.Call` parameter; the result is stored into a local `int *` variable or a struct field for later use in the function body. |
| P2: Assign to a pointer from a freshly allocated SEXP, or pass directly as a function argument | `rpart.c:195`, `rpart.c:279`, `rpart.c:286`, `rpart.c:295`, `pred_rpart.c:140`, `rpartexp2.c:48` | `INTEGER` is applied to a SEXP that was just created by `allocVector(INTSXP, ...)` or `allocMatrix(INTSXP, ...)`, yielding the writable `int *` buffer. In `pred_rpart.c:140` and `rpartexp2.c:48` the result is passed directly as a function argument without an intermediate variable. |
| P3: Assign to a static module-level `int *` from a SEXP obtained via `R_getVar` | `rpart_callback.c:69` | `INTEGER` is applied to `stemp`, which holds the result of `R_getVar(install("nback"), rho, FALSE)`. The `int *` result is stored in the static global `ndata`. The `INTEGER` call itself is identical to P1 mechanically; the distinctiveness lies in how the source SEXP was produced. |

Patterns P1, P2, and P3 share the identical fake `INTEGER` implementation — all three resolve to `static_cast<int *>(s->data)`. The only guide-level distinction worth noting for P3 is that the SEXP was produced by a Category E item (`R_getVar`), so the code path through `rpart_callback.c:69` is only reachable at runtime once the `R_getVar` function-pointer bridge has been registered.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`INTEGER` is declared in `Rinternals.h` as a function with the unusual syntax `int *(INTEGER)(SEXP x)`. The parentheses around the name are a C technique that forces the compiler to treat the declaration as a function (not a macro call) even when a macro of the same name is in scope. In practice, `Rinternals.h` uses `USE_RINTERNALS`-gated `#define` aliases that expand `INTEGER(x)` to an inline access through the internal ALTREP layer in modern R. Since rpart does not define `USE_RINTERNALS`, none of those gated expansions are active; the function declared at line 286 of `Rinternals.h` is the one the compiler resolves.

**Chosen mechanism.**

The fake implements `INTEGER` as a C++ `inline` function with the signature:

```cpp
inline int *INTEGER(SEXP s) {
    return static_cast<int *>(s->data);
}
```

This is correct because the `SEXPREC` fake (from `SEXP.md`) stores the element buffer in `s->data` as a `void *`. When `allocVector(INTSXP, n)` or `allocMatrix(INTSXP, ...)` creates the SEXP, it heap-allocates `int[length]` and stores the pointer in `s->data`. `INTEGER` simply casts that pointer back to `int *`. The `static_cast` is safe because the source SEXP was always allocated with `sizeof(int)` per element (enforced by `sexptype_element_size(INTSXP)` in the allocator).

For input-parameter SEXPs constructed by the Python-side caller, the Python code must similarly place `int *`-compatible data in the `data` field of the constructed `SEXPREC` node before invoking the `.Call` wrapper.

**`#define` aliases that must be preserved.**

The real `Rinternals.h` does not define a macro alias `#define INTEGER(x) ...` in the non-`USE_RINTERNALS` build path (the parenthesised function declaration `int *(INTEGER)(SEXP x)` prevents the compiler from treating it as a macro). Therefore no `#define` is required in the fake header for `INTEGER` itself. However, the companion read-only accessor `INTEGER_RO` (declared at line 291 of `Rinternals.h` as `const int *(INTEGER_RO)(SEXP x)`) is not used by rpart but must not be omitted from the fake header if any downstream include transitively requires it. A conservative implementation can provide it as:

```cpp
inline const int *INTEGER_RO(SEXP s) {
    return static_cast<const int *>(s->data);
}
```

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `INTEGER` itself. The function performs a cast and cannot fail. The functions that produce the SEXP argument (`allocVector`, `allocMatrix`, `R_getVar`) may throw `RError`, but `INTEGER` is called after they return successfully.
- Invariant 2 (arena memory): not triggered by `INTEGER`. The function reads `s->data`, which points to heap memory (for SEXPs from `allocVector`/`allocMatrix`) or to Python-managed memory (for input-parameter SEXPs). The arena governs `R_alloc`/`ALLOC` scratch allocations that appear in the same function bodies but are independent of `INTEGER`.
- Invariant 3 (R Interpreter Items): not applicable. `INTEGER` itself does not invoke the interpreter. The single occurrence at `rpart_callback.c:69` where the source SEXP came from `R_getVar` does not affect the `INTEGER` implementation — `INTEGER` merely receives a valid SEXP pointer and extracts its data field.

---

### 4. Fake Implementation Examples

#### Pattern P1: Assign to a Local or Struct `int *` Pointer from an Input SEXP Parameter

- **Locations:** `rpart.c:75`, `rpart.c:76`, `rpart.c:112`, `xpred.c:69`, `xpred.c:70`, `xpred.c:110`

- **Original R API Usage:**

```c
/* rpart.c:75-76 — input parameters, assigned to local int * variables */
ncat = INTEGER(ncat2);
xgrp = INTEGER(xgrp2);

/* rpart.c:112 — assigned to a struct field */
rp.numcat = INTEGER(ncat2);

/* xpred.c:69-70, xpred.c:110 — same pattern in the xpred entry point */
ncat = INTEGER(ncat2);
xgrp = INTEGER(xgrp2);
/* ... */
rp.numcat = INTEGER(ncat2);
```

These appear inside the `rpart()` and `xpred()` `.Call` entry points, where `ncat2` and `xgrp2` are `SEXP` parameters passed in from R (or from Python via ctypes). The local variables `ncat` and `xgrp` are declared as `int *` at the top of the function body; `rp.numcat` is a field of type `int *` in the global `rp` struct.

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — INTEGER accessor, Category B)
// Must appear after the SEXPREC struct and SEXP typedef from SEXP.md.

#pragma once
#ifndef FAKE_RINTERNALS_H
#define FAKE_RINTERNALS_H

// ... (SEXPREC, SEXP, SEXPTYPE block, allocVector, PROTECT/UNPROTECT,
//      RError, and ArenaFrame from SEXP.md / fake_arena.hpp) ...

// -------------------------------------------------------------------------
// INTEGER — returns the int * data pointer of an INTSXP SEXP.
//
// Corresponds to the Rinternals.h declaration:
//   int *(INTEGER)(SEXP x);
//
// The fake casts s->data (void *) to int *.
// This is safe because allocVector(INTSXP, n) allocates int[n] into s->data,
// and Python-side SEXP construction for input parameters must do the same.
// -------------------------------------------------------------------------
inline int *INTEGER(SEXP s) {
    return static_cast<int *>(s->data);
}

// Read-only variant (not used by rpart source, but present in Rinternals.h).
inline const int *INTEGER_RO(SEXP s) {
    return static_cast<const int *>(s->data);
}

#endif // FAKE_RINTERNALS_H
```

The `.Call` entry-point boundary for `rpart()` illustrates that `INTEGER` itself needs no special guard — the `ArenaFrame` is required because `rpart()` also calls `ALLOC`/`R_alloc`, not because of `INTEGER`:

```cpp
// Entry-point wrapper for rpart (illustrative; INTEGER is called inside).
extern "C" SEXP rpart_entry(
        SEXP ncat2, SEXP method2, SEXP opt2,
        SEXP parms2, SEXP xvals2, SEXP xgrp2,
        SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2) {
    ArenaFrame _frame;   // frees R_alloc / ALLOC scratch on exit (Invariant 2)
    try {
        return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                     ymat2, xmat2, wt2, ny2, cost2);
    } catch (const RError &e) {
        set_python_error(e.what());   // store for Python to read
        return nullptr;
    }
}
```

Inside `rpart()` the original lines compile unchanged:

```c
// rpart.c:75-76 — unchanged original source
ncat = INTEGER(ncat2);   // expands to: ncat = static_cast<int *>(ncat2->data);
xgrp = INTEGER(xgrp2);
```

- **Explanation:**

  `INTEGER(ncat2)` resolves to `static_cast<int *>(ncat2->data)`. The `ncat2` SEXP was constructed by the Python-side caller before the `.Call` boundary: Python allocates a `SEXPREC` node with `type=INTSXP`, `length=n`, and `data` pointing to a contiguous `int[n]` buffer (e.g., a `ctypes` array or a numpy int32 array cast to a pointer). After the call, `ncat` is a bare `int *` pointing into that buffer; no SEXP bookkeeping remains.

  The original source file is not modified. The inline function `INTEGER` is resolved at compile time; the parenthesised declaration in the real header (`int *(INTEGER)(SEXP x)`) is replaced by the inline definition in the fake, which the compiler prefers.

  `rp.numcat = INTEGER(ncat2)` on line 112 of `rpart.c` (and line 110 of `xpred.c`) stores the pointer into a struct field. Because `rp` is a module-level global struct, the pointer remains valid for the life of the function invocation.

---

#### Pattern P2: Assign to a Pointer from a Freshly Allocated SEXP, or Pass Directly as a Function Argument

- **Locations:** `rpart.c:195`, `rpart.c:279`, `rpart.c:286`, `rpart.c:295`, `pred_rpart.c:140`, `rpartexp2.c:48`

- **Original R API Usage:**

```c
/* rpart.c:194-195 — allocate then immediately get the int * */
which3 = PROTECT(allocVector(INTSXP, n));
rp.which = INTEGER(which3);

/* rpart.c:278-283 — matrix allocation; stride over columns */
inode3 = PROTECT(allocMatrix(INTSXP, nodecount, 6));
iptr = INTEGER(inode3);
for (i = 0; i < 6; i++) {
    iinode[i] = iptr;
    iptr += nodecount;    /* advance one column (column-major layout) */
}

/* rpart.c:285-290 — same column-stride pattern */
isplit3 = PROTECT(allocMatrix(INTSXP, splitcount, 3));
iptr = INTEGER(isplit3);
for (i = 0; i < 3; i++) {
    iisplit[i] = iptr;
    iptr += splitcount;
}

/* rpart.c:293-301 — conditional matrix; same column-stride pattern */
if (catcount > 0) {
    csplit3 = PROTECT(allocMatrix(INTSXP, catcount, maxcat));
    iptr = INTEGER(csplit3);
    for (i = 0; i < maxcat; i++) {
        ccsplit[i] = iptr;
        iptr += catcount;
        for (j = 0; j < catcount; j++)
            ccsplit[i][j] = 0;
    }
}

/* pred_rpart.c:139-144 — INTEGER result passed directly as argument */
SEXP where = PROTECT(allocVector(INTSXP, n));
pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit),
            INTEGER(dimc), INTEGER(nnum), INTEGER(nodes2),
            INTEGER(vnum), REAL(split2), INTEGER(csplit2),
            INTEGER(usesur), REAL(xdata2), INTEGER(xmiss2),
            INTEGER(where));
UNPROTECT(1);
return where;

/* rpartexp2.c:47-48 — INTEGER result passed directly as argument */
SEXP keep = PROTECT(allocVector(INTSXP, n));
Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
UNPROTECT(1);
return keep;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (INTEGER — same definition as in Pattern P1)
// The implementation does not change; the pattern here is about usage context.

inline int *INTEGER(SEXP s) {
    return static_cast<int *>(s->data);
}

// For completeness, the allocVector / allocMatrix fakes that produce the
// SEXPs consumed by INTEGER in this pattern (from SEXP.md / INTSXP.md):

inline SEXP allocVector(SEXPTYPE type, int length) {
    SEXPREC *s = static_cast<SEXPREC *>(std::malloc(sizeof(SEXPREC)));
    if (!s) throw RError("allocVector: out of memory (SEXPREC)");
    s->type   = type;
    s->length = length;
    s->nrow   = length;
    s->ncol   = 1;
    std::size_t bytes = static_cast<std::size_t>(length)
                        * sexptype_element_size(type);
    if (bytes == 0) bytes = 1;
    s->data = std::malloc(bytes);
    if (!s->data) { std::free(s); throw RError("allocVector: out of memory (data)"); }
    std::memset(s->data, 0, bytes);
    return s;
}

inline SEXP allocMatrix(SEXPTYPE type, int nrow, int ncol) {
    SEXP s = allocVector(type, nrow * ncol);
    s->nrow = nrow;
    s->ncol = ncol;
    return s;
}
```

The `.Call` wrapper for `pred_rpart` shows the `ArenaFrame` guard (needed because `pred_rpart0` and its callees use `ALLOC`) and the `try/catch` boundary (Invariant 1):

```cpp
extern "C" SEXP pred_rpart_entry(
        SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
        SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
        SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2) {
    ArenaFrame _frame;   // arena scratch freed here (Invariant 2)
    try {
        return pred_rpart(dimx, nnode, nsplit, dimc, nnum, nodes2,
                          vnum, split2, csplit2, usesur, xdata2, xmiss2);
    } catch (const RError &e) {
        set_python_error(e.what());
        return nullptr;
    }
}
```

- **Arena / Memory Notes:**

  The SEXP nodes produced by `allocVector(INTSXP, n)` and `allocMatrix(INTSXP, ...)` are heap-allocated via `std::malloc` — they are **not** arena-managed. The `int` data buffers pointed to by `INTEGER(sexp)` are likewise heap-allocated as part of the SEXP. They must survive the `.Call` function frame because several of them — `which3` in `rpart.c`, `where` in `pred_rpart.c`, `keep` in `rpartexp2.c` — are the return values handed back to Python.

  The `ArenaFrame` in the `.Call` wrapper frees only memory allocated via `R_alloc`/`ALLOC`. In `pred_rpart.c` the internal function `pred_rpart0` and its callees allocate scratch via `ALLOC`; those arena blocks are freed at `ArenaFrame` destruction. The heap-allocated return SEXP (`where`) is unaffected.

  For `rpart.c:279–295`, the local `iptr` variable is a bare `int *` pointing into the data buffer of a heap-allocated matrix SEXP. After `INTEGER(inode3)` returns `iptr`, the code advances it by column strides (`iptr += nodecount`). This pointer arithmetic is valid because `allocMatrix(INTSXP, nodecount, 6)` allocated a flat `int[nodecount * 6]` buffer, and the column-major striding is the standard rpart pattern. No arena interaction occurs here.

  If `allocVector` or `allocMatrix` fails, `RError` is thrown before `INTEGER` is ever called. The `.Call` boundary wrapper catches the exception.

- **Explanation:**

  For `pred_rpart.c:140`, the seven `INTEGER(...)` calls appear as direct function arguments to `pred_rpart0`. The compiler evaluates each as `static_cast<int *>(sexp->data)` and passes the resulting `int *` to the corresponding parameter of `pred_rpart0`. No intermediate variable is required. This form compiles identically to storing the result in a named variable first.

  For `rpartexp2.c:48`, `INTEGER(keep)` passes the freshly allocated `int *` buffer to `Rpartexp2`, which populates it in-place. After `Rpartexp2` returns, `keep` (the SEXP) is returned from `rpartexp2()` to Python. Python then calls `INTEGER(keep)` (or equivalently reads `keep->data` directly as `int *`) to extract the result array.

  `PROTECT(allocVector(INTSXP, n))` expands to `Rf_protect(allocVector(INTSXP, n))`, which is the identity function in the fake. `UNPROTECT(1)` expands to `Rf_unprotect(1)`, a no-op. Neither changes any state. The original source files compile unchanged.

---

#### Pattern P3: Assign to a Static Module-Level `int *` from a SEXP Obtained via `R_getVar`

- **Locations:** `rpart_callback.c:69`

- **Original R API Usage:**

```c
/* rpart_callback.c:68-69 */
stemp = R_getVar(install("nback"), rho, FALSE);
ndata = INTEGER(stemp);
```

`stemp` is a local `SEXP` variable declared at `rpart_callback.c:51`. `R_getVar` retrieves the `SEXP` bound to the symbol `"nback"` in the evaluation environment `rho`. `ndata` is the static `int *` global declared at `rpart_callback.c:40`. The subsequent use of `ndata` in callback bodies provides per-observation node counts to the user-defined split function.

- **C++ Fake Implementation:**

```cpp
// rpart_callback.c compiles without modification using fake_Rinternals.hpp.
// The INTEGER call on line 69 is mechanically identical to Pattern P1:

inline int *INTEGER(SEXP s) {
    return static_cast<int *>(s->data);
}

// The only difference is that 'stemp' was produced by R_getVar (a Category E
// item), not by allocVector.  INTEGER itself has no awareness of this
// distinction — it simply casts s->data to int *.
//
// At runtime, this code path is reachable only when:
//   1. init_rpcallback() has been called (registering rho and the expressions).
//   2. The R_getVar function-pointer bridge has been registered via
//      register_R_getVar_fn() (see the R_getVar fake guide).
//   3. rpart() is subsequently called with method=4 (user-defined splits),
//      which causes the callback infrastructure to be invoked.
//
// If R_getVar returns a valid SEXP whose data holds int[n] (i.e., the Python
// callback returns a correctly constructed SEXPREC for the "nback" symbol),
// then INTEGER(stemp) = static_cast<int *>(stemp->data) is correct and safe.
//
// .Call boundary wrapper for init_rpcallback:
//
//   extern "C" SEXP init_rpcallback_entry(
//           SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x) {
//       ArenaFrame _frame;
//       try {
//           return init_rpcallback(rhox, ny, nr, expr1x, expr2x);
//       } catch (const RError &e) {
//           set_python_error(e.what());
//           return nullptr;
//       }
//   }
//
// The RError thrown by the R_getVar stub (when the pointer is not registered)
// propagates through init_rpcallback to the wrapper, which catches it and
// stores the error message for Python.
```

- **Explanation:**

  The `INTEGER` fake is unchanged from Patterns P1 and P2. The source SEXP `stemp` is produced by `R_getVar`, which in the fake runtime is implemented as a function-pointer stub (Category E, documented in the `R_getVar`/`findVar` fake guide). When that stub is registered, it returns a SEXP constructed by Python whose `data` field contains an `int *`-compatible buffer for the `"nback"` integer vector. `INTEGER(stemp)` then casts that `data` pointer to `int *` and stores it in `ndata`. The original source line 69 compiles and runs correctly with no modification.

  This code path is only reached during user-defined splitting (method=4). All standard rpart methods (anova, poisson, class, exp) never invoke `init_rpcallback` and never reach line 69. Therefore the `R_getVar` bridge not being registered does not block standard usage.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` — `fake_Rinternals.hpp` | The `SEXPREC` struct with a `void *data` field. `INTEGER` casts `s->data` to `int *`; the struct definition must precede the `INTEGER` inline function in the header. `SEXP.md` is the authoritative source for the complete `fake_Rinternals.hpp` in which `INTEGER` resides. |
| `INTSXP.md` | Establishes `#define INTSXP 13` in the `SEXPTYPE` block. This tag is set by `allocVector(INTSXP, n)` when constructing the SEXPs whose data `INTEGER` later reads. Although `INTEGER` itself does not reference `INTSXP` numerically, correct program behaviour requires that the SEXPs passed to `INTEGER` were allocated with `INTSXP` so that their `data` buffers hold `int` elements. |
| `fake_arena.hpp` (no separate guide; generated as a foundation) | The `ArenaFrame` RAII struct, `gArenaStack` thread-local vector, `arena_alloc`, and `arena_calloc`. Required at the `.Call` wrapper layer for functions (`rpart`, `xpred`, `pred_rpart`, `rpartexp2`, `init_rpcallback`) that call both `INTEGER` and `R_alloc`/`ALLOC` in the same body. `INTEGER` itself does not use the arena; the dependency is at the enclosing function level. |
| `allocVector.md` / `SEXP.md` | The `allocVector` and `allocMatrix` fakes, which are what creates the SEXPs passed to `INTEGER` in Pattern P2. Both are defined in `fake_Rinternals.hpp` (see `SEXP.md` Pattern P2 and `INTSXP.md`). |
| `error.md` — `RError` definition | `struct RError : public std::runtime_error`. Used by `allocVector`/`allocMatrix` to signal allocation failure. `INTEGER` itself does not throw, but `RError` must be defined before `allocVector` in the header, and `allocVector` calls precede `INTEGER` calls in the source. |
| `R_getVar` / `findVar` fake guide (Category E, not yet generated) | Required at runtime for `rpart_callback.c:68–69` (Pattern P3). `INTEGER` compiles without it; the runtime path through `ndata = INTEGER(stemp)` is only reachable after the `R_getVar` function-pointer bridge is registered. |
