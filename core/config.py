from shapely.geometry import LineString, box, Polygon
import os
import json

# === CONFIGURATION GLOBALE ===
DATA_DIR = "data"
DATA_FILE = os.path.join(DATA_DIR, "data.json")
CONFIG_FILE = os.path.join(DATA_DIR, "current_config.json")

# === CONFIGURATION ACTIVE (sera définie par le préset choisi) ===
ACTIVE_PRESET = None
GATEWAY_POSITIONS = {}
ZONES = []
CORRECTION_RSSI = {}
IMAGE_FILE = ""
EXTENT = [0, 20, 0, 11]
floors = []  # Ajouter cette variable globale

def load_preset(preset_key):
    """Charger un préset de configuration"""
    global ACTIVE_PRESET, GATEWAY_POSITIONS, ZONES, CORRECTION_RSSI, IMAGE_FILE, EXTENT, floors
    
    from core.presets import PRESETS
    
    if preset_key not in PRESETS:
        raise ValueError(f"Préset '{preset_key}' inexistant")
    
    preset = PRESETS[preset_key]
    ACTIVE_PRESET = preset_key
    
    # S'assurer que le dossier data existe
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Vérifier si c'est un préset multi-étages
    if preset.get("multi_floor", False):
        # Configuration multi-étages
        floors = preset["floors"]
        
        # Fusionner tous les gateways
        GATEWAY_POSITIONS = {}
        ZONES = []
        for floor in floors:
            GATEWAY_POSITIONS.update(floor["gateway_positions"])
            ZONES.extend(floor["zones"])
        
        CORRECTION_RSSI = preset["correction_rssi"]
        IMAGE_FILE = ""  # Pas d'image unique
        EXTENT = preset["floors"][0]["extent"]  # Utiliser l'extent du premier étage
        
    else:
        # Configuration simple étage
        floors = []  # Réinitialiser
        GATEWAY_POSITIONS = preset["gateway_positions"]
        ZONES = preset["zones"]
        CORRECTION_RSSI = preset["correction_rssi"]
        IMAGE_FILE = preset["image_file"]
        EXTENT = preset["extent"]
    
    # Sauvegarder la config
    config_data = {
        "active_preset": ACTIVE_PRESET,
        "gateway_positions": GATEWAY_POSITIONS,
        "zones": ZONES,
        "correction_rssi": CORRECTION_RSSI,
        "image_file": IMAGE_FILE,
        "extent": EXTENT
    }
    
    # Ajouter les étages si multi-floor
    if preset.get("multi_floor", False):
        config_data["floors"] = floors
    
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=2)
        print(f"[CONFIG] Configuration sauvegardée dans {CONFIG_FILE}")
    except Exception as e:
        print(f"[ERREUR] Impossible de sauvegarder la config : {e}")
    
    print(f"[CONFIG] Préset '{preset['name']}' chargé")
    if floors:
        print(f"[CONFIG] Mode multi-étages: {len(floors)} étages")
    else:
        print(f"[CONFIG] Image: {IMAGE_FILE}")
    print(f"[CONFIG] Gateways: {len(GATEWAY_POSITIONS)}")
    print(f"[CONFIG] Zones: {len(ZONES)}")

def load_config_from_file():
    """Charger la configuration depuis le fichier (pour les processus séparés)"""
    global ACTIVE_PRESET, GATEWAY_POSITIONS, ZONES, CORRECTION_RSSI, IMAGE_FILE, EXTENT, floors
    
    if not os.path.exists(CONFIG_FILE):
        print(f"[WARNING] Fichier de config {CONFIG_FILE} introuvable")
        return False
    
    try:
        with open(CONFIG_FILE, "r") as f:
            config_data = json.load(f)
        
        ACTIVE_PRESET = config_data.get("active_preset")
        GATEWAY_POSITIONS = config_data.get("gateway_positions", {})
        ZONES = config_data.get("zones", [])
        CORRECTION_RSSI = config_data.get("correction_rssi", {})
        IMAGE_FILE = config_data.get("image_file", "")
        EXTENT = config_data.get("extent", [0, 20, 0, 11])
        
        # Charger les étages si présents
        floors = config_data.get("floors", [])
        
        print(f"[CONFIG] Configuration chargée depuis {CONFIG_FILE}")
        if floors:
            print(f"[CONFIG] Mode multi-étages: {len(floors)} étages")
        else:
            print(f"[CONFIG] Image: {IMAGE_FILE}")
        print(f"[CONFIG] Gateways: {len(GATEWAY_POSITIONS)}")
        
        return True
    except Exception as e:
        print(f"[ERREUR] Impossible de charger la config : {e}")
        return False

def get_current_preset_info():
    """Retourne les infos du préset actuel"""
    if ACTIVE_PRESET:
        from core.presets import PRESETS
        return PRESETS[ACTIVE_PRESET]
    return None

# === RÉGIONS D'ATTÉNUATION (optionnel) ===
ATTENUATION_REGIONS = [
    {
        "polygon": box(5.167, 10.077, 2.973, 6.520),
        "attenuation_db": 10
    }
]
