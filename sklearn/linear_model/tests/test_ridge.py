import numpy as np
import scipy.sparse as sp

from sklearn.utils.testing import assert_true
from sklearn.utils.testing import assert_almost_equal
from sklearn.utils.testing import assert_array_almost_equal
from sklearn.utils.testing import assert_equal
from sklearn.utils.testing import assert_array_equal
from sklearn.utils.testing import assert_greater
from sklearn.utils.testing import assert_raises

from sklearn import datasets
from sklearn.metrics import mean_squared_error

from sklearn.linear_model.base import LinearRegression
from sklearn.linear_model.ridge import ridge_regression
from sklearn.linear_model.ridge import Ridge
from sklearn.linear_model.ridge import _RidgeGCV
from sklearn.linear_model.ridge import RidgeCV
from sklearn.linear_model.ridge import RidgeClassifier
from sklearn.linear_model.ridge import RidgeClassifierCV


from sklearn.cross_validation import KFold

diabetes = datasets.load_diabetes()
X_diabetes, y_diabetes = diabetes.data, diabetes.target
ind = np.arange(X_diabetes.shape[0])
rng = np.random.RandomState(0)
rng.shuffle(ind)
ind = ind[:200]
X_diabetes, y_diabetes = X_diabetes[ind], y_diabetes[ind]

iris = datasets.load_iris()

X_iris = sp.csr_matrix(iris.data)
y_iris = iris.target

DENSE_FILTER = lambda X: X
SPARSE_FILTER = lambda X: sp.csr_matrix(X)


def test_ridge():
    """Ridge regression convergence test using score

    TODO: for this test to be robust, we should use a dataset instead
    of np.random.
    """
    rng = np.random.RandomState(0)
    alpha = 1.0

    for solver in ("svd", "sparse_cg", "dense_cholesky", "lsqr"):
        # With more samples than features
        n_samples, n_features = 6, 5
        y = rng.randn(n_samples)
        X = rng.randn(n_samples, n_features)

        ridge = Ridge(alpha=alpha, solver=solver)
        ridge.fit(X, y)
        assert_equal(ridge.coef_.shape, (X.shape[1], ))
        assert_greater(ridge.score(X, y), 0.47)

        ridge.fit(X, y, sample_weight=np.ones(n_samples))
        assert_greater(ridge.score(X, y), 0.47)

        # With more features than samples
        n_samples, n_features = 5, 10
        y = rng.randn(n_samples)
        X = rng.randn(n_samples, n_features)
        ridge = Ridge(alpha=alpha, solver=solver)
        ridge.fit(X, y)
        assert_greater(ridge.score(X, y), .9)

        ridge.fit(X, y, sample_weight=np.ones(n_samples))
        assert_greater(ridge.score(X, y), 0.9)


def test_ridge_sample_weights():
    rng = np.random.RandomState(0)
    alpha = 1.0

    for solver in ("svd", "sparse_cg", "dense_cholesky", "lsqr"):
        for n_samples, n_features in ((6, 5), (5, 10)):
            y = rng.randn(n_samples)
            X = rng.randn(n_samples, n_features)
            sample_weight = 1 + rng.rand(n_samples)

            coefs = ridge_regression(X, y, alpha, sample_weight,
                                     solver=solver)
            # Sample weight can be implemented via a simple rescaling
            # for the square loss
            coefs2 = ridge_regression(
                X * np.sqrt(sample_weight)[:, np.newaxis],
                y * np.sqrt(sample_weight),
                alpha, solver=solver)
            assert_array_almost_equal(coefs, coefs2)


def test_ridge_shapes():
    """Test shape of coef_ and intercept_
    """
    rng = np.random.RandomState(0)
    n_samples, n_features = 5, 10
    X = rng.randn(n_samples, n_features)
    y = rng.randn(n_samples)
    Y1 = y[:, np.newaxis]
    Y = np.c_[y, 1 + y]

    ridge = Ridge()

    ridge.fit(X, y)
    assert_equal(ridge.coef_.shape, (n_features,))
    assert_equal(ridge.intercept_.shape, ())

    ridge.fit(X, Y1)
    assert_equal(ridge.coef_.shape, (1, n_features))
    assert_equal(ridge.intercept_.shape, (1, ))

    ridge.fit(X, Y)
    assert_equal(ridge.coef_.shape, (2, n_features))
    assert_equal(ridge.intercept_.shape, (2, ))


