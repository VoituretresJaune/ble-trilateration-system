from flask import Flask, request, jsonify
from datetime import datetime
import logging
import json
import os
from collections import defaultdict
from core.config import DATA_DIR, DATA_FILE  # 🔁 On récupère depuis config
import socket

# === Setup ===
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
app = Flask(__name__)

os.makedirs(DATA_DIR, exist_ok=True)

rssi_data = []
sliding_windows = defaultdict(list)
WINDOW_SIZE = 5

BEACON_ALIASES = {
    "C300003731FD": "balise_1",
    "C300003731FC": "balise_2",
    "C300003731F8": "balise_4",
    "C300003731DD": "balise_5"
}

def save_to_beacon_file(entry):
    """Sauvegarder une entrée dans le fichier spécifique du beacon"""
    beacon_name = entry["beacon"]
    beacon_file = os.path.join(DATA_DIR, f"{beacon_name}.json")
    
    try:
        # Charger les données existantes
        if os.path.exists(beacon_file):
            with open(beacon_file, "r") as f:
                beacon_data = json.load(f)
        else:
            beacon_data = []
        
        # Ajouter la nouvelle entrée
        beacon_data.append(entry)
        
        # Sauvegarder
        with open(beacon_file, "w") as f:
            json.dump(beacon_data, f, indent=2)
            
    except Exception as e:
        print(f"[ERREUR] Impossible d'écrire dans {beacon_file} : {e}")

# === Chargement initial du fichier de données
if os.path.exists(DATA_FILE) and os.path.getsize(DATA_FILE) > 2:
    try:
        with open(DATA_FILE, "r") as f:
            rssi_data = json.load(f)
    except Exception as e:
        print(f"[WARN] Le fichier {DATA_FILE} est corrompu. Réinitialisation. ({e})")
        rssi_data = []

def compute_sliding_median(mac, new_rssi):
    window = sliding_windows[mac]
    window.append(new_rssi)
    if len(window) > WINDOW_SIZE:
        window.pop(0)
    sorted_vals = sorted(window)
    n = len(sorted_vals)
    return sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2

@app.route('/collect_gateway_info', methods=['POST'])
def collect_data():
    global rssi_data
    data = request.get_json()

    if not data:
        print("[ERREUR] JSON non reçu ou invalide")
        return jsonify({'error': 'No JSON received'}), 400

    entries_to_add = []

    # === Cas ESP32 → JSON sous forme d'objet
    if isinstance(data, dict) and "gateway_id" in data:
        gateway_id = data.get('gateway_id')
        beacon_name = data.get('beacon_name')
        try:
            rssi = int(data.get('rssi'))
            median = int(data.get('median'))
        except (ValueError, TypeError):
            return jsonify({'error': 'RSSI/median must be int'}), 400

        alias = BEACON_ALIASES.get(beacon_name.upper(), beacon_name)
        timestamp = data.get('timestamp', datetime.utcnow().isoformat())
        entry = {
            "time": timestamp,
            "beacon": alias,
            "rssi": rssi,
            "median": median,
            "source": gateway_id
        }
        entries_to_add.append(entry)
        
        # Sauvegarder dans le fichier individuel du beacon
        save_to_beacon_file(entry)

        print(f"[{timestamp}] {gateway_id} → {alias} | RSSI: {rssi} | Médiane: {median}")

    # === Cas MINEW G1 → JSON sous forme de liste
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("type") == "iBeacon":
                mac = item.get("mac")
                try:
                    rssi = int(item.get("rssi"))
                except (ValueError, TypeError):
                    continue
                if mac:
                    alias = BEACON_ALIASES.get(mac.upper(), mac)
                    median = compute_sliding_median(mac, rssi)
                    entry = {
                        "time": datetime.utcnow().isoformat(),
                        "beacon": alias,
                        "rssi": rssi,
                        "median": median,
                        "source": "minew"
                    }
                    entries_to_add.append(entry)
                    
                    # Sauvegarder dans le fichier individuel du beacon
                    save_to_beacon_file(entry)
                    
                    print(f"[Minew G1] → {alias} | RSSI: {rssi} | Médiane glissante: {median:.1f}")

    # === Sauvegarde dans le fichier global (optionnel, peut être supprimé)
    rssi_data.extend(entries_to_add)
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(rssi_data, f, indent=2)
    except Exception as e:
        print(f"[ERREUR] Impossible d'écrire dans {DATA_FILE} : {e}")

    return jsonify({'status': 'ok', 'received': len(entries_to_add)}), 200



def start_server():
    # Obtenir l'adresse IP locale réelle du serveur
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "127.0.0.1"

    print(f"[INFO] IP locale du serveur Flask : {local_ip}")
    print(f"[INFO] Flask démarre sur http://0.0.0.0:5001/ (accessible à http://{local_ip}:5001/)")
    
    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)

if __name__ == '__main__':
    start_server()
