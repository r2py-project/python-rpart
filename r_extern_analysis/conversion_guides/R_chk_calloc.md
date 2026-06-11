# Conversion Guide: `R_chk_calloc`

## 1. Overview of `R_chk_calloc` in R API

`R_chk_calloc` is a low-level C function declared in `R_ext/RS.h` (included transitively through `R.h`) with the signature:

```c
extern void *R_chk_calloc(R_SIZE_T nmemb, R_SIZE_T size);
```

It allocates `nmemb * size` bytes of zero-initialised heap memory, exactly like the standard C `calloc`, but adds R's internal error-checking wrapper: if allocation fails, it calls R's error handler rather than returning `NULL`, so the caller never needs to check for a `NULL` return value. The returned pointer must be explicitly freed with `R_Free` (which calls `R_chk_free`) when it is no longer needed — unlike `R_alloc`, it is **not** collected automatically when the enclosing `.Call` invocation returns. Within rpart, `R_chk_calloc` is never called directly; it is always invoked through the convenience macro defined in `rpart.h`:

```c
#define CALLOC(a, b)  R_chk_calloc((size_t)(a), b)
```

The comment in `rpart.h` makes the ownership distinction explicit: objects allocated with `CALLOC` must be freed manually with `R_Free`, whereas objects allocated with `ALLOC` (`R_alloc`) are freed automatically by R.

---

## 2. Contextual Usage Analysis

### Declaration site

| File | Line | Statement |
|------|------|-----------|
| `rpart.h` | 26 | `#define CALLOC(a,b) R_chk_calloc((size_t)(a), b)` |

### All call sites (via the `CALLOC` macro)

| File | Lines | Allocated type | Purpose | Paired `R_Free` site |
|------|-------|----------------|---------|----------------------|
| `insert_split.c` | 25, 37, 65, 74 | `pSplit` (`Split *`) | Heap-allocated split nodes in a dynamically managed bounded sorted linked list | `insert_split.c` lines 36, 63; `free_tree.c` line 13 |
| `partition.c` | 98, 113 | `pNode` (`Node *`) | Left and right child nodes in the recursively grown decision tree | `free_tree.c` line 29 |
| `xval.c` | 58 | `double *` (`xtemp`) | Flat scratch buffer of length `3 * rp.num_unique_cp` holding temporary cross-validation scores; subdivided via pointer arithmetic into `xtemp`, `xpred`, `cp` | `xval.c` line 179 |
| `xval.c` | 61 | `int *` (`savew`) | Flat integer buffer of length `rp.n` preserving the original `rp.which` group assignments across cross-validation folds | `xval.c` line 178 |
| `xval.c` | 134 | `pNode` (`Node *`) | Root node of each per-fold cross-validation tree; freed recursively via `free_tree(xtree, 1)` after fold evaluation | `free_tree.c` line 29 (called from `xval.c` line 167) |

### Data types

- **`pSplit` / `Split *`**: a variable-size struct defined in `node.h`. The actual allocation size is computed as `sizeof(Split) + (ncat - 20) * sizeof(int)` to accommodate a variable-length `csplit[]` array for categorical splits.
- **`pNode` / `Node *`**: a variable-size struct defined in `node.h`. The actual allocation size is held in the global `nodesize`, computed in `rpart.c` as `sizeof(Node) + (rp.num_resp - 20) * sizeof(double)`.
- **`double *`** and **`int *`**: plain flat C arrays used as function-scoped scratch buffers in `xval.c`.

### Memory-management macros used alongside `CALLOC`

- `R_Free(p)`: paired deallocation macro (`R_chk_free(p); p = NULL`). Every `CALLOC` block in rpart has a matching `R_Free` call.
- `ALLOC(a, b)` (`R_alloc`): the alternative allocation macro for objects whose lifetime is bounded by the enclosing `.Call` invocation. The rpart source explicitly contrasts the two in the comment at `rpart.h` lines 20-24.

