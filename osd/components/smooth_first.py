# -*- coding: utf-8 -*-
''' Smooth Component (1)

This module contains the class for a smooth signal that is penalized for large
first-order differences

Author: Bennet Meyers
'''

import scipy.linalg as spl
import numpy as np
import cvxpy as cvx
from functools import partial
from osd.components.component import Component
from osd.utilities import compose

class SmoothFirstDifference(Component):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._c = None
        self._last_weight = None
        self._last_rho = None
        return

    @property
    def is_convex(self):
        return True

    def _get_cost(self):
        diff1 = partial(cvx.diff, k=1)
        cost = compose(cvx.sum_squares, diff1)
        return cost

    def prox_op(self, v, weight, rho):
        c = self._c
        cond1 = c is None
        cond2 = self._last_weight != weight
        cond3 = self._last_rho != rho
        if cond1 or cond2 or cond3:
            n = len(v)
            M = np.diff(np.eye(n), axis=0, n=1)
            r = 2 * weight / rho
            ab = np.zeros((2, n))
            A = np.eye(n) + r * M.T.dot(M)
            for i in range(2):
                ab[i] = np.pad(np.diag(A, k=i), (0, i))
            c = spl.cholesky_banded(ab, lower=True)
            self._c = c
        return spl.cho_solve_banded((c, True), v)