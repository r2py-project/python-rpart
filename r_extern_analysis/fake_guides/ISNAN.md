# Fake Header Implementation Guide: `ISNAN`

---

### 1. Overview of `ISNAN` in R API

`ISNAN` is a preprocessor macro defined in `R_ext/Arith.h` (included transitively by `R.h`) that tests whether a `double` value is either R's `NA_REAL` sentinel or an IEEE 754 NaN. In the C++ branch of the header it expands to `R_isnancpp(x)` — a function in `libR.so` whose implementation handles both cases — while in plain C it expands to `(isnan(x)!=0)`. In rpart, `ISNAN` appears exclusively as the body of the local package macro `RPARTNA(a)` defined in `rpart.h:27`, which is the project's single canonical predicate for testing whether a predictor observation is missing. The only input type is `double`; the return value is `int` (0 or 1, mapping to false/true).

---

### 2. Contextual Usage Analysis

**Source file examined.**

| File | Line | Context |
|---|---|---|
| `rpart.h` | 27 | `#define RPARTNA(a) ISNAN(a)` |

**Step 1 extended context — call sites of `RPARTNA` and related NA tests.**

`RPARTNA` is defined at `rpart.h:27` but is never called directly in the rpart source tree. A complete text search of all `.c` and `.h` files under `rpart/src/` confirms zero call sites for `RPARTNA`. This means `ISNAN` is only required so that the macro definition at line 27 compiles; the macro body must be syntactically valid C++ and must produce the correct `int` result for any `double` argument.

The rpart source instead uses the companion macro `R_FINITE(x)` (from the same `R_ext/Arith.h` header) in five locations: `branch.c:39`, `branch.c:59`, `nodesplit.c:107`, `rpart.c:154`, and `xpred.c:153`. Those are guarded by `!R_FINITE(...)`, meaning "not a finite number, i.e., missing or infinite." `R_FINITE` is documented separately as a dependency of this guide.

**C types.**

| Role | Type |
|---|---|
| Argument `a` | `double` (all call sites pass a `double` array element, e.g., `xdata[j][obs]`) |
| Return value | `int` — non-zero (1) if the value is NaN or R's NA, zero (0) otherwise |

**Co-occurring R API items.**

- `R_FINITE(x)` — the complementary test, appearing at every missing-data check in the rpart C source. Both macros originate in `R_ext/Arith.h` and must be defined in the same fake header.
- `NA_REAL` / `R_NaReal` — the `double` constant holding R's NA (a specific NaN bit-pattern). Not used directly in any rpart `.c` file, but it is declared in `R_ext/Arith.h` next to `ISNAN` and must be provided in the fake to satisfy the header's declarations.
- `R_NaN`, `R_PosInf`, `R_NegInf` — additional `LibExtern double` constants from `R_ext/Arith.h`. Not referenced in rpart source files, but declared alongside `ISNAN` in the original header.
- `R_IsNA(double)`, `R_IsNaN(double)`, `R_finite(double)` — function declarations in `R_ext/Arith.h` whose implementations live in `libR.so`. Not called in rpart source, but they must be declared (or defined as inline stubs) so that any indirect inclusion of `R_ext/Arith.h` does not produce undefined-symbol link errors.
- `ISNA(x)` — sibling macro `#define ISNA(x) R_IsNA(x)` appearing in the same header; must also be defined.

**Distinct implementation patterns.**

There is exactly one usage pattern in the CSV:

| Pattern | Location | Description |
|---|---|---|
| P1: Macro body definition for `RPARTNA` | `rpart.h:27` | `#define RPARTNA(a) ISNAN(a)` — `ISNAN` must be a valid expression macro taking a `double` and returning `int`. No allocation, no error, no interpreter involvement. |

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`ISNAN` is purely a predicate function on a `double`. In R's real header it has two branches: the C++ branch calls `R_isnancpp(x)` (a function in `libR.so`) and the plain-C branch calls the C standard `isnan()`. Because the fake build compiles as C++ (the fake headers are C++ and the wrapper glue is compiled with a C++ compiler), the relevant branch is the `R_isnancpp` one. In the fake, `R_isnancpp` is implemented as an `inline` C++ function that uses `std::isnan` from `<cmath>`. This avoids any dependency on `libR.so` while remaining semantically correct for the rpart use case.

**Chosen mechanism.**

In a standalone C++ build, `<cmath>` provides `std::isnan(double)` which returns `true` for any IEEE 754 NaN bit-pattern, including R's `NA_REAL` (which is a specific quiet NaN). This is the correct behavior for `ISNAN`: both NaN and NA must return non-zero. The fake therefore:

1. Defines `inline int R_isnancpp(double x) { return std::isnan(x) ? 1 : 0; }`.
2. Preserves the original `#ifdef __cplusplus` / `#else` macro structure so that if any translation unit is compiled as C (unlikely for the fake build, but safe), it falls back to `(isnan(x)!=0)`.
3. Defines the companion items declared in the same `R_ext/Arith.h` header: `R_IsNA`, `R_IsNaN`, `R_finite` (all as inline stubs), `ISNA`, `R_FINITE`, and the `LibExtern double` constants (`R_NaN`, `R_PosInf`, `R_NegInf`, `R_NaReal`).

