# Fake Header Implementation Guide: `nrows`

---

### 1. Overview of `nrows` in R API

`nrows` is a C API accessor declared in `Rinternals.h` as `int Rf_nrows(SEXP);` and exposed to package source via the macro alias `#define nrows Rf_nrows`. It returns the number of rows of an R matrix or array object (a `SEXP` with a `dim` attribute). For a one-dimensional vector the real R implementation returns the element count itself; for a two-dimensional matrix it returns the first element of the `dim` attribute (`nrow`). The input is a `SEXP` (`SEXPREC *`) and the return value is a plain C `int`. In the fake runtime, `nrows` is implemented as a C++ `inline` function that reads the `nrow` field directly from the `SEXPREC` struct defined in `SEXP.md`, making it a zero-cost accessor with no heap allocation and no arena interaction. It is the direct row-axis counterpart of `ncols` (documented in `ncols.md`).

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `rpart.c` | 108 | `rp.n = nrows(xmat2);` |
| `xpred.c` | 106 | `rp.n = nrows(xmat2);` |

**Surrounding context (15 lines each side).**

In both `rpart.c` and `xpred.c` the call to `nrows(xmat2)` appears in the parameter-initialization block that executes immediately after extracting scalar options from the `opt2` SEXP. In both files the call is immediately followed (one line below) by a call to `ncols(xmat2)`. The two calls together extract the complete shape of the predictor matrix `xmat2`:

```c
/* rpart.c:107-115 */
rp.maxnode = (int) pow((double) 2.0, (double) dptr[7]) - 1;
rp.n    = nrows(xmat2);          // total number of observations
n       = rp.n;                  // convenience alias: "I get tired of typing rp.n"
rp.nvar = ncols(xmat2);          // number of predictor variables
rp.numcat = INTEGER(ncat2);
rp.wt     = wt;
rp.iscale = 0.0;
rp.vcost  = REAL(cost2);

/* xpred.c:105-113 (structurally identical) */
rp.maxnode = (int) pow((double) 2.0, (double) dptr[7]) - 1;
rp.n    = nrows(xmat2);
n       = rp.n;
rp.nvar = ncols(xmat2);
rp.numcat = INTEGER(ncat2);
rp.wt     = wt;
rp.iscale = 0.0;
rp.vcost  = REAL(cost2);
```

`xmat2` is the eighth `SEXP` parameter to both `rpart()` and `xpred()`. It is a two-dimensional column-major matrix of doubles (`REALSXP`): `nrows(xmat2)` yields the number of observations and is stored in `rp.n` (type `int`, field of `struct rpart_struct rp` in `rpart.h:58`). The value `n = rp.n` is subsequently used as the observation-loop bound throughout both functions (e.g., for sorting and ragged-array pointer setup at `rpart.c:122–133`).

**C types of arguments and return values.**

| Item | Type | Notes |
|---|---|---|
| Argument `xmat2` | `SEXP` (`SEXPREC *`) | A 2-D `REALSXP` matrix, column-major layout, `nrow` = number of observations |
| Return value | `int` | Number of rows; assigned to `rp.n` (field `int n` in `struct rpart_struct`) and to local `int n` |

**Co-occurring R API items.**

- `ncols(xmat2)` — called one line below on the same `SEXP`; returns `int`. The two calls are always paired and use the same argument. Both are macro aliases: `nrows` expands to `Rf_nrows`, `ncols` expands to `Rf_ncols`.
- `REAL(opt2)` — called a few lines above to extract the `dptr` double-array from the option SEXP, from which `rp.maxnode` is computed just before `nrows`.
- `INTEGER(ncat2)` — called one line after `ncols(xmat2)` on a different `SEXP`.
- `REAL(xmat2)` — called at `rpart.c:122` / `xpred.c:121` on the same `xmat2` SEXP to obtain the `double *` data pointer for column-pointer setup. The value returned by `nrows(xmat2)` is used as the column stride in that setup (`dptr += n`).
- `ALLOC(rp.nvar, sizeof(double *))` — called at `rpart.c:123` / `xpred.c:122`, using `rp.nvar` (the `ncols` result) as the count. This is an arena allocation and is independent of `nrows`.

**Distinct implementation patterns.**

