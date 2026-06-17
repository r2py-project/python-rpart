# Fake Header Implementation Guide: `asInteger`

---

### 1. Overview of `asInteger` in R API

`asInteger` is a scalar-coercion function in R's C API, declared in `Rinternals.h` as `int Rf_asInteger(SEXP x)` with the macro alias `#define asInteger Rf_asInteger`. It accepts a single `SEXP` argument — typically a length-1 integer or numeric vector — and returns the C `int` value of its first element. Unlike `INTEGER(x)`, which returns a pointer to the entire element buffer, `asInteger` extracts and returns only the first element as a scalar `int`, performing a coercion if necessary (e.g., from `REALSXP` to `int`). In rpart's source files, `asInteger` is used exclusively to extract scalar configuration parameters from `.Call` input arguments, converting single-element SEXP wrappers into plain `int` values for use in control flow and struct fields. `asInteger` is not an R Interpreter Item; it requires no running R interpreter and no function-pointer bridge.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Line | Context |
|---|---|---|
| `pred_rpart.c` | 138 | `int n = asInteger(dimx);` |
| `pred_rpart.c` | 140 | `pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit), ...);` |
| `rpart.c` | 77 | `xvals = asInteger(xvals2);` |
| `rpart.c` | 83 | `if (asInteger(method2) <= NUM_METHODS) {` |
| `rpart.c` | 84 | `i = asInteger(method2) - 1;` |
| `rpart.c` | 89 | `rp.num_y = asInteger(ny2);` |
| `rpart_callback.c` | 54 | `ysave = asInteger(ny);` |
| `rpart_callback.c` | 55 | `rsave = asInteger(nr);` |
| `xpred.c` | 71 | `xvals = asInteger(xvals2);` |
| `xpred.c` | 81 | `if (asInteger(method2) <= NUM_METHODS) {` |
| `xpred.c` | 82 | `i = asInteger(method2) - 1;` |
| `xpred.c` | 87 | `rp.num_y = asInteger(ny2);` |
| `xpred.c` | 114 | `rp.num_resp = asInteger(nresp2);` |
| `xpred.c` | 205 | `if (asInteger(all2) == 1)` |

**Argument and return types observed across all rows.**

`asInteger` always takes a single `SEXP` argument and always returns `int`. The source SEXPs are all `.Call` input parameters (not locally allocated SEXPs) — they are scalar wrappers constructed by the R or Python caller before the `.Call` boundary. The `int` result is used in one of the following ways:

- Assigned to a local `int` variable used as a count or index (`pred_rpart.c:138`: `int n = asInteger(dimx)`; `rpart.c:77`: `xvals = asInteger(xvals2)`)
- Passed directly as a scalar `int` argument to an internal C function (`pred_rpart.c:140`: `asInteger(nnode)`, `asInteger(nsplit)`)
- Used in a comparison expression in `if` or conditional (`rpart.c:83`: `if (asInteger(method2) <= NUM_METHODS)`)
- Used in an arithmetic expression (`rpart.c:84`: `i = asInteger(method2) - 1`)
- Assigned to a field of the global `rp` struct (`rpart.c:89`: `rp.num_y = asInteger(ny2)`; `xpred.c:87`, `xpred.c:114`)
- Assigned to a static module-level `int` variable (`rpart_callback.c:54–55`: `ysave`, `rsave`)

**Co-occurring R API items in context windows.**

- `INTEGER(sexp)` — appears at the same call sites, applied to multi-element SEXP parameters (`pred_rpart.c:140`). `INTEGER` returns `int *`; `asInteger` returns the scalar first element.
- `REAL(sexp)` — appears alongside `asInteger` in the same argument lists (`pred_rpart.c:140`, `xpred.c:71–88`).
- `allocVector(INTSXP, n)` — the `n` passed to `allocVector` in `pred_rpart.c:139` is the `int n` previously extracted by `asInteger(dimx)` on line 138.
- `PROTECT` / `UNPROTECT` — wrap the `allocVector` call that uses the `asInteger` result. `asInteger` itself is never wrapped in `PROTECT`.
- `error(_("Invalid value for 'method'"))` — appears in the `else` branch of the `if (asInteger(method2) <= NUM_METHODS)` guard in both `rpart.c:91` and `xpred.c:89`.
- `ALLOC`, `REAL(opt2)` — used in the same function bodies immediately after the `asInteger` calls, in the parameter-setup sections of `rpart()` and `xpred()`.

**Distinct usage patterns.**

