import multiprocessing
from multiprocessing import Process
import os
import time
import json
from core import server
from core import trilateration_plot
from core.config import load_preset
from core.presets import get_available_presets, get_preset_info, validate_preset

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "data.json")

# Liste des beacons pour créer les fichiers individuels
BEACON_LIST = ["balise_1", "balise_2", "balise_4", "balise_5"]

def select_preset():
    """Interface de sélection du préset"""
    print("\n" + "="*50)
    print("🏢 SÉLECTION DE LA CONFIGURATION")
    print("="*50)
    
    presets = get_available_presets()
    
    # Afficher les options
    for i, preset_key in enumerate(presets, 1):
        preset_info = get_preset_info(preset_key)
        valid, msg = validate_preset(preset_key)
        status = "✅" if valid else "❌"
        print(f"{i}. {status} {preset_info['name']} ({preset_key})")
        if not valid:
            print(f"   ⚠️  {msg}")
    
    print("\n0. Quitter")
    
    # Sélection utilisateur
    while True:
        try:
            choice = input(f"\nChoisissez une configuration (1-{len(presets)} ou 0): ").strip()
            
            if choice == "0":
                print("Arrêt du programme.")
                return None
            
            choice_num = int(choice)
            if 1 <= choice_num <= len(presets):
                selected_preset = presets[choice_num - 1]
                
                # Vérifier la validité
                valid, msg = validate_preset(selected_preset)
                if not valid:
                    print(f"❌ {msg}")
                    continue
                
                preset_info = get_preset_info(selected_preset)
                print(f"\n✅ Configuration sélectionnée : {preset_info['name']}")
                return selected_preset
            else:
                print("❌ Choix invalide.")
                
        except ValueError:
            print("❌ Veuillez entrer un nombre.")
        except KeyboardInterrupt:
            print("\n\nArrêt du programme.")
            return None

def clear_data_file():
    try:
        with open(DATA_FILE, "w") as f:
            f.write("[]")
        print(f"[INFO] Fichier data.json réinitialisé.")
    except Exception as e:
        print(f"[ERREUR] Impossible de vider {DATA_FILE} : {e}")

def create_beacon_files():
    """Créer un fichier JSON vide pour chaque beacon"""
    for beacon in BEACON_LIST:
        beacon_file = os.path.join(DATA_DIR, f"{beacon}.json")
        try:
            with open(beacon_file, "w") as f:
                json.dump([], f, indent=2)
            print(f"[INFO] Fichier {beacon}.json créé/réinitialisé.")
        except Exception as e:
            print(f"[ERREUR] Impossible de créer {beacon_file} : {e}")

if __name__ == '__main__':
    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        pass  # contexte déjà initialisé

    # === SÉLECTION DU PRÉSET ===
    selected_preset = select_preset()
    if not selected_preset:
        exit(0)
    
    # === CHARGEMENT DE LA CONFIGURATION ===
    try:
        load_preset(selected_preset)
        print(f"[MAIN] Préset '{selected_preset}' chargé avec succès")
        
        # Détecter si c'est un préset multi-étages
        from core.presets import PRESETS
        is_multifloor = PRESETS[selected_preset].get("multi_floor", False)
        
    except Exception as e:
        print(f"❌ Erreur lors du chargement du préset : {e}")
        exit(1)

    # === INITIALISATION ===
    clear_data_file()
    create_beacon_files()

    try:
        # Lancer le serveur
        p1 = Process(target=server.start_server, daemon=True)
        p1.start()
        print("[INFO] Serveur lancé.")

        time.sleep(1)

        # Choisir le bon type de plot
        if is_multifloor:
            from core import multifloor_plot
            p2 = Process(target=multifloor_plot.start_multifloor, daemon=True)
            print("[INFO] Plot multi-étages lancé.")
        else:
            from core import trilateration_plot
            p2 = Process(target=trilateration_plot.start, daemon=True)
            print("[INFO] Plot simple lancé.")
        
        p2.start()

        # Boucle d'attente infinie jusqu'à interruption clavier
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[INFO] Interruption clavier (Ctrl+C) détectée.")

    finally:
        if 'p1' in locals() and p1.is_alive():
            print("[INFO] Arrêt du serveur Flask...")
            p1.terminate()
            p1.join()

        if 'p2' in locals() and p2.is_alive():
            print("[INFO] Arrêt du processus de plot...")
            p2.terminate()
            p2.join()

        clear_data_file()
        for beacon in BEACON_LIST:
            beacon_file = os.path.join(DATA_DIR, f"{beacon}.json")
            try:
                with open(beacon_file, "w") as f:
                    json.dump([], f, indent=2)
            except:
                pass
        
        print("[INFO] Fin du programme.")
