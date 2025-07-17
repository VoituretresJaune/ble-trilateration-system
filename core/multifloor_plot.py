import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import matplotlib.image as mpimg
import numpy as np
import json
import os
from datetime import datetime

from core.filters import apply_kalman_filter, apply_butterworth_filter
from core.attenuation import apply_path_based_attenuation
from core.trilateration_utils import trilateration_optim, rssi_to_distance, apply_proximity_bonus
from core import config

# === Variables globales ===
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
beacon_points_floor1 = {}
beacon_points_floor2 = {}
beacon_colors = ['red', 'green', 'blue', 'orange', 'purple']
circle_artists_floor1 = []
circle_artists_floor2 = []
text_artists_floor1 = []  # Ajouter pour les textes
text_artists_floor2 = []  # Ajouter pour les textes

def setup_multifloor_plot():
    """Configuration du plot multi-étages"""
    if not hasattr(config, 'floors') or not config.floors:
        print("[ERREUR] Configuration multi-étages non trouvée")
        return
    
    # Configuration du RDC (gauche)
    floor1 = config.floors[0]
    ax1.clear()
    ax1.set_title(f"{floor1['name']} ({len(floor1['gateway_positions'])} ESP32)")
    
    if os.path.exists(floor1['image_file']):
        img1 = mpimg.imread(floor1['image_file'])
        # Modification ici : origin='upper' au lieu de 'lower'
        ax1.imshow(img1, extent=floor1['extent'], origin='upper', alpha=0.8)
        print(f"[PLOT] Image RDC chargée: {floor1['image_file']}")
    
    # Afficher ESP32 du RDC
    for label, (x, y, _) in floor1['gateway_positions'].items():
        ax1.scatter(x, y, marker="s", label=label, s=100, color='black')
        ax1.text(x + 0.1, y + 0.1, label, fontweight='bold')
    
    # Afficher zones du RDC
    for name, x1, y1, x2, y2 in floor1['zones']:
        ax1.add_patch(plt.Rectangle((x1, y1), x2 - x1, y2 - y1, 
                                   fill=False, edgecolor='blue', linestyle=':', linewidth=1))
        ax1.text((x1 + x2) / 2, (y1 + y2) / 2, name, fontsize=8, ha='center', va='center', color='blue')
    
    ax1.set_xlim(floor1['extent'][0], floor1['extent'][1])
    ax1.set_ylim(floor1['extent'][2], floor1['extent'][3])
    ax1.grid(True)
    ax1.legend()
    
    # Configuration du 1er étage (droite)
    floor2 = config.floors[1]
    ax2.clear()
    ax2.set_title(f"{floor2['name']} ({len(floor2['gateway_positions'])} ESP32)")
    
    if os.path.exists(floor2['image_file']):
        img2 = mpimg.imread(floor2['image_file'])
        # Modification ici également
        ax2.imshow(img2, extent=floor2['extent'], origin='upper', alpha=0.8)
        print(f"[PLOT] Image R1 chargée: {floor2['image_file']}")
    
    # Afficher ESP32 du 1er étage
    for label, (x, y, _) in floor2['gateway_positions'].items():
        ax2.scatter(x, y, marker="s", label=label, s=100, color='black')
        ax2.text(x + 0.1, y + 0.1, label, fontweight='bold')
    
    # Afficher zones du 1er étage
    for name, x1, y1, x2, y2 in floor2['zones']:
        ax2.add_patch(plt.Rectangle((x1, y1), x2 - x1, y2 - y1, 
                                   fill=False, edgecolor='blue', linestyle=':', linewidth=1))
        ax2.text((x1 + x2) / 2, (y1 + y2) / 2, name, fontsize=8, ha='center', va='center', color='blue')
    
    ax2.set_xlim(floor2['extent'][0], floor2['extent'][1])
    ax2.set_ylim(floor2['extent'][2], floor2['extent'][3])
    ax2.grid(True)
    ax2.legend()
    
    plt.tight_layout()

def load_data():
    if not os.path.exists(config.DATA_FILE):
        return []
    try:
        with open(config.DATA_FILE, "r") as f:
            data = json.load(f)
            for d in data:
                if isinstance(d.get("time"), str):
                    d["time"] = datetime.fromisoformat(d["time"])
            return data
    except Exception as e:
        print(f"[ERREUR] Lecture {config.DATA_FILE} : {e}")
        return []

