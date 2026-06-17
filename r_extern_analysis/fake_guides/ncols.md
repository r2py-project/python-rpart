# Fake Header Implementation Guide: `ncols`

---

### 1. Overview of `ncols` in R API

`ncols` is a C API accessor declared in `Rinternals.h` as `int Rf_ncols(SEXP);` and exposed to package source via the macro alias `#define ncols Rf_ncols`. It returns the number of columns of an R matrix or array object (a `SEXP` with a `dim` attribute). For a one-dimensional vector the real R implementation returns `1`; for a two-dimensional matrix it returns the second element of the `dim` attribute (`ncol`). The input is a `SEXP` (`SEXPREC *`) and the return value is a plain C `int`. In the fake runtime, `ncols` is implemented as a C++ `inline` function that reads the `ncol` field directly from the `SEXPREC` struct defined in `SEXP.md`, making it a zero-cost accessor with no heap allocation and no arena interaction.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `rpart.c` | 111 | `rp.nvar = ncols(xmat2);` |
| `xpred.c` | 109 | `rp.nvar = ncols(xmat2);` |

**Surrounding context (15 lines each side).**

In both `rpart.c` and `xpred.c` the call to `ncols(xmat2)` appears immediately after a call to `nrows(xmat2)` (one line above at `rpart.c:108` and `xpred.c:106`). The two calls together extract the shape of the predictor matrix `xmat2`:

```c
/* rpart.c:108-115 */
rp.n    = nrows(xmat2);       // total number of observations
n       = rp.n;               // convenience alias
rp.nvar = ncols(xmat2);       // number of predictor variables
rp.numcat = INTEGER(ncat2);
rp.wt     = wt;
rp.iscale = 0.0;
rp.vcost  = REAL(cost2);
```

`xmat2` is a `SEXP` parameter of type `REALSXP` received as the eighth argument of `rpart()` and the eighth argument of `xpred()`. It is a two-dimensional column-major matrix of doubles: `nrows(xmat2)` is the number of observations, and `ncols(xmat2)` is the number of predictor variables. The result is stored in the `int` field `rp.nvar` of the global `struct rpart_struct rp` (defined in `rpart.h`). `rp.nvar` is subsequently used throughout both functions to iterate over predictor columns (e.g., `for (i = 0; i < rp.nvar; i++) { rp.xdata[i] = dptr; dptr += n; }`).

**C types of arguments and return values.**

| Item | Type | Notes |
|---|---|---|
| Argument `xmat2` | `SEXP` (`SEXPREC *`) | A 2-D `REALSXP` matrix, column-major layout |
| Return value | `int` | Number of columns; assigned to `rp.nvar` (type `int`) |

**Co-occurring R API items.**

- `nrows(xmat2)` — called one line above on the same `SEXP`; returns `int`. The two calls are always paired. Both are accessor macros aliasing `Rf_nrows` and `Rf_ncols`.
- `REAL(xmat2)` — called shortly after (`rpart.c:122`, `xpred.c:121`) to obtain a `double *` into the data buffer for column-pointer setup.
- `INTEGER(ncat2)` — called on a separate `SEXP` parameter in the same initialization block.
- `ALLOC(rp.nvar, sizeof(double *))` — called at `rpart.c:123` and `xpred.c:122` using `rp.nvar` (the value returned by `ncols`) as the element count. This is an arena allocation.

**Distinct implementation patterns.**

There is exactly one implementation pattern across both CSV rows: extract the column count of a 2-D matrix `SEXP` and return it as `int`. Both call sites (`rpart.c:111` and `xpred.c:109`) are structurally identical — same argument type, same return type assignment, same surrounding context. A single fake definition covers both.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`ncols` is classified as Category B because it is a pure read accessor that extracts a scalar integer from a `SEXP` struct field, performs no allocation, no error-raising, and does not require a running R interpreter.

**Chosen mechanism.**

The real `Rinternals.h` declares `int Rf_ncols(SEXP)` as a non-inline function implemented in R's shared library (`libR.so`). The real implementation reads the second element of the `dim` attribute SEXP attached to the object. In the fake runtime, no attribute list exists on `SEXPREC` nodes. Instead, `allocMatrix` (documented in `allocMatrix.md`) explicitly sets the `ncol` field of the `SEXPREC` struct when it creates the matrix. The `ncols` fake therefore reads `s->ncol` directly — a one-field read that is semantically equivalent to extracting the second element of the `dim` attribute.

The fake `Rf_ncols` is an `inline` function (not a macro) to match the observable C signature (`int Rf_ncols(SEXP)`), preserve type safety, and allow the compiler to inline the single-field read at every call site. The `#define ncols Rf_ncols` alias from the original `Rinternals.h` is preserved verbatim so that `rpart.c` and `xpred.c` compile without modification — they use the bare name `ncols`, not `Rf_ncols`.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered. `ncols` performs no error or warning calls. If a null pointer were passed, a segfault would occur, but the original R implementation makes the same assumption (a valid non-null SEXP). No defensive null-check is added.
- Invariant 2 (arena memory): not triggered. `ncols` performs no allocation whatsoever.
- Invariant 3 (R Interpreter Items): not triggered. `ncols` does not require interpreter state.

