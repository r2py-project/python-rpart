# Fake Header Implementation Guide: `REAL`

---

### 1. Overview of `REAL` in R API

`REAL` is a Category B accessor function declared in `Rinternals.h` as `double *(REAL)(SEXP x)`. Its sole purpose is to extract the raw `double *` data pointer from a `SEXP` object whose type tag is `REALSXP` (value `14`). It takes a single `SEXP` argument — an integer or real vector or matrix already allocated and populated — and returns a pointer to its contiguous `double` element buffer, giving the calling C code direct read/write access to the floating-point data without going through R's value-semantics layer. In R's real implementation the function body reaches into the internal `SEXPREC` structure via the ALTREP layer; in the fake runtime it casts `sexp->data` to `double *`. `REAL` is not an R Interpreter Item; it requires no running R interpreter and no function-pointer bridge.

---

### 2. Contextual Usage Analysis

**Source files examined.**

| File | Lines read | Key observations |
|---|---|---|
| `pred_rpart.c` | 125–147 | `REAL(split2)` and `REAL(xdata2)` are passed directly as `double *` arguments to `pred_rpart0` on line 140–143; no intermediate variables |
| `rpart.c` | 63–142 | `REAL` applied to five distinct input-parameter SEXPs: `wt2`, `parms2`, `opt2`, `cost2`, `xmat2`, `ymat2`; results assigned to local `double *` or struct fields |
| `rpart.c` | 235–277 | `REAL` applied immediately after `allocMatrix(REALSXP, ...)` to obtain the writable `double *` for `cptable3`, `dnode3`, `dsplit3` |
| `rpart_callback.c` | 45–120 | `REAL` applied to SEXPs obtained via `R_getVar` (`stemp` for `ydata`, `wdata`, `xdata`) and to `value` returned by `eval(expr2, rho)` |
| `rpart_callback.c` | 125–160 | `REAL` applied to `goodness`, the SEXP returned by `eval(expr1, rho)` |
| `rpartexp2.c` | 38–51 | `REAL(dtimes)` passed directly as a `double *` argument to `Rpartexp2` on line 48; `dtimes` is an input parameter SEXP |
| `xpred.c` | 60–134 | `REAL` applied to six input-parameter SEXPs: `wt2`, `parms2`, `cp2`, `opt2`, `cost2`, `xmat2`, `ymat2`; results assigned to local `double *` or struct fields |
| `xpred.c` | 195–218 | `REAL` applied immediately after `allocVector(REALSXP, n*ncp*nresp)` to obtain the writable `double *` for `predict2` |

**Argument and return types observed across all rows.**

`REAL` always takes a single `SEXP` argument and always returns `double *`. The receiving variable is one of:

- `double *wt`, `double *parms`, `double *dptr`, `double *cp`, `double *predict` — local pointer variables in `rpart()`, `xpred()`, and `xpred_callback`-related functions, assigned from SEXP input parameters or freshly allocated SEXPs.
- `rp.vcost` — a `double *` struct field inside the global `rp` struct (`rpart.c:115`, `xpred.c:113`).
- `double *ydata`, `double *wdata`, `double *xdata`, `double *dptr` — static module-level pointers in `rpart_callback.c` set from SEXPs obtained via `R_getVar`.
- A `double *` passed directly as a function argument without an intermediate variable (`pred_rpart.c:140–142`, `rpartexp2.c:48`, `rpart_callback.c:117`, `rpart_callback.c:150`).

**Co-occurring R API items in context windows.**