**Relationship between `ISNAN` and `NA_REAL`.**

R's `NA_REAL` is the specific quiet-NaN bit-pattern `0x7FF00000000007A2` used to represent integer NA coerced to double. `std::isnan` returns true for this pattern, so `ISNAN(NA_REAL)` correctly yields 1. In the fake, `R_NaReal` is defined as a `constexpr double` using the same bit-pattern via `std::numeric_limits` or a `union` reinterpret cast, so that code which compares against `NA_REAL` or passes `NA_REAL` as a sentinel still works.

**`#define` aliases that must be preserved.**

The real `R_ext/Arith.h` defines:
```c
#define ISNA(x)    R_IsNA(x)
#define ISNAN(x)   R_isnancpp(x)    /* C++ branch */
#define R_FINITE(x) isfinite(x)     /* when HAVE_WORKING_ISFINITE */
```

All three must appear in the fake header so that `rpart.h:27` (`#define RPARTNA(a) ISNAN(a)`) and the five `R_FINITE` call sites in the rpart source compile unchanged.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered. `ISNAN` never calls `Rf_error` or `Rf_warning`. It is a pure predicate.
- Invariant 2 (arena memory): not triggered. No allocation of any kind.
- Invariant 3 (R Interpreter Items): not triggered. `ISNAN` is a pure arithmetic test with no interpreter dependency.

---

### 4. Fake Implementation Examples

#### Pattern P1: Macro Body Definition for `RPARTNA`

- **Locations:** `rpart.h:27`

- **Original R API Usage:**

```c
/* rpart.h:27 — the only occurrence of ISNAN in the rpart source tree */
#define RPARTNA(a) ISNAN(a)

/* The real R_ext/Arith.h defines ISNAN as (C++ branch): */
int R_isnancpp(double); /* in arithmetic.c (libR.so) */
#define ISNAN(x)   R_isnancpp(x)
```

- **C++ Fake Implementation:**

```cpp
// fake_Arith.hpp
// Drop-in replacement for R_ext/Arith.h.
// Provides: ISNAN, R_FINITE, ISNA, R_NaReal, R_NaN, R_PosInf, R_NegInf,
//           R_IsNA, R_IsNaN, R_finite, NA_REAL, NA_INTEGER.
//
// Include order: this file is included by fake_R.hpp, which replaces R.h.
// It must be included before any rpart source file that includes rpart.h,
// because rpart.h:27 uses ISNAN in a macro body.
//
// No dependency on SEXP or any other fake header.

#pragma once
#ifndef FAKE_ARITH_H
#define FAKE_ARITH_H

#include <cmath>      // std::isnan, std::isinf, std::isfinite
#include <limits>     // std::numeric_limits
#include <climits>    // INT_MIN (for NA_INTEGER / R_NaInt)
#include <cstdint>    // uint64_t (for NA_REAL bit-pattern)
#include <cstring>    // std::memcpy (for type-punning)

// -----------------------------------------------------------------------
// R_isnancpp — C++ inline replacement for the libR.so function.
//
// std::isnan returns true for any IEEE 754 NaN, including R's NA_REAL
// (a specific quiet NaN bit-pattern 0x7FF00000000007A2).  This is the
// correct semantics: ISNAN must be true for both plain NaN and R's NA.
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
// R_finite — inline replacement for the libR.so function.
//
// Returns 1 (true) if x is a finite number: not NaN, not NA, not +/-Inf.
// std::isfinite already handles all these cases because NaN and +/-Inf
// are the only non-finite IEEE 754 values.  R's NA_REAL is a NaN, so
// R_finite(NA_REAL) correctly returns 0.
// -----------------------------------------------------------------------
inline int R_finite(double x) {
    return std::isfinite(x) ? 1 : 0;
}

// R_FINITE macro — used in branch.c, nodesplit.c, rpart.c, xpred.c.
// The real header uses isfinite() when HAVE_WORKING_ISFINITE is set (the
// common case on Linux/glibc); the fake always uses std::isfinite.
#define R_FINITE(x)  (std::isfinite(x) ? 1 : 0)

// -----------------------------------------------------------------------
// R_NaReal — the double value used as R's NA for real vectors.
//
// R's NA_REAL is the IEEE 754 quiet NaN with the specific bit-pattern
// 0x7FF00000000007A2 (little-endian: bytes 7F F0 00 00 00 00 07 A2).
// We reconstruct it via memcpy from a uint64_t constant to avoid
// undefined behaviour from direct float reinterpretation.
//
// std::isnan(R_NaReal) == true, so ISNAN(R_NaReal) == 1 and
// R_FINITE(R_NaReal) == 0, matching R's semantics exactly.
// -----------------------------------------------------------------------
namespace fake_r_arith_detail {
    inline double make_na_real() {
        // Bit pattern for R's NA_REAL (matches R's main/arithmetic.c).
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

// Global constants matching the LibExtern declarations in R_ext/Arith.h.
// In the real R runtime these are external symbols in libR.so; in the
// fake they are inline-initialized global variables.
//
// Declared inline (C++17) or static to avoid ODR violations when multiple
// translation units include this header.
static const double R_NaReal = fake_r_arith_detail::make_na_real();
static const double R_NaN    = fake_r_arith_detail::make_nan();
static const double R_PosInf = fake_r_arith_detail::make_pos_inf();
static const double R_NegInf = fake_r_arith_detail::make_neg_inf();

// NA_REAL and NA_INTEGER are the aliases used in rpart source code.
// NA_REAL matches R_NaReal; NA_INTEGER matches INT_MIN (R_NaInt).
#define NA_REAL      R_NaReal
#define NA_INTEGER   INT_MIN
#define NA_LOGICAL   INT_MIN

// R_NaInt — scalar integer version of NA (= INT_MIN in R's implementation).
static const int R_NaInt = INT_MIN;

// -----------------------------------------------------------------------
// R_IsNA — true only for R's specific NA_REAL bit-pattern.
//
// Unlike ISNAN, R_IsNA returns 0 for plain NaN and 1 only for NA_REAL.
// The implementation compares the bit-pattern of x against NA_REAL's
// bit-pattern to distinguish them; this requires memcpy-based comparison
// to avoid UB.
//
// In rpart source files, R_IsNA is not called directly; it is only
// declared via the ISNA macro.  The inline implementation is provided
// for completeness and for code that calls ISNA(x).
// -----------------------------------------------------------------------
inline int R_IsNA(double x) {
    // Any NaN that is not the specific NA_REAL bit-pattern is a plain NaN.
    if (!std::isnan(x)) return 0;
    uint64_t x_bits, na_bits;
    const uint64_t kNaRealBits = UINT64_C(0x7FF00000000007A2);
    std::memcpy(&x_bits, &x, sizeof(x_bits));
    std::memcpy(&na_bits, &R_NaReal, sizeof(na_bits));
    return (x_bits == kNaRealBits) ? 1 : 0;
}

// ISNA macro — matches R_ext/Arith.h.
#define ISNA(x)  R_IsNA(x)

// -----------------------------------------------------------------------
// R_IsNaN — true for IEEE NaN but NOT for R's NA.
//
// R_IsNaN(NA_REAL) == 0; R_IsNaN(NaN) == 1.
// (The inverse of R_IsNA among the set of all NaN values.)
// -----------------------------------------------------------------------
inline int R_IsNaN(double x) {
    if (!std::isnan(x)) return 0;
    return R_IsNA(x) ? 0 : 1;
}

#endif // FAKE_ARITH_H
```

