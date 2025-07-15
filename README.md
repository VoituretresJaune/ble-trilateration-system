# Système de Trilatération BLE Multi-Étages

## 📋 Description
Système de localisation indoor utilisant des balises BLE et des ESP32 pour la trilatération en temps réel, avec support multi-étages.

## 🏗️ Architecture
- **ESP32** : Récepteurs BLE pour capturer les signaux RSSI
- **Python Flask** : Serveur de traitement des données
- **Matplotlib** : Visualisation temps réel des positions
- **Filtrage avancé** : Kalman + Butterworth pour la stabilité

## 📊 Balises supportées
| Adresse MAC | Nom de balise |
|-------------|--------------|
| `c3:00:00:37:31:fd` | balise_1 |
| `c3:00:00:37:31:04` | balise_2 |
| `c3:00:00:37:31:f8` | balise_4 |
| `c3:00:00:37:31:dd` | balise_5 |

## 🚀 Installation

### Prérequis
- Python 3.8+
- ESP32 avec firmware BLE
- Balises BLE configurées

### Installation
```bash
# Cloner le repository
git clone https://github.com/YOUR_USERNAME/ble-trilateration-system.git
cd ble-trilateration-system

# Installer les dépendances
pip install -r requirements.txt

# Lancer le système
python main.py