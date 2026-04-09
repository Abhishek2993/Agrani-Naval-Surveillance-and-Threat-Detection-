"""
generate_training_data.py — Agrani Naval Surveillance System
Generates 50,000 synthetic, labelled sensor readings across 5 threat classes.

Classes:
  0 — normal           (ambient sea activity)
  1 — diver            (slow-moving, small magnetic signature)
  2 — small_watercraft (medium speed, moderate magnetic)
  3 — submarine        (strong magnetic, slow, close range)
  4 — mine             (strong magnetic, stationary, very close)

Features:
  magnetic_intensity   (µT)
  doppler_velocity     (m/s)
  ultrasonic_distance  (m)
  hour_of_day          (0–23)
  baseline_deviation   (% deviation from rolling 10-min mean)
"""

import numpy as np
import pandas as pd
import os

# ─── Reproducibility ──────────────────────────────────────────────────────────
SEED = 42
np.random.seed(SEED)

OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "training_data.csv")

# ─── Per-class distribution parameters ───────────────────────────────────────
# Each entry: (magnetic_mean, magnetic_std, doppler_mean, doppler_std,
#              ultrasonic_mean, ultrasonic_std, n_samples)
CLASS_CONFIG = {
    "normal": {
        "magnetic":   (32,  8),
        "doppler":    (0.4, 0.25),
        "ultrasonic": (22,  5),
        "n":          20000,
    },
    "diver": {
        "magnetic":   (65,  15),
        "doppler":    (1.2, 0.4),
        "ultrasonic": (10,  3),
        "n":          8000,
    },
    "small_watercraft": {
        "magnetic":   (95,  20),
        "doppler":    (4.0, 1.0),
        "ultrasonic": (14,  4),
        "n":          8000,
    },
    "submarine": {
        "magnetic":   (185, 25),
        "doppler":    (1.5, 0.8),
        "ultrasonic": (6,   2),
        "n":          7000,
    },
    "mine": {
        "magnetic":   (210, 20),
        "doppler":    (0.05, 0.05),
        "ultrasonic": (1.5, 0.5),
        "n":          7000,
    },
}

LABEL_MAP = {
    "normal": 0,
    "diver": 1,
    "small_watercraft": 2,
    "submarine": 3,
    "mine": 4,
}


def generate_class(class_name: str, cfg: dict) -> pd.DataFrame:
    n = cfg["n"]
    mag_mean, mag_std  = cfg["magnetic"]
    dop_mean, dop_std  = cfg["doppler"]
    ult_mean, ult_std  = cfg["ultrasonic"]

    magnetic   = np.abs(np.random.normal(mag_mean, mag_std, n))
    doppler    = np.abs(np.random.normal(dop_mean, dop_std, n))
    ultrasonic = np.abs(np.random.normal(ult_mean, ult_std, n))
    ultrasonic = np.clip(ultrasonic, 0.3, 50.0)

    # Hour of day: divers more at night; submarines random
    if class_name == "diver":
        hour = np.random.choice(np.concatenate([np.arange(20, 24), np.arange(0, 5)]), n)
    else:
        hour = np.random.randint(0, 24, n)

    # Baseline deviation: higher for anomalous classes
    base_dev_std = {"normal": 3, "diver": 15, "small_watercraft": 22, "submarine": 35, "mine": 30}
    baseline_deviation = np.abs(np.random.normal(0, base_dev_std[class_name], n))

    label = np.full(n, LABEL_MAP[class_name])

    return pd.DataFrame({
        "magnetic_intensity":  np.round(magnetic, 2),
        "doppler_velocity":    np.round(doppler, 3),
        "ultrasonic_distance": np.round(ultrasonic, 2),
        "hour_of_day":         hour,
        "baseline_deviation":  np.round(baseline_deviation, 2),
        "label":               label,
        "class_name":          class_name,
    })


def generate_all() -> pd.DataFrame:
    frames = [generate_class(name, cfg) for name, cfg in CLASS_CONFIG.items()]
    df = pd.concat(frames, ignore_index=True)
    # Add noise / overlap between classes for realism
    noise_rows = df.sample(frac=0.03, random_state=SEED)
    df.loc[noise_rows.index, "magnetic_intensity"]  += np.random.uniform(-20, 20, len(noise_rows))
    df.loc[noise_rows.index, "doppler_velocity"]    += np.random.uniform(-0.5, 0.5, len(noise_rows))
    df["doppler_velocity"]    = df["doppler_velocity"].clip(lower=0)
    df["magnetic_intensity"]  = df["magnetic_intensity"].clip(lower=0)
    df["ultrasonic_distance"] = df["ultrasonic_distance"].clip(lower=0.3)
    # Shuffle
    df = df.sample(frac=1, random_state=SEED).reset_index(drop=True)
    return df


if __name__ == "__main__":
    print("Generating Agrani training data...")
    df = generate_all()
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved {len(df)} samples to {OUTPUT_CSV}")
    print("\nClass distribution:")
    print(df["class_name"].value_counts())
    print("\nFeature statistics:")
    print(df[["magnetic_intensity", "doppler_velocity", "ultrasonic_distance",
              "hour_of_day", "baseline_deviation"]].describe().round(2))