**`#define` aliases that must be preserved.**

The original `Rinternals.h` at line 1027 defines:

```c
#define ncols   Rf_ncols
```

This alias must be reproduced in `fake_Rinternals.hpp` so that the unqualified name `ncols(xmat2)` used in `rpart.c:111` and `xpred.c:109` resolves to the fake `Rf_ncols` function without any change to the original source files.

The `nrows` alias (`#define nrows Rf_nrows`) is the direct counterpart and must be defined in the same header (see `nrows.md` if generated; if not, the definition is embedded in `fake_Rinternals.hpp` from `SEXP.md` which already shows `#define nrows(x) Rf_nrows(x)`).

---

### 4. Fake Implementation Examples

#### Pattern: Extract Column Count from a 2-D Matrix SEXP

- **Locations:** `rpart.c:111`, `xpred.c:109`

- **Original R API Usage:**

```c
/* rpart.c:108-111 */
rp.n    = nrows(xmat2);
n       = rp.n;
rp.nvar = ncols(xmat2);   /* xmat2 is a REALSXP matrix: nrow=n_obs, ncol=n_vars */

/* xpred.c:106-109 (structurally identical) */
rp.n    = nrows(xmat2);
n       = rp.n;
rp.nvar = ncols(xmat2);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp
// This definition belongs in the "Length and shape accessors" section
// of fake_Rinternals.hpp, immediately after the Rf_nrows definition.
// It must appear after the SEXPREC struct definition and the SEXP typedef.

// -----------------------------------------------------------------------
// Rf_ncols — returns the column count stored in sexp->ncol.
//
// For matrices created by allocMatrix(type, nrow, ncol), s->ncol is set
// to `ncol` at allocation time.
// For 1-D vectors created by allocVector(type, n), s->ncol is set to 1
// by the allocVector implementation (s->nrow = n, s->ncol = 1).
//
// The real Rf_ncols reads the second element of the dim attribute SEXP.
// The fake reads s->ncol directly — semantically equivalent because
// allocMatrix is the only allocation path for matrix SEXPs in rpart.
// -----------------------------------------------------------------------
inline int Rf_ncols(SEXP s) { return s->ncol; }
#define ncols Rf_ncols

// Rf_nrows companion (shown here for completeness; defined in the same block):
inline int Rf_nrows(SEXP s) { return s->nrow; }
#define nrows Rf_nrows
```

- **Explanation:**

  `rpart.c:111` expands `ncols(xmat2)` to `Rf_ncols(xmat2)` via the `#define ncols Rf_ncols` alias. The fake `Rf_ncols` reads `xmat2->ncol`, which was set to the number of predictor variables when `xmat2` was constructed by the Python-side caller (via `allocMatrix` or directly by setting the `ncol` field on the `SEXPREC` node passed in). The result is a plain `int` assigned to `rp.nvar`. No memory, no exception path, and no interpreter interaction are involved.

  The original source files `rpart.c` and `xpred.c` compile unchanged because:
  1. They `#include "rpart.h"` which transitively includes `Rinternals.h`; in the fake build `Rinternals.h` is replaced by `fake_Rinternals.hpp`.
  2. The `#define ncols Rf_ncols` alias in `fake_Rinternals.hpp` makes the unqualified call `ncols(xmat2)` resolve to `Rf_ncols(xmat2)`.
  3. `Rf_ncols` is an `inline int` function accepting `SEXP` and returning `int`, matching the signature that the original code expects.

  The `SEXP.md` guide already embeds this definition within the "Length and shape accessors" block of `fake_Rinternals.hpp` (see the `#define nrows(x) Rf_nrows(x)` / `#define ncols(x) Rf_ncols(x)` lines in Section 4, Pattern P2 of `SEXP.md`). This guide provides the standalone documentation for `ncols` specifically and confirms that the implementation in `fake_Rinternals.hpp` is authoritative.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` | Provides the `SEXPREC` struct definition with the `ncol` field (`int ncol`). `Rf_ncols` reads `s->ncol`; without `SEXPREC` defined, this field access does not compile. `SEXP.md` is the authoritative source for `fake_Rinternals.hpp` and must be included before this definition. |
| `allocMatrix.md` | Establishes that `allocMatrix(type, nrow, ncol)` sets `s->ncol = ncol` on the returned `SEXPREC`. This is the contract that makes `Rf_ncols(s)` return the correct value for any matrix `SEXP` constructed by the fake runtime. Without `allocMatrix` setting `ncol`, `Rf_ncols` would return zero (the zero-initialized default). |