### Distinct usage patterns

**Pattern A — Flat temporary scratch arrays** (`xval.c` lines 58, 61): Plain `double *` and `int *` buffers allocated at the top of a function and freed at the bottom. Lifetime is strictly one invocation of `xval()`.

**Pattern B — Dynamically managed linked-list nodes** (`insert_split.c` lines 25, 37, 65, 74): `pSplit` structs of variable size allocated and freed during the construction of a bounded sorted list. The allocation size varies per call because it depends on `ncat`. Slots are freed mid-function when a better split evicts a list tail entry.

**Pattern C — Recursive tree node allocation** (`partition.c` lines 98, 113; `xval.c` line 134): `pNode` structs of fixed-but-runtime-computed size allocated as child nodes during recursive tree growth. The entire subtree is freed later via `free_tree(..., 1)`.

---

## 3. Pure C/C++ Conversion Strategy

### API paradigm shift

`R_chk_calloc` is part of R's S-compatible memory API and is only available in code compiled against `R.h`. It cannot be used in code intended to be called via `.C`/`.Fortran`, which expects plain C types and no R-internal symbols.

The core conversion rule is: **all memory that the C code needs must be pre-allocated on the R side and passed in as plain pointer arguments**. The C code receives those pointers and uses them directly without calling any allocation or deallocation function. R reclaims the memory automatically after the `.C` call returns.

The three rpart patterns each require a distinct approach:

**Pattern A (flat scratch arrays):** Replace `CALLOC(n, sizeof(T))` with an additional `.C` argument of type `integer(n)` or `double(n)` pre-allocated in R. The C function gains the corresponding `int *` or `double *` parameter; the `CALLOC` statement and the matching `R_Free` statement are both deleted. Because `.C` zero-initialises arguments passed as `integer(n)` or `double(n)`, the zero-initialisation guarantee of `calloc` is preserved automatically.

**Pattern B (variable-size split nodes in a linked list):** `Split` structs have a variable allocation size determined at runtime by `ncat`. In the `.C` paradigm, variable-size heap structs must be replaced by a statically sized flat-array pool. Pre-allocate a pool of `MAX_SPLITS` slots on the R side, where each split field is a separate flat array (one array per field: `split_improve`, `split_spoint`, `split_nextsplit`, `split_var_num`, etc.). An `int split_pool_active[MAX_SPLITS]` bitmap tracks which slots are occupied. Allocation becomes slot-claiming (`active[i] = 1`); freeing becomes slot-marking (`active[i] = 0`). Because `calloc` zero-initialises, the slot must be explicitly zeroed when claimed (the R-side pre-allocation provides this for the initial state; zero-reinitialisation before reuse must be done explicitly in C).

**Pattern C (recursive tree nodes):** `Node` structs have a runtime-variable size (`nodesize`) and are organised into a binary tree by pointer. The same pool pattern applies: replace the pointer-linked tree with flat parallel arrays pre-allocated by R, using integer indices as node references. The recursive `free_tree` traversal becomes a slot-marking loop. The complete strategy is documented in the companion `R_Free.md` guide.

### Zero-initialisation guarantee

Standard `calloc` (and `R_chk_calloc`) zero-initialises the allocated memory. When converting to pre-allocated R vectors, this is preserved automatically: `integer(n)` in R creates a zero-filled integer vector, and `double(n)` creates a zero-filled double vector. When slots are recycled mid-computation (Pattern B), the C code must explicitly zero-fill the slot fields before marking it active.

### Type mapping

| `.Call` usage | `.C`-compatible equivalent |
|---|---|
| `(double *) CALLOC(n, sizeof(double))` | `double *` pre-allocated by R: `double(n)` |
| `(int *)    CALLOC(n, sizeof(int))` | `int *` pre-allocated by R: `integer(n)` |
| `(pSplit) CALLOC(1, splitsize)` (variable-size struct) | Flat pool arrays per field, pre-allocated by R; slot index replaces pointer |
| `(pNode)  CALLOC(1, nodesize)` (variable-size struct) | Flat pool arrays per field, pre-allocated by R; slot index replaces pointer |
| Paired `R_Free(p)` | Deleted entirely (R reclaims pre-allocated vectors) or replaced by `active[i] = 0` (pool recycling) |

