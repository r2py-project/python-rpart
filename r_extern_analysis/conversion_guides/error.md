# Conversion Guide: `error`

---

## 1. Overview of `error` in R API

`error` is a macro defined in `R_ext/Error.h` as `#define error Rf_error`, where `Rf_error` has the signature `NORET void Rf_error(const char *fmt, ...)`. It accepts a `printf`-style format string followed by variadic arguments, formats the message, and immediately raises an R-level error by performing a `longjmp` back to R's top-level error handler — the function is annotated `[[noreturn]]`/`_Noreturn`/`__attribute__((noreturn))` and never returns to its call site. In the `.Call/.External` API this mechanism is the standard way to abort a C routine with a user-visible error message; in code targeting the `.C/.Fortran` API the same `Rf_error` call is still legal and is in fact the recommended pattern, because `.C` provides no alternative error-return channel through its argument list.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rpart.c` | 91 | `error(_("Invalid value for 'method'"));` |
| `rpart.c` | 203 | `error("%s", errmsg);` |
| `rpart_callback.c` | 24 | `error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));` |
| `rpart_callback.c` | 114 | `error(_("return value not a vector"));` |
| `rpart_callback.c` | 116 | `error(_("returned value is the wrong length"));` |
| `rpart_callback.c` | 148 | `error(_("the expression expr1 did not return a vector!"));` |
| `xpred.c` | 89 | `error(_("Invalid value for 'method'"));` |

### Data types and surrounding context

**`rpart.c` line 91 / `xpred.c` line 89 — guard on `method` integer argument.**
Both sites sit inside an `else` branch that is reached when `asInteger(method2)` exceeds `NUM_METHODS`:

```c
if (asInteger(method2) <= NUM_METHODS) {
    i = asInteger(method2) - 1;
    rp_init   = func_table[i].init_split;
    rp_choose = func_table[i].choose_split;
    rp_eval   = func_table[i].eval;
    rp_error  = func_table[i].error;
    rp.num_y  = asInteger(ny2);
} else
    error(_("Invalid value for 'method'"));
```

No format arguments; the call takes only a translated literal string produced by the `_()` NLS macro (defined in `rpart.h` as `dgettext("rpart", String)` when `ENABLE_NLS` is set, or the identity macro otherwise). No SEXP types or memory allocation are involved.

**`rpart.c` line 203 — propagation of a C-string error message from a callback.**
The `rp_init` function pointer (typed `int (*)(int, double **, int, char **, double *, int *, int, double *)`) fills the `char **errmsg` out-parameter with a plain `const char *` when it detects a problem and returns a positive integer:

```c
char *errmsg;
/* ... */
errmsg = _("unknown error");
/* ... */
i = (*rp_init)(n, rp.ydata, maxcat, &errmsg, parms, &rp.num_resp, 1, wt);
if (i > 0)
    error("%s", errmsg);
```

`errmsg` is a `char *` pointing to a string literal; passing it through `"%s"` rather than directly as the format string avoids a `-Wformat-security` warning. No SEXP types involved.

**`rpart_callback.c` line 24 — variable-not-found guard inside a compatibility shim.**
This is inside a `static` helper `compat_getVar` that is compiled only for R < 4.5.0:

```c
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
    SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
    if (val == R_UnboundValue)
        error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
    return val;
}
```

`CHAR(PRINTNAME(sym))` extracts the name string of the symbol `sym` as a `const char *`. This function is part of the R-session callback machinery that evaluates user-defined split expressions; it is not called from the main `.C`-entry-point code path.

**`rpart_callback.c` lines 114 and 116 — type and length guards on eval() result.**
These sit inside `rpart_callback1`, which is invoked as a function pointer from the main rpart C loop (not via `.Call` or `.C` directly):

```c
value = eval(expr2, rho);
if (!isReal(value))
    error(_("return value not a vector"));
if (LENGTH(value) != (1 + rsave))
    error(_("returned value is the wrong length"));
```

Both calls take only a translated literal string; no format arguments.

**`rpart_callback.c` line 148 — type guard on split-expression eval() result.**
Inside `rpart_callback2`, also invoked as a function pointer:

```c
goodness = eval(expr1, rho);
if (!isReal(goodness))
    error(_("the expression expr1 did not return a vector!"));
```

Again a literal-only call with no format arguments.

### Distinct usage patterns