def get_floor_for_gateway(gateway_id):
    """Détermine sur quel étage se trouve un gateway"""
    if not hasattr(config, 'floors'):
        return None, None
    
    for i, floor in enumerate(config.floors):
        if gateway_id in floor['gateway_positions']:
            return i, floor
    return None, None

def update_multifloor(frame):
    """Mise à jour des deux étages avec filtrage des balises"""
    global circle_artists_floor1, circle_artists_floor2, text_artists_floor1, text_artists_floor2
    global beacon_points_floor1, beacon_points_floor2
    
    if not hasattr(config, 'floors') or not config.floors:
        return
    
    data = load_data()
    if not data:
        return

    # Nettoyer les anciens cercles ET textes
    for circ in circle_artists_floor1:
        circ.remove()
    for circ in circle_artists_floor2:
        circ.remove()
    for text in text_artists_floor1:
        text.remove()
    for text in text_artists_floor2:
        text.remove()
    
    circle_artists_floor1.clear()
    circle_artists_floor2.clear()
    text_artists_floor1.clear()
    text_artists_floor2.clear()

    # Grouper les données par beacon
    beacon_data = {}
    for d in data:
        beacon_name = d.get("beacon")
        if beacon_name not in beacon_data:
            beacon_data[beacon_name] = []
        beacon_data[beacon_name].append(d)

    # APPLIQUER LE FILTRE DES BALISES
    from core.config import should_process_beacon
    
    filtered_beacon_data = {}
    for beacon_name, beacon_entries in beacon_data.items():
        if should_process_beacon(beacon_name):
            filtered_beacon_data[beacon_name] = beacon_entries
        else:
            print(f"[FILTER] Balise {beacon_name} ignorée par le filtre")
    
    beacon_data = filtered_beacon_data
    
    if not beacon_data:
        print("[FILTER] Aucune balise autorisée détectée")
        return

    print(f"[FILTER] Balises autorisées détectées: {list(beacon_data.keys())}")

    print(f"\n=== UPDATE MULTI-ÉTAGES ===")
    print(f"Balises détectées: {list(beacon_data.keys())}")

    # Traiter chaque balise avec la nouvelle logique
    for i, (beacon_name, beacon_entries) in enumerate(beacon_data.items()):
        color = beacon_colors[i % len(beacon_colors)]
        
        # Collecter les RSSI par étage
        floor_data = {0: {}, 1: {}}  # RDC et 1er étage
        
        for d in beacon_entries:
            gateway_id = d.get("source")
            floor_idx, floor_info = get_floor_for_gateway(gateway_id)
            
            if floor_idx is not None:
                if gateway_id not in floor_data[floor_idx]:
                    floor_data[floor_idx][gateway_id] = []
                
                rssi_value = d.get("median", d["rssi"]) + config.CORRECTION_RSSI.get(gateway_id, 0)
                floor_data[floor_idx][gateway_id].append(rssi_value)

        # Utiliser la nouvelle fonction de trilatération intelligente
        from core.trilateration_utils import trilateration_multifloor
        
        selected_floor, position_3d = trilateration_multifloor(
            floor_data, config.floors, beacon_name
        )
        
        print(f"[DEBUG] {beacon_name}: étage sélectionné = {selected_floor}, position = {position_3d}")
        
        if selected_floor is not None:
            # Déterminer les objets d'affichage pour l'étage sélectionné
            ax = ax1 if selected_floor == 0 else ax2
            beacon_points = beacon_points_floor1 if selected_floor == 0 else beacon_points_floor2
            
            # Créer le point pour cette balise s'il n'existe pas sur l'étage approprié
            if beacon_name not in beacon_points:
                point, = ax.plot([], [], 'o', color=color, label=f"{beacon_name}", markersize=8)
                beacon_points[beacon_name] = point
                print(f"[DEBUG] Point créé pour {beacon_name} sur étage {selected_floor}")
            
            # Afficher les cercles de tous les gateways qui captent cette balise
            for floor_idx, gateways_data in floor_data.items():
                if not gateways_data or floor_idx >= len(config.floors):
                    continue
                    
                floor_cfg = config.floors[floor_idx]
                ax_display = ax1 if floor_idx == 0 else ax2
                circle_list = circle_artists_floor1 if floor_idx == 0 else circle_artists_floor2
                text_list = text_artists_floor1 if floor_idx == 0 else text_artists_floor2
                
                # Filtrer et afficher les cercles
                for gw, values in gateways_data.items():
                    if len(values) >= 3 and gw in floor_cfg['gateway_positions']:
                        from core.filters import apply_kalman_filter, apply_butterworth_filter
                        kalman_values = apply_kalman_filter(values[-10:])
                        butter_values = apply_butterworth_filter(kalman_values)
                        rssi_val = np.mean(butter_values[-5:])
                        
                        x_gw, y_gw, _ = floor_cfg['gateway_positions'][gw]
                        radius = rssi_to_distance(rssi_val)
                        
                        # Style selon l'étage
                        if floor_idx == selected_floor:
                            linestyle = '-'
                            alpha = 0.6
                            linewidth = 2
                        else:
                            linestyle = ':'
                            alpha = 0.3
                            linewidth = 1
                        
                        circle = plt.Circle((x_gw, y_gw), radius, 
                                          color=color, fill=False, 
                                          linestyle=linestyle, alpha=alpha, linewidth=linewidth)
                        ax_display.add_patch(circle)
                        circle_list.append(circle)
                        
                        # Ajouter le texte à la liste appropriée
                        text = ax_display.text(x_gw + radius * 0.7, y_gw + radius * 0.7, 
                                              f"{radius:.1f}m", fontsize=7, color=color, alpha=alpha)
                        text_list.append(text)
            
            # Afficher la position de la balise sur l'étage sélectionné
            if position_3d is not None and beacon_name in beacon_points:
                x, y = position_3d[0], position_3d[1]
                beacon_points[beacon_name].set_data(x, y)
                print(f"[DEBUG] Position mise à jour pour {beacon_name}: ({x:.2f}, {y:.2f})")
                
                # Vérifier si dans une zone
                in_zone, zone_name = is_position_in_zones(x, y, selected_floor)
                if in_zone:
                    print(f"[INFO] ✅ {beacon_name} dans zone {zone_name} (étage {selected_floor + 1})")
                else:
                    print(f"[INFO] ⚠️  {beacon_name} hors zone (étage {selected_floor + 1}): ({x:.2f}, {y:.2f})")
            else:
                print(f"[WARNING] Impossible d'afficher {beacon_name}: position={position_3d}, dans beacon_points={beacon_name in beacon_points}")
        else:
            print(f"[WARNING] Aucun étage sélectionné pour {beacon_name}")

    # Mise à jour des légendes pour les deux étages
    ax1.legend(loc='upper right')
    ax2.legend(loc='upper right')
    
    # Forcer le rafraîchissement
    plt.draw()