---

## 4. Step-by-Step Conversion Examples

### Pattern A: Flat Temporary Scratch Array Allocation

- **Locations:** `xval.c` lines 58, 61

- **Original Context (.Call):**

```c
/* xval.c — top of xval() */
double *xtemp, *xpred;
int    *savew;
double *cp;

/* Allocate and partition a contiguous double buffer into three sub-arrays */
xtemp = (double *) CALLOC(3 * rp.num_unique_cp, sizeof(double));
xpred = xtemp + rp.num_unique_cp;
cp    = xpred + rp.num_unique_cp;

/* Allocate a flat integer scratch buffer */
savew = (int *) CALLOC(rp.n, sizeof(int));
for (i = 0; i < rp.n; i++)
    savew[i] = rp.which[i];   /* save initial group assignments */

/* ... algorithm body ... */

/* Cleanup at bottom of xval() */
for (i = 0; i < rp.n; i++)
    rp.which[i] = savew[i];   /* restore group assignments */
R_Free(savew);
R_Free(xtemp);
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Both CALLOC blocks are removed.  The buffers are pre-allocated by R
 * and passed as additional arguments.  No CALLOC, no R_Free.
 *
 * xtemp_buf : double *, length 3 * num_unique_cp  — R: double(3 * num_unique_cp)
 * savew_buf : int *,    length n                  — R: integer(n)
 */
void xval_c(int    *n_xval,
            int    *num_unique_cp,
            int    *n,
            double *xtemp_buf,   /* pre-allocated, zero-filled by R */
            int    *savew_buf,   /* pre-allocated, zero-filled by R */
            /* ... other args ... */)
{
    /* Pointer arithmetic into the pre-allocated buffer: unchanged */
    double *xtemp = xtemp_buf;
    double *xpred = xtemp_buf + *num_unique_cp;
    double *cp    = xtemp_buf + 2 * (*num_unique_cp);
    int    *savew = savew_buf;

    for (int i = 0; i < *n; i++)
        savew[i] = which[i];    /* save initial group assignments */

    /* ... algorithm body unchanged ... */

    for (int i = 0; i < *n; i++)
        which[i] = savew[i];    /* restore group assignments */

    /* No R_Free calls: R reclaims xtemp_buf and savew_buf after .C returns */
}
```

Corresponding R-side call:

```r
result <- .C("xval_c",
    n_xval        = as.integer(n_xval),
    num_unique_cp = as.integer(num_unique_cp),
    n             = as.integer(n),
    xtemp_buf     = double(3L * num_unique_cp),  # zero-filled; replaces CALLOC
    savew_buf     = integer(n),                  # zero-filled; replaces CALLOC
    # ... other args ...
)
```

- **Explanation:** `CALLOC(3 * rp.num_unique_cp, sizeof(double))` and `CALLOC(rp.n, sizeof(int))` are deleted from C. The buffers are pre-allocated in R using `double(3L * num_unique_cp)` and `integer(n)`, both of which produce zero-filled vectors, preserving the zero-initialisation guarantee of `calloc`. The pointer arithmetic that subdivides `xtemp_buf` into `xtemp`, `xpred`, and `cp` sub-arrays is unchanged. Both `R_Free` calls are deleted entirely because `.C` hands ownership of the buffer memory back to R's garbage collector on return.

---

### Pattern B: Variable-Size Linked-List Node Allocation

- **Locations:** `insert_split.c` lines 25, 37, 65, 74

- **Original Context (.Call):**