- `allocVector(REALSXP, n)` and `allocMatrix(REALSXP, nrow, ncol)` — for several occurrences (`rpart.c:243`, `rpart.c:263`, `rpart.c:270`, `xpred.c:210`) the SEXP passed to `REAL` was just produced by one of these allocators. For input parameters the SEXP was constructed by the Python-side caller.
- `PROTECT` / `UNPROTECT` — every freshly allocated SEXP is wrapped in `PROTECT` before `REAL` is applied to it. In the fake runtime `PROTECT` is a no-op identity, so this wrapping is transparent.
- `INTEGER(sexp)` — appears at the same call sites, accessing `int *` data from `INTSXP` SEXPs in the same function bodies (`pred_rpart.c:140–144`, `rpart.c:75–76`, `rpartexp2.c:48`, `xpred.c:69–70`).
- `asReal(sexp)` — used at nearby lines to extract a single `double` scalar from a length-1 SEXP; different from `REAL` in that it returns a scalar, not a pointer.
- `R_getVar(install(...), rho, FALSE)` — in `rpart_callback.c:59–66`, the SEXPs passed to `REAL` for `ydata`, `wdata`, and `xdata` come from `R_getVar` (Category E). The `REAL` call itself is mechanically identical to other patterns.
- `eval(expr2, rho)` and `eval(expr1, rho)` — in `rpart_callback.c:112–117` and `rpart_callback.c:146–150`, the SEXPs passed to `REAL` are return values of `eval` (Category E). Again, `REAL` itself is unchanged.
- `ALLOC` / `R_alloc` — used in the same function bodies for scratch arrays (arena-managed), independent of `REAL`.
- `nrows(xmat2)` / `ncols(xmat2)` — used immediately before `REAL(xmat2)` in `rpart.c:108–122` and `xpred.c:106–121` to read matrix dimensions.

**Distinct usage patterns.**

Four structural patterns appear across the 24 CSV rows:

| Pattern | CSV rows | Description |
|---|---|---|
| P1: Assign `double *` from an input SEXP parameter | `rpart.c:78,79,96,115,122,130`; `xpred.c:72,73,75,94,113,121,129` | `REAL` applied to a SEXP received as a `.Call` parameter; the result is stored in a local `double *` variable or struct field for later use in the function body. |
| P2: Assign `double *` from a freshly allocated SEXP, or pass as a direct function argument from an input SEXP | `rpart.c:243,263,270`; `xpred.c:210`; `pred_rpart.c:140`; `rpartexp2.c:48` | `REAL` applied either to a SEXP just created by `allocMatrix(REALSXP, ...)` or `allocVector(REALSXP, ...)`, or to an input SEXP passed directly as a function argument without an intermediate variable. |
| P3: Assign static module-level `double *` from a SEXP obtained via `R_getVar` | `rpart_callback.c:60,63,66` | `REAL` applied to `stemp`, which holds the result of `R_getVar(install("yback"/"wback"/"xback"), rho, FALSE)`. The result is stored in the static globals `ydata`, `wdata`, `xdata`. |
| P4: Assign `double *` from a SEXP returned by `eval()` | `rpart_callback.c:117,150` | `REAL` applied to `value` (from `eval(expr2, rho)`) and `goodness` (from `eval(expr1, rho)`). |

Patterns P1, P2, P3, and P4 share the identical fake `REAL` implementation — all four resolve to `static_cast<double *>(s->data)`. The structural distinction between patterns matters only at the level of how the source SEXP was produced: patterns P3 and P4 depend on Category E items (`R_getVar`, `eval`) that require function-pointer bridges, while P1 and P2 are fully available without any interpreter.

---

### 3. Fake C++ Implementation Strategy

**Category: B — Accessor Macro or Inline Function.**

`REAL` is declared in `Rinternals.h` at line 288 as `double *(REAL)(SEXP x)`. The parentheses around the function name are a C technique that forces the compiler to treat the declaration as a true function even when a macro of the same name is in scope. In modern R, `USE_RINTERNALS`-gated `#define` aliases expand `REAL(x)` to a direct ALTREP-layer access. Since rpart does not define `USE_RINTERNALS`, none of those gated expansions are active; the function declaration at line 288 is what the compiler resolves.

**Chosen mechanism.**

The fake implements `REAL` as a C++ `inline` function:

```cpp
inline double *REAL(SEXP s) {
    return static_cast<double *>(s->data);
}
```

This is correct because the `SEXPREC` fake (from `SEXP.md`) stores the element buffer in `s->data` as a `void *`. When `allocVector(REALSXP, n)` or `allocMatrix(REALSXP, ...)` creates the SEXP, it heap-allocates `double[length]` and stores the pointer in `s->data`. `REAL` simply casts that `void *` back to `double *`. The `static_cast` is safe because `sexptype_element_size(REALSXP)` returns `sizeof(double)` in the allocator, guaranteeing the buffer was allocated at double granularity.