def test_ridge_intercept():
    """Test intercept with multiple targets GH issue #708
    """
    rng = np.random.RandomState(0)
    n_samples, n_features = 5, 10
    X = rng.randn(n_samples, n_features)
    y = rng.randn(n_samples)
    Y = np.c_[y, 1. + y]

    ridge = Ridge()

    ridge.fit(X, y)
    intercept = ridge.intercept_

    ridge.fit(X, Y)
    assert_almost_equal(ridge.intercept_[0], intercept)
    assert_almost_equal(ridge.intercept_[1], intercept + 1.)


def test_toy_ridge_object():
    """Test BayesianRegression ridge classifier

    TODO: test also n_samples > n_features
    """
    X = np.array([[1], [2]])
    Y = np.array([1, 2])
    clf = Ridge(alpha=0.0)
    clf.fit(X, Y)
    X_test = [[1], [2], [3], [4]]
    assert_almost_equal(clf.predict(X_test), [1., 2, 3, 4])

    assert_equal(len(clf.coef_.shape), 1)
    assert_equal(type(clf.intercept_), np.float64)

    Y = np.vstack((Y, Y)).T

    clf.fit(X, Y)
    X_test = [[1], [2], [3], [4]]

    assert_equal(len(clf.coef_.shape), 2)
    assert_equal(type(clf.intercept_), np.ndarray)


def test_ridge_vs_lstsq():
    """On alpha=0., Ridge and OLS yield the same solution."""

    rng = np.random.RandomState(0)
    # we need more samples than features
    n_samples, n_features = 5, 4
    y = rng.randn(n_samples)
    X = rng.randn(n_samples, n_features)

    ridge = Ridge(alpha=0., fit_intercept=False)
    ols = LinearRegression(fit_intercept=False)

    ridge.fit(X, y)
    ols.fit(X, y)
    assert_almost_equal(ridge.coef_, ols.coef_)

    ridge.fit(X, y)
    ols.fit(X, y)
    assert_almost_equal(ridge.coef_, ols.coef_)


def test_ridge_multi_target_individual_penalties():
    """Test multi-target, individual penalties ridge"""

    rng = np.random.RandomState(42)
    n_samples, n_features, n_targets, n_penalties = 20, 10, 5, 3
    X = rng.randn(n_samples, n_features)
    y = rng.randn(n_samples, n_targets)

    penalties = np.arange(n_targets * n_penalties).reshape(
        n_targets, n_penalties).T

    # calculate coefs using cholesky ridge:
    coefs = np.empty([n_penalties, n_targets, n_features])
    for t, (target, ps) in enumerate(zip(y.T, penalties.T)):
        for i, p in enumerate(ps):
            coefs[i, t] = ridge_regression(X, target, p,
                                           solver='dense_cholesky')
    assert_array_almost_equal(coefs,
                        ridge_regression(X, y, penalties, solver='svd'))


def test_ridge_path():
    """Test multiple penalties on one target"""

    rng = np.random.RandomState(42)
    n_samples, n_features, n_penalties = 10, 20, 1000
    pen_min, pen_max = .001, 1000

    X = rng.randn(n_samples, n_features)
    y = rng.randn(n_samples)

    penalties = np.logspace(np.log10(pen_min), np.log10(pen_max),
                            n_penalties)

    cholesky_path = np.empty([len(penalties), n_features])
    for c, p in zip(cholesky_path, penalties):
        c[:] = ridge_regression(X, y, p, solver='dense_cholesky')

    assert_array_almost_equal(cholesky_path,
                ridge_regression(X, y, penalties, solver='svd'))


