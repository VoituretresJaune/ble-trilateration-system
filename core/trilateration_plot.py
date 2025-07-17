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
fig, ax = plt.subplots()
beacon_points = {}
beacon_colors = ['red', 'green', 'blue', 'orange', 'purple']
circle_artists = []
text_artists = []  # Ajouter cette liste pour les textes
legend_updated = False

def transform_coordinates(x, y):
    """Transformer les coordonnées pour corriger l'inversion de la map"""
    # Inverser les coordonnées X et Y selon l'extent
    extent = config.EXTENT
    
    # Inversion X : x_new = extent_max - x + extent_min
    x_inverted = extent[1] - x + extent[0]
    
    # Inversion Y : y_new = extent_max - y + extent_min  
    y_inverted = extent[3] - y + extent[2]
    
    return x_inverted, y_inverted

def setup_plot():
    """Configuration du plot avec les valeurs du préset chargé"""
    ax.clear()
    
    print(f"[PLOT] Configuration avec:")
    print(f"  - Image: {config.IMAGE_FILE}")
    print(f"  - Extent: {config.EXTENT}")
    print(f"  - Gateways: {len(config.GATEWAY_POSITIONS)}")
    
    # Récupérer les valeurs de config au moment de l'exécution
    if config.IMAGE_FILE and os.path.exists(config.IMAGE_FILE):
        try:
            img = mpimg.imread(config.IMAGE_FILE)
            # MODIFICATION ICI : origin='upper' + flipud() pour inverser l'image
            ax.imshow(np.flipud(img), extent=config.EXTENT, origin='lower', alpha=0.8)
            print(f"[PLOT] Image chargée: {config.IMAGE_FILE}")
        except Exception as e:
            print(f"[ERREUR] Impossible de charger l'image: {e}")
    else:
        print(f"[WARNING] Image non trouvée: {config.IMAGE_FILE}")

    # Affichage des ESP32 (coordonnées normales)
    for label, (x, y, _) in config.GATEWAY_POSITIONS.items():
        ax.scatter(x, y, marker="s", label=label, s=100, color='black')
        ax.text(x + 0.1, y + 0.1, label, fontweight='bold')

    # Affichage des zones (coordonnées normales)
    if hasattr(config, 'USE_ZONES') and config.USE_ZONES:
        for name, x1, y1, x2, y2 in config.ZONES:
            ax.add_patch(plt.Rectangle((x1, y1), x2 - x1, y2 - y1, 
                                     fill=False, edgecolor='blue', linestyle=':', linewidth=1))
            ax.text((x1 + x2) / 2, (y1 + y2) / 2, name, fontsize=8, ha='center', va='center', color='blue')

    ax.set_xlim(config.EXTENT[0], config.EXTENT[1])
    ax.set_ylim(config.EXTENT[2], config.EXTENT[3])
    ax.set_title("Position estimée des balises (projection 2D)")
    ax.grid(True)
    ax.legend()

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

def is_position_in_zones(x, y):
    """Vérifier si la position (x, y) est dans une des zones définies"""
    if not hasattr(config, 'USE_ZONES') or not config.USE_ZONES:
        return True, None
        
    for name, x1, y1, x2, y2 in config.ZONES:
        if x1 <= x <= x2 and y1 <= y <= y2:
            return True, name
    return False, None

def find_closest_zone(x, y):
    """Trouver la zone la plus proche et retourner une position corrigée"""
    if not hasattr(config, 'USE_ZONES') or not config.USE_ZONES:
        return None, (x, y)
        
    min_distance = float('inf')
    closest_zone = None
    corrected_pos = (x, y)
    
    for name, x1, y1, x2, y2 in config.ZONES:
        corrected_x = max(x1, min(x, x2))
        corrected_y = max(y1, min(y, y2))
        distance = ((x - corrected_x) ** 2 + (y - corrected_y) ** 2) ** 0.5
        
        if distance < min_distance:
            min_distance = distance
            closest_zone = name
            corrected_pos = (corrected_x, corrected_y)
    
    return closest_zone, corrected_pos

