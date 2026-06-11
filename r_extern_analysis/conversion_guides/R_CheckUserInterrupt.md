# Conversion Guide: `R_CheckUserInterrupt`

## 1. Overview of `R_CheckUserInterrupt` in R API

`R_CheckUserInterrupt` is a C function declared in `R_ext/Utils.h` with the signature `void R_CheckUserInterrupt(void)`. It polls R's event loop for a pending user interrupt signal (e.g., Ctrl-C / SIGINT from the R console) and, if one has been received, throws a non-local R-level error that unwinds the call stack and returns control to the R interpreter. Its sole purpose is to make long-running C loops responsive to user cancellation; it has no return value, produces no output, and performs no computation on data. Because it interacts directly with R's internal signal-handling and longjmp-based error mechanism, it is only meaningful when called from code executing inside R's runtime.

---

## 2. Contextual Usage Analysis

### Source locations

| File | Line | Context |
|------|------|---------|
| `xpred.c` | 291 | `R_CheckUserInterrupt();` |
| `xval.c`  | 168 | `R_CheckUserInterrupt();` |

### Data types and surrounding logic

**`xpred.c` line 291** — The call sits at the tail of the outer cross-validation loop body (`for (xgroup = 0; xgroup < xvals; xgroup++)`). Each iteration builds a hold-out tree via `partition`, runs held-out observations down the tree with `rundown2`, then frees the tree with `free_tree(xtree, 0)`. `R_CheckUserInterrupt()` fires immediately after `free_tree`, once per fold, giving the user a clean cancellation point between folds. The only surrounding R API usage in this loop is the `predict2 = PROTECT(allocVector(REALSXP, n * ncp * nresp))` allocation made before the loop begins (line 209) and the `UNPROTECT(1)` / `return predict2` block after the loop ends (lines 294-295).

**`xval.c` line 168** — The call sits at the tail of the outer cross-validation loop body (`for (xgroup = 0; xgroup < n_xval; xgroup++)`). Each iteration builds a hold-out tree, runs held-out observations with `rundown`, accumulates cross-validation risk into a linked list of `cptable` entries, then frees the tree with `free_tree(xtree, 1)`. `R_CheckUserInterrupt()` fires immediately after `free_tree`, once per fold. This function (`xval`) returns `void` and uses no SEXP objects; it communicates entirely through C-level struct pointers and Calloc-allocated arrays.

### Distinct implementation patterns

There is exactly one pattern across both files:

**Periodic interrupt check at the end of a long-running outer loop iteration** — `R_CheckUserInterrupt()` is called unconditionally, with no arguments and no use of its (void) return, once per fold of a cross-validation loop. The call is always placed after all data-processing work for the iteration is complete and after any temporary tree structures have been freed, making it a clean, side-effect-free checkpoint.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_CheckUserInterrupt` is not an allocator, type, or memory-management macro — it is a runtime signal-handling hook that is tightly coupled to R's own event loop and error-unwinding mechanism (`longjmp`). It has no standard C equivalent that replicates its exact semantics. The conversion strategy depends on the desired behavior:

1. **Remove entirely (simplest, recommended default).** When the C code is called via `.C`, it runs synchronously in a single R thread. R itself periodically checks for interrupts between `.C` call boundaries. For most workloads this is acceptable, and the call is simply deleted. The function becomes a plain `void` C routine with no changes to its argument list.

2. **Replace with a POSIX signal check (portable approximation).** If the computation is so long that per-fold responsiveness is required even inside `.C`, the C code can inspect a `volatile sig_atomic_t` flag that a `SIGINT` handler sets. This requires registering a signal handler from R before the `.C` call (e.g., via `tools::pskill` or a custom handler registered with `signal(SIGINT, handler)`) and passing a pointer to the flag as an extra argument. This approach is more complex and platform-dependent.

3. **Keep `R_CheckUserInterrupt` if the function remains `.Call`-callable.** If the surrounding function still uses `.Call` (as is the case for `xpred.c`, which returns a `SEXP`), the call can be left unchanged. Only functions fully converted to `.C` with no remaining SEXP usage need this guide.

For a full `.C` conversion, **option 1 (removal) is the standard approach**. The `.C` API itself provides no mechanism to surface R-level interrupts inside the C body, and R's own scheduler will check for signals when control returns to R after the `.C` call.

### Why removal is safe

- The `.C` call is synchronous: R is blocked for the duration. Pressing Ctrl-C sends SIGINT to the R process; the default R signal handler sets an internal flag, but `R_CheckUserInterrupt` is the only way to act on that flag from within C code compiled against the R API. Without the R runtime present (which is always present for `.C` calls), the call is a no-op in terms of actual interrupt delivery.
- The cross-validation loops in `xpred.c` and `xval.c` iterate over a number of folds (`xvals`, `n_xval`) that is small in practice (typically 10). The per-fold overhead of not having a mid-loop interrupt check is negligible.
- Removing the call eliminates the only remaining dependency on `R_ext/Utils.h` in the converted function bodies, simplifying the header include list.

---

## 4. Step-by-Step Conversion Examples

### Pattern: Periodic Interrupt Check at End of Cross-Validation Loop Iteration

- **Locations:** `xpred.c` line 291; `xval.c` line 168

- **Original Context (.Call):**

```c
/* xpred.c: outer cross-validation loop (simplified) */
for (xgroup = 0; xgroup < xvals; xgroup++) {
    /* ... rebuild sorts, fix up y-vector, rescale cp ... */

    xtree->num_obs = k;
    (*rp_init)(k, rp.ytemp, maxcat, &errmsg, parms, &ii, 2, rp.wtemp);
    (*rp_eval)(k, rp.ytemp, xtree->response_est, &(xtree->risk), rp.wtemp);
    xtree->complexity = xtree->risk;
    partition(1, xtree, &temp, 0, k);
    fix_cp(xtree, xtree->complexity);

    for (i = k; i < rp.n; i++) {
        j = rp.sorts[0][i];
        rundown2(xtree, j, cp, (predict + j * ncp * nresp), nresp);
    }

    free_tree(xtree, 0);
    R_CheckUserInterrupt();   /* <-- signal-check hook, end of fold */
}

/* xval.c: outer cross-validation loop (simplified) */
for (xgroup = 0; xgroup < n_xval; xgroup++) {
    /* ... rebuild sorts, fix up y-vector, rescale cp ... */

    xtree = (pNode) CALLOC(1, nodesize);
    xtree->num_obs = k;
    (*rp_init)(k, rp.ytemp, maxcat, errmsg, parms, &itemp, 2, rp.wtemp);
    (*rp_eval)(k, rp.ytemp, xtree->response_est, &(xtree->risk), rp.wtemp);
    xtree->complexity = xtree->risk;
    partition(1, xtree, &temp, 0, k);
    fix_cp(xtree, xtree->complexity);

    for (i = k; i < rp.n; i++) {
        j = rp.sorts[0][i];
        rundown(xtree, j, cp, xpred, xtemp);
        /* accumulate xrisk / xstd into cplist linked list */
    }

    free_tree(xtree, 1);      /* Calloc-ed */
    R_CheckUserInterrupt();   /* <-- signal-check hook, end of fold */
}
```

- **C/C++ Equivalent (.C):**

```c
/* Option 1: Remove entirely (recommended) */