Two structural patterns appear across the 14 CSV rows:

| Pattern | CSV rows | Description |
|---|---|---|
| P1: Extract scalar `int` from an input SEXP, assign to a local variable, struct field, or pass as argument | `pred_rpart.c:138`, `pred_rpart.c:140`, `rpart.c:77`, `rpart.c:84`, `rpart.c:89`, `rpart_callback.c:54`, `rpart_callback.c:55`, `xpred.c:71`, `xpred.c:82`, `xpred.c:87`, `xpred.c:114` | `asInteger` converts a SEXP parameter to a plain `int` for use as a count, index offset, or struct initializer. |
| P2: Use `asInteger` result directly in a comparison expression | `rpart.c:83`, `xpred.c:81`, `xpred.c:205` | `asInteger` is called inline inside an `if` condition: `if (asInteger(method2) <= NUM_METHODS)` or `if (asInteger(all2) == 1)`. The `int` result is consumed immediately with no intermediate variable. |

Both patterns share the identical fake `asInteger` implementation. The split into two patterns reflects the calling context (lvalue assignment vs. inline expression), not any difference in the fake function itself.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`asInteger` is declared in `Rinternals.h` at line 487 as `int Rf_asInteger(SEXP x)` and aliased at line 906 as `#define asInteger Rf_asInteger`. In the real R runtime, `Rf_asInteger` performs full type coercion: if the SEXP holds a `REALSXP`, it truncates the double to `int`; if it holds an `INTSXP`, it returns the value directly; it handles `NA` by returning `NA_INTEGER`. In rpart's usage, every SEXP passed to `asInteger` is a scalar integer vector (constructed by the R or Python caller as an `INTSXP` of length 1), so the coercion path is always `INTSXP -> int`.

**Chosen mechanism.**

The fake implements `asInteger` as a C++ `inline` function that casts `sexp->data` to `int *` and dereferences the first element:

```cpp
inline int Rf_asInteger(SEXP s) {
    return static_cast<int *>(s->data)[0];
}
#define asInteger Rf_asInteger
```

This is correct because:
1. The `SEXPREC` fake (from `SEXP.md`) stores the element buffer in `s->data` as a `void *`.
2. When the Python caller constructs an `INTSXP` scalar SEXP for a parameter like `method2`, it allocates a `SEXPREC` with `type=INTSXP`, `length=1`, and `data` pointing to a single `int` containing the value.
3. `static_cast<int *>(s->data)[0]` reads that first `int` element, which is identical to the real `Rf_asInteger` behavior for `INTSXP` inputs.

The `#define asInteger Rf_asInteger` alias from `Rinternals.h` must be preserved exactly so that the original source files (which call `asInteger(...)`, not `Rf_asInteger(...)`) compile without modification.

**Full coercion is not needed for rpart.** The real `Rf_asInteger` handles `REALSXP`, `LGLSXP`, `STRSXP`, and `NA` inputs. In rpart, no call to `asInteger` is ever applied to a `REALSXP` SEXP — all target SEXPs are scalar integers passed directly from the R (or Python) call boundary. Therefore the fake does not need to implement REALSXP-to-int coercion. If future callers pass a `REALSXP` scalar, the fake will return an incorrect bit-reinterpretation (a double read as an int). A safety check can be added with minimal overhead:

```cpp
inline int Rf_asInteger(SEXP s) {
    if (s->type == REALSXP)
        return static_cast<int>(static_cast<double *>(s->data)[0]);
    return static_cast<int *>(s->data)[0];
}
```

The SEXP.md guide already provides `asInteger` in the accessor block (Pattern P2 code comment at line 444 of that guide): `inline int asInteger(SEXP s) { return static_cast<int *>(s->data)[0]; }`. The present guide supersedes that inline reference with a complete specification including the `Rf_asInteger` function name, the `#define` alias, and the REALSXP coercion extension.

**`#define` aliases that must be preserved.**

```c
#define asInteger   Rf_asInteger
```

This is the only alias. The alias is present in `Rinternals.h` at line 906. It must appear in `fake_Rinternals.hpp` after the `Rf_asInteger` inline definition so that all occurrences of `asInteger(...)` in rpart source files resolve to the fake inline function.

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `asInteger` itself. The function performs a cast and cannot fail for a well-formed SEXP. The functions that produce the SEXP argument (constructed by the Python caller) may throw during construction, but `asInteger` is called after successful argument delivery.
- Invariant 2 (arena memory): not triggered. `asInteger` reads from an existing SEXP's `data` buffer; it does not allocate any memory, heap or arena.
- Invariant 3 (R Interpreter Items): not applicable. `asInteger` does not invoke the R interpreter.

