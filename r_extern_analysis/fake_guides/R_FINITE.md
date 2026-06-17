# Fake Header Implementation Guide: `R_FINITE`

---

### 1. Overview of `R_FINITE` in R API

`R_FINITE` is a preprocessor macro defined in `R_ext/Arith.h` (included transitively by `R.h`) that tests whether a `double` value is a finite real number — that is, neither NaN, R's `NA_REAL` (a specific quiet NaN), nor positive or negative infinity. In the standard Linux/glibc build where `HAVE_WORKING_ISFINITE` is set, the macro expands to the C99 function-like macro `isfinite(x)` from `<math.h>`. When that compile-time flag is absent, it falls back to calling the `libR.so` function `R_finite(double x)`. In rpart, `R_FINITE` is used as a predicate to detect missing predictor values before split direction decisions and before sort-index construction: a non-finite value is treated as missing. The only input type is `double`; the return value is a non-zero `int` for finite values and zero for non-finite values. `R_FINITE` is not an R Interpreter Item; it requires no running interpreter and no function-pointer bridge.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `branch.c` | 39 | `if (R_FINITE(xdata[j][obs]))` — primary split direction test |
| `branch.c` | 59 | `if (R_FINITE(xdata[j][obs]))` — surrogate split direction test |
| `nodesplit.c` | 107 | `if (!R_FINITE(xdata[var][j])) continue;` — skip missing surrogate observation |
| `rpart.c` | 154 | `if (!R_FINITE(rp.xdata[i][k]))` — detect missing predictor in sort-index build |
| `xpred.c` | 153 | `if (!R_FINITE(rp.xdata[i][k]))` — detect missing predictor in cross-prediction sort-index build |

**Surrounding context — branch.c:39.**

The variable `xdata` is a `double **` field from the `rp` global struct, accessed as `xdata[j][obs]` where `j` is the predictor variable index (from `tsplit->var_num`) and `obs` is the observation index (an `int` parameter to the enclosing function). `R_FINITE` is the first test performed on the data value; a finite result causes the code to proceed directly to the split comparison (`xdata[j][obs] < tsplit->spoint`). A non-finite result falls through to surrogate handling.

**Surrounding context — nodesplit.c:107.**

Inside a loop over surrogate splits, `xdata[var][j]` is tested before the surrogate split value is used. The `continue` on a non-finite result means only finite predictor values are considered for surrogate splitting. No SEXP, `PROTECT`, or allocation calls appear adjacent to this use.

**Surrounding context — rpart.c:154 and xpred.c:153.**

Both files iterate over all observations for each predictor variable to build sort index arrays. When `!R_FINITE(rp.xdata[i][k])`, the observation is encoded as missing by writing `-(k + 1)` into `rp.tempvec[k]` and setting `rp.xtemp[k] = 0`. When it is finite, `rp.tempvec[k] = k` and `rp.xtemp[k] = rp.xdata[i][k]`. The adjacent memory operations use `ALLOC`-managed (`arena_alloc`) scratch arrays (`rp.xtemp`, `rp.tempvec`, `rp.sorts`), not `SEXP` or heap allocations.

**C types observed.**

| Role | Type |
|---|---|
| Argument to `R_FINITE` | `double` (element of a `double **` predictor matrix) |
| Return value | `int` — non-zero (1 = finite) or zero (0 = non-finite: NaN, NA, +/-Inf) |

**Co-occurring R API items.**

- `ALLOC(n, size)` — a macro in `rpart.h` that expands to `R_alloc(n, size)`. Appears in the surrounding code of `rpart.c:154` and `xpred.c:153`. The arena allocator governs this memory; `R_FINITE` itself performs no allocation.
- `ISNAN(x)` — the companion predicate from the same `R_ext/Arith.h` header. `ISNAN` returns true for both R's `NA_REAL` and plain IEEE NaN; `R_FINITE` returns false for those and also for `+/-Inf`. Both must be defined in the same fake header (`fake_Arith.hpp`). The `ISNAN` fake guide (`ISNAN.md`) is already established and defines `R_FINITE` as part of `fake_Arith.hpp`; this guide is the authoritative specification for that definition.
- No `SEXP`, `PROTECT`, `allocVector`, or interpreter items (`eval`, `findVar`) appear adjacent to any of the five `R_FINITE` call sites. `R_FINITE` is used exclusively in pure arithmetic predicate context.