def update(frame):
    """Mise à jour avec filtrage des balises et transformation des coordonnées"""
    global circle_artists, text_artists, beacon_points
    
    # Utiliser config.* au lieu des variables importées
    if not config.GATEWAY_POSITIONS:
        return
        
    data = load_data()
    if not data:
        return

    # Nettoyage des anciens cercles ET des textes
    for circ in circle_artists:
        circ.remove()
    for text in text_artists:
        text.remove()
    circle_artists.clear()
    text_artists.clear()

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
    
    new_beacon_added = False
    
    # Traiter chaque balise séparément
    for i, (beacon_name, beacon_entries) in enumerate(beacon_data.items()):
        color = beacon_colors[i % len(beacon_colors)]
        
        # Créer le point pour cette balise s'il n'existe pas
        if beacon_name not in beacon_points:
            point, = ax.plot([], [], 'o', color=color, label=f"{beacon_name}", markersize=8)
            beacon_points[beacon_name] = point
            new_beacon_added = True
            print(f"[DEBUG] Nouveau point créé pour {beacon_name}")

        filtered_rssi = {}
        for gw in config.GATEWAY_POSITIONS:
            values = [
                d.get("median", d["rssi"]) + config.CORRECTION_RSSI.get(gw, 0)
                for d in beacon_entries if d.get("source") == gw 
            ]
            if len(values) < 5:
                continue
            kalman_values = apply_kalman_filter(values[-10:])
            butter_values = apply_butterworth_filter(kalman_values)
            filtered_rssi[gw] = np.mean(butter_values[-5:])

        print(f"[DEBUG] {beacon_name}: {len(filtered_rssi)} gateways avec données")

        if len(filtered_rssi) < 3:
            print(f"[DEBUG] {beacon_name}: Pas assez de gateways ({len(filtered_rssi)} < 3)")
            # Réinitialiser la position si pas assez de données
            beacon_points[beacon_name].set_data([], [])
            continue

        # Synchronisation distances ↔ positions
        valid_gateways = [gw for gw in config.GATEWAY_POSITIONS if gw in filtered_rssi]
        distances = [rssi_to_distance(filtered_rssi[gw]) for gw in valid_gateways]
        positions = [config.GATEWAY_POSITIONS[gw] for gw in valid_gateways]

        print(f"[DEBUG] {beacon_name}: distances = {[f'{d:.1f}m' for d in distances]}")

        # Affichage des cercles de trilatération pour cette balise avec coordonnées transformées
        for j, ((x_gw, y_gw, _), radius) in enumerate(zip(positions, distances)):
            x_gw_display, y_gw_display = transform_coordinates(x_gw, y_gw)
            
            circle = plt.Circle((x_gw_display, y_gw_display), radius, 
                              color=color, fill=False, 
                              linestyle='--', alpha=0.4, linewidth=1.5)
            ax.add_patch(circle)
            circle_artists.append(circle)
            
            # Ajouter le texte à la liste des textes à supprimer
            text = ax.text(x_gw_display + radius * 0.7, y_gw_display + radius * 0.7, 
                          f"{radius:.2f}m", fontsize=8, color=color, alpha=0.7)
            text_artists.append(text)

        # Trilateration et mise à jour de la position de la balise
        pos_3d = trilateration_optim(distances, positions)
        if pos_3d is not None:
            # Appliquer les corrections
            filtered_rssi = apply_path_based_attenuation(pos_3d[:2], filtered_rssi, config.GATEWAY_POSITIONS)
            filtered_rssi = apply_proximity_bonus(distances, filtered_rssi, config.GATEWAY_POSITIONS)

            x, y = pos_3d[0], pos_3d[1]
            
            print(f"[DEBUG] {beacon_name}: Position calculée = ({x:.2f}, {y:.2f})")
            
            # Vérifier si le système de zones est activé
            if hasattr(config, 'USE_ZONES') and config.USE_ZONES and config.ZONES:
                # Vérifier si la position est dans une zone autorisée
                in_zone, zone_name = is_position_in_zones(x, y)
                
                if in_zone:
                    x_display, y_display = transform_coordinates(x, y)
                    beacon_points[beacon_name].set_data([x_display], [y_display])
                    print(f"[INFO] ✅ {beacon_name} détectée dans la zone : {zone_name} ({x:.2f}, {y:.2f}) -> affichage ({x_display:.2f}, {y_display:.2f})")
                else:
                    closest_zone, (corrected_x, corrected_y) = find_closest_zone(x, y)
                    x_display, y_display = transform_coordinates(corrected_x, corrected_y)
                    beacon_points[beacon_name].set_data([x_display], [y_display])
                    print(f"[WARNING] ⚠️  {beacon_name} corrigée vers : {closest_zone} ({corrected_x:.2f}, {corrected_y:.2f}) -> affichage ({x_display:.2f}, {y_display:.2f})")
            else:
                # Pas de contrainte de zones - utiliser la position brute transformée
                x_display, y_display = transform_coordinates(x, y)
                beacon_points[beacon_name].set_data([x_display], [y_display])
                print(f"[INFO] 📍 {beacon_name} position libre : ({x:.2f}, {y:.2f}) -> affichage ({x_display:.2f}, {y_display:.2f})")
        else:
            print(f"[DEBUG] {beacon_name}: Échec de la trilatération")
            # Réinitialiser la position si échec
            beacon_points[beacon_name].set_data([], [])

    # Mettre à jour la légende si de nouvelles balises ont été ajoutées
    if new_beacon_added:
        ax.legend(loc='upper right')

    # Forcer le rafraîchissement du plot
    plt.draw()
    plt.pause(0.01)  # Petite pause pour forcer l'actualisation

def start():
    """Fonction principale pour démarrer le plot"""
    print("[PLOT] Démarrage du système de visualisation...")
    
    # Charger la configuration depuis le fichier
    if not config.load_config_from_file():
        print("[ERREUR] Impossible de charger la configuration")
        return
    
    # Attendre que la config soit complètement chargée
    import time
    timeout = 10  # 10 secondes maximum
    start_time = time.time()
    
    while not config.GATEWAY_POSITIONS and (time.time() - start_time) < timeout:
        print("[PLOT] Attente de la configuration...")
        time.sleep(0.5)
        config.load_config_from_file()
    
    if not config.GATEWAY_POSITIONS:
        print("[ERREUR] Configuration non disponible après timeout")
        return
    
    # Configurer le plot avec le préset chargé
    setup_plot()
    
    # Démarrer l'animation
    ani = FuncAnimation(fig, update, interval=4000, cache_frame_data=False)
    plt.show()