For input-parameter SEXPs constructed by the Python-side caller before the `.Call` boundary, Python must place a `double *`-compatible buffer in `sexp->data` (e.g., a numpy float64 array cast to a pointer).

**`#define` aliases that must be preserved.**

The real `Rinternals.h` does not define a macro alias `#define REAL(x) ...` in the non-`USE_RINTERNALS` build path — the parenthesised function declaration prevents the compiler from treating it as a macro. Therefore no `#define` alias is required in the fake header for `REAL` itself. The companion read-only accessor `REAL_RO` (declared at line 293 of `Rinternals.h` as `const double *(REAL_RO)(SEXP x)`) is not used by rpart source files but must be provided for completeness:

```cpp
inline const double *REAL_RO(SEXP s) {
    return static_cast<const double *>(s->data);
}
```

**Invariant applicability.**

- Invariant 1 (C++ error/warning): not triggered by `REAL` itself. The function performs a pointer cast and cannot fail. The functions that produce the SEXP argument (`allocVector`, `allocMatrix`, `R_getVar`, `eval`) may throw `RError`, but `REAL` is called only after they return successfully.
- Invariant 2 (arena memory): not triggered by `REAL`. The function reads `s->data`, which points to heap memory (for SEXPs from `allocVector`/`allocMatrix`) or to Python-managed memory (for input-parameter SEXPs). The arena exclusively governs `R_alloc`/`ALLOC` scratch allocations that appear in the same function bodies but are entirely independent of `REAL`.
- Invariant 3 (R Interpreter Items): not applicable. `REAL` itself does not invoke the interpreter. The occurrences in Patterns P3 and P4 where the source SEXP came from `R_getVar` or `eval` do not affect the `REAL` implementation — `REAL` merely receives a valid `SEXP` pointer and extracts its `data` field.

---

### 4. Fake Implementation Examples

#### Pattern P1: Assign `double *` from an Input SEXP Parameter

- **Locations:** `rpart.c:78`, `rpart.c:79`, `rpart.c:96`, `rpart.c:115`, `rpart.c:122`, `rpart.c:130`, `xpred.c:72`, `xpred.c:73`, `xpred.c:75`, `xpred.c:94`, `xpred.c:113`, `xpred.c:121`, `xpred.c:129`

- **Original R API Usage:**

```c
/* rpart.c:78-79 — input parameters, assigned to local double * variables */
wt    = REAL(wt2);
parms = REAL(parms2);

/* rpart.c:96 — options vector; elements read by index immediately after */
dptr = REAL(opt2);
rp.min_node  = (int) dptr[1];
rp.min_split = (int) dptr[0];
rp.complexity = dptr[2];

/* rpart.c:115 — assigned to a double * struct field */
rp.vcost = REAL(cost2);

/* rpart.c:122 — xmat2 is a column-major REALSXP matrix; dptr strides columns */
dptr = REAL(xmat2);
rp.xdata = (double **) ALLOC(rp.nvar, sizeof(double *));
for (i = 0; i < rp.nvar; i++) {
    rp.xdata[i] = dptr;
    dptr += n;
}

/* rpart.c:130 — ymat2 is a row-major REALSXP matrix */
dptr = REAL(ymat2);
for (i = 0; i < n; i++) {
    rp.ydata[i] = dptr;
    dptr += rp.num_y;
}

/* xpred.c:75 — cp is a 1-D REALSXP parameter; elements read by index */
cp = REAL(cp2);
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp  (excerpt — REAL accessor, Category B)
// Must appear after the SEXPREC struct and SEXP typedef from SEXP.md.

#pragma once
#ifndef FAKE_RINTERNALS_H
#define FAKE_RINTERNALS_H

// ... (SEXPREC, SEXP, SEXPTYPE block, allocVector, PROTECT/UNPROTECT,
//      RError, INTEGER, asReal, and all other items from SEXP.md) ...

// -------------------------------------------------------------------------
// REAL — returns the double * data pointer of a REALSXP SEXP.
//
// Corresponds to the Rinternals.h declaration:
//   double *(REAL)(SEXP x);
//
// The fake casts s->data (void *) to double *.
// This is safe because:
//   - allocVector(REALSXP, n) and allocMatrix(REALSXP, nrow, ncol) allocate
//     double[n] (or double[nrow*ncol]) into s->data.
//   - Python-side SEXP construction for input parameters must likewise set
//     s->data to point to a double[n] buffer (e.g., a numpy float64 array).
// -------------------------------------------------------------------------
inline double *REAL(SEXP s) {
    return static_cast<double *>(s->data);
}

// Read-only variant (not used by rpart source, but present in Rinternals.h).
inline const double *REAL_RO(SEXP s) {
    return static_cast<const double *>(s->data);
}

#endif // FAKE_RINTERNALS_H
```

