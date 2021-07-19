# -*- coding: utf-8 -*-
''' Data Handler Module

This module contains a class for defining a signal demixing optimization problem


Author: Bennet Meyers
'''

import numpy as np
import cvxpy as cvx
from itertools import chain
import abc
from scipy.optimize import minimize_scalar
from osd.signal_decomp_admm import run_admm
from osd.utilities import compose
import matplotlib.pyplot as plt

class Problem():
    def __init__(self, data, components, residual_term=0):
        self.data = data
        self.components = [c() if type(c) is abc.ABCMeta else c
                           for c in components]
        self.num_components = len(components)
        self.parameters = {i: c.parameters for i, c in enumerate(self.components)
                           if c.parameters is not None}
        self.num_parameters = int(
            np.sum([len(value) if value is not None else 0
                    for key, value in self.parameters.items()])
        )
        self.estimates = None
        self.problem = None
        self.admm_result = None
        K = self.num_components
        # TODO: refactor this so that weights used for CVX solve are the same
        #  as the thetas associated with each class
        self.weights = cvx.Parameter(shape=K, nonneg=True, value=[1]*K)
        self.residual_term = residual_term

    def decompose(self, use_set=None, reset=False, admm=False,
                  num_iter=50, rho=0.5, verbose=True,
                  randomize_start=False, X_init=None, stop_early=False,
                  **cvx_kwargs):
        if np.alltrue([c.is_convex for c in self.components]) and not admm:
            self.weights.value = [c.theta for c in self.components]
            if self.problem is None or reset:
                problem = self.__construct_cvx_problem(use_set=use_set)
                self.problem = problem
            else:
                problem = self.problem
            if X_init is not None:
                cvx_kwargs['warm_start'] = True
                for ix, x in enumerate(problem.variables()):
                    x.value = X_init[ix, :]
            problem.solve(**cvx_kwargs)
            ests = np.array([x.value for x in problem.variables()])
            self.estimates = ests
        elif admm:
            result = run_admm(
                self.data, self.components, num_iter=num_iter, rho=rho,
                use_ix=use_set, verbose=verbose,
                randomize_start=randomize_start, X_init=X_init,
                stop_early=stop_early
            )
            self.admm_result = result
            self.estimates = result['X']
        else:
            m1 = 'This problem is non-convex and not solvable with CVXPY. '
            m2 = 'Please try solving with ADMM.'
            print(m1 + m2)

    def plot_decomposition(self, X_real=None, figsize=(10, 8)):
        K = len(self.components)
        fig, ax = plt.subplots(nrows=K + 1, sharex=True, figsize=figsize)
        for k in range(K + 1):
            if k < K:
                est = self.estimates[k]
                ax[k].plot(est, label='estimated', linewidth=1)
                ax[k].set_title('Component $x^{}$'.format(k + 1))
                if X_real is not None:
                    true = X_real[k]
                    ax[k].plot(true, label='true', linewidth=1)
            else:
                ax[k].plot(self.data, label='observed, $y$',
                           linewidth=1, alpha=0.3, marker='.', color='green')
                ax[k].plot(np.sum(self.estimates[1:], axis=0),
                           label='estimated', linewidth=1)
                if X_real is not None:
                    ax[k].plot(np.sum(X_real[1:], axis=0), label='true', linewidth=1)
                ax[k].set_title('Composed Signal')
            ax[k].legend()
        plt.tight_layout()
        return fig

    def optimize_weights(self, solver='ECOS', seed=None):
        if seed is None:
            seed = np.random.random_integers(0, 1000)
        if self.num_components == 2:
            search_ix = 1 - self.residual_term
            _ = self.holdout_validation(solver=solver, seed=seed)
            new_vals = np.ones(2)

            def cost_meta(v):
                val = 10 ** v
                new_vals[search_ix] = val
                self.weights.value = new_vals
                cost = self.holdout_validation(solver=solver, seed=seed,
                                               reuse=True)
                return cost
            res = minimize_scalar(cost_meta, bounds=(-2, 10), method='bounded')
            best_val = 10 ** res.x
            new_vals[search_ix] = best_val
            self.weights.value = new_vals
            self.demix(solver=solver, reset=True)
            return
        else:
            print('IN PROGRESS')

    def optimize_parameters(self, solver='ECOS', seed=None):
        if seed is None:
            seed = np.random.random_integers(0, 1000)
        if self.num_parameters == 1:
            k1, k2 = [(k1, k2) for k1, value in self.parameters.items()
                      for k2 in value.keys()][0]
            _ = self.holdout_validation(solver=solver, seed=seed)
            def cost_meta(val):
                self.parameters[k1][k2].value = val
                cost = self.holdout_validation(solver=solver, seed=seed,
                                               reuse=True)
                return cost
            res = minimize_scalar(cost_meta, bounds=(0, 1), method='bounded')
            best_val = res.x
            self.parameters[k1][k2].value = best_val
            self.decompose(solver=solver, reset=True)
            return
        else:
            print('IN PROGRESS')

    def holdout_validation(self, holdout=0.2, seed=None, solver='ECOS',
                               reuse=False, cost=None, admm=False):
        T = len(self.data)
        if seed is not None:
            np.random.seed(seed)
        hold_set = np.random.uniform(0, 1, T) <= holdout
        use_set = ~hold_set
        if not reuse:
            self.decompose(solver=solver, use_set=use_set, admm=admm, reset=True)
        else:
            self.decompose(solver=solver, admm=admm, reset=False)
        est_array = np.array(self.estimates)
        hold_est = np.sum(est_array[:, hold_set], axis=0)
        hold_y = self.data[hold_set]
        residuals = hold_y - hold_est
        if cost is None:
            resid_cost = self.components[self.residual_term].cost
        elif cost == 'l1':
            resid_cost = compose(cvx.sum, cvx.abs)
        elif cost == 'l2':
            resid_cost = cvx.sum_squares
        holdout_cost = resid_cost(residuals).value
        return holdout_cost.item()

    def __construct_cvx_problem(self, use_set=None):
        if use_set is None:
            use_set = np.s_[:]
        y = self.data
        T = len(y)
        K = self.num_components
        weights = self.weights
        xs = [cvx.Variable(T) for _ in range(K)]
        costs = [c.cost(x) for c, x in zip(self.components, xs)]
        costs = [weights[i] * cost for i, cost in enumerate(costs)]
        constraints = [c.make_constraints(x) for c, x in zip(self.components, xs)]
        constraints = list(chain.from_iterable(constraints))
        constraints.append(cvx.sum([x[use_set] for x in xs], axis=0) == y[use_set])
        objective = cvx.Minimize(cvx.sum(costs))
        problem = cvx.Problem(objective, constraints)
        return problem
