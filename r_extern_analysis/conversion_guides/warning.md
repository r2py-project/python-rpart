# Conversion Guide: `warning`

---

## 1. Overview of `warning` in R API

`warning` is a macro defined in `R_ext/Error.h` as `#define warning Rf_warning`, where `Rf_warning` has the signature `void Rf_warning(const char *fmt, ...)`. It accepts a `printf`-style format string followed by variadic arguments, formats the message, and registers a non-fatal warning through R's warning system — in contrast to `Rf_error`, it returns normally to its call site rather than performing a `longjmp`. In the `.Call/.External` API this mechanism is the standard way to emit a user-visible warning from C code without aborting the computation; in code targeting the `.C/.Fortran` API, the same `Rf_warning` call is equally legal and is in fact the recommended pattern, because `.C` provides no alternative warning-delivery channel through its argument list.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `rundown.c` | 48 | `warning("Warning message--see rundown.c");` |
| `rundown2.c` | 48 | `warning("Warning message--see rundown2.c");` |

### Data types and surrounding context

Both call sites are structurally identical. They appear at the end of their respective functions (`rundown` and `rundown2`) inside an `oops` label block that is jumped to via `goto oops` when tree traversal encounters an unexpected condition (a `NULL` branch pointer). The full function signatures use only plain C types:

```c
/* rundown.c:10-11 */
void rundown(pNode tree, int obs, double *cp, double *xpred, double *xtemp)

/* rundown2.c:10-11 */
void rundown2(pNode tree, int obs, double *cp, double *xpred, int nresp)
```

The `goto oops` jump target is reached when `branch(tree, obs)` returns `NULL` (line 25-26 in both files) and the `rp.usesurrogate < 2` check fails (line 36). The warning fires only in this exceptional case, which the source comments describe as "impossible (I think)" — a defensive guard for a condition the authors do not expect to occur in practice.

The `warning` calls take only a string literal with no format arguments and no SEXP types. Neither call site involves `PROTECT`, `UNPROTECT`, `allocVector`, SEXP accessors, or any R memory management macro.

**`rundown.c` lines 33–49 — full `oops` block:**

```c
oops:;
    if (rp.usesurrogate < 2) {  /* must have hit a missing value */
        for (; i < rp.num_unique_cp; i++)
            xpred[i] = otree->response_est[0];
        xtemp[i] = (*rp_error) (rp.ydata[obs2], otree->response_est);
        return;
    }
    /*
     * I never really expect to get to this code.  It can only happen if
     *  the last cp on my list is smaller than the terminal cp of the
     *  xval tree just built.  This is impossible (I think).  But just in
     *  case I put a message here.
     */
    warning("Warning message--see rundown.c");
```

**`rundown2.c` lines 33–49 — full `oops` block:**

```c
oops:;
    if (rp.usesurrogate < 2) {  /* must have hit a missing value */
        for (; i < rp.num_unique_cp; i++)
            for (j = 0; j < nresp; j++)
                xpred[k++] = otree->response_est[j];
        return;
    }
    /*
     * I never really expect to get to this code.  It can only happen if
     *  the last cp on my list is smaller than the terminal cp of the
     *  xval tree just built.  This is impossible (I think).  But just in
     *  case I put a message here.
     */
    warning("Warning message--see rundown2.c");
```

### Distinct usage patterns

Only one functionally distinct pattern exists across both CSV rows:

1. **Literal-only defensive warning at an unreachable code path** — `warning("…")` with a plain string literal and no format arguments, emitted immediately before implicit fall-off at the end of a `void` function, guarded by a `goto`-based error path that the authors consider effectively unreachable.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

Unlike `allocVector`, `PROTECT`, or `SEXP` accessor macros, `warning` (`Rf_warning`) is **not an item that must be removed** when migrating from `.Call` to `.C`. The `.C` API restricts only the types of arguments exchanged at the R-to-C boundary (they must be `int *`, `double *`, `char **`, etc., not `SEXP`). Inside the C function body, any R runtime function that neither returns nor consumes a `SEXP` — including `Rf_warning`, `Rf_error`, `Rprintf`, and `R_CheckUserInterrupt` — is completely legal and functions correctly when called from a `.C`-invoked routine.

Specific points for this item:

1. **Retain `warning()`/`Rf_warning()` unchanged.** It is fully legal in `.C`-called C code. No substitution with `fprintf(stderr, …)` or a custom error-flag output argument is needed or appropriate.

