"""Regressão do aluguel em reais, com o mesmo protocolo sem vazamento da classificação.

O alvo é o log do aluguel (forte assimetria à direita); ``TransformedTargetRegressor``
devolve as previsões em reais, e todas as métricas são calculadas em reais.
O intervalo de previsão vem dos resíduos fora da amostra no treino e tem a
cobertura verificada no teste reservado.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.compose import TransformedTargetRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error, mean_squared_error, r2_score
from sklearn.model_selection import GridSearchCV, GroupKFold, GroupShuffleSplit
from sklearn.neighbors import KNeighborsRegressor
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import Pipeline
from sklearn.svm import SVR
from sklearn.tree import DecisionTreeRegressor

from .classificacao import preprocessor
from .dataset import ModelData

INTERVAL = (0.10, 0.90)   # intervalo de previsão de 80%
SCORING = {"mae": "neg_mean_absolute_error", "rmse": "neg_root_mean_squared_error",
           "mape": "neg_mean_absolute_percentage_error", "r2": "r2"}


class BairroMedianRegressor(RegressorMixin, BaseEstimator):
    """Referência: aluguel mediano do bairro no treino (ou o global, se o bairro for novo)."""

    def __init__(self, column: str = "bairro_oficial"):
        self.column = column

    def fit(self, X, y):
        rent = pd.Series(np.asarray(y, dtype=float), index=X.index)
        self.global_ = float(rent.median())
        self.medians_ = rent.groupby(X[self.column]).median().to_dict()
        return self

    def predict(self, X):
        return X[self.column].map(self.medians_).fillna(self.global_).to_numpy(dtype=float)


def log_target(regressor) -> TransformedTargetRegressor:
    return TransformedTargetRegressor(regressor=regressor, func=np.log, inverse_func=np.exp)


def regression_specs(seed: int) -> dict[str, tuple[object, dict]]:
    """Modelos e grades; todos usam o mesmo pré-processamento e o alvo em log."""
    def pipe(model):
        return log_target(Pipeline([("prep", preprocessor()), ("reg", model)]))

    return {
        "baseline_mediana_bairro": (BairroMedianRegressor(), {}),
        "regressao_linear": (pipe(Ridge()), {"regressor__reg__alpha": [0.1, 1.0, 10.0]}),
        "arvore_decisao": (pipe(DecisionTreeRegressor(random_state=seed)),
                           {"regressor__reg__max_depth": [3, 5, 8, None],
                            "regressor__reg__min_samples_leaf": [1, 3, 5, 10]}),
        "knn": (pipe(KNeighborsRegressor()),
                {"regressor__reg__n_neighbors": [3, 5, 7, 11, 15],
                 "regressor__reg__weights": ["uniform", "distance"]}),
        "svr": (pipe(SVR()), {"regressor__reg__C": [0.1, 1, 10, 100],
                              "regressor__reg__gamma": ["scale", 0.01, 0.1],
                              "regressor__reg__epsilon": [0.05, 0.1]}),
        "mlp": (pipe(MLPRegressor(max_iter=3000, random_state=seed)),
                {"regressor__reg__hidden_layer_sizes": [(16,), (32,), (32, 16)],
                 "regressor__reg__alpha": [1e-4, 1e-2, 1.0]}),
    }


def metrics(y_true, y_pred) -> dict[str, float]:
    y_true, y_pred = np.asarray(y_true, float), np.asarray(y_pred, float)
    return {"mae": float(mean_absolute_error(y_true, y_pred)),
            "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
            "mape": float(mean_absolute_percentage_error(y_true, y_pred)),
            "r2": float(r2_score(y_true, y_pred)),
            "erro_mediano": float(np.median(np.abs(y_true - y_pred)))}


def oof_log_residuals(model, X, y, groups, cv) -> np.ndarray:
    """Resíduos log(real/previsto) de previsões fora da amostra (cada casa prevista sem ser vista)."""
    residuals = np.empty(len(y))
    for train, test in cv.split(X, y, groups):
        fitted = clone(model).fit(X.iloc[train], y.iloc[train])
        residuals[test] = np.log(y.iloc[test].to_numpy() / fitted.predict(X.iloc[test]))
    return residuals


@dataclass
class RegressionResult:
    name: str
    best_params: dict
    cv: dict[str, tuple[float, float]]
    test: dict[str, float]
    predictions: np.ndarray
    estimator: object


@dataclass
class RegressionExperiment:
    seed: int
    dev_index: pd.Index
    test_index: pd.Index
    results: dict[str, RegressionResult]
    selected: str
    interval_log: tuple[float, float]      # quantis dos resíduos log fora da amostra (modelo selecionado)
    interval_coverage: float               # fração do teste dentro do intervalo
    warnings: list[str] = field(default_factory=list)

    def metrics_table(self) -> pd.DataFrame:
        rows = []
        for name, result in self.results.items():
            row = {"modelo": name, "selecionado": name == self.selected}
            for metric, (mean, std) in result.cv.items():
                row[f"cv_{metric}_media"], row[f"cv_{metric}_desvio"] = mean, std
            row.update({f"teste_{k}": v for k, v in result.test.items()})
            row["melhores_parametros"] = str(result.best_params)
            rows.append(row)
        return pd.DataFrame(rows)


def run_regression(data: ModelData, *, seed: int = 42, test_size: float = 0.2, cv_splits: int = 5,
                   specs: dict | None = None) -> RegressionExperiment:
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    dev_pos, test_pos = next(splitter.split(data.X, data.y, data.groups))
    X_dev, X_test = data.X.iloc[dev_pos], data.X.iloc[test_pos]
    y_dev, y_test = data.y.iloc[dev_pos], data.y.iloc[test_pos]
    groups_dev = data.groups.iloc[dev_pos]
    cv = GroupKFold(n_splits=cv_splits, shuffle=True, random_state=seed)
    results, notes = {}, []
    for name, (estimator, grid) in (specs or regression_specs(seed)).items():
        search = GridSearchCV(estimator, [grid] if grid else [{}], scoring=SCORING, refit="mae", cv=cv)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            search.fit(X_dev, y_dev, groups=groups_dev)
        if any(issubclass(w.category, ConvergenceWarning) for w in caught):
            notes.append(f"{name}: alguma configuração da grade não convergiu (ConvergenceWarning).")
        i = search.best_index_
        # scikit-learn maximiza: erros vêm negativos e voltam ao sinal natural aqui.
        cv_scores = {m: ((1 if m == "r2" else -1) * float(search.cv_results_[f"mean_test_{m}"][i]),
                         float(search.cv_results_[f"std_test_{m}"][i])) for m in SCORING}
        predictions = search.best_estimator_.predict(X_test)
        results[name] = RegressionResult(
            name, {k.split("__")[-1]: v for k, v in search.best_params_.items()}, cv_scores,
            metrics(y_test, predictions), predictions, search.best_estimator_)
    # Seleção pelo menor MAE médio na validação cruzada (nunca pelo teste).
    selected = min(results, key=lambda n: results[n].cv["mae"][0])
    best = results[selected].estimator
    residuals = oof_log_residuals(best, X_dev, y_dev, groups_dev, cv)
    low, high = (float(q) for q in np.quantile(residuals, INTERVAL))
    pred = results[selected].predictions
    inside = (y_test.to_numpy() >= pred * np.exp(low)) & (y_test.to_numpy() <= pred * np.exp(high))
    return RegressionExperiment(seed, data.X.index[dev_pos], data.X.index[test_pos], results, selected,
                                (low, high), float(inside.mean()), notes)


def regression_stability(data: ModelData, *, seeds=range(10), specs_factory=None) -> pd.DataFrame:
    rows = []
    for seed in seeds:
        exp = run_regression(data, seed=seed, specs=specs_factory(seed) if specs_factory else None)
        for name, result in exp.results.items():
            rows.append({"semente": seed, "modelo": name, "selecionado": name == exp.selected,
                         "cv_mae": result.cv["mae"][0], **{f"teste_{k}": v for k, v in result.test.items()},
                         "cobertura_intervalo": exp.interval_coverage if name == exp.selected else np.nan})
    return pd.DataFrame(rows)


def stability_summary(runs: pd.DataFrame) -> pd.DataFrame:
    summary = runs.groupby("modelo").agg(
        cv_mae=("cv_mae", "mean"), teste_mae=("teste_mae", "mean"), teste_mae_desvio=("teste_mae", "std"),
        teste_mape=("teste_mape", "mean"), teste_r2=("teste_r2", "mean"),
        teste_erro_mediano=("teste_erro_mediano", "mean"), vezes_selecionado=("selecionado", "sum"),
        cobertura_media=("cobertura_intervalo", "mean"))
    return summary.sort_values("cv_mae").reset_index()


def residual_analysis(experiment: RegressionExperiment, data: ModelData,
                      band_limits: list[float]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Erros do modelo selecionado no teste: por casa, por bairro e por faixa de preço real."""
    result = experiment.results[experiment.selected]
    table = data.frame.loc[experiment.test_index].copy()
    table["previsto"] = result.predictions
    table["erro"] = table.previsto - table.aluguel
    table["erro_percentual"] = table.erro / table.aluguel
    names = ["baixa", "média", "alta", "muito alta", "extra"][:len(band_limits) + 1]
    table["faixa_real"] = np.array(names)[np.digitize(table.aluguel, band_limits, right=True)]

    def summarize(group):
        return pd.Series({"n": len(group), "mae": group.erro.abs().mean(),
                          "mape": group.erro_percentual.abs().mean(),
                          "vies_mediano": group.erro_percentual.median()})

    by_bairro = table.groupby("bairro_oficial")[["erro", "erro_percentual"]].apply(summarize).sort_values("n", ascending=False)
    by_band = table.groupby("faixa_real")[["erro", "erro_percentual"]].apply(summarize).reindex(names).dropna(how="all")
    return table.sort_values("erro_percentual", key=np.abs, ascending=False), by_bairro, by_band
