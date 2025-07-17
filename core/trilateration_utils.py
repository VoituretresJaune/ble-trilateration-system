import numpy as np
from scipy.optimize import minimize

# === Configuration centralisée ===
from core.config import GATEWAY_POSITIONS

def rssi_to_distance(rssi, tx_power=-59):
    """
    Convertit un RSSI en distance estimée (modèle empirique).
    """
    if rssi == 0:
        return -1
    ratio = rssi / tx_power
    if ratio < 1.0:
        return pow(ratio, 10)
    else:
        return 0.89976 * pow(ratio, 7.7095) + 0.111

def trilateration_optim(distances, positions):
    """
    Effectue une trilatération 3D à partir des distances connues et des positions des ESP32.
    Utilise une optimisation pour minimiser l'erreur sur les distances.
    """
    if len(distances) != len(positions):
        print(f"[ERREUR] Nombre de distances ({len(distances)}) != nombre de positions ({len(positions)})")
        return None
    
    if len(distances) < 3:
        print(f"[ERREUR] Pas assez de points pour trilatération ({len(distances)} < 3)")
        return None
    
    def loss(pos):
        x, y, z = pos
        error = sum(
            (np.sqrt((x - xi)**2 + (y - yi)**2 + (z - zi)**2) - di)**2
            for (xi, yi, zi), di in zip(positions, distances)
        )
        return error

    x0 = np.mean([p[0] for p in positions])
    y0 = np.mean([p[1] for p in positions])
    z0 = 0.5  # Hauteur estimée du beacon

    bounds = [(0, 20), (0, 11), (0, 3)]  # Adapté à ton plan (voir map)
    
    from scipy.optimize import minimize
    result = minimize(loss, (x0, y0, z0), method='L-BFGS-B', bounds=bounds)
    
    if result.success:
        print(f"[TRILATERATION] ✅ Succès: position = ({result.x[0]:.2f}, {result.x[1]:.2f}, {result.x[2]:.2f})")
        return result.x
    else:
        print(f"[TRILATERATION] ❌ Échec: {result.message}")
        return None

def apply_proximity_bonus(distances, filtered_rssi, gateway_positions=None, threshold=1.0, max_bonus_db=3):
    """
    Ajoute un bonus au RSSI si la distance entre beacon et ESP est très courte.
    """
    if gateway_positions is None:
        gateway_positions = GATEWAY_POSITIONS

    adjusted = filtered_rssi.copy()
    for dist, gw_name in zip(distances, gateway_positions):
        if 0 < dist < threshold:
            bonus = max_bonus_db * (1 - dist / threshold)
            adjusted[gw_name] += bonus
    return adjusted

def detect_floor_from_rssi(floor_data, config_floors, rssi_threshold=15, ratio_threshold=1.5):
    """
    Détermine sur quel étage se trouve une balise basé sur la force du signal RSSI.
    
    Args:
        floor_data: {floor_idx: {gateway: [rssi_values]}}
        config_floors: Configuration des étages
        rssi_threshold: Différence RSSI minimale pour forcer un étage (dB)
        ratio_threshold: Ratio minimal de force de signal
    
    Returns:
        floor_idx ou None si pas de détection claire
    """
    floor_strengths = {}
    
    # Calculer la force moyenne de chaque étage
    for floor_idx, gateways_data in floor_data.items():
        if not gateways_data:
            continue
            
        # Moyenne des RSSI les plus récents de cet étage
        rssi_values = []
        for gateway_id, values in gateways_data.items():
            if len(values) >= 3:
                recent_rssi = np.mean(values[-5:])  # 5 dernières valeurs
                rssi_values.append(recent_rssi)
        
        if rssi_values:
            # Force = RSSI moyen + bonus pour nombre de gateways
            avg_rssi = np.mean(rssi_values)
            max_rssi = np.max(rssi_values)
            gateway_count = len(rssi_values)
            
            # Score composite : signal le plus fort + moyenne + nombre de gateways
            floor_strengths[floor_idx] = {
                'avg_rssi': avg_rssi,
                'max_rssi': max_rssi,
                'gateway_count': gateway_count,
                'score': max_rssi * 0.6 + avg_rssi * 0.3 + gateway_count * 2
            }
    
    if len(floor_strengths) < 2:
        return None  # Pas assez de données pour comparer
    
    # Trier par score
    sorted_floors = sorted(floor_strengths.items(), key=lambda x: x[1]['score'], reverse=True)
    best_floor, best_data = sorted_floors[0]
    second_floor, second_data = sorted_floors[1]
    
    print(f"[FLOOR_DETECT] Étage {best_floor}: score={best_data['score']:.1f}, max_rssi={best_data['max_rssi']:.1f}")
    print(f"[FLOOR_DETECT] Étage {second_floor}: score={second_data['score']:.1f}, max_rssi={second_data['max_rssi']:.1f}")
    
    # Vérifications pour forcer un étage
    rssi_diff = best_data['max_rssi'] - second_data['max_rssi']
    score_ratio = best_data['score'] / max(second_data['score'], 0.1)
    
    # Cas 1: Signal beaucoup plus fort sur un étage
    if rssi_diff >= rssi_threshold:
        print(f"[FLOOR_DETECT] ✅ Étage {best_floor} sélectionné (diff RSSI: {rssi_diff:.1f} dB)")
        return best_floor
    
    # Cas 2: Score significativement meilleur
    if score_ratio >= ratio_threshold:
        print(f"[FLOOR_DETECT] ✅ Étage {best_floor} sélectionné (ratio score: {score_ratio:.1f})")
        return best_floor
    
    # Cas 3: ESP32 unique à l'étage avec signal fort
    for floor_idx, data in floor_strengths.items():
        floor_config = config_floors[floor_idx] if floor_idx < len(config_floors) else None
        if floor_config and len(floor_config['gateway_positions']) == 1:  # Étage avec 1 seul ESP32
            if data['max_rssi'] > -50:  # Signal très fort (proche)
                print(f"[FLOOR_DETECT] ✅ Étage {floor_idx} sélectionné (ESP unique + signal fort: {data['max_rssi']:.1f})")
                return floor_idx
    
    print(f"[FLOOR_DETECT] ⚠️  Pas de détection claire, étage par défaut: {best_floor}")
    return best_floor