The `.Call` entry-point wrapper for `rpart()` shows that `REAL` itself needs no special guard — the `ArenaFrame` is required because `rpart()` also calls `ALLOC`/`R_alloc`, not because of `REAL`:

```cpp
// Entry-point wrapper for rpart (illustrative; REAL is called inside the body).
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

Inside `rpart()` the original lines compile unchanged:

```c
// rpart.c:78-79 — unchanged original source
wt    = REAL(wt2);    // resolves to: wt    = static_cast<double *>(wt2->data);
parms = REAL(parms2); // resolves to: parms = static_cast<double *>(parms2->data);
```

- **Arena / Memory Notes:** Not applicable for P1. `REAL` performs a cast and allocates nothing. The `double *` pointers returned by `REAL(wt2)`, `REAL(parms2)`, etc. point into Python-owned buffers that are passed into the `.Call` boundary as pre-constructed `SEXPREC` nodes. No arena interaction occurs. The arena exclusively governs `R_alloc`/`ALLOC` scratch arrays allocated later in the same function body (e.g., `rp.xdata` at `rpart.c:123`, `rp.ydata` at `rpart.c:128`).

- **Explanation:**

  `REAL(wt2)` resolves to `static_cast<double *>(wt2->data)`. The `wt2` SEXP was constructed by the Python-side caller before the `.Call` boundary: Python allocates a `SEXPREC` node with `type=REALSXP`, `length=n`, and `data` pointing to a contiguous `double[n]` buffer (e.g., a numpy float64 array or a `ctypes` c_double array). After the call, `wt` is a bare `double *` pointing into that buffer; no SEXP bookkeeping remains within the C code.

  For `rp.vcost = REAL(cost2)` at `rpart.c:115` (and `xpred.c:113`), the result is stored directly in a `double *` field of the global `rp` struct. Since `rp` is module-level, the pointer remains valid for the duration of the function invocation. The original source file is not modified.

  For `dptr = REAL(xmat2)` at `rpart.c:122`, the `xmat2` SEXP is a column-major real matrix. `REAL` extracts the flat `double *` buffer; the subsequent loop advances `dptr` by `n` (the number of rows) per iteration to build `rp.xdata`, a ragged-array pointer into the matrix columns. This pointer arithmetic is valid because `allocMatrix(REALSXP, n, rp.nvar)` (or the Python-side equivalent) allocates a flat `double[n * rp.nvar]` buffer in column-major order.

---

#### Pattern P2: Assign `double *` from a Freshly Allocated SEXP, or Pass as Direct Function Argument

- **Locations:** `rpart.c:243`, `rpart.c:263`, `rpart.c:270`, `xpred.c:210`, `pred_rpart.c:140`, `rpartexp2.c:48`

- **Original R API Usage:**

```c
/* rpart.c:241-250 — allocMatrix then REAL for the cptable output matrix */
cptable3 = PROTECT(allocMatrix(REALSXP, xvals > 1 ? 5 : 3, rp.num_unique_cp));
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

/* rpart.c:261-267 — allocMatrix then REAL for the dnode output matrix */
dnode3 = PROTECT(allocMatrix(REALSXP, nodecount, (3 + rp.num_resp)));
ddnode = (double **) ALLOC(3 + rp.num_resp, sizeof(double *));
dptr = REAL(dnode3);
for (i = 0; i < 3 + rp.num_resp; i++) {
    ddnode[i] = dptr;
    dptr += nodecount;   /* column-major stride */
}