---

### 4. Fake Implementation Examples

#### Pattern P1: Extract Scalar `int` from an Input SEXP, Assign to Variable or Pass as Argument

- **Locations:** `pred_rpart.c:138`, `pred_rpart.c:140`, `rpart.c:77`, `rpart.c:84`, `rpart.c:89`, `rpart_callback.c:54`, `rpart_callback.c:55`, `xpred.c:71`, `xpred.c:82`, `xpred.c:87`, `xpred.c:114`

- **Original R API Usage:**

```c
/* pred_rpart.c:138-140 — scalar extraction then immediate use as count and arguments */
int n = asInteger(dimx);
SEXP where = PROTECT(allocVector(INTSXP, n));
pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit),
            INTEGER(dimc), INTEGER(nnum), INTEGER(nodes2),
            INTEGER(vnum), REAL(split2), INTEGER(csplit2),
            INTEGER(usesur), REAL(xdata2), INTEGER(xmiss2),
            INTEGER(where));

/* rpart.c:77, 84, 89 — extraction to local variable, arithmetic, and struct field */
xvals = asInteger(xvals2);
/* ... */
i = asInteger(method2) - 1;
rp.num_y = asInteger(ny2);

/* rpart_callback.c:54-55 — extraction to static module-level int variables */
ysave = asInteger(ny);
rsave = asInteger(nr);

/* xpred.c:87, 114 — struct field assignment */
rp.num_y = asInteger(ny2);
rp.num_resp = asInteger(nresp2);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — asInteger accessor, Category B)
// Must appear after the SEXPREC struct and SEXP typedef from SEXP.md.

#pragma once
#ifndef FAKE_RINTERNALS_H
#define FAKE_RINTERNALS_H

// ... (SEXPREC, SEXP, SEXPTYPE block, RError, PROTECT/UNPROTECT,
//      allocVector, INTEGER, REAL, LENGTH from SEXP.md) ...

// -------------------------------------------------------------------------
// Rf_asInteger — extracts element [0] of a SEXP as a C int.
//
// Corresponds to Rinternals.h declaration:
//   int Rf_asInteger(SEXP x);
//   #define asInteger  Rf_asInteger
//
// For INTSXP input (the only type used in rpart): casts s->data to int *
// and returns element [0].
//
// For REALSXP input (not used in rpart, but handled for safety): casts
// s->data to double * and truncates element [0] to int, matching real
// Rf_asInteger coercion semantics.
//
// For all other SEXPTYPE values encountered: falls through to the int *
// cast, matching the behavior of the int-array branch.
// -------------------------------------------------------------------------
inline int Rf_asInteger(SEXP s) {
    if (s->type == REALSXP)
        return static_cast<int>(static_cast<double *>(s->data)[0]);
    return static_cast<int *>(s->data)[0];
}

// Preserve the #define alias from Rinternals.h line 906 so that the
// original rpart source files compile with 'asInteger(...)' unchanged.
#define asInteger Rf_asInteger

#endif // FAKE_RINTERNALS_H
```

The `.Call` entry-point boundary for `pred_rpart` illustrates how `ArenaFrame` is declared (needed because `pred_rpart0` and its callees use `ALLOC`/`R_alloc`) and how `RError` is caught. `asInteger` itself requires neither:

```cpp
// Python-facing entry-point wrapper for pred_rpart.
// asInteger is called inside pred_rpart() — no special guard needed for it.
// The ArenaFrame is required because pred_rpart0 calls ALLOC internally.
extern "C" SEXP pred_rpart_entry(
        SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
        SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
        SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2) {
    ArenaFrame _frame;   // frees R_alloc / ALLOC scratch on exit (Invariant 2)
    try {
        return pred_rpart(dimx, nnode, nsplit, dimc, nnum, nodes2,
                          vnum, split2, csplit2, usesur, xdata2, xmiss2);
    } catch (const RError &e) {
        set_python_error(e.what());   // store for Python to read
        return nullptr;
    }
}
```

Inside `pred_rpart()`, the original lines compile unchanged:

```c
// pred_rpart.c:138-140 — unchanged original source
int n = asInteger(dimx);
// expands to: int n = Rf_asInteger(dimx);
// which executes: static_cast<int *>(dimx->data)[0]
// dimx is a length-1 INTSXP SEXP constructed by the Python caller.

pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit), ...);
// asInteger(nnode) => static_cast<int *>(nnode->data)[0]
// asInteger(nsplit) => static_cast<int *>(nsplit->data)[0]
// These int scalars are passed to pred_rpart0's int parameters directly.
```