```c
/* insert_split.c — variable-size Split node allocation */
int splitsize = sizeof(Split) + (ncat - 20) * sizeof(int);

/* First call: allocate head of new list */
s3 = (pSplit) CALLOC(1, splitsize);
s3->nextsplit = NULL;
*listhead = s3;

/* max==1 branch: evict and replace existing head (categorical split) */
if (ncat > 1) {
    R_Free(s3);                          /* free old head */
    s3 = (pSplit) CALLOC(1, splitsize);  /* allocate fresh block */
    s3->nextsplit = NULL;
    *listhead = s3;
}

/* list-full branch: evict and replace tail element (categorical split) */
if (ncat > 1) {
    R_Free(s4);                          /* free tail */
    s4 = (pSplit) CALLOC(1, splitsize);  /* allocate fresh block */
}
/* non-categorical path: ncat <= 1 — existing slot is reused in place */

/* New split appended (list not yet full) */
s4 = (pSplit) CALLOC(1, splitsize);
s4->nextsplit = s2;
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Each Split struct is replaced by an integer slot index into a pool
 * of flat parallel arrays, one array per struct field.
 *
 * Pool arrays (pre-allocated by R, length MAX_SPLITS each):
 *   double *split_improve    — Split.improve
 *   double *split_adj        — Split.adj
 *   double *split_spoint     — Split.spoint
 *   int    *split_nextsplit  — Split.nextsplit  (-1 = NULL sentinel)
 *   int    *split_var_num    — Split.var_num
 *   int    *split_count      — Split.count
 *   int    *split_csplit     — Split.csplit[], laid out as
 *                              [slot * MAX_NCAT + k] for category k
 *   int    *split_active     — 1 = slot occupied, 0 = free
 */

#define NO_SPLIT  -1   /* sentinel replacing NULL pSplit */

/* Claim the next free slot; zero-fills the slot before returning its index */
static int alloc_split_slot(int *split_active,
                             double *split_improve, double *split_adj,
                             double *split_spoint,
                             int *split_nextsplit, int *split_var_num,
                             int *split_count,
                             int *split_csplit, int max_ncat,
                             int max_splits)
{
    for (int i = 0; i < max_splits; i++) {
        if (!split_active[i]) {
            split_active[i]      = 1;
            split_improve[i]     = 0.0;
            split_adj[i]         = 0.0;
            split_spoint[i]      = 0.0;
            split_nextsplit[i]   = NO_SPLIT;
            split_var_num[i]     = 0;
            split_count[i]       = 0;
            for (int k = 0; k < max_ncat; k++)
                split_csplit[i * max_ncat + k] = 0;
            return i;
        }
    }
    return -1;  /* pool exhausted — caller must handle error */
}

/* Free a slot: simply mark it available for reuse */
static void free_split_slot(int idx, int *split_active,
                             int *split_nextsplit)
{
    if (idx == NO_SPLIT) return;
    split_active[idx]    = 0;
    split_nextsplit[idx] = NO_SPLIT;
}

/* --- Converted insert_split logic --- */

/* First call: claim head slot */
int s3_idx = alloc_split_slot(split_active, split_improve, split_adj,
                               split_spoint, split_nextsplit,
                               split_var_num, split_count,
                               split_csplit, max_ncat, max_splits);
split_nextsplit[s3_idx] = NO_SPLIT;
*listhead_idx = s3_idx;

/* max==1 branch: evict and replace head (all splits, not just ncat > 1) */
if (ncat > 1) {
    free_split_slot(s3_idx, split_active, split_nextsplit);  /* "R_Free(s3)" */
    s3_idx = alloc_split_slot(/* ... */);                    /* "CALLOC(1, splitsize)" */
    split_nextsplit[s3_idx] = NO_SPLIT;
    *listhead_idx = s3_idx;
}

/* list-full branch: evict and replace tail (ncat > 1 guard preserved) */
if (ncat > 1) {
    free_split_slot(s4_idx, split_active, split_nextsplit);
    s4_idx = alloc_split_slot(/* ... */);
}
/* ncat <= 1: s4_idx already holds the tail slot; reuse in place, no free/alloc */

/* New split appended (list not yet full) */
int s4_idx = alloc_split_slot(/* ... */);
split_nextsplit[s4_idx] = s2_idx;
```