/* rpart.c:269-276 — allocMatrix then REAL for the dsplit output matrix */
dsplit3 = PROTECT(allocMatrix(REALSXP, splitcount, 3));
dptr = REAL(dsplit3);
for (i = 0; i < 3; i++) {
    ddsplit[i] = dptr;
    dptr += splitcount;
    for (j = 0; j < splitcount; j++)
        ddsplit[i][j] = 0.0;
}

/* xpred.c:209-210 — allocVector then REAL for the prediction output vector */
predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp));
predict = REAL(predict2);

/* pred_rpart.c:140-143 — REAL applied to input SEXPs, results passed directly */
pred_rpart0(INTEGER(dimx), asInteger(nnode), asInteger(nsplit),
            INTEGER(dimc), INTEGER(nnum), INTEGER(nodes2),
            INTEGER(vnum), REAL(split2), INTEGER(csplit2),
            INTEGER(usesur), REAL(xdata2), INTEGER(xmiss2),
            INTEGER(where));

/* rpartexp2.c:48 — REAL applied to input SEXP dtimes, passed directly */
Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
```

- **C++ Fake Implementation:**

```cpp
// fake_Rinternals.hpp (REAL — same definition as in Pattern P1)
// The implementation does not change; the pattern here is about usage context.

inline double *REAL(SEXP s) {
    return static_cast<double *>(s->data);
}

// For completeness, the allocVector / allocMatrix fakes that produce the
// SEXPs consumed by REAL in this pattern (from SEXP.md / REALSXP.md):

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

  The SEXP nodes produced by `allocMatrix(REALSXP, ...)` and `allocVector(REALSXP, ...)` are **heap-allocated** via `std::malloc` — they are not arena-managed. The `double` data buffers pointed to by `REAL(sexp)` are likewise heap-allocated as part of each SEXP. They must survive the `.Call` function frame because several of them — `cptable3`, `dnode3`, `dsplit3` in `rpart()`, and `predict2` in `xpred()` — are components of the return value handed back to Python via the output list SEXP.

  In the allocation-then-REAL pattern (e.g., `rpart.c:261–267`), the `ArenaFrame` in the `.Call` wrapper frees only memory allocated via `R_alloc`/`ALLOC`. The `ddnode` scratch pointer array at `rpart.c:262` is arena-allocated (`ALLOC(3 + rp.num_resp, sizeof(double *))`); these arena pointers point into the heap-allocated `dnode3` buffer. After `ArenaFrame` destruction, the arena pointers are freed but the `dnode3` buffer (and its containing SEXP) remain intact on the heap.

  For `pred_rpart.c:140–143` and `rpartexp2.c:48`, the `REAL(split2)`, `REAL(xdata2)`, and `REAL(dtimes)` calls are applied to input-parameter SEXPs (constructed by Python before the `.Call` boundary). No allocation occurs; `REAL` merely extracts the `double *` pointer from the pre-existing buffer and passes it directly to the C function. If `allocVector` or `allocMatrix` fails earlier in the same function body, `RError` is thrown before `REAL` is reached; the `.Call` wrapper catches it.

- **Explanation:**

  For `rpart.c:243`, `PROTECT(allocMatrix(REALSXP, nrow, ncol))` expands to `Rf_protect(allocMatrix(REALSXP, nrow, ncol))`, which is the identity function in the fake. So `cptable3 = PROTECT(allocMatrix(...))` is equivalent to `cptable3 = allocMatrix(...)`. The returned `SEXPREC` has `type=REALSXP`, `nrow=nrow`, `ncol=ncol`, `length=nrow*ncol`, and `data` pointing to a zero-initialized `double[nrow*ncol]` buffer. `dptr = REAL(cptable3)` then extracts that `double *` and the loop populates it in column-major order.

  For `pred_rpart.c:140–143`, the two `REAL(split2)` and `REAL(xdata2)` calls appear as direct function arguments evaluated by the compiler as `static_cast<double *>(split2->data)` and `static_cast<double *>(xdata2->data)` respectively. The calling convention is identical to assigning to a named `double *` variable first.

  For `rpartexp2.c:48`, `REAL(dtimes)` passes the `double *` buffer of the input SEXP `dtimes` directly to `Rpartexp2`, which reads from it. No SEXP is allocated here; `dtimes` was constructed by Python before the call boundary.

