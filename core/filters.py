from filterpy.kalman import KalmanFilter
from scipy.signal import butter, filtfilt
import numpy as np

# Aucun paramètre de config global requis ici,
# donc pas besoin d'importer tout config.py inutilement
# (inutile : GATEWAY_POSITIONS, ZONES, etc.)

def apply_kalman_filter(values, R=17, Q_scale=0.02):
    """Applique un filtre de Kalman à une série de valeurs."""
    if not values:
        return []
    
    kf = KalmanFilter(dim_x=2, dim_z=1)
    kf.x = np.array([[values[0]], [0.]])  # état initial
    kf.F = np.array([[1., 1.], [0., 1.]])  # matrice de transition
    kf.H = np.array([[1., 0.]])           # matrice d'observation
    kf.P *= 1000.                         # incertitude initiale
    kf.R = R                              # bruit de mesure
    kf.Q = np.array([[1., 0.], [0., 1.]]) * Q_scale  # bruit de process

    return [kf.update(np.array([[v]])) or kf.x[0, 0] for v in (kf.predict() or v for v in values)]


def apply_butterworth_filter(data, order=2, cutoff=0.1):
    """Applique un filtre passe-bas de Butterworth."""
    if len(data) < max(3 * order, 10):
        return data
    b, a = butter(order, cutoff, btype='low', analog=False)
    return filtfilt(b, a, data).tolist()