2. **Both call sites are already SEXP-free.** The `rundown` and `rundown2` functions take only `pNode` (a struct pointer defined in `node.h`), `int`, and `double *` arguments. No SEXP type appears anywhere in either function body, so no SEXP-related removals are required at all.

3. **The surrounding `goto`-based control flow is unaffected.** The `goto oops` pattern and the `oops:` label are standard C and require no modification under `.C`.

4. **No memory allocation or protection macros are involved.** Neither call site uses `PROTECT`, `UNPROTECT`, `allocVector`, or any R object allocation; the output arrays (`xpred`, `xtemp`) are pre-allocated `double *` arguments — exactly the pattern the `.C` API expects.

### Why `warning` is compatible with `.C` without modification

`Rf_warning` routes the message through R's internal warning list, which is maintained by the R runtime regardless of whether the C code was entered via `.Call` or `.C`. The warning is collected and reported to the user after the `.C` call returns, following R's standard deferred-warning semantics. This mechanism works correctly across both APIs without any change to the C code.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Literal-Only Defensive Warning at an Unreachable Code Path

- **Locations:** `rundown.c` line 48; `rundown2.c` line 48

- **Original Context (.Call):**

```c
/* rundown.c — function called from xval.c via function pointer;
   xval() itself is invoked from .Call-entry-point rpart() */
void rundown(pNode tree, int obs, double *cp, double *xpred, double *xtemp)
{
    int i, obs2 = (obs < 0) ? -(1 + obs) : obs;
    pNode otree = tree;

    for (i = 0; i < rp.num_unique_cp; i++) {
        while (cp[i] < tree->complexity) {
            tree = branch(tree, obs);
            if (tree == 0)
                goto oops;
            otree = tree;
        }
        xpred[i] = tree->response_est[0];
        xtemp[i] = (*rp_error)(rp.ydata[obs2], tree->response_est);
    }
    return;

oops:;
    if (rp.usesurrogate < 2) {
        for (; i < rp.num_unique_cp; i++)
            xpred[i] = otree->response_est[0];
        xtemp[i] = (*rp_error)(rp.ydata[obs2], otree->response_est);
        return;
    }
    warning("Warning message--see rundown.c");
}
```

- **C/C++ Equivalent (.C):**

```c
/*
 * No changes are required to the warning() call or to any part of this
 * function. warning() (Rf_warning) is fully legal in .C-called C code.
 * The function already uses only plain C types at its boundary.
 *
 * If rundown() is called from a .C-entry-point function (rather than via
 * a function pointer from a .Call-entry-point), the code below is the
 * complete, correct .C-compatible implementation.
 */
void rundown(pNode tree, int obs, double *cp, double *xpred, double *xtemp)
{
    int i, obs2 = (obs < 0) ? -(1 + obs) : obs;
    pNode otree = tree;

    for (i = 0; i < rp.num_unique_cp; i++) {
        while (cp[i] < tree->complexity) {
            tree = branch(tree, obs);
            if (tree == 0)
                goto oops;
            otree = tree;
        }
        xpred[i] = tree->response_est[0];
        xtemp[i] = (*rp_error)(rp.ydata[obs2], tree->response_est);
    }
    return;

oops:;
    if (rp.usesurrogate < 2) {
        for (; i < rp.num_unique_cp; i++)
            xpred[i] = otree->response_est[0];
        xtemp[i] = (*rp_error)(rp.ydata[obs2], otree->response_est);
        return;
    }
    warning("Warning message--see rundown.c");  /* UNCHANGED */
}
```

- **Explanation:**
  - The `warning("…")` call requires zero changes. It takes only a string literal and no SEXP arguments; `Rf_warning` is a plain variadic C function compatible with both `.Call` and `.C` entry paths.
  - The function signature `(pNode tree, int obs, double *cp, double *xpred, double *xtemp)` uses only struct pointers and basic C types. No `SEXP` argument is present, so no boundary-type conversion is required.
  - The `goto oops` / `oops:` idiom is standard C and needs no adjustment under `.C`.
  - The `rp.usesurrogate` check, the `for` loop over `xpred`, and the `(*rp_error)(…)` function pointer call are all SEXP-free and remain unchanged.
  - The same analysis applies identically to `rundown2.c` line 48: the only structural difference between the two functions is that `rundown2` fills a multi-response `xpred` array with a nested `j`-loop and omits the `xtemp` update; the `warning()` call at line 48 is syntactically and semantically identical and requires no modification.
  - No `PROTECT`, `UNPROTECT`, `allocVector`, or any other R memory-management macro appears anywhere in either function, so there is nothing to strip out as part of a `.C` migration.
