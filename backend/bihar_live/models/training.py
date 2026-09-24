"""Time-ordered synthetic rainfall training and evaluation."""
from __future__ import annotations
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error
from .rainfall import RainfallModel

def build_training_series(rows):
    rows = sorted(rows, key=lambda r: r.timestamp_utc)
    rain = np.array([float(r.value or 0.0) for r in rows if r.variable == "rain_mm"], dtype=float)
    if len(rain) < 12:
        raise ValueError("Need at least 12 rainfall observations")
    X=[]; y=[]
    for i in range(6, len(rain)-1):
        X.append([rain[i-1], rain[i-3:i].mean(), rain[max(0,i-6):i].sum()])
        y.append(rain[i+1])
    return np.asarray(X), np.asarray(y)

def train_evaluate(rows):
    X,y=build_training_series(rows)
    cut=max(1,int(len(X)*0.8))
    model=RainfallModel().fit(X[:cut],y[:cut])
    pred=model.predict(X[cut:])
    metrics={"mae":float(mean_absolute_error(y[cut:],pred)),
             "rmse":float(np.sqrt(mean_squared_error(y[cut:],pred))),
             "train_rows":int(cut),"test_rows":int(len(y)-cut),
             "split":"chronological","data_mode":"synthetic"}
    return model,metrics