**Distinct implementation patterns.**

All five CSV rows share a single implementation pattern:

| Pattern | Locations | Description |
|---|---|---|
| P1: Finite-value guard on `double` element of `double **` | `branch.c:39`, `branch.c:59`, `nodesplit.c:107`, `rpart.c:154`, `xpred.c:153` | `R_FINITE(xdata[var][obs])` or `R_FINITE(rp.xdata[i][k])` — the macro is called with a `double` expression and its result is used directly in an `if` condition to detect missing predictor values. No surrounding allocation, no SEXP interaction, no error mechanism. |

All five call sites are structurally identical: a direct `if (R_FINITE(...))` or `if (!R_FINITE(...))` guard. No variation in argument type, no variation in surrounding allocation context. A single fake definition handles all five.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`R_FINITE` is a predicate macro on a `double` value. In the real `R_ext/Arith.h`, it has two branches:

```c
#ifdef HAVE_WORKING_ISFINITE
# define R_FINITE(x)    isfinite(x)
#else
# define R_FINITE(x)    R_finite(x)
#endif
```

On Linux with glibc (the target build environment), `HAVE_WORKING_ISFINITE` is defined and the macro expands to the C99 `isfinite(x)` from `<math.h>`. In a C++ translation unit the appropriate equivalent is `std::isfinite(x)` from `<cmath>`, which returns `true` for finite values and `false` for NaN, NA (a specific quiet NaN), and `+/-Inf`.

**Chosen mechanism.**

The fake defines `R_FINITE` as a direct macro over `std::isfinite`, cast to `int` for strict C compatibility:

```cpp
#define R_FINITE(x)  (std::isfinite(x) ? 1 : 0)
```

Additionally, the companion inline function `R_finite(double x)` (which serves as the fallback in the `#else` branch of the real header) is provided as an `inline` C++ function delegating to `std::isfinite`. This function-form definition also ensures that any translation unit that calls `R_finite(v)` directly (rather than via the macro) links correctly without `libR.so`.

**Relationship to `ISNAN` and `fake_Arith.hpp`.**

The `ISNAN.md` guide established `fake_Arith.hpp` as the single file that replaces `R_ext/Arith.h` and houses both `ISNAN` and `R_FINITE`. This guide specifies the authoritative definition for `R_FINITE` within that same file. The code block in Section 4 shows the complete `fake_Arith.hpp` as it must appear, incorporating both `ISNAN` (from `ISNAN.md`) and `R_FINITE` (this guide), which is consistent with the preliminary `R_FINITE` definition already shown in `ISNAN.md`'s fake implementation.

**Correctness for R's missing-value semantics.**

R's `NA_REAL` is the specific quiet-NaN bit-pattern `0x7FF00000000007A2`. `std::isfinite` returns `false` for any NaN (including this specific bit-pattern) and for `+/-Inf`, and returns `true` for all normal, subnormal, and zero double values. This exactly matches R's contract: `R_FINITE(NA_REAL) == 0`, `R_FINITE(NaN) == 0`, `R_FINITE(Inf) == 0`, `R_FINITE(-Inf) == 0`, `R_FINITE(0.0) == 1`, `R_FINITE(1.5) == 1`. No special bit-pattern manipulation is required.

**`#define` alias from original header that must be preserved.**

The real `R_ext/Arith.h` defines:

```c
#define R_FINITE(x)    isfinite(x)    /* when HAVE_WORKING_ISFINITE */
```

The fake replaces this with `std::isfinite` to avoid the unqualified-`isfinite` lookup issue in C++ (where `<cmath>` may `#undef` the C99 macro form). The macro name `R_FINITE` is preserved verbatim so that all five call sites in the rpart source compile without modification.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered. `R_FINITE` is a pure arithmetic predicate. It never calls `Rf_error` or `Rf_warning`. The five surrounding `if (!R_FINITE(...))` guards write to scratch arrays or `continue` a loop; they do not throw.
- Invariant 2 (arena memory): not triggered. `R_FINITE` performs no memory allocation.
- Invariant 3 (R Interpreter Items): not triggered. `R_FINITE` is a pure IEEE 754 finiteness test with no interpreter dependency.

---

### 4. Fake Implementation Examples

#### Pattern P1: Finite-Value Guard on `double` Element of `double **`

- **Locations:** `branch.c:39`, `branch.c:59`, `nodesplit.c:107`, `rpart.c:154`, `xpred.c:153`

- **Original R API Usage:**

```c
/* branch.c:39 — primary split direction */
if (R_FINITE(xdata[j][obs])) {
    if (rp.numcat[j] == 0) {        /* continuous */
        dir = (xdata[j][obs] < tsplit->spoint) ?
            tsplit->csplit[0] : -tsplit->csplit[0];
        goto down;
    } else {                         /* categorical predictor */
        category = (int) xdata[j][obs];
        dir = (tsplit->csplit)[category - 1];
        if (dir)
            goto down;
    }
}

/* branch.c:59 — surrogate split (semantically identical) */
if (R_FINITE(xdata[j][obs])) {  /* not missing */
    ...
}

/* nodesplit.c:107 — skip non-finite surrogate observation */
if (!R_FINITE(xdata[var][j]))
    continue;

/* rpart.c:154 — sort-index build, missing-value encoding */
if (!R_FINITE(rp.xdata[i][k])) {
    rp.tempvec[k] = -(k + 1);   /* this variable is missing */
    rp.xtemp[k] = 0;
} else {
    rp.tempvec[k] = k;
    rp.xtemp[k] = rp.xdata[i][k];
}

/* xpred.c:153 — identical pattern to rpart.c:154 */
if (!R_FINITE(rp.xdata[i][k])) {
    rp.tempvec[k] = -(k + 1);
    rp.xtemp[k] = 0;
} else {
    rp.tempvec[k] = k;
    rp.xtemp[k] = rp.xdata[i][k];
}
```

- **C++ Fake Implementation:**