def _test_ridge_loo(filter_):
    # test that can work with both dense or sparse matrices
    n_samples = X_diabetes.shape[0]

    ret = []

    ridge_gcv = _RidgeGCV(fit_intercept=False)
    ridge = Ridge(alpha=1.0, fit_intercept=False)

    # generalized cross-validation (efficient leave-one-out)
    decomp = ridge_gcv._pre_compute(X_diabetes, y_diabetes)
    errors, c = ridge_gcv._errors(1.0, y_diabetes, *decomp)
    values, c = ridge_gcv._values(1.0, y_diabetes, *decomp)

    # brute-force leave-one-out: remove one example at a time
    errors2 = []
    values2 = []
    for i in range(n_samples):
        sel = np.arange(n_samples) != i
        X_new = X_diabetes[sel]
        y_new = y_diabetes[sel]
        ridge.fit(X_new, y_new)
        value = ridge.predict([X_diabetes[i]])[0]
        error = (y_diabetes[i] - value) ** 2
        errors2.append(error)
        values2.append(value)

    # check that efficient and brute-force LOO give same results
    assert_almost_equal(errors, errors2)
    assert_almost_equal(values, values2)

    # generalized cross-validation (efficient leave-one-out,
    # SVD variation)
    decomp = ridge_gcv._pre_compute_svd(X_diabetes, y_diabetes)
    errors3, c = ridge_gcv._errors_svd(ridge.alpha, y_diabetes, *decomp)
    values3, c = ridge_gcv._values_svd(ridge.alpha, y_diabetes, *decomp)

    # check that efficient and SVD efficient LOO give same results
    assert_almost_equal(errors, errors3)
    assert_almost_equal(values, values3)

    # check best alpha
    ridge_gcv.fit(filter_(X_diabetes), y_diabetes)
    alpha_ = ridge_gcv.alpha_
    ret.append(alpha_)

    # check that we get same best alpha with custom loss_func
    ridge_gcv2 = RidgeCV(fit_intercept=False, loss_func=mean_squared_error)
    ridge_gcv2.fit(filter_(X_diabetes), y_diabetes)
    assert_equal(ridge_gcv2.alpha_, alpha_)

    # check that we get same best alpha with custom score_func
    func = lambda x, y: -mean_squared_error(x, y)
    ridge_gcv3 = RidgeCV(fit_intercept=False, score_func=func)
    ridge_gcv3.fit(filter_(X_diabetes), y_diabetes)
    assert_equal(ridge_gcv3.alpha_, alpha_)

    # check that we get same best alpha with sample weights
    ridge_gcv.fit(filter_(X_diabetes), y_diabetes,
                  sample_weight=np.ones(n_samples))
    assert_equal(ridge_gcv.alpha_, alpha_)

    # simulate several responses
    Y = np.vstack((y_diabetes, y_diabetes)).T

    ridge_gcv.fit(filter_(X_diabetes), Y)
    Y_pred = ridge_gcv.predict(filter_(X_diabetes))
    ridge_gcv.fit(filter_(X_diabetes), y_diabetes)
    y_pred = ridge_gcv.predict(filter_(X_diabetes))

    assert_array_almost_equal(np.vstack((y_pred, y_pred)).T,
                              Y_pred, decimal=5)

    return ret


def _test_ridge_cv(filter_):
    n_samples = X_diabetes.shape[0]

    ridge_cv = RidgeCV()
    ridge_cv.fit(filter_(X_diabetes), y_diabetes)
    ridge_cv.predict(filter_(X_diabetes))

    assert_equal(len(ridge_cv.coef_.shape), 1)
    assert_equal(type(ridge_cv.intercept_), np.float64)

    cv = KFold(n_samples, 5)
    ridge_cv.set_params(cv=cv)
    ridge_cv.fit(filter_(X_diabetes), y_diabetes)
    ridge_cv.predict(filter_(X_diabetes))

    assert_equal(len(ridge_cv.coef_.shape), 1)
    assert_equal(type(ridge_cv.intercept_), np.float64)


def _test_ridge_diabetes(filter_):
    ridge = Ridge(fit_intercept=False)
    ridge.fit(filter_(X_diabetes), y_diabetes)
    return np.round(ridge.score(filter_(X_diabetes), y_diabetes), 5)


def _test_multi_ridge_diabetes(filter_):
    # simulate several responses
    Y = np.vstack((y_diabetes, y_diabetes)).T
    n_features = X_diabetes.shape[1]

    ridge = Ridge(fit_intercept=False)
    ridge.fit(filter_(X_diabetes), Y)
    assert_equal(ridge.coef_.shape, (2, n_features))
    Y_pred = ridge.predict(filter_(X_diabetes))
    ridge.fit(filter_(X_diabetes), y_diabetes)
    y_pred = ridge.predict(filter_(X_diabetes))
    assert_array_almost_equal(np.vstack((y_pred, y_pred)).T,
                              Y_pred, decimal=3)


