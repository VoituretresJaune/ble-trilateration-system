import os

# === PRÉSETS DE CONFIGURATION ===

PRESETS = {
    "salle_1": {
        "name": "Gare du Nord",
        "image_file": "data/map_GDN1.png",
        "extent": [0, 20, 0, 11],
        "gateway_positions": {
            "esp32_1": (0.93, 7.83, 0.7),
            "esp32_2": (0.87, 1.47, 0.7),
            "esp32_3": (13.24, 6.94, 3.8),
            "esp32_4": (14.0, 3.43, 3.8),
        },
        "zones": [
            ("zone_1", 0.883, 5.38, 4.8, 7.89),
            ("zone_2", 0.883, 1.5, 4.8, 4.2),
            ("zone_3", 1.1, 0.1, 19, 0.7),
            ("zone_4", 10.5, 2.5, 13, 7.35),
            ("zone_5", 13.3, 1.3, 19, 3.5),
            ("zone_6", 14, 3.5, 19, 7.85),
            ("zone_7", 5, 6.2, 9, 8),
            ("zone_8", 5, 1, 11, 2.5)
        ],
        "correction_rssi": {
            "esp32_1": +10,
            "esp32_2": +10,
            "esp32_3": +13,
            "esp32_4": +13,
        }
    },

    
    "salle_2_multi": {
        "name": "Rambuteau - Multi-étages",
        "multi_floor": True,
        "floors": [
            {
                "name": "Rez-de-chaussée",
                "image_file": "data/RambuteauRC.png",
                "extent": [0, 25, 0, 15],
                "gateway_positions": {
                    "esp32_1": (2.56, 4.10, 1),
                    "esp32_2": (24.65, 3.88, 1),
                    "esp32_3": (0.2, 12, 1)
                },
                "zones": [
                    ("zone_1", 11, 0.45, 25, 4.0),
                    ("zone_2", 22, 4, 25, 6.6),
                    ("zone_3", 0, 8, 6.5, 13.5),
                    ("zone_4", 0.8, 0.55, 8.5, 6)


                ]
            },
            {
                "name": "1er étage",
                "image_file": "data/RambuteauEtage.png",
                "extent": [0, 25, 0, 15],
                "gateway_positions": {
                    "esp32_4": (20, 1.73, 1)
                },
                "zones": [
                    ("zone_4", 0, 0, 25, 15)

                ]
            }
        ],
        "correction_rssi": {
            "esp32_1": +0,
            "esp32_2": +0,
            "esp32_3": +0,
            "esp32_4": +0
        }
    },
}

def get_available_presets():
    """Retourne la liste des présets disponibles"""
    return list(PRESETS.keys())

def get_preset_info(preset_key):
    """Retourne les informations d'un préset"""
    return PRESETS.get(preset_key, None)

def validate_preset(preset_key):
    """Vérifie qu'un préset existe et que ses images sont disponibles"""
    if preset_key not in PRESETS:
        return False, f"Préset '{preset_key}' inexistant"
    
    preset = PRESETS[preset_key]
    
    # Gestion des présets multi-étages
    if preset.get("multi_floor", False):
        # Vérifier les images de chaque étage
        for i, floor in enumerate(preset.get("floors", [])):
            image_path = floor.get("image_file", "")
            if not os.path.exists(image_path):
                return False, f"Image étage {i+1} '{image_path}' introuvable"
        return True, "OK"
    
    # Gestion des présets simples
    image_path = preset.get("image_file", "")
    if not image_path:
        return False, "Aucune image définie"
    
    if not os.path.exists(image_path):
        return False, f"Image '{image_path}' introuvable"
    
    return True, "OK"