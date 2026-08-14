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
/*
 *   Cut down a list of death times, to avoid ones that differ by
 *    very, very little.
 *	n	number of death times
 *	y	list of death times, sorted
 *	eps     machine precision
 * output
 *      keep    1=keep this one, 0=don't
 */
#include "rpart.h"
/* [FAKE_R] #include <Rinternals.h> */
#include "fake_R.h"  /* replaces all R API headers above */

static void
Rpartexp2(int n, double *y, double eps, int *keep)
{
    double delta;
    int i, j;
    double lasty;

    /* let delta = eps * interquartile range */

    i = n / 4;
    j = (3 * n) / 4;
    delta = eps * (y[j] - y[i]);


    /*
     * make sure that each y is at least "delta" greater than
     * the last y that we have decided to keep
     */
    lasty = y[0];
    keep[0] = 1;
    for (i = 1; i < n; i++) {
	if ((y[i] - lasty) <= delta)
	    keep[i] = 0;
	else {
	    keep[i] = 1;
	    lasty = y[i];
	}
    }
}

SEXP
rpartexp2(SEXP dtimes, SEXP eps)
{
    int n = LENGTH(dtimes);
    SEXP keep = PROTECT(allocVector(INTSXP, n));
    Rpartexp2(n, REAL(dtimes), asReal(eps), INTEGER(keep));
    UNPROTECT(1);
    return keep;
}