```cpp
// fake_Arith.hpp
// Drop-in replacement for R_ext/Arith.h.
// Provides: R_FINITE, R_finite, ISNAN, R_isnancpp, ISNA,
//           R_IsNA, R_IsNaN, R_NaReal, R_NaN, R_PosInf, R_NegInf,
//           NA_REAL, NA_INTEGER, NA_LOGICAL, R_NaInt.
//
// Include order: included by fake_R.hpp, which replaces R.h.
// Must be included before any rpart source file that includes rpart.h,
// because rpart.h:27 (#define RPARTNA(a) ISNAN(a)) uses ISNAN in a
// macro body, and all five R_FINITE call sites are in rpart source files.
//
// No dependency on SEXP, RError, or the arena.

#pragma once
#ifndef FAKE_ARITH_H
#define FAKE_ARITH_H

#include <cmath>      // std::isnan, std::isinf, std::isfinite
#include <limits>     // std::numeric_limits
#include <climits>    // INT_MIN (for NA_INTEGER / R_NaInt)
#include <cstdint>    // uint64_t (for NA_REAL bit-pattern)
#include <cstring>    // std::memcpy (for type-punning)

// -----------------------------------------------------------------------
// R_finite — inline replacement for the libR.so function R_finite(double).
//
// Returns 1 if x is a finite number: not NaN, not NA (a specific NaN),
// and not +/-Inf.  std::isfinite returns false for every non-finite
// IEEE 754 value, which exactly matches R's semantics:
//   R_finite(NA_REAL)  == 0   (NA is a quiet NaN)
//   R_finite(NaN)      == 0
//   R_finite(+Inf)     == 0
//   R_finite(-Inf)     == 0
//   R_finite(0.0)      == 1
//   R_finite(1.5)      == 1
// -----------------------------------------------------------------------
inline int R_finite(double x) {
    return std::isfinite(x) ? 1 : 0;
}

// -----------------------------------------------------------------------
// R_FINITE macro — preserves the exact macro name from R_ext/Arith.h so
// that all five call sites in the rpart source compile without modification:
//
//   branch.c:39    if (R_FINITE(xdata[j][obs]))
//   branch.c:59    if (R_FINITE(xdata[j][obs]))
//   nodesplit.c:107 if (!R_FINITE(xdata[var][j]))
//   rpart.c:154    if (!R_FINITE(rp.xdata[i][k]))
//   xpred.c:153    if (!R_FINITE(rp.xdata[i][k]))
//
// In the real R_ext/Arith.h the macro expands to isfinite(x) (the C99
// function-like macro from <math.h>) when HAVE_WORKING_ISFINITE is set.
// The fake always uses std::isfinite to avoid the unqualified-isfinite
// lookup ambiguity in C++ (where <cmath> may #undef the C99 macro form
// on some platforms, notably macOS).
//
// The cast to int is not strictly necessary because std::isfinite already
// returns bool (implicitly convertible to int), but it makes the 0/1
// contract explicit and matches R's documented int return type for
// R_finite().
// -----------------------------------------------------------------------
#define R_FINITE(x)  (std::isfinite(x) ? 1 : 0)

// -----------------------------------------------------------------------
// R_isnancpp — C++ inline replacement for the libR.so function.
//
// std::isnan returns true for any IEEE 754 NaN, including R's NA_REAL
// (bit-pattern 0x7FF00000000007A2).  This is the correct semantics:
// ISNAN must be true for both plain NaN and R's NA.
// -----------------------------------------------------------------------
inline int R_isnancpp(double x) {
    return std::isnan(x) ? 1 : 0;
}

// -----------------------------------------------------------------------
// ISNAN macro — matches the C++ branch of R_ext/Arith.h exactly.
// Expands to R_isnancpp(x) so that rpart.h:27
//   #define RPARTNA(a) ISNAN(a)
// compiles without modification.
// -----------------------------------------------------------------------
#ifdef __cplusplus
#  define ISNAN(x)   R_isnancpp(x)
#else
#  define ISNAN(x)   (isnan(x) != 0)
#endif

// -----------------------------------------------------------------------
// R_NaReal — the double value used as R's NA for real vectors.
//
// R's NA_REAL is the IEEE 754 quiet NaN with bit-pattern
// 0x7FF00000000007A2.  Reconstructed via memcpy from a uint64_t constant
// to avoid undefined behaviour from direct float reinterpretation.
//
// std::isnan(R_NaReal)    == true   => ISNAN(R_NaReal)    == 1
// std::isfinite(R_NaReal) == false  => R_FINITE(R_NaReal) == 0
// -----------------------------------------------------------------------
namespace fake_r_arith_detail {
    inline double make_na_real() {
        const uint64_t kNaRealBits = UINT64_C(0x7FF00000000007A2);
        double v;
        std::memcpy(&v, &kNaRealBits, sizeof(v));
        return v;
    }
    inline double make_nan() {
        return std::numeric_limits<double>::quiet_NaN();
    }
    inline double make_pos_inf() {
        return std::numeric_limits<double>::infinity();
    }
    inline double make_neg_inf() {
        return -std::numeric_limits<double>::infinity();
    }
}

// Declared static to avoid ODR violations when multiple translation
// units include this header.
static const double R_NaReal = fake_r_arith_detail::make_na_real();
static const double R_NaN    = fake_r_arith_detail::make_nan();
static const double R_PosInf = fake_r_arith_detail::make_pos_inf();
static const double R_NegInf = fake_r_arith_detail::make_neg_inf();

// Aliases used in rpart source code.
#define NA_REAL      R_NaReal
#define NA_INTEGER   R_NaInt
#define NA_LOGICAL   R_NaInt

// R_NaInt — scalar integer version of NA (= INT_MIN in R's implementation).
static const int R_NaInt = INT_MIN;

// -----------------------------------------------------------------------
// R_IsNA — true only for R's specific NA_REAL bit-pattern.
//
// Unlike ISNAN, R_IsNA returns 0 for plain NaN and 1 only for NA_REAL.
// -----------------------------------------------------------------------
inline int R_IsNA(double x) {
    if (!std::isnan(x)) return 0;
    const uint64_t kNaRealBits = UINT64_C(0x7FF00000000007A2);
    uint64_t x_bits;
    std::memcpy(&x_bits, &x, sizeof(x_bits));
    return (x_bits == kNaRealBits) ? 1 : 0;
}

// ISNA macro — matches R_ext/Arith.h.
#define ISNA(x)  R_IsNA(x)

// -----------------------------------------------------------------------
// R_IsNaN — true for IEEE NaN but NOT for R's NA.
// R_IsNaN(NA_REAL) == 0; R_IsNaN(NaN) == 1.
// -----------------------------------------------------------------------
inline int R_IsNaN(double x) {
    if (!std::isnan(x)) return 0;
    return R_IsNA(x) ? 0 : 1;
}

#endif // FAKE_ARITH_H
```