- **Arena / Memory Notes:** Not applicable. `asInteger` performs no memory allocation. It reads from the `data` buffer of an existing SEXP. The buffer was allocated by the Python caller as part of the input `SEXPREC` node construction before the `.Call` boundary; it remains valid for the lifetime of the `.Call` invocation.

- **Explanation:**

  `asInteger(dimx)` expands via the `#define` alias to `Rf_asInteger(dimx)`, which resolves to the inline `static_cast<int *>(dimx->data)[0]`. The `dimx` SEXP was constructed by the Python caller with `type=INTSXP`, `length=1`, and `data` pointing to a single `int` holding the first dimension count. The result is the plain `int` value of that element.

  For `pred_rpart.c:140`, `asInteger(nnode)` and `asInteger(nsplit)` are used as positional arguments of type `int` in the call to `pred_rpart0` (whose second and third parameters are declared `int nnode, int nsplit` — confirmed at `pred_rpart.c:30–31`). The compiler passes the extracted `int` values directly in registers; no pointer or SEXP crosses the function boundary.

  For `rpart_callback.c:54–55`, the results of `asInteger(ny)` and `asInteger(nr)` are stored in the static module-level `int` variables `ysave` and `rsave`. These persist across the `.Call` boundary for later use by the callback functions `rpart_callback1` and `rpart_callback2`. The storage into static ints is transparent to the fake — `asInteger` returns a plain `int` that C++ assigns to a static `int` variable with no type conversion needed.

  The original source files are not modified. The `#define asInteger Rf_asInteger` alias in `fake_Rinternals.hpp` ensures that every occurrence of `asInteger(...)` in the rpart source resolves to the fake inline function.

---

#### Pattern P2: Use `asInteger` Result Directly in a Comparison Expression

- **Locations:** `rpart.c:83`, `xpred.c:81`, `xpred.c:205`

- **Original R API Usage:**

```c
/* rpart.c:83-91 — asInteger used inline in if-condition and else-branch error */
if (asInteger(method2) <= NUM_METHODS) {
    i = asInteger(method2) - 1;
    rp_init   = func_table[i].init_split;
    rp_choose = func_table[i].choose_split;
    rp_eval   = func_table[i].eval;
    rp_error  = func_table[i].error;
    rp.num_y  = asInteger(ny2);
} else
    error(_("Invalid value for 'method'"));

/* xpred.c:81-89 — identical pattern */
if (asInteger(method2) <= NUM_METHODS) {
    i = asInteger(method2) - 1;
    /* ... function table lookups ... */
    rp.num_y = asInteger(ny2);
} else
    error(_("Invalid value for 'method'"));

/* xpred.c:205 — scalar boolean test */
if (asInteger(all2) == 1)
    nresp = rp.num_resp;
else
    nresp = 1;
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (asInteger — same definition as Pattern P1)
// The implementation is identical; the pattern here reflects inline usage
// in comparison expressions rather than assignment.

inline int Rf_asInteger(SEXP s) {
    if (s->type == REALSXP)
        return static_cast<int>(static_cast<double *>(s->data)[0]);
    return static_cast<int *>(s->data)[0];
}
#define asInteger Rf_asInteger

// The error() call in the else branch is a Category D item.
// It expands via Rinternals.h as: #define error Rf_error
// In the fake, Rf_error formats a message and throws RError (Invariant 1).
// The RError propagates through rpart() / xpred() to the .Call wrapper:

struct RError : public std::runtime_error {
    using std::runtime_error::runtime_error;
};

inline void Rf_error(const char *fmt, ...) {
    char buf[512];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    throw RError(buf);
}
#define error Rf_error

// .Call boundary wrapper for rpart — catches RError thrown by error()
// in the else branch of the method guard:
extern "C" SEXP rpart_entry(
        SEXP ncat2, SEXP method2, SEXP opt2,
        SEXP parms2, SEXP xvals2, SEXP xgrp2,
        SEXP ymat2, SEXP xmat2, SEXP wt2, SEXP ny2, SEXP cost2) {
    ArenaFrame _frame;   // frees R_alloc / ALLOC scratch on exit (Invariant 2)
    try {
        return rpart(ncat2, method2, opt2, parms2, xvals2, xgrp2,
                     ymat2, xmat2, wt2, ny2, cost2);
    } catch (const RError &e) {
        set_python_error(e.what());   // store message for Python to read
        return nullptr;
    }
}
```