1. **Literal-only error with NLS translation** — `error(_("…"))` with no format arguments. Found at `rpart.c` line 91, `rpart_callback.c` lines 114, 116, 148, and `xpred.c` line 89.
2. **`%s`-forwarding of a C-string error message** — `error("%s", errmsg)` where `errmsg` is a `char *` set by a callback. Found at `rpart.c` line 203.
3. **Formatted error with a runtime string argument** — `error(_("… '%s' …"), CHAR(PRINTNAME(sym)))` inside a SEXP-aware helper function. Found at `rpart_callback.c` line 24.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Unlike `allocVector`, `PROTECT`, or `SEXP` accessor macros, `error` (`Rf_error`) is **not an item that must be removed** when migrating from `.Call` to `.C`. The `.C` API imposes no restriction on calling `Rf_error` from within C code — it is a plain variadic function that takes only a `const char *` format string and basic C scalar arguments. It performs a `longjmp` back to R's error handler, which is the correct and documented mechanism for aborting a `.C` call with a user-visible message.

The key architectural points are:

1. **Retain `error()`/`Rf_error()` unchanged.** It is fully legal and correct in `.C`-called C code. No substitution with `return`, `exit()`, or `fprintf(stderr, …)` is needed or appropriate.

2. **Remove only the SEXP dependencies in the surrounding guard code.** At `rpart.c` lines 83–91 and `xpred.c` lines 81–89, the guard condition calls `asInteger(method2)` where `method2` is a `SEXP`. In a `.C` rewrite, the integer value arrives directly as `const int *method`, so `asInteger(method2)` becomes `*method` and the `error()` call itself is unchanged.

3. **The `_()` NLS macro is unrelated to the SEXP API and is retained as-is.** It expands to either `dgettext("rpart", string)` or the identity, neither of which involves R objects.

4. **`char *errmsg` propagation (pattern 2) requires no changes.** The `errmsg` variable is already a plain `char *`; the `error("%s", errmsg)` call is SEXP-free and needs no modification.

5. **Pattern 3 (`CHAR(PRINTNAME(sym))`) remains SEXP-dependent.** This pattern lives inside `compat_getVar`, which is itself a SEXP-typed helper that cannot be called from a pure `.C` path. If the user-split callback machinery is ever ported to `.C`, `CHAR(PRINTNAME(sym))` would need to be replaced by a pre-computed `const char *` name string passed as a function argument. The `error(…)` call itself still does not change.

### Why `error` is compatible with `.C` without modification

The `.C` API restricts only the types of arguments exchanged at the R-to-C boundary (they must be `int *`, `double *`, `char **`, etc., not `SEXP`). Inside the C function body, any R runtime function that does not return or consume a `SEXP` — including `Rf_error`, `Rf_warning`, `Rprintf`, and `R_CheckUserInterrupt` — is completely legal. `Rf_error`'s `longjmp`-based abort propagates correctly through both `.Call`-invoked and `.C`-invoked stack frames.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Literal-Only Error with NLS Translation

- **Locations:** `rpart.c` line 91; `rpart_callback.c` lines 114, 116, 148; `xpred.c` line 89

- **Original Context (.Call):**

```c
/* rpart.c:83-91 — method guard inside SEXP rpart(...) */
if (asInteger(method2) <= NUM_METHODS) {
    i = asInteger(method2) - 1;
    rp_init   = func_table[i].init_split;
    rp_choose = func_table[i].choose_split;
    rp_eval   = func_table[i].eval;
    rp_error  = func_table[i].error;
    rp.num_y  = asInteger(ny2);
} else
    error(_("Invalid value for 'method'"));

/* rpart_callback.c:113-116 — type/length guards, no SEXP inputs to error() */
if (!isReal(value))
    error(_("return value not a vector"));
if (LENGTH(value) != (1 + rsave))
    error(_("returned value is the wrong length"));
```

- **C/C++ Equivalent (.C):**

```c
/*
 * The error() call itself is UNCHANGED.
 * The only modification is to the guard condition: SEXP accessor
 * asInteger(method2) becomes a direct dereference of the int* argument.
 */
void rpart_c(const int *ncat,
             const int *method,   /* was: SEXP method2; asInteger(method2) -> *method */
             const double *opt,
             /* ... remaining arguments ... */)
{
    int i;

    if (*method <= NUM_METHODS) {
        i = *method - 1;
        rp_init   = func_table[i].init_split;
        rp_choose = func_table[i].choose_split;
        rp_eval   = func_table[i].eval;
        rp_error  = func_table[i].error;
        /* rp.num_y set from a separate int* argument */
    } else
        error(_("Invalid value for 'method'"));  /* UNCHANGED */

    /* rpart_callback.c guard — already SEXP-free on the error() line itself */
    if (!isReal(value))
        error(_("return value not a vector"));    /* UNCHANGED */
    if (LENGTH(value) != (1 + rsave))
        error(_("returned value is the wrong length")); /* UNCHANGED */
}
```