- **Arena / Memory Notes:** Not applicable. `R_FINITE` is a pure scalar predicate with no heap or arena allocation. The surrounding code in `rpart.c:154` and `xpred.c:153` writes to `rp.tempvec` and `rp.xtemp`, which are `int *` and `double *` scratch arrays previously allocated via `ALLOC(n, sizeof(...))` (i.e., `arena_alloc`). The `R_FINITE` test itself has no interaction with the arena; it merely determines which write branch executes.

- **Explanation:**

  The macro `R_FINITE` is defined with the name preserved verbatim from `R_ext/Arith.h`. All five rpart source call sites use `xdata[j][obs]` or `rp.xdata[i][k]`, which are `double` l-values obtained by double-dereferencing a `double **`. The `std::isfinite` function accepts `double` directly and returns `bool`, which is promoted to `int` in the ternary expression `std::isfinite(x) ? 1 : 0`. The explicit `? 1 : 0` ensures that the result is strictly `0` or `1` as an `int`, matching R's documented behavior for `R_finite`.

  The companion inline function `R_finite(double x)` is provided alongside the macro because the real `R_ext/Arith.h` declares `int R_finite(double)` as a function prototype (the `#else` branch of the `HAVE_WORKING_ISFINITE` guard falls back to calling this function). If any rpart source or included header calls `R_finite(v)` as a function rather than `R_FINITE(v)` as a macro, the inline definition satisfies the call without requiring `libR.so`.

  The macro does not need `#ifdef __cplusplus` guards because `std::isfinite` is available and unambiguous in C++ via `<cmath>`. In the fake build, all translation units including this header are compiled as C++; the `#else` plain-C fallback is not used.

  The complete `fake_Arith.hpp` shown above incorporates both `R_FINITE` (this guide) and `ISNAN` (from `ISNAN.md`) as a single coherent header. This is consistent with the fact that both macros originate from the same `R_ext/Arith.h` source header. The `ISNAN.md` guide already showed a preliminary version of `fake_Arith.hpp` that included `R_FINITE`; this guide is the definitive specification, with the implementation detail that `R_FINITE` must use `std::isfinite` from `<cmath>` rather than the unqualified C99 `isfinite` from `<math.h>`.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| None | `R_FINITE` and all items in `fake_Arith.hpp` depend only on C++ standard library headers (`<cmath>`, `<limits>`, `<climits>`, `<cstdint>`, `<cstring>`). No fake guide for `SEXP`, `RError`, or the arena allocator is required before this file is included. |

**Dependency from other guides on this one.**

- `ISNAN.md` — established `fake_Arith.hpp` as the replacement header for `R_ext/Arith.h`, and showed a preliminary `R_FINITE` definition within it. This guide supersedes that preliminary definition. The two guides together form the complete specification of `fake_Arith.hpp`; the implementation shown in Section 4 of this guide is the canonical version.
- `SEXP.md` — the `fake_Rinternals.hpp` shown there includes `fake_arena.hpp` but does not include `fake_Arith.hpp`. The master fake header (`fake_R.hpp`, replacing `R.h`) must include `fake_Arith.hpp` before `fake_Rinternals.hpp`, matching the include order in the real `R.h` (which includes `R_ext/Arith.h` before `Rinternals.h`).

**Consume order note.** `fake_Arith.hpp` must be included before any rpart source file that includes `rpart.h`, because `rpart.h:9` includes `R.h` (the master include), and `rpart.h:27` uses `ISNAN` in a macro body. In the fake build, `fake_R.hpp` (the master fake header replacing `R.h`) should include `fake_Arith.hpp` as its first sub-header.