Corresponding R-side setup:

```r
max_splits <- as.integer(rp_maxsur + rp_maxpri + 10)  # conservative upper bound
max_ncat   <- as.integer(max(rp_numcat, 1L))

split_pool <- list(
    improve    = double(max_splits),
    adj        = double(max_splits),
    spoint     = double(max_splits),
    nextsplit  = integer(max_splits),   # 0-initialised = NO_SPLIT if sentinel is -1 after call
    var_num    = integer(max_splits),
    count      = integer(max_splits),
    csplit     = integer(max_splits * max_ncat),
    active     = integer(max_splits)
)
```

- **Explanation:** `CALLOC(1, splitsize)` is replaced by `alloc_split_slot`, which scans the `split_active` bitmap for the first free entry and zero-fills all its fields before returning the index. The variable `splitsize` (which differs between categorical and continuous splits because of the trailing `csplit[]` array) is handled by pre-allocating the `split_csplit` pool with a flat stride of `max_ncat` per slot, using the index formula `slot * max_ncat + k`. `R_Free(s3)` and `R_Free(s4)` become `free_split_slot` calls that set `active[idx] = 0`. The `ncat > 1` guard is preserved exactly: for continuous splits (`ncat <= 1`), the existing slot is reused in place without a free/alloc cycle, exactly as in the original code. No R-specific headers or functions are required.

---

### Pattern C: Recursive Tree Node Allocation

- **Locations:** `partition.c` lines 98, 113; `xval.c` line 134

- **Original Context (.Call):**

```c
/* partition.c — child node allocation during recursive tree growth */
me->leftson  = (pNode) CALLOC(1, nodesize);
(me->leftson)->complexity = tempcp - rp.alpha;
left_split = partition(2 * nodenum, me->leftson, &left_risk, n1, n1 + nleft);

me->rightson = (pNode) CALLOC(1, nodesize);
(me->rightson)->complexity = tempcp - rp.alpha;
right_split  = partition(1 + 2 * nodenum, me->rightson,
                          &right_risk, n1 + nleft, n1 + nleft + nright);

/* xval.c — root node of a per-fold cross-validation tree */
xtree = (pNode) CALLOC(1, nodesize);
xtree->num_obs = k;
/* ... tree built by recursive partition() calls ... */
free_tree(xtree, 1);   /* recursively frees all CALLOC-ed nodes */
```

- **C/C++ Equivalent (.C):**