---

#### Pattern P3: Assign Static Module-Level `double *` from a SEXP Obtained via `R_getVar`

- **Locations:** `rpart_callback.c:60`, `rpart_callback.c:63`, `rpart_callback.c:66`

- **Original R API Usage:**

```c
/* rpart_callback.c:59-66 — in init_rpcallback */
stemp = R_getVar(install("yback"), rho, FALSE);
ydata = REAL(stemp);

stemp = R_getVar(install("wback"), rho, FALSE);
wdata = REAL(stemp);

stemp = R_getVar(install("xback"), rho, FALSE);
xdata = REAL(stemp);
```

`stemp` is a local `SEXP` variable declared at line 51. `R_getVar` retrieves the `SEXP` bound to each symbol in the evaluation environment `rho`. `ydata`, `wdata`, and `xdata` are the static `double *` globals declared at approximately lines 38–40 of `rpart_callback.c`. They are subsequently used in `rpart_callback1` and `rpart_callback2` to copy observation data into R's evaluation frame for user-defined split functions.

- **C++ Fake Implementation:**

```cpp
// rpart_callback.c compiles without modification using fake_Rinternals.hpp.
// The REAL calls on lines 60, 63, and 66 are mechanically identical to
// Pattern P1: static_cast<double *>(stemp->data).
//
// The only distinction is that 'stemp' was produced by R_getVar (a Category E
// item), not by allocVector or a .Call parameter.  REAL itself has no
// awareness of this distinction — it simply casts s->data to double *.
//
// The REAL implementation remains:
inline double *REAL(SEXP s) {
    return static_cast<double *>(s->data);
}
//
// At runtime, this code path is reachable only when:
//   1. init_rpcallback() has been called (registering rho and the expressions).
//   2. The R_getVar function-pointer bridge has been registered via
//      register_R_getVar_fn() (see the R_getVar / findVar fake guide).
//   3. rpart() is subsequently called with method=4 (user-defined splits),
//      which causes the callback infrastructure to be invoked.
//
// If R_getVar returns a valid SEXP whose data holds double[n] (i.e., the Python
// callback returns a correctly constructed SEXPREC for the given symbol),
// then REAL(stemp) = static_cast<double *>(stemp->data) is correct and safe.
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

- **Arena / Memory Notes:** Not applicable. `REAL` performs a cast only. The `double *` results are stored in static module-level globals (`ydata`, `wdata`, `xdata`). These globals point into SEXP data buffers whose lifetime is managed by the Python-side caller (via the `R_getVar` function-pointer bridge). No arena interaction occurs.

- **Python Interop Notes:**

  This pattern is only reachable when the user-defined splitting method (`method=4`) is active. All standard rpart methods (anova, poisson, class, exp) never call `init_rpcallback` and therefore never execute lines 59–66 of `rpart_callback.c`.

  For user-defined splits, the Python side must:
  1. Register the `R_getVar` function-pointer bridge via `register_R_getVar_fn()` (see the `R_getVar`/`findVar` fake guide).
  2. Call `init_rpcallback` (via its `.Call` entry point) with an `rho` SEXP that acts as an environment mapping symbol names (`"yback"`, `"wback"`, `"xback"`, `"nback"`) to pre-allocated SEXP objects backed by `double[]` and `int[]` buffers.
  3. The Python-side `R_getVar` callback receives the symbol name and returns the appropriate SEXP, whose `data` field must point to a live Python-owned buffer that remains pinned until `rpart()` returns.

  The fake `REAL` call extracts the `double *` from that SEXP and stores it in the static global — from that point on the C code uses the pointer directly without going through SEXP again.

- **Explanation:**

  The `REAL` fake is unchanged from Patterns P1 and P2. The source SEXP `stemp` is produced by `R_getVar`, which in the fake runtime is implemented as a function-pointer stub (Category E, documented in the `R_getVar`/`findVar` fake guide). When that stub is registered and returns a correctly formed SEXP, `REAL(stemp)` casts `stemp->data` to `double *` and stores it in `ydata`/`wdata`/`xdata`. The original source lines 60, 63, and 66 compile and execute correctly with no modification.

---

#### Pattern P4: Assign `double *` from a SEXP Returned by `eval()`

- **Locations:** `rpart_callback.c:117`, `rpart_callback.c:150`

- **Original R API Usage:**

```c
/* rpart_callback.c:112-119 — in rpart_callback1 */
value = eval(expr2, rho);
if (!isReal(value))
    error(_("return value not a vector"));
