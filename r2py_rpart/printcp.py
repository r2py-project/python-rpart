from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd



def printcp(x: dict, digits: int = 2) -> np.ndarray | pd.DataFrame:
    if not (isinstance(x, dict) and x.get('__class__') == 'rpart'):
        raise TypeError('x must be an "rpart" object')
    _METHOD_HEADER = {
        'anova':   '\nRegression tree:\n',
        'class':   '\nClassification tree:\n',
        'poisson': '\nRates regression tree:\n',
        'exp':     '\nSurvival regression tree:\n',
    }
    print(_METHOD_HEADER[x['method']], end='')
    cl = x.get('call')
    if cl is not None:
        print(repr(cl))
        print()
    frame = x['frame']
    leaves = frame['var'] == '<leaf>'
    used = frame['var'][~leaves].unique()
    if used is not None and len(used) > 0:
        print('Variables actually used in tree construction:')
        print(sorted(str(v) for v in used))
        print()
    dev0 = frame['dev'].iloc[0]
    n0 = frame['n'].iloc[0]
    print(
        f'Root node error: {format(dev0, f".{digits}g")}/{n0} = '
        f'{format(dev0 / n0, f".{digits}g")}',
    )
    print()
    n = x['frame']['n']
    omit = x.get('na.action')
    if omit is not None and len(omit) > 0:
        n_omit = len(omit)
        noun = 'observation' if n_omit == 1 else 'observations'
        naprint_str = f'{n_omit} {noun} deleted due to missingness'
        print(f'n={n.iloc[0]} ({naprint_str})', end='\n\n')
    else:
        print(f'n={n.iloc[0]}', end='\n\n')
    cptable = x['cptable']
    if isinstance(cptable, pd.DataFrame):
        print(cptable.to_string(float_format=lambda v: format(v, f'.{digits}g')))
    else:
        col_names = ['CP', 'nsplit', 'rel error', 'xerror', 'xstd']
        row_names = [str(i + 1) for i in range(cptable.shape[0])]
        cptable_df = pd.DataFrame(cptable, index=row_names, columns=col_names[:cptable.shape[1]])
        print(cptable_df.to_string(float_format=lambda v: format(v, f'.{digits}g')))
    return x['cptable']
