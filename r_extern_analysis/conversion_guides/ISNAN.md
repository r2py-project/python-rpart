# Conversion Guide: `ISNAN`

## 1. Overview of `ISNAN` in R API

`ISNAN(x)` is a macro defined in `R_ext/Arith.h` (pulled in by `R.h`) that tests whether a `double` value is either a standard IEEE 754 NaN **or** R's special `NA_REAL` value. It returns a non-zero integer (true) for both cases, making it distinct from the POSIX `ISNA(x)` macro, which is true only for R's `NA_real_` sentinel. Under C compilation it expands to `(isnan(x) != 0)` from `<math.h>`; under C++ it delegates to R's internal `R_isnancpp()` to work around the fact that C++ math headers may undefine the C99 `isnan` macro. In rpart, it is wrapped by the project-local alias `RPARTNA(a)` defined in `rpart.h` line 27.

## 2. Contextual Usage Analysis

### CSV entry

| Field | Value |
|---|---|
| `file_name` | `rpart.h` |
| `line_number` | 27 |
| `context_statement` | `#define RPARTNA(a) ISNAN(a)` |

### Source window (lines 12–42 of `rpart.h`)

`RPARTNA` is introduced alongside two other convenience macros:

```c
#define ALLOC(a,b)  R_alloc(a,b)
#define CALLOC(a,b) R_chk_calloc((size_t)(a), b)
#define RPARTNA(a) ISNAN(a)
```

`RPARTNA` is the *only* occurrence of `ISNAN` across the entire `rpart/src/` directory. No `.c` file calls `ISNAN` directly; they all test for missing continuous predictor values through the related macro `R_FINITE()` (e.g., `rpart.c:154`, `xpred.c:153`). The actual call sites that would trigger `RPARTNA` are the places where a floating-point value must be classified as missing before it is placed in the sort index (encoded as a negative index, `-(k+1)`).

**Data types involved:** `double` (continuous predictor values stored in `rp.xdata`).

**Memory management macros used alongside:** None. `ISNAN`/`RPARTNA` is a pure predicate; it does not allocate or protect any R objects.

**Distinct usage pattern found:** One pattern — definition of a project-level NaN/NA predicate alias (`#define RPARTNA(a) ISNAN(a)`). At actual call sites the codebase currently uses `R_FINITE` (its logical complement) rather than `RPARTNA` directly, but both idioms are conceptually identical and convert identically.

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`ISNAN` is already a thin wrapper around C99's `isnan()`. When migrating from the `.Call`/`.External` API to the `.C`/`.Fortran` API:

- **Remove the `R.h` include** (and with it the dependency on `R_ext/Arith.h`). Replace it with `#include <math.h>` (C) or `#include <cmath>` (C++).
- **Replace `ISNAN(x)` with `isnan(x)`** (C99/C11, available in `<math.h>`). The semantics are identical for all standard NaN bit patterns, including R's `NA_real_` value, which is itself an IEEE NaN.
- **Replace `RPARTNA(a)` with `isnan(a)`** throughout the codebase (or re-define the macro against `isnan`).
- **Replace `R_FINITE(x)` with `isfinite(x)`** (C99, `<math.h>`) at the complementary call sites.

### Why this ensures `.C` API compatibility

The `.C` interface passes `double *` arrays directly; there is no `SEXP` wrapping and no R memory management involved. The `isnan` and `isfinite` predicates from `<math.h>` operate on plain `double` scalars — exactly the type that `.C` provides — with no dependency on R's internal runtime. Sentinel encoding of missing values (negative sort indices) is preserved unchanged.

## 4. Step-by-Step Conversion Examples

### Pattern: Project-level NaN/NA predicate macro definition

- **Locations:** `rpart.h`, line 27
- **Original Context (.Call):**

```c
/* rpart.h — requires #include <R.h> */
#include <R.h>

#define RPARTNA(a) ISNAN(a)
```

Downstream usage in sorting loops (e.g., `rpart.c:154`):

```c
/* uses R_FINITE, the logical complement of ISNAN */
if (!R_FINITE(rp.xdata[i][k])) {
    rp.tempvec[k] = -(k + 1);   /* mark as missing */
    rp.xtemp[k] = 0;
} else {
    rp.tempvec[k] = k;
    rp.xtemp[k] = rp.xdata[i][k];
}
```

- **C/C++ Equivalent (.C):**

```c
/* rpart.h — no R.h dependency */
#include <math.h>   /* provides isnan(), isfinite() */

/* Option A: re-define the macro against standard C99 */
#define RPARTNA(a) (isnan(a) != 0)

/* Option B: remove the macro entirely and use isnan() directly */
/* #define RPARTNA(a) isnan(a)  — also acceptable */
```

Converted downstream usage:

```c
/* uses isfinite(), the C99 complement of isnan() */
if (!isfinite(rp.xdata[i][k])) {
    rp.tempvec[k] = -(k + 1);   /* mark as missing */
    rp.xtemp[k] = 0.0;
} else {
    rp.tempvec[k] = k;
    rp.xtemp[k] = rp.xdata[i][k];
}
```

- **Explanation:**
  - `ISNAN(x)` expands to `(isnan(x) != 0)` in C; the converted macro is a direct textual substitution.
  - `R_FINITE(x)` expands to `isfinite(x)` on systems with a working C99 `isfinite` (the common case); the conversion is likewise a direct substitution.
  - No indexing adjustments are required: the missing-value sentinel scheme (encoding missing observations as negative sort indices `-(k+1)`) is a pure C convention and is retained unchanged.
  - No R memory management macros (`PROTECT`, `UNPROTECT`, `allocVector`, etc.) are present at these sites; no changes to the argument list are needed for this particular macro.
  - The `<math.h>` header must be present (either directly or via `<stddef.h>` chain). In the rpart sources, `rpart.c` already includes `<math.h>` explicitly; after removing `<R.h>`, other translation units must add this include as needed.