There is exactly one implementation pattern across both CSV rows: extract the row count of a 2-D matrix `SEXP` and return it as `int`. Both call sites (`rpart.c:108` and `xpred.c:106`) are structurally identical — same argument type (`SEXP`), same return type assignment (`int rp.n`), and the same surrounding context. A single fake definition covers both.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`nrows` is classified as Category B because it is a pure read accessor that extracts a scalar integer from a `SEXP` struct field, performs no allocation, no error-raising, and does not require a running R interpreter.

**Chosen mechanism.**

The real `Rinternals.h` declares `int Rf_nrows(SEXP)` as a non-inline function implemented inside R's shared library (`libR.so`). The real implementation reads the first element of the `dim` attribute SEXP attached to the object. In the fake runtime, no attribute list exists on `SEXPREC` nodes. Instead, `allocMatrix` (documented in `allocMatrix.md`) explicitly sets the `nrow` field of the `SEXPREC` struct when it creates the matrix:

```cpp
inline SEXP Rf_allocMatrix(SEXPTYPE type, int nrow, int ncol) {
    SEXP s = allocVector(type, nrow * ncol);
    s->nrow = nrow;   // <- set here
    s->ncol = ncol;
    return s;
}
```

For 1-D vectors, `allocVector` sets `s->nrow = length` and `s->ncol = 1`. The `nrows` fake therefore reads `s->nrow` directly — a one-field read that is semantically equivalent to extracting the first element of the `dim` attribute.

The fake `Rf_nrows` is an `inline` function (not a macro) to match the observable C signature (`int Rf_nrows(SEXP)`), preserve type safety, and allow the compiler to inline the single-field read at every call site. The `#define nrows Rf_nrows` alias from the original `Rinternals.h` is preserved verbatim so that `rpart.c` and `xpred.c` compile without modification — they use the bare name `nrows`, not `Rf_nrows`.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered. `nrows` performs no error or warning calls. If a null pointer were passed, a segfault would occur, but the original R implementation makes the same assumption (a valid non-null SEXP). No defensive null-check is added.
- Invariant 2 (arena memory): not triggered. `nrows` performs no allocation whatsoever.
- Invariant 3 (R Interpreter Items): not triggered. `nrows` does not require interpreter state.

**`#define` aliases that must be preserved.**

The original `Rinternals.h` at line 1030 defines:

```c
#define nrows   Rf_nrows
```

This alias must be reproduced in `fake_Rinternals.hpp` so that the unqualified name `nrows(xmat2)` used in `rpart.c:108` and `xpred.c:106` resolves to the fake `Rf_nrows` function without any change to the original source files.

The `ncols` alias (`#define ncols Rf_ncols`) is the direct counterpart and must be defined in the same header (documented in `ncols.md`). Both aliases appear together in the "Length and shape accessors" section of `fake_Rinternals.hpp`.

---

### 4. Fake Implementation Examples

#### Pattern: Extract Row Count from a 2-D Matrix SEXP

- **Locations:** `rpart.c:108`, `xpred.c:106`

- **Original R API Usage:**

```c
/* rpart.c:107-111 */
rp.maxnode = (int) pow((double) 2.0, (double) dptr[7]) - 1;
rp.n    = nrows(xmat2);     /* xmat2 is a REALSXP matrix: nrow=n_obs, ncol=n_vars */
n       = rp.n;             /* I get tired of typing "rp.n" 100 times below */
rp.nvar = ncols(xmat2);

/* xpred.c:105-109 (structurally identical) */
rp.maxnode = (int) pow((double) 2.0, (double) dptr[7]) - 1;
rp.n    = nrows(xmat2);
n       = rp.n;
rp.nvar = ncols(xmat2);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// This definition belongs in the "Length and shape accessors" section
// of fake_Rinternals.hpp, alongside the Rf_ncols definition.
// It must appear after the SEXPREC struct definition and the SEXP typedef.

// -----------------------------------------------------------------------
// Rf_nrows — returns the row count stored in sexp->nrow.
//
// For matrices created by allocMatrix(type, nrow, ncol), s->nrow is set
// to `nrow` at allocation time (inside Rf_allocMatrix, after the call to
// allocVector).
// For 1-D vectors created by allocVector(type, n), s->nrow is set to n
// and s->ncol is set to 1 by the allocVector implementation.
//
// The real Rf_nrows reads the first element of the dim attribute SEXP.
// The fake reads s->nrow directly — semantically equivalent because
// allocMatrix is the only allocation path for matrix SEXPs in rpart,
// and allocVector correctly sets s->nrow = length for 1-D objects.
// -----------------------------------------------------------------------
inline int Rf_nrows(SEXP s) { return s->nrow; }
#define nrows Rf_nrows

// Rf_ncols companion (shown here for completeness; defined in the same block):
inline int Rf_ncols(SEXP s) { return s->ncol; }
#define ncols Rf_ncols
```