def is_position_in_zones(x, y, floor_idx):
    """Vérifier si la position est dans une zone de l'étage spécifié"""
    if not hasattr(config, 'floors') or floor_idx >= len(config.floors):
        return False, None
    
    floor_zones = config.floors[floor_idx]['zones']
    for name, x1, y1, x2, y2 in floor_zones:
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True, name
    return False, None

def start_multifloor():
    """Démarrer le plot multi-étages"""
    print("[PLOT] Démarrage du système multi-étages...")
    
    # Charger la configuration
    if not config.load_config_from_file():
        print("[ERREUR] Impossible de charger la configuration")
        return
    
    # Attendre la config
    import time
    timeout = 10
    start_time = time.time()
    
    while not hasattr(config, 'floors') and (time.time() - start_time) < timeout:
        print("[PLOT] Attente de la configuration multi-étages...")
        time.sleep(0.5)
        config.load_config_from_file()
    
    if not hasattr(config, 'floors') or not config.floors:
        print("[ERREUR] Configuration multi-étages non disponible")
        return
    
    print(f"[PLOT] Configuration multi-étages chargée: {len(config.floors)} étages")
    setup_multifloor_plot()
    
    # Corriger le warning en désactivant le cache
    ani = FuncAnimation(fig, update_multifloor, interval=3000, repeat=True, cache_frame_data=False)
    plt.show()