if (LENGTH(value) != (1 + rsave))
    error(_("returned value is the wrong length"));
dptr = REAL(value);
for (i = 0; i <= rsave; i++)
    z[i] = dptr[i];

/* rpart_callback.c:146-156 — in rpart_callback2 */
goodness = eval(expr1, rho);
if (!isReal(goodness))
    error(_("the expression expr1 did not return a vector!"));
j = LENGTH(goodness);
dptr = REAL(goodness);
```

`value` and `goodness` are local `SEXP` variables declared at `rpart_callback.c:92` and `rpart_callback.c:131`. They receive the return values of `eval(expr2, rho)` and `eval(expr1, rho)` respectively. `dptr` is a local `double *` that reads the result data element-by-element into the output arrays `z` and `good`.

- **C++ Fake Implementation:**

```cpp
// The SEXP declarations (SEXP value; SEXP goodness;) compile correctly with
// fake_Rinternals.hpp — they declare SEXPREC* local variables.
//
// The REAL calls on lines 117 and 150 use the same implementation:
inline double *REAL(SEXP s) {
    return static_cast<double *>(s->data);
}
//
// The runtime paths through eval() require the Category E function-pointer
// bridge.  The fake eval stub (from the 'eval' guide) is:
//
//   typedef SEXP (*eval_fn_t)(SEXP expr, SEXP rho);
//   static eval_fn_t g_eval_fn = nullptr;
//
//   extern "C" void register_eval_fn(eval_fn_t fn) { g_eval_fn = fn; }
//
//   inline SEXP eval(SEXP expr, SEXP rho) {
//       if (!g_eval_fn)
//           throw RError("eval: Python callback not registered. "
//                        "User-defined splits (method=4) require "
//                        "registration via register_eval_fn().");
//       return g_eval_fn(expr, rho);
//   }
//   #define Rf_eval eval
//
// When the Python-side eval callback is registered and invoked, it must
// return a SEXP with:
//   - type == REALSXP
//   - length == (1 + rsave) for the eval(expr2, rho) case
//   - data pointing to a double[(1 + rsave)] buffer
// so that REAL(value) returns a valid double * and the isReal(value) check
// passes.
//
// For the eval(expr1, rho) case in rpart_callback2, the returned SEXP must
// have type == REALSXP and length == 2*(n-1) (for continuous splits) or
// 2*n (for categorical splits), as verified by the length checks that follow.
//
// The isReal(), LENGTH(), and error() functions used alongside REAL in this
// pattern are all defined in fake_Rinternals.hpp / fake_Error.hpp:
//   inline int isReal(SEXP s) { return s->type == REALSXP; }
//   inline int LENGTH(SEXP s) { return s->length; }
//   // error() -> Rf_error() -> throw RError(msg);
```

- **Python Interop Notes:**

  Lines 117 and 150 of `rpart_callback.c` are only reachable during user-defined split evaluation (`method=4`). For all standard rpart methods, `rpart_callback1` and `rpart_callback2` are never called through the C API, so these lines are dead code.

  For user-defined splits, Python must:
  1. Register the `eval` function-pointer bridge via `register_eval_fn()` (see the `eval` fake guide).
  2. Implement the Python callback to accept `(expr_sexp, rho_sexp)` and return a `SEXP` backed by a `double[]` buffer of the expected length.
  3. The SEXP returned must have `type=REALSXP` and `data` pointing to a `ctypes` or numpy-backed `double` array that remains live until `rpart_callback1` or `rpart_callback2` returns.

  The `REAL` call on the returned SEXP extracts the `double *` immediately. The downstream indexing `z[i] = dptr[i]` copies the values into C arrays before the Python callback's SEXP is discarded, so the buffer lifetime requirement is short (the duration of one callback invocation).

- **Arena / Memory Notes:** Not applicable. `REAL` performs a cast only. The SEXP returned by `eval()` is produced by the Python-side callback; its `data` buffer lifetime is managed by the Python caller. No arena interaction occurs.

- **Explanation:**

  `REAL(value)` at line 117 resolves to `static_cast<double *>(value->data)`. The source SEXP `value` was returned by the Python-side `eval` callback, which must construct it as a `SEXPREC` with `type=REALSXP` and a live `double *` in `data`. The `isReal(value)` guard before `REAL(value)` checks `value->type == REALSXP` and throws `RError` (via `error()`) if the type is wrong; `LENGTH(value)` checks `value->length`. Both are inline functions from `fake_Rinternals.hpp` that operate on the same `SEXPREC` fields. No modification to the original source is required.

---

### 5. Integration Requirements

| Dependency | Specific definition needed |
|---|---|
| `SEXP.md` — `fake_Rinternals.hpp` | The `SEXPREC` struct with `void *data`, `SEXPTYPE type`, and `int length` fields. `REAL` casts `s->data` to `double *`; the struct definition must precede the `REAL` inline function in the header. `SEXP.md` is the authoritative source for the complete `fake_Rinternals.hpp` in which `REAL` resides alongside `INTEGER`, `PROTECT`, `allocVector`, `allocMatrix`, and all other `Rinternals.h` items. |
| `REALSXP.md` | Establishes `#define REALSXP 14` in the `SEXPTYPE` constant block. This tag is set by `allocVector(REALSXP, n)` and `allocMatrix(REALSXP, ...)` when constructing the SEXPs whose `data` buffers `REAL` later reads. Although `REAL` itself does not reference `REALSXP` numerically, correct program behavior requires that the SEXPs passed to `REAL` were allocated with `REALSXP` so that their `data` buffers hold `double` elements. |
| `fake_arena.hpp` (no separate guide; generated as a foundation) | The `ArenaFrame` RAII struct, `gArenaStack` thread-local vector, `arena_alloc`, and `arena_calloc`. Required at the `.Call` wrapper layer for all functions (`rpart`, `xpred`, `pred_rpart`, `rpartexp2`, `init_rpcallback`) that call both `REAL` and `R_alloc`/`ALLOC` in the same body. `REAL` itself does not use the arena; the dependency is at the enclosing function level. |
| `INTEGER.md` | Establishes `inline int *INTEGER(SEXP s)` in `fake_Rinternals.hpp`. `REAL` and `INTEGER` always appear together in the same call sites (`pred_rpart.c:140–143`, `rpartexp2.c:48`, `rpart.c:75–76`, `xpred.c:69–70`). Both reside in `fake_Rinternals.hpp` and share the same `SEXPREC->data` cast pattern; consistency between their implementations is required. |
| `error.md` — `RError` definition | `struct RError : public std::runtime_error`. Used by `allocVector`/`allocMatrix` to signal allocation failure, and used by `error()` within `rpart_callback.c` when `isReal(value)` fails. `RError` must be defined in the header before `allocVector` and before the `Rf_error`/`error` function fake. |
| `PROTECT.md` | Establishes `inline SEXP Rf_protect(SEXP s) { return s; }` and `#define PROTECT(s) Rf_protect(s)`. Every freshly allocated SEXP passed to `REAL` in Pattern P2 is wrapped in `PROTECT` first; the no-op fake must be present for the surrounding expressions to compile. |
| `R_getVar` / `findVar` fake guide (Category E, not yet generated) | Required at runtime for `rpart_callback.c:59–66` (Pattern P3). `REAL` compiles without it; the runtime path is only reachable after the `R_getVar` function-pointer bridge is registered. |
| `eval` fake guide (Category E, not yet generated) | Required at runtime for `rpart_callback.c:112–117` and `rpart_callback.c:146–150` (Pattern P4). `REAL` compiles without it; the runtime path is only reachable after the `eval` function-pointer bridge is registered. Both P3 and P4 are exclusively exercised by `method=4` (user-defined splits). |