Inside `rpart()`, the original lines compile unchanged:

```c
// rpart.c:83-84 — unchanged original source
if (asInteger(method2) <= NUM_METHODS) {
    i = asInteger(method2) - 1;
// asInteger(method2) expands to: Rf_asInteger(method2)
// which executes: static_cast<int *>(method2->data)[0]
// The result is compared to NUM_METHODS (an integer constant from rpart.h)
// and used as an array index after subtracting 1.
```

- **Arena / Memory Notes:** Not applicable. `asInteger` in this pattern only reads an existing SEXP's data field. No memory allocation occurs in the `asInteger` call itself. The `error()` call in the `else` branch does not allocate arena memory; it formats a string on the stack and throws `RError`.

- **Explanation:**

  `if (asInteger(method2) <= NUM_METHODS)` evaluates `Rf_asInteger(method2)` to obtain the method code as a plain `int`, then compares it to the compile-time constant `NUM_METHODS` (defined in `rpart.h`). If the condition is false, `error(_("Invalid value for 'method'"))` throws `RError` via the Category D fake (documented in the `error.md` guide). That exception propagates up through `rpart()` to the `.Call` wrapper's `catch (const RError &e)` block, which stores the message and returns a sentinel (`nullptr`) to Python. Python reads the stored error message and raises a Python exception.

  The double call `asInteger(method2)` on lines 83 and 84 of `rpart.c` reads `method2->data[0]` twice. This is safe and correct: the SEXP is an input parameter whose memory is owned by the Python caller and remains valid for the duration of the `.Call` invocation. The second call incurs only a trivial cast and dereference, consistent with how the real R runtime handles re-evaluation of `asInteger` on an already-coerced SEXP.

  For `xpred.c:205`, `if (asInteger(all2) == 1)` follows the same pattern: `all2` is a length-1 `INTSXP` parameter holding a boolean flag (0 or 1). `asInteger` returns the `int` value, the comparison `== 1` yields a C `bool`, and the branch selects `nresp = rp.num_resp` or `nresp = 1`. No side effects beyond the read.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` — `fake_Rinternals.hpp` | The `SEXPREC` struct with a `void *data` field and a `SEXPTYPE type` field. `Rf_asInteger` casts `s->data` to `int *` and reads element `[0]`; the `REALSXP` coercion branch reads `s->type`. The `SEXPREC` and `SEXP` typedef must appear before `Rf_asInteger` in the header. `SEXP.md` is the authoritative source for `fake_Rinternals.hpp`; `asInteger` resides in that same header. The SEXP.md guide already shows `asInteger` as a one-liner inline (Pattern P2 code block, line 444) — the present guide supersedes that with the full `Rf_asInteger` / `#define asInteger` form and the REALSXP coercion branch. |
| `INTSXP.md` | Establishes `#define INTSXP 13` and `#define REALSXP 14` in the `SEXPTYPE` constant block. The `Rf_asInteger` fake references `REALSXP` by name in the type-dispatch branch. |
| `error.md` — `RError` and `Rf_error` | The `RError : public std::runtime_error` exception class and the `Rf_error` / `#define error` fake. Required because `asInteger` is called immediately before `error(...)` in the `else` branches of the method guard at `rpart.c:91` and `xpred.c:89`. The `error()` call must be defined in the same header file or an included header. |
| `fake_arena.hpp` (no separate guide; generated as a foundation) | The `ArenaFrame` RAII struct and `gArenaStack`. Not used by `asInteger` directly, but required at the `.Call` wrapper level for `rpart()`, `xpred()`, `pred_rpart()`, and `init_rpcallback()`, all of which call `asInteger` and also call `ALLOC`/`R_alloc` in the same function body. |
| `INTEGER.md` | The `INTEGER` inline accessor. Used at the same call sites as `asInteger` in `pred_rpart.c:140`, `rpart.c:75–76`, and `xpred.c:69–70`. Both `INTEGER` and `asInteger` are defined together in `fake_Rinternals.hpp`; the `INTEGER.md` guide documents the `int *` accessor while this guide documents the scalar extractor. |
| `REAL.md` | The `REAL` inline accessor. Used alongside `asInteger` at `pred_rpart.c:140`, `xpred.c:72`, `xpred.c:94`. Both reside in `fake_Rinternals.hpp`. |