/* xpred_c: no R API headers required for interrupt handling */
for (xgroup = 0; xgroup < xvals; xgroup++) {
    /* ... rebuild sorts, fix up y-vector, rescale cp ... */

    xtree->num_obs = k;
    (*rp_init)(k, rp.ytemp, maxcat, &errmsg, parms, &ii, 2, rp.wtemp);
    (*rp_eval)(k, rp.ytemp, xtree->response_est, &(xtree->risk), rp.wtemp);
    xtree->complexity = xtree->risk;
    partition(1, xtree, &temp, 0, k);
    fix_cp(xtree, xtree->complexity);

    for (i = k; i < rp.n; i++) {
        j = rp.sorts[0][i];
        rundown2(xtree, j, cp, (predict + j * ncp * nresp), nresp);
    }

    free_tree(xtree, 0);
    /* R_CheckUserInterrupt() removed: no .C-compatible equivalent */
}

/* xval_c: identical treatment */
for (xgroup = 0; xgroup < n_xval; xgroup++) {
    /* ... rebuild sorts, fix up y-vector, rescale cp ... */

    xtree = (pNode) R_Calloc(1, Node);
    xtree->num_obs = k;
    (*rp_init)(k, rp.ytemp, maxcat, errmsg, parms, &itemp, 2, rp.wtemp);
    (*rp_eval)(k, rp.ytemp, xtree->response_est, &(xtree->risk), rp.wtemp);
    xtree->complexity = xtree->risk;
    partition(1, xtree, &temp, 0, k);
    fix_cp(xtree, xtree->complexity);

    for (i = k; i < rp.n; i++) {
        j = rp.sorts[0][i];
        rundown(xtree, j, cp, xpred, xtemp);
        /* accumulate xrisk / xstd into cplist linked list */
    }

    free_tree(xtree, 1);
    /* R_CheckUserInterrupt() removed */
}
```

```c
/* Option 2: POSIX signal-flag approximation (advanced, platform-dependent) */
#include <signal.h>

static volatile sig_atomic_t user_interrupt_flag = 0;

static void interrupt_handler(int sig) {
    user_interrupt_flag = 1;
}

/*
 * The C function receives an extra int* output argument that the R caller
 * inspects after .C() returns to decide whether to stop further processing.
 */
void xval_c(/* ... normal args ... */,
            int *was_interrupted)   /* output: set to 1 if Ctrl-C was pressed */
{
    void (*old_handler)(int) = signal(SIGINT, interrupt_handler);
    user_interrupt_flag = 0;
    *was_interrupted = 0;

    for (xgroup = 0; xgroup < n_xval; xgroup++) {
        /* ... per-fold work ... */
        free_tree(xtree, 1);

        if (user_interrupt_flag) {
            *was_interrupted = 1;
            break;   /* exit loop cleanly; R caller checks was_interrupted */
        }
    }

    signal(SIGINT, old_handler);   /* restore previous handler */
}
```

Corresponding R-side handling for option 2:

```r
result <- .C("xval_c",
             # ... normal arguments ...
             was_interrupted = integer(1L))

if (result$was_interrupted == 1L)
    stop("Cross-validation interrupted by user.")
```

- **Explanation:**
  - **Option 1** is a straight deletion. `R_CheckUserInterrupt()` is a void call with no side effects on any data the C code reads or writes; removing it leaves the loop logic entirely unchanged. The `#include <R_ext/Utils.h>` directive can be dropped from the file if it was included solely for this function. No argument list changes are required.
  - **Option 2** replaces R's internal signal hook with a POSIX `SIGINT` handler that sets a `volatile sig_atomic_t` flag. An extra `int *was_interrupted` output argument is added so the R caller can check the flag after `.C` returns and raise an R-level error with `stop()` if needed. The previous `SIGINT` handler is saved and restored to avoid interfering with R's own signal management. This approach is portable to Linux and macOS but requires care on Windows, where `SIGINT` semantics differ.
  - In both options, the `R_ext/Utils.h` include for `R_CheckUserInterrupt` is removed from the converted file; other declarations in that header (e.g., `R_CheckStack`) are evaluated independently.
  - The placement of the check — after `free_tree` and before the next iteration — is the correct location in both options: any allocated tree memory is already reclaimed, so there is no resource leak if the loop exits early.
