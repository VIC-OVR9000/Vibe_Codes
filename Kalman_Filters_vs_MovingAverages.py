import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pykalman import KalmanFilter

# 1. Generate Noisy Data (Sine wave with random noise)
np.random.seed(42)
t = np.linspace(0, 10, 100)
true_signal = np.sin(t)
noisy_data = true_signal + np.random.normal(0, 0.2, size=len(t))

# 2. Compute Moving Average (Window size = 10)
moving_avg = pd.Series(noisy_data).rolling(window=10, center=False).mean()

# 3. Compute Kalman Filter
kf = KalmanFilter(transition_matrices=[1], observation_matrices=[1], 
                  initial_state_mean=0, initial_state_covariance=1, 
                  observation_covariance=0.04, transition_covariance=0.01)
kalman_smoothed, _ = kf.filter(noisy_data)

# 4. Plotting
plt.figure(figsize=(12, 6))
plt.scatter(t, noisy_data, color='lightgray', label='Noisy Data', alpha=0.6)
plt.plot(t, true_signal, label='True Signal', color='black', linestyle='--')
plt.plot(t, moving_avg, label='10-pt Moving Average', color='red', linewidth=2)
plt.plot(t, kalman_smoothed, label='Kalman Filter', color='blue', linewidth=2)

plt.title("Kalman Filter vs. Moving Average (2026 Comparison)")
plt.legend()
plt.grid(True)
plt.show()
