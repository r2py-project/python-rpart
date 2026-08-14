/*
 * Modified 2026 by Yufei Cai and Jun Li (University of Notre Dame) for
 * r2py_rpart.  The only changes are to #include directives: R's API headers
 * are replaced by the standalone headers in r_fake_headers/.  Each such
 * change is marked inline with a [FAKE_R] comment.  No executable logic in
 * this file has been altered.
 *
 * Original file from the R package rpart 4.1.27 by Terry M. Therneau and
 * Beth Atkinson, R port by Brian D. Ripley.  Distributed under the GNU
 * General Public License, version 2 or 3.
 */
#include "rpart.h"
/* [FAKE_R] #include "R_ext/Rdynload.h" */
#include "fake_R.h"  /* replaces all R API headers above */
#include "node.h"
#include "rpartproto.h"

SEXP init_rpcallback(SEXP rhox, SEXP ny, SEXP nr, SEXP expr1x, SEXP expr2x);
SEXP rpartexp2(SEXP dtimes, SEXP seps);
SEXP pred_rpart(SEXP dimx, SEXP nnode, SEXP nsplit, SEXP dimc,
		SEXP nnum, SEXP nodes2, SEXP vnum, SEXP split2,
		SEXP csplit2, SEXP usesur, SEXP xdata2, SEXP xmiss2);

static const R_CallMethodDef CallEntries[] = {
    {"init_rpcallback", (DL_FUNC) &init_rpcallback, 5},
    {"rpart", (DL_FUNC) &rpart, 11},
    {"xpred", (DL_FUNC) &xpred, 15},
    {"rpartexp2", (DL_FUNC) &rpartexp2, 2},
    {"pred_rpart", (DL_FUNC) &pred_rpart, 12},
    {NULL, NULL, 0}
};

/* [FAKE_R] #include <Rversion.h> */
void
R_init_rpart(DllInfo * dll)
{
    R_registerRoutines(dll, NULL, CallEntries, NULL, NULL);
    R_useDynamicSymbols(dll, FALSE);
#if defined(R_VERSION) && R_VERSION >= R_Version(2, 16, 0)
    R_forceSymbols(dll, TRUE);
#endif
}
