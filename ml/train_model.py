"""
train_model.py — Agrani Naval Surveillance System
Trains a RandomForestClassifier on synthetic sensor data and exports:
  model.pkl         — trained pipeline (scaler + classifier)
  label_encoder.pkl — LabelEncoder mapping int labels → class names

Run:
  python generate_training_data.py   # creates training_data.csv
  python train_model.py              # trains, evaluates, and exports model
"""

import os
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
import warnings
warnings.filterwarnings("ignore")

BASE_DIR  = os.path.dirname(__file__)
CSV_PATH  = os.path.join(BASE_DIR, "training_data.csv")
MODEL_OUT = os.path.join(BASE_DIR, "model.pkl")
LE_OUT    = os.path.join(BASE_DIR, "label_encoder.pkl")

FEATURES = [
    "magnetic_intensity",
    "doppler_velocity",
    "ultrasonic_distance",
    "hour_of_day",
    "baseline_deviation",
]

CLASS_NAMES = ["normal", "diver", "small_watercraft", "submarine", "mine"]


def load_data():
    if not os.path.exists(CSV_PATH):
        print(f"Training data not found at {CSV_PATH}")
        print("Running generate_training_data.py first...")
        import subprocess, sys
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "generate_training_data.py")], check=True)
    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} samples from {CSV_PATH}")
    return df


def train():
    df = load_data()
    X  = df[FEATURES].values
    y  = df["label"].values

    # LabelEncoder for human-readable class names during inference
    le = LabelEncoder()
    le.classes_ = np.array(CLASS_NAMES)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"Train: {len(X_train)} samples | Test: {len(X_test)} samples")

    # Pipeline: StandardScaler → RandomForest
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("clf",    RandomForestClassifier(
                        n_estimators=200,
                        max_depth=20,
                        min_samples_split=4,
                        min_samples_leaf=2,
                        class_weight="balanced",
                        random_state=42,
                        n_jobs=-1,
                    )),
    ])

    print("\nTraining RandomForest pipeline...")
    pipeline.fit(X_train, y_train)

    # Evaluate
    y_pred = pipeline.predict(X_test)
    print("\n── Classification Report ──────────────────────────────────────")
    print(classification_report(y_test, y_pred, target_names=CLASS_NAMES))

    print("── Confusion Matrix ───────────────────────────────────────────")
    cm = confusion_matrix(y_test, y_pred)
    cm_df = pd.DataFrame(cm, index=CLASS_NAMES, columns=CLASS_NAMES)
    print(cm_df)

    # Cross-validation
    cv_scores = cross_val_score(pipeline, X_train, y_train, cv=5, scoring="accuracy", n_jobs=-1)
    print(f"\n── 5-Fold CV Accuracy: {cv_scores.mean():.4f} ± {cv_scores.std():.4f}")

    # Feature importance
    clf = pipeline.named_steps["clf"]
    importance = pd.Series(clf.feature_importances_, index=FEATURES).sort_values(ascending=False)
    print("\n── Feature Importances ─────────────────────────────────────────")
    for feat, imp in importance.items():
        bar = "█" * int(imp * 40)
        print(f"  {feat:<25} {imp:.4f}  {bar}")

    # Export
    with open(MODEL_OUT, "wb") as f:
        pickle.dump(pipeline, f)
    with open(LE_OUT, "wb") as f:
        pickle.dump(le, f)

    print(f"\n✓ Model saved   → {MODEL_OUT}")
    print(f"✓ Encoder saved → {LE_OUT}")
    return pipeline, le


if __name__ == "__main__":
    train()