- **Explanation:**
  - The `error(_("…"))` calls require zero changes. They take only a string literal and no SEXP arguments.
  - The enclosing guard `asInteger(method2)` is the only SEXP-dependent expression; it is replaced by `*method` once `method2` (a `SEXP`) becomes `method` (a `const int *` argument under `.C`).
  - The `_()` macro is retained without modification — it is an NLS translation helper entirely independent of the SEXP API.
  - No `PROTECT`, `UNPROTECT`, allocation, or type unwrapping is involved at any of these call sites.

---

### Pattern: `%s`-Forwarding of a C-String Error Message

- **Locations:** `rpart.c` line 203

- **Original Context (.Call):**

```c
/* rpart.c:193-203 */
char *errmsg;
errmsg = _("unknown error");

/* rp_init: int (*)(int, double **, int, char **, double *, int *, int, double *) */
i = (*rp_init)(n, rp.ydata, maxcat, &errmsg, parms, &rp.num_resp, 1, wt);
if (i > 0)
    error("%s", errmsg);
```

- **C/C++ Equivalent (.C):**

```c
/*
 * errmsg is already a plain char*; error("%s", errmsg) is SEXP-free.
 * No change is needed to this call site.
 * The surrounding variable declarations and rp_init invocation are also
 * SEXP-free at this specific location.
 */
void rpart_c(/* ... */)
{
    char *errmsg;
    int i;

    errmsg = _("unknown error");

    i = (*rp_init)(n, rp.ydata, maxcat, &errmsg, parms, &rp.num_resp, 1, wt);
    if (i > 0)
        error("%s", errmsg);   /* UNCHANGED */
}
```

- **Explanation:**
  - `errmsg` is a `char *` pointing to a C string literal set by the `rp_init` callback; it has no SEXP type and requires no conversion.
  - `error("%s", errmsg)` uses a single `%s` format specifier with a `char *` argument, which is a valid basic C type under the `.C` API.
  - The `"%s"` indirection (rather than passing `errmsg` directly as the format string) is intentional: it suppresses `-Wformat-security` warnings that arise from passing a non-literal format string. This idiom must be preserved unchanged.
  - No memory allocation, PROTECT, or SEXP accessor is involved at this call site.

---

### Pattern: Formatted Error with a Runtime String Argument (SEXP-Adjacent Context)

- **Locations:** `rpart_callback.c` line 24

- **Original Context (.Call):**

```c
/* rpart_callback.c:20-26 — compat shim for R < 4.5.0 */
static SEXP compat_getVar(SEXP sym, SEXP rho, Rboolean inherits)
{
    SEXP val = inherits ? findVar(sym, rho) : findVarInFrame(rho, sym);
    if (val == R_UnboundValue)
        error(_("variable '%s' not found"), CHAR(PRINTNAME(sym)));
    return val;
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * compat_getVar is a SEXP-typed helper and cannot exist as-is under .C.
 * The function must be restructured: the symbol name is resolved to a
 * plain const char* before entering .C-callable code, and that string
 * is passed directly to the error() call if needed.
 *
 * The error() call itself is UNCHANGED; only its argument source changes.
 */

/* R side: resolve sym name before the .C call */
/* sym_name <- as.character(sym)  →  passed as char** into .C */

/* C side: receive the pre-resolved name as a plain string */
void check_variable_c(const char **sym_name,
                      /* other args such as the looked-up value ... */
                      int *found)
{
    if (!(*found)) {
        /* CHAR(PRINTNAME(sym)) replaced by *sym_name, a pre-resolved const char* */
        error(_("variable '%s' not found"), *sym_name);  /* error() UNCHANGED */
    }
}
```

- **Explanation:**
  - `CHAR(PRINTNAME(sym))` extracts the print name of a `SEXP` symbol as a `const char *`. Under `.C`, the `SEXP sym` argument cannot be passed across the boundary; the symbol's name string must be resolved in R (or in a `.Call`-invoked wrapper) and passed as a `character` scalar, which arrives in C as `char **`.
  - Once `*sym_name` is available as a `const char *`, the `error(_("… '%s' …"), *sym_name)` call is structurally identical to the original — no change to the `error()` call is required.
  - `findVar`, `findVarInFrame`, `R_UnboundValue`, and `R_getVar` all operate on `SEXP` objects and must be removed from `.C`-callable code; the variable lookup must be performed on the R side before the `.C` call.
  - If the callback machinery that drives `rpart_callback.c` is retained as `.Call`-invoked code (which is the most natural architecture, since it already relies on `eval()`, `SEXP`, and R's environment model), this pattern requires no change at all — `error()` within `.Call`-called code is fully correct.
