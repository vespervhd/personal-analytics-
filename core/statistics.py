"""Per-column statistics and dataset-level numeric helpers.

All results are plain Python types (no numpy scalars, no NaN) so they can
go straight into JSON, the database, or a report. NaN statistics (e.g.
skew of a constant column) become ``None`` instead of leaking NaN.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from utils.logger import get_logger

log = get_logger("statistics")


class StatisticsError(ValueError):
    """Raised when a statistic cannot be computed from the given data."""


def _clean(value) -> float | int | None:
    """Convert a numpy scalar to a JSON-safe Python value (NaN -> None)."""
    if value is None:
        return None
    number = float(value)
    if np.isnan(number) or np.isinf(number):
        return None
    return number


def _first_mode(series: pd.Series):
    modes = series.mode(dropna=True)
    return modes.iloc[0] if len(modes) else None


def describe_numeric(series: pd.Series) -> dict:
    """Full numeric summary: centre, spread, range, shape."""
    clean = series.dropna()
    if len(clean) == 0:
        raise StatisticsError(f"Column '{series.name}' has no non-null values.")
    result = {
        "count": int(clean.count()),
        "missing": int(series.isna().sum()),
        "mean": _clean(clean.mean()),
        "median": _clean(clean.median()),
        "mode": _first_mode(clean),
        "std": _clean(clean.std()),
        "min": _clean(clean.min()),
        "max": _clean(clean.max()),
        "q1": _clean(clean.quantile(0.25)),
        "q3": _clean(clean.quantile(0.75)),
        "skew": _clean(scipy_stats.skew(clean, nan_policy="omit")),
        "kurtosis": _clean(scipy_stats.kurtosis(clean, nan_policy="omit")),
    }
    # Mode may be a numpy scalar; normalise it for JSON safety.
    mode = result["mode"]
    result["mode"] = None if mode is None else (
        mode.item() if hasattr(mode, "item") else mode
    )
    return result


def describe_categorical(series: pd.Series) -> dict:
    """Categorical summary: counts, uniques, and most frequent values."""
    clean = series.dropna()
    counts = clean.value_counts()
    top = counts.head(5)
    return {
        "count": int(clean.count()),
        "missing": int(series.isna().sum()),
        "unique": int(clean.nunique()),
        "top_value": None if len(counts) == 0 else str(counts.index[0]),
        "top_frequency": int(counts.iloc[0]) if len(counts) else 0,
        "top_values": {str(k): int(v) for k, v in top.items()},
    }


def column_summary(df: pd.DataFrame) -> dict[str, dict]:
    """One summary per column, numeric- or categorical-aware."""
    summaries: dict[str, dict] = {}
    for column in df.columns:
        series = df[column]
        if pd.api.types.is_bool_dtype(series):
            summaries[str(column)] = {"type": "categorical", **describe_categorical(series)}
        elif pd.api.types.is_numeric_dtype(series):
            summaries[str(column)] = {"type": "numeric", **describe_numeric(series)}
        else:
            summaries[str(column)] = {"type": "categorical", **describe_categorical(series)}
    log.info("column_summary built for {} columns", len(summaries))
    return summaries


def correlation_matrix(
    df: pd.DataFrame, columns: list[str] | None = None, method: str = "pearson"
) -> pd.DataFrame:
    """Correlation matrix over numeric columns (default: all numeric)."""
    numeric = df.select_dtypes(include="number")
    targets = columns if columns else list(numeric.columns)
    unknown = [c for c in targets if c not in df.columns]
    if unknown:
        raise StatisticsError(f"Unknown columns: {unknown}")
    non_numeric = [c for c in targets if c not in numeric.columns]
    if non_numeric:
        raise StatisticsError(f"Correlation needs numeric columns: {non_numeric}")
    if len(targets) < 2:
        raise StatisticsError("Correlation needs at least 2 numeric columns.")
    if method not in ("pearson", "spearman", "kendall"):
        raise StatisticsError("method must be pearson, spearman, or kendall.")
    return df[targets].corr(method=method, numeric_only=True)


def distribution_analysis(series: pd.Series) -> dict:
    """Shape analysis: skew, kurtosis, and a Shapiro-Wilk normality check.

    Shapiro-Wilk runs only for 3–5000 observations (its valid range); for
    larger samples the test is skipped and the reason is reported.
    """
    clean = series.dropna()
    if pd.api.types.is_numeric_dtype(series) is False:
        raise StatisticsError(f"Column '{series.name}' must be numeric.")
    if len(clean) < 3:
        raise StatisticsError("Distribution analysis needs at least 3 values.")
    result = {
        "skew": _clean(scipy_stats.skew(clean, nan_policy="omit")),
        "kurtosis": _clean(scipy_stats.kurtosis(clean, nan_policy="omit")),
        "shapiro_statistic": None,
        "shapiro_p_value": None,
        "shapiro_note": "Skipped: Shapiro-Wilk needs 3–5000 observations.",
    }
    if 3 <= len(clean) <= 5000:
        statistic, p_value = scipy_stats.shapiro(clean)
        result["shapiro_statistic"] = _clean(statistic)
        result["shapiro_p_value"] = _clean(p_value)
        result["shapiro_note"] = (
            "p >= 0.05 is consistent with normality; p < 0.05 is not."
        )
    return result


def ols_regression(
    df: pd.DataFrame, target: str, features: list[str]
) -> dict:
    """Ordinary least squares via statsmodels.

    Rows with missing values in the used columns are dropped, and the
    dropped count is reported — never hidden. Returns coefficients,
    p-values, R-squared, and adjusted R-squared as plain floats.
    """
    import statsmodels.api as sm

    used = [target] + list(features)
    unknown = [c for c in used if c not in df.columns]
    if unknown:
        raise StatisticsError(f"Unknown columns: {unknown}")
    non_numeric = [c for c in used if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        raise StatisticsError(f"OLS needs numeric columns: {non_numeric}")
    if not features:
        raise StatisticsError("OLS needs at least one feature column.")
    work = df[used].dropna()
    dropped = len(df) - len(work)
    if len(work) < len(features) + 2:
        raise StatisticsError("Not enough complete rows to fit OLS.")
    model = sm.OLS(work[target].astype(float), sm.add_constant(work[features].astype(float)))
    fitted = model.fit()
    params = fitted.params.to_dict()
    pvalues = fitted.pvalues.to_dict()
    result = {
        "target": target,
        "features": list(features),
        "rows_used": int(len(work)),
        "rows_dropped_missing": int(dropped),
        "r_squared": _clean(fitted.rsquared),
        "adj_r_squared": _clean(fitted.rsquared_adj),
        "coefficients": {str(k): _clean(v) for k, v in params.items()},
        "p_values": {str(k): _clean(v) for k, v in pvalues.items()},
    }
    log.info("ols_regression fitted {} on {} rows", target, len(work))
    return result
