# -*- coding: utf-8 -*-
''' Gaussian Noise Component

This module contains the class for Gaussian Noise

Author: Bennet Meyers
'''

import cvxpy as cvx
import numpy as np
from osd.components.component import Component

class Blank(Component):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        return

    @property
    def is_convex(self):
        return True

    def _get_cost(self):
        return lambda x: 0

    def prox_op(self, v, theta, rho):
        r = rho / (2 * theta + rho)
        return v