def _test_ridge_classifiers(filter_):
    n_classes = np.unique(y_iris).shape[0]
    n_features = X_iris.shape[1]
    for clf in (RidgeClassifier(), RidgeClassifierCV()):
        clf.fit(filter_(X_iris), y_iris)
        assert_equal(clf.coef_.shape, (n_classes, n_features))
        y_pred = clf.predict(filter_(X_iris))
        assert_greater(np.mean(y_iris == y_pred), .79)

    n_samples = X_iris.shape[0]
    cv = KFold(n_samples, 5)
    clf = RidgeClassifierCV(cv=cv)
    clf.fit(filter_(X_iris), y_iris)
    y_pred = clf.predict(filter_(X_iris))
    assert_true(np.mean(y_iris == y_pred) >= 0.8)


def _test_tolerance(filter_):
    ridge = Ridge(tol=1e-5)
    ridge.fit(filter_(X_diabetes), y_diabetes)
    score = ridge.score(filter_(X_diabetes), y_diabetes)

    ridge2 = Ridge(tol=1e-3)
    ridge2.fit(filter_(X_diabetes), y_diabetes)
    score2 = ridge2.score(filter_(X_diabetes), y_diabetes)

    assert_true(score >= score2)


def test_dense_sparse():
    for test_func in (_test_ridge_loo,
                      _test_ridge_cv,
                      _test_ridge_diabetes,
                      _test_multi_ridge_diabetes,
                      _test_ridge_classifiers,
                      _test_tolerance):
        # test dense matrix
        ret_dense = test_func(DENSE_FILTER)
        # test sparse matrix
        ret_sparse = test_func(SPARSE_FILTER)
        # test that the outputs are the same
        if ret_dense is not None and ret_sparse is not None:
            assert_array_almost_equal(ret_dense, ret_sparse, decimal=3)


def test_ridge_cv_sparse_svd():
    X = sp.csr_matrix(X_diabetes)
    ridge = RidgeCV(gcv_mode="svd")
    assert_raises(TypeError, ridge.fit, X)


def test_class_weights():
    """
    Test class weights.
    """
    X = np.array([[-1.0, -1.0], [-1.0, 0], [-.8, -1.0],
                  [1.0, 1.0], [1.0, 0.0]])
    y = [1, 1, 1, -1, -1]

    clf = RidgeClassifier(class_weight=None)
    clf.fit(X, y)
    assert_array_equal(clf.predict([[0.2, -1.0]]), np.array([1]))

    # we give a small weights to class 1
    clf = RidgeClassifier(class_weight={1: 0.001})
    clf.fit(X, y)

    # now the hyperplane should rotate clock-wise and
    # the prediction on this point should shift
    assert_array_equal(clf.predict([[0.2, -1.0]]), np.array([-1]))


def test_class_weights_cv():
    """
    Test class weights for cross validated ridge classifier.
    """
    X = np.array([[-1.0, -1.0], [-1.0, 0], [-.8, -1.0],
                  [1.0, 1.0], [1.0, 0.0]])
    y = [1, 1, 1, -1, -1]

    clf = RidgeClassifierCV(class_weight=None, alphas=[.01, .1, 1])
    clf.fit(X, y)

    # we give a small weights to class 1
    clf = RidgeClassifierCV(class_weight={1: 0.001}, alphas=[.01, .1, 1, 10])
    clf.fit(X, y)

    assert_array_equal(clf.predict([[-.2, 2]]), np.array([-1]))


def test_ridgecv_store_cv_values():
    """
    Test _RidgeCV's store_cv_values attribute.
    """
    rng = rng = np.random.RandomState(42)

    n_samples = 8
    n_features = 5
    x = rng.randn(n_samples, n_features)
    alphas = [1e-1, 1e0, 1e1]
    n_alphas = len(alphas)

    r = RidgeCV(alphas=alphas, store_cv_values=True)

    # with len(y.shape) == 1
    y = rng.randn(n_samples)
    r.fit(x, y)
    assert_equal(r.cv_values_.shape, (n_samples, n_alphas))

    # with len(y.shape) == 2
    n_responses = 3
    y = rng.randn(n_samples, n_responses)
    r.fit(x, y)
    assert_equal(r.cv_values_.shape, (n_samples, n_responses, n_alphas))
