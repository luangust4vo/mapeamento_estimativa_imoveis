"""Classificação de casas em faixas de aluguel, sem vazamento entre treino e teste.

O alvo recebido é o aluguel contínuo. ``QuantileBandClassifier`` calcula os
limites das faixas (quantis) dentro do ``fit``, ou seja, apenas com os dados de
treino de cada partição, e as métricas convertem o aluguel de validação/teste
com esses mesmos limites. Assim nenhuma faixa é definida olhando o teste.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import GridSearchCV, GroupKFold, GroupShuffleSplit
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

from .dataset import CATEGORICAL_FEATURES, NUMERIC_FEATURES, ModelData

BAND_NAMES = {2: ["baixa", "alta"], 3: ["baixa", "média", "alta"], 4: ["baixa", "média", "alta", "muito alta"],
              5: ["muito baixa", "baixa", "média", "alta", "muito alta"]}


class QuantileBandClassifier(ClassifierMixin, BaseEstimator):
    """Discretiza o aluguel em ``n_bands`` quantis do treino e ajusta ``estimator`` nas faixas."""

    def __init__(self, estimator=None, n_bands: int = 3):
        self.estimator = estimator
        self.n_bands = n_bands

    def fit(self, X, y):
        rent = np.asarray(y, dtype=float)
        self.thresholds_ = np.quantile(rent, np.linspace(0, 1, self.n_bands + 1)[1:-1])
        self.classes_ = np.arange(self.n_bands)
        self.estimator_ = clone(self.estimator).fit(X, self.to_bands(rent))
        return self

    def to_bands(self, rent) -> np.ndarray:
        """Faixa 0 = aluguel até o 1º limite (inclusive), e assim por diante."""
        return np.digitize(np.asarray(rent, dtype=float), self.thresholds_, right=True)

    def predict(self, X):
        return self.estimator_.predict(X)


class BairroModeClassifier(ClassifierMixin, BaseEstimator):
    """Baseline: prevê a faixa mais frequente do bairro no treino (ou a global, se o bairro for novo)."""

    def __init__(self, column: str = "bairro_oficial"):
        self.column = column

    def fit(self, X, y):
        bands = pd.Series(np.asarray(y), index=X.index)
        self.classes_ = np.unique(bands)
        self.global_ = bands.mode().min()
        self.modes_ = bands.groupby(X[self.column]).agg(lambda s: s.mode().min()).to_dict()
        return self

    def predict(self, X):
        return X[self.column].map(self.modes_).fillna(self.global_).astype(int).to_numpy()


def _band_metric(metric, **kwargs):
    def scorer(estimator, X, rent):
        return metric(estimator.to_bands(rent), estimator.predict(X), **kwargs)
    return scorer


SCORING = {
    "balanced_accuracy": _band_metric(balanced_accuracy_score),
    "f1_macro": _band_metric(f1_score, average="macro", zero_division=0),
    "accuracy": _band_metric(accuracy_score),
}


def preprocessor() -> ColumnTransformer:
    numeric = Pipeline([("imputar", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)),
                        ("padronizar", StandardScaler())])
    categorical = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    return ColumnTransformer([("num", numeric, NUMERIC_FEATURES), ("cat", categorical, CATEGORICAL_FEATURES)])


def model_specs(seed: int) -> dict[str, tuple[object, dict]]:
    """Modelos e grades de hiperparâmetros; todos recebem o mesmo pré-processamento."""
    def pipe(clf):
        return Pipeline([("prep", preprocessor()), ("clf", clf)])

    return {
        "baseline_classe_frequente": (DummyClassifier(strategy="most_frequent"), {}),
        "baseline_bairro": (BairroModeClassifier(), {}),
        "arvore_decisao": (pipe(DecisionTreeClassifier(random_state=seed)),
                           {"clf__max_depth": [3, 5, 8, None], "clf__min_samples_leaf": [1, 3, 5, 10]}),
        "knn": (pipe(KNeighborsClassifier()),
                {"clf__n_neighbors": [3, 5, 7, 11, 15], "clf__weights": ["uniform", "distance"]}),
        "svm": (pipe(SVC(random_state=seed)),
                {"clf__C": [0.1, 1, 10, 100], "clf__gamma": ["scale", 0.01, 0.1]}),
        "mlp": (pipe(MLPClassifier(max_iter=3000, random_state=seed)),
                {"clf__hidden_layer_sizes": [(16,), (32,), (32, 16)], "clf__alpha": [1e-4, 1e-2, 1.0]}),
    }


@dataclass
class ModelResult:
    name: str
    best_params: dict
    cv: dict[str, tuple[float, float]]      # métrica -> (média, desvio) nas 5 dobras
    test: dict[str, float]
    confusion: np.ndarray
    predictions: np.ndarray
    estimator: QuantileBandClassifier


@dataclass
class ExperimentResult:
    n_bands: int
    band_names: list[str]
    thresholds: np.ndarray
    seed: int
    dev_index: pd.Index
    test_index: pd.Index
    y_test_bands: np.ndarray
    results: dict[str, ModelResult]
    selected: str
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


def _test_metrics(y_true, y_pred) -> dict[str, float]:
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "precision_macro": precision_score(y_true, y_pred, average="macro", zero_division=0),
        "recall_macro": recall_score(y_true, y_pred, average="macro", zero_division=0),
        "f1_macro": f1_score(y_true, y_pred, average="macro", zero_division=0),
        # Faixas são ordenadas: errar por duas ou mais faixas é o erro mais grave.
        "erro_grave": float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred)) >= 2)),
    }


def run_experiment(data: ModelData, *, n_bands: int = 3, seed: int = 42, test_size: float = 0.2,
                   cv_splits: int = 5, specs: dict | None = None) -> ExperimentResult:
    if n_bands not in BAND_NAMES:
        raise ValueError(f"Número de faixas deve estar entre {min(BAND_NAMES)} e {max(BAND_NAMES)}.")
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    dev_pos, test_pos = next(splitter.split(data.X, data.y, data.groups))
    X_dev, X_test = data.X.iloc[dev_pos], data.X.iloc[test_pos]
    y_dev, y_test = data.y.iloc[dev_pos], data.y.iloc[test_pos]
    cv = GroupKFold(n_splits=cv_splits, shuffle=True, random_state=seed)
    results, notes = {}, []
    for name, (estimator, grid) in (specs or model_specs(seed)).items():
        search = GridSearchCV(QuantileBandClassifier(estimator, n_bands),
                              [{f"estimator__{k}": v for k, v in grid.items()}],
                              scoring=SCORING, refit="balanced_accuracy", cv=cv)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            search.fit(X_dev, y_dev, groups=data.groups.iloc[dev_pos])
        if any(issubclass(w.category, ConvergenceWarning) for w in caught):
            notes.append(f"{name}: alguma configuração da grade não convergiu (ConvergenceWarning).")
        i = search.best_index_
        cv_scores = {m: (float(search.cv_results_[f"mean_test_{m}"][i]), float(search.cv_results_[f"std_test_{m}"][i]))
                     for m in SCORING}
        model = search.best_estimator_
        y_true, y_pred = model.to_bands(y_test), model.predict(X_test)
        results[name] = ModelResult(
            name, {k.removeprefix("estimator__"): v for k, v in search.best_params_.items()}, cv_scores,
            _test_metrics(y_true, y_pred), confusion_matrix(y_true, y_pred, labels=np.arange(n_bands)),
            y_pred, model)
    # Seleção pela validação cruzada (nunca pelo teste); desempate pelo F1 macro.
    selected = max(results, key=lambda n: (results[n].cv["balanced_accuracy"][0], results[n].cv["f1_macro"][0]))
    reference = results[selected].estimator
    return ExperimentResult(n_bands, BAND_NAMES[n_bands], reference.thresholds_, seed,
                            data.X.index[dev_pos], data.X.index[test_pos], reference.to_bands(y_test),
                            results, selected, notes)


def feature_importance(experiment: ExperimentResult, data: ModelData, *, repeats: int = 30) -> pd.DataFrame:
    """Importância por permutação do modelo selecionado no teste (queda de balanced accuracy)."""
    model = experiment.results[experiment.selected].estimator
    X_test, y_test = data.X.loc[experiment.test_index], data.y.loc[experiment.test_index]
    scores = permutation_importance(model, X_test, y_test, scoring=SCORING["balanced_accuracy"],
                                    n_repeats=repeats, random_state=experiment.seed)
    return (pd.DataFrame({"atributo": X_test.columns, "importancia_media": scores.importances_mean,
                          "importancia_desvio": scores.importances_std})
            .sort_values("importancia_media", ascending=False, ignore_index=True))


def holdout_errors(experiment: ExperimentResult, data: ModelData) -> pd.DataFrame:
    """Previsões do modelo selecionado no teste, com os erros mais distantes primeiro."""
    result = experiment.results[experiment.selected]
    table = data.frame.loc[experiment.test_index].copy()
    names = np.array(experiment.band_names)
    table["faixa_real"] = names[experiment.y_test_bands]
    table["faixa_prevista"] = names[result.predictions]
    table["distancia_faixas"] = result.predictions - experiment.y_test_bands
    table["acertou"] = table.distancia_faixas.eq(0)
    return table.sort_values("distancia_faixas", key=np.abs, ascending=False)


def stability(data: ModelData, *, n_bands: int = 3, seeds=range(10), specs_factory=None) -> pd.DataFrame:
    """Repete o experimento inteiro (partição, busca e seleção) com várias sementes.

    Com poucas casas no teste, o resultado de uma única partição oscila bastante;
    a distribuição entre sementes mostra quanto da diferença entre modelos é robusta.
    """
    rows = []
    for seed in seeds:
        specs = specs_factory(seed) if specs_factory else None
        experiment = run_experiment(data, n_bands=n_bands, seed=seed, specs=specs)
        for name, result in experiment.results.items():
            rows.append({"semente": seed, "modelo": name, "selecionado": name == experiment.selected,
                         "cv_balanced_accuracy": result.cv["balanced_accuracy"][0],
                         "teste_balanced_accuracy": result.test["balanced_accuracy"],
                         "teste_f1_macro": result.test["f1_macro"], "teste_erro_grave": result.test["erro_grave"]})
    return pd.DataFrame(rows)


def stability_summary(runs: pd.DataFrame) -> pd.DataFrame:
    summary = runs.groupby("modelo").agg(
        cv_media=("cv_balanced_accuracy", "mean"), teste_media=("teste_balanced_accuracy", "mean"),
        teste_desvio=("teste_balanced_accuracy", "std"), teste_min=("teste_balanced_accuracy", "min"),
        teste_max=("teste_balanced_accuracy", "max"), f1_media=("teste_f1_macro", "mean"),
        erro_grave_medio=("teste_erro_grave", "mean"), vezes_selecionado=("selecionado", "sum"))
    return summary.sort_values("cv_media", ascending=False).reset_index()