- **Explanation:**

  `rpart.c:108` expands `nrows(xmat2)` to `Rf_nrows(xmat2)` via the `#define nrows Rf_nrows` alias. The fake `Rf_nrows` reads `xmat2->nrow`, which was set to the number of observations when `xmat2` was constructed by the Python-side caller. In the fake runtime, `xmat2` is a `SEXPREC` node whose `nrow` field was set either by `allocMatrix(REALSXP, n_obs, n_vars)` (inside the Python wrapper that builds the input SEXP from a NumPy array) or by directly assigning `s->nrow` on a manually constructed `SEXPREC`. The result is a plain `int` assigned to `rp.n` and then copied to local `int n`. No memory, no exception path, and no interpreter interaction are involved.

  The identical call at `xpred.c:106` is handled by the same fake definition: the macro `nrows` is active for all translation units that include `fake_Rinternals.hpp` through `rpart.h`.

  The original source files `rpart.c` and `xpred.c` compile unchanged because:
  1. They `#include "rpart.h"` which transitively includes `Rinternals.h`; in the fake build `Rinternals.h` is replaced by `fake_Rinternals.hpp`.
  2. The `#define nrows Rf_nrows` alias in `fake_Rinternals.hpp` makes the unqualified call `nrows(xmat2)` resolve to `Rf_nrows(xmat2)`.
  3. `Rf_nrows` is an `inline int` function accepting `SEXP` and returning `int`, matching the observable signature that the original code expects.

  The `SEXP.md` guide already embeds this definition within the "Length and shape accessors" block of `fake_Rinternals.hpp` (see lines 453–455 of `SEXP.md`, Section 4, Pattern P2):

  ```cpp
  inline int Rf_nrows(SEXP s)    { return s->nrow; }
  inline int Rf_ncols(SEXP s)    { return s->ncol; }
  #define nrows(x) Rf_nrows(x)
  #define ncols(x) Rf_ncols(x)
  ```

  This guide provides the standalone documentation for `nrows` specifically and confirms that the implementation in `fake_Rinternals.hpp` is authoritative. Note: the alias form may be written as either `#define nrows Rf_nrows` (object-like macro) or `#define nrows(x) Rf_nrows(x)` (function-like macro). Both forms are equivalent for all call sites in rpart since `nrows` is always called with a single argument. The object-like form (`#define nrows Rf_nrows`) more closely mirrors the real `Rinternals.h` line 1030 and is preferred.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct definition with the `nrow` field (`int nrow`). `Rf_nrows` reads `s->nrow`; without `SEXPREC` defined, this field access does not compile. `SEXP.md` is the authoritative source for `fake_Rinternals.hpp` and must be included before this definition. |
| `allocMatrix.md` | Establishes that `Rf_allocMatrix(type, nrow, ncol)` sets `s->nrow = nrow` on the returned `SEXPREC`. This is the contract that makes `Rf_nrows(s)` return the correct number of observations for any matrix `SEXP` constructed by the fake runtime. Without `allocMatrix` setting `nrow`, `Rf_nrows` would return the full element count (`nrow * ncol`) rather than just the row count, because `allocVector` initialises `s->nrow = length` before `allocMatrix` overwrites it. |
| `ncols.md` | `ncols` and `nrows` are always defined together in the same "Length and shape accessors" block of `fake_Rinternals.hpp`. Both are called on the same `xmat2` SEXP in the same initialization block in both `rpart.c` and `xpred.c`. The `ncols.md` guide documents the companion `Rf_ncols` / `#define ncols Rf_ncols` definition and must be consistent with this guide. |