def trilateration_multifloor(floor_data, config_floors, beacon_name, force_floor=None):
    """
    Trilatération intelligente multi-étages avec sélection automatique d'étage.
    
    Args:
        floor_data: {floor_idx: {gateway: [rssi_values]}}
        config_floors: Configuration des étages
        beacon_name: Nom de la balise (pour debug)
        force_floor: Forcer un étage spécifique (None = auto)
    
    Returns:
        (floor_idx, position_3d) ou (None, None)
    """
    # Filtrer les RSSI pour chaque étage
    floor_filtered_rssi = {}
    
    for floor_idx, gateways_data in floor_data.items():
        if floor_idx >= len(config_floors):
            continue
            
        floor_config = config_floors[floor_idx]
        filtered_rssi = {}
        
        for gw, values in gateways_data.items():
            if len(values) >= 3:  # Minimum de valeurs
                from core.filters import apply_kalman_filter, apply_butterworth_filter
                kalman_values = apply_kalman_filter(values[-10:])
                butter_values = apply_butterworth_filter(kalman_values)
                filtered_rssi[gw] = np.mean(butter_values[-5:])
        
        if len(filtered_rssi) >= 1:  # Au moins 1 gateway
            floor_filtered_rssi[floor_idx] = filtered_rssi
    
    # Détecter l'étage automatiquement ou utiliser le forcé
    if force_floor is not None and force_floor in floor_filtered_rssi:
        selected_floor = force_floor
        print(f"[TRILATERATION] {beacon_name}: Étage forcé = {selected_floor}")
    else:
        selected_floor = detect_floor_from_rssi(floor_data, config_floors)
        if selected_floor is None or selected_floor not in floor_filtered_rssi:
            print(f"[TRILATERATION] {beacon_name}: Aucun étage détectable")
            return None, None
    
    # Effectuer la trilatération sur l'étage sélectionné
    floor_config = config_floors[selected_floor]
    filtered_rssi = floor_filtered_rssi[selected_floor]
    
    # Vérifier qu'on a assez de gateways pour la trilatération
    if len(filtered_rssi) < 3:
        print(f"[TRILATERATION] {beacon_name}: Pas assez de gateways sur étage {selected_floor} ({len(filtered_rssi)} < 3)")
        # Essayer avec moins de contraintes si on a au moins 2 gateways
        if len(filtered_rssi) >= 2:
            print(f"[TRILATERATION] {beacon_name}: Trilatération approximative avec {len(filtered_rssi)} gateways")
        else:
            return selected_floor, None
    
    # Préparer les données pour la trilatération
    valid_gateways = list(filtered_rssi.keys())
    distances = [rssi_to_distance(filtered_rssi[gw]) for gw in valid_gateways]
    positions = [floor_config['gateway_positions'][gw] for gw in valid_gateways]
    
    print(f"[TRILATERATION] {beacon_name} sur étage {selected_floor}: {len(valid_gateways)} gateways, distances={[f'{d:.1f}m' for d in distances]}")
    
    # Trilatération avec bounds adaptés à l'étage
    extent = floor_config['extent']
    bounds = [(extent[0], extent[1]), (extent[2], extent[3]), (0, 3)]
    
    def loss(pos):
        x, y, z = pos
        return sum(
            (np.sqrt((x - xi)**2 + (y - yi)**2 + (z - zi)**2) - di)**2
            for (xi, yi, zi), di in zip(positions, distances)
        )

    x0 = np.mean([p[0] for p in positions])
    y0 = np.mean([p[1] for p in positions])
    z0 = 0.5
    
    from scipy.optimize import minimize
    result = minimize(loss, (x0, y0, z0), method='L-BFGS-B', bounds=bounds)
    
    if result.success:
        print(f"[TRILATERATION] {beacon_name}: Position trouvée sur étage {selected_floor}: ({result.x[0]:.2f}, {result.x[1]:.2f})")
        return selected_floor, result.x
    else:
        print(f"[TRILATERATION] {beacon_name}: Échec trilatération sur étage {selected_floor}")
        return selected_floor, None