```c
/*
 * Each Node struct becomes a slot index into flat parallel arrays.
 * The recursive pointer links (leftson, rightson, primary, surrogate)
 * become integer arrays storing slot indices; NO_NODE (-1) replaces NULL.
 *
 * Node pool arrays (pre-allocated by R, length MAX_NODES each):
 *   double *node_risk         — Node.risk
 *   double *node_complexity   — Node.complexity
 *   double *node_sum_wt       — Node.sum_wt
 *   int    *node_rightson     — Node.rightson   (-1 = leaf)
 *   int    *node_leftson      — Node.leftson    (-1 = leaf)
 *   int    *node_primary      — index into split pool (-1 = none)
 *   int    *node_surrogate    — index into split pool (-1 = none)
 *   int    *node_num_obs      — Node.num_obs
 *   int    *node_lastsurr     — Node.lastsurrogate
 *   double *node_response     — Node.response_est[], laid out as
 *                               [slot * MAX_RESP + k]
 *   int    *node_active       — 1 = slot occupied, 0 = free
 *   int    *node_count        — scalar: number of slots currently active
 */

#define NO_NODE  -1

static int alloc_node_slot(int *node_active,
                            double *node_risk, double *node_complexity,
                            double *node_sum_wt,
                            int *node_rightson, int *node_leftson,
                            int *node_primary, int *node_surrogate,
                            int *node_num_obs, int *node_lastsurr,
                            double *node_response, int max_resp,
                            int *node_count, int max_nodes)
{
    int i = *node_count;  /* nodes are always allocated in order during growth */
    if (i >= max_nodes) return -1;   /* caller must treat as error */
    node_active[i]      = 1;
    node_risk[i]        = 0.0;
    node_complexity[i]  = 0.0;
    node_sum_wt[i]      = 0.0;
    node_rightson[i]    = NO_NODE;
    node_leftson[i]     = NO_NODE;
    node_primary[i]     = NO_NODE;
    node_surrogate[i]   = NO_NODE;
    node_num_obs[i]     = 0;
    node_lastsurr[i]    = 0;
    for (int k = 0; k < max_resp; k++)
        node_response[i * max_resp + k] = 0.0;
    (*node_count)++;
    return i;
}

/* "free_tree(xtree, 1)" equivalent: mark a subtree's slots as inactive */
static void free_node_recursive(int idx, int *node_active,
                                 int *node_rightson, int *node_leftson)
{
    if (idx == NO_NODE) return;
    free_node_recursive(node_rightson[idx], node_active,
                        node_rightson, node_leftson);
    free_node_recursive(node_leftson[idx],  node_active,
                        node_rightson, node_leftson);
    node_active[idx] = 0;
}

/* --- Converted partition() logic (fragment) --- */

int left_idx = alloc_node_slot(/* pool args */);
node_complexity[left_idx] = tempcp - alpha;
left_split = partition_c(2 * nodenum, left_idx, &left_risk,
                          n1, n1 + nleft, /* pool args */);

int right_idx = alloc_node_slot(/* pool args */);
node_complexity[right_idx] = tempcp - alpha;
right_split = partition_c(1 + 2 * nodenum, right_idx, &right_risk,
                           n1 + nleft, n1 + nleft + nright, /* pool args */);

/* --- Converted xval() fragment --- */
int xtree_idx = alloc_node_slot(/* pool args */);
node_num_obs[xtree_idx] = k;
/* ... recursive partition_c() calls build the tree ... */
free_node_recursive(xtree_idx, node_active, node_rightson, node_leftson);
```

Corresponding R-side setup:

```r
max_nodes <- as.integer(2L * n + 1L)   # worst-case binary tree node count
max_resp  <- as.integer(rp_num_resp)

node_pool <- list(
    risk       = double(max_nodes),
    complexity = double(max_nodes),
    sum_wt     = double(max_nodes),
    rightson   = integer(max_nodes),    # initialised to 0; C sets unused slots to NO_NODE
    leftson    = integer(max_nodes),
    primary    = integer(max_nodes),
    surrogate  = integer(max_nodes),
    num_obs    = integer(max_nodes),
    lastsurr   = integer(max_nodes),
    response   = double(max_nodes * max_resp),
    active     = integer(max_nodes),
    count      = integer(1L)
)

result <- .C("xval_c", ..., as.list(node_pool), ...)
```

- **Explanation:** `CALLOC(1, nodesize)` is replaced by `alloc_node_slot`, which claims the next available index from the pre-allocated pool arrays and zero-fills the slot. The variable `nodesize` (which accommodates a trailing `response_est[]` array of runtime length `rp.num_resp`) is absorbed by pre-allocating `node_response` as a flat array with stride `max_resp` per slot, accessing element `k` of slot `i` as `node_response[i * max_resp + k]`. The `rightson` and `leftson` struct pointer members become integer arrays holding slot indices; the `NULL` sentinel becomes `NO_NODE` (-1). `free_tree(xtree, 1)` becomes `free_node_recursive`, which marks slots as inactive by setting `node_active[idx] = 0` rather than calling `R_chk_free`. Because R pre-allocates all pool arrays, no `CALLOC`, `R_Free`, or any R-specific memory function remains in the C code.