- **Arena / Memory Notes:** Not applicable. `ISNAN`, `R_FINITE`, and all related items in this header are pure scalar predicates. No heap or arena allocation occurs.

- **Explanation:**

  The single CSV row `rpart.h:27` requires `ISNAN` to be a valid C++ macro or inline function that accepts a `double` argument and returns an `int`. The rpart source never invokes `RPARTNA(a)` directly — it is defined but unused in the present call-tree — yet the macro definition at line 27 must compile. The fake achieves this by replacing `R_isnancpp`, the `libR.so` function that the real C++ branch of `ISNAN` delegates to, with an `inline int R_isnancpp(double x)` that calls `std::isnan`.

  The `#ifdef __cplusplus` guard in the original `R_ext/Arith.h` is preserved in the fake so the header is safe to include from both C++ and C translation units (though in practice only C++ units are used in the fake build).

  The five `R_FINITE(...)` call sites in the rpart source (`branch.c:39`, `branch.c:59`, `nodesplit.c:107`, `rpart.c:154`, `xpred.c:153`) use a separate macro that is defined in the same `R_ext/Arith.h`. The fake provides `R_FINITE` as a direct macro over `std::isfinite`, which is correct for all four non-finite cases: NaN, NA (a specific NaN), +Inf, and -Inf all return 0 from `std::isfinite`.

  The `LibExtern double R_NaReal; R_NaN; R_PosInf; R_NegInf;` declarations in the real header are external symbols resolved at link time against `libR.so`. In the fake they are replaced by `static const double` variables with values computed from `std::numeric_limits` and a memcpy-based bit-pattern reconstruction of `R_NaReal`. They are `static` to avoid ODR violations when multiple translation units include this header.

  The `NA_REAL` macro alias used in the original header expands to `R_NaReal`, so any rpart code that writes `NA_REAL` (none observed, but possible in future additions) still compiles and carries the correct bit-pattern.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| None | `ISNAN` and all items in `fake_Arith.hpp` depend only on C++ standard library headers (`<cmath>`, `<limits>`, `<climits>`, `<cstdint>`, `<cstring>`). No fake guide for `SEXP`, `RError`, or the arena is required before this file is included. |

**Consume order note.** `fake_Arith.hpp` must be included before `rpart.h` is parsed (since `rpart.h:9` includes `R.h`, which transitively includes `R_ext/Arith.h`). In the fake build, the master fake header (`fake_R.hpp`, replacing `R.h`) should include `fake_Arith.hpp` as its first sub-header, matching the include order in the real `R.h:69`.
