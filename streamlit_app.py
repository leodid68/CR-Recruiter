import requests
import time
from collections import deque

# --- CONFIGURATION ---
# REMPLACEZ CECI PAR VOTRE NOUVELLE CLÉ (celle postée est compromise)
API_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6ImJlYzUzMzc0LTg1MmEtNDgzMS05NmYxLTYxMDA5ZjU1Y2ZmMSIsImlhdCI6MTc2NjM5OTY2Nywic3ViIjoiZGV2ZWxvcGVyLzQzMGFmNGE1LWYzYjQtMGQzOS1iOWIyLTljZGFmMGNiYzlhMyIsInNjb3BlcyI6WyJyb3lhbGUiXSwibGltaXRzIjpbeyJ0aWVyIjoiZGV2ZWxvcGVyL3NpbHZlciIsInR5cGUiOiJ0aHJvdHRsaW5nIn0seyJjaWRycyI6WyIxNzYuMTcwLjY5LjIwNCJdLCJ0eXBlIjoiY2xpZW50In1dfQ.YnJQOep4EeaZoSVsNfGG9kbLlkdbiME0H_q7FIiaoGHCD3Y39v1HqfqYZ7q05bB6OPzjssSSMeDQ86WUTwuooQ"
BASE_URL = "https://api.clashroyale.com/v1"

# Le point de départ
SEED_PLAYER_TAG = "#989R2RPQ"

# Filtres de recrutement (Ce qu'on cherche)
MIN_TROPHIES = 7500
MAX_TROPHIES = 11000

# Filtre de "qualité de scan" 
# Pour éviter de scanner des joueurs trop faibles qui polluent la recherche,
# on ajoute à la file d'attente seulement les joueurs au dessus de ce score :
MIN_TROPHIES_TO_SCAN = 7000 

headers = {
    "Authorization": f"Bearer {API_TOKEN}",
    "Accept": "application/json"
}

# --- FONCTIONS API ---

def get_battle_log(player_tag):
    """Récupère les derniers combats"""
    clean_tag = player_tag.replace("#", "%23")
    url = f"{BASE_URL}/players/{clean_tag}/battlelog"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def get_player_detail(player_tag):
    """Récupère les détails précis"""
    clean_tag = player_tag.replace("#", "%23")
    url = f"{BASE_URL}/players/{clean_tag}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# --- MOTEUR SNOWBALL ---

def start_snowball(seed_tag):
    # La file d'attente (FIFO - First In First Out)
    scan_queue = deque([seed_tag])
    
    # Mémoire cache pour ne pas scanner deux fois le même joueur
    visited_tags = set([seed_tag])
    
    found_count = 0
    scanned_count = 0

    print(f"🚀 Démarrage du Snowball à partir de {seed_tag}...")
    print(f"🎯 Cible : {MIN_TROPHIES} - {MAX_TROPHIES} trophées sans clan.")
    print("-" * 50)

    while len(scan_queue) > 0:
        # 1. On prend le prochain joueur dans la file
        current_tag = scan_queue.popleft()
        
        # Petit affichage de progression
        # print(f"🔍 Scan du journal de {current_tag} (File d'attente: {len(scan_queue)})")

        battles = get_battle_log(current_tag)
        
        # Pour chaque combat dans son historique
        for battle in battles:
            opponents = battle.get('opponent', [])
            
            for opp in opponents:
                opp_tag = opp['tag']

                # Si on ne connait pas ce joueur, on l'analyse
                if opp_tag not in visited_tags:
                    visited_tags.add(opp_tag) # On le marque comme "vu"
                    
                    player_data = get_player_detail(opp_tag)
                    scanned_count += 1
                    
                    if player_data:
                        trophies = player_data.get("trophies", 0)
                        has_clan = "clan" in player_data
                        name = player_data.get("name", "Unknown")

                        # --- VERIFICATION : EST-CE UNE RECRUE POTENTIELLE ? ---
                        if not has_clan and MIN_TROPHIES <= trophies <= MAX_TROPHIES:
                            found_count += 1
                            print(f"✅ [{found_count}] RECRUE TROUVÉE !")
                            print(f"   Nom: {name} | Trophées: {trophies}")
                            print(f"   Tag: {opp_tag}")
                            print(f"   🔗 https://royaleapi.com/player/{opp_tag.replace('#', '')}")
                            print("-" * 30)
                        
                        # --- LOGIQUE DE CASCADE ---
                        # Si le joueur a un bon niveau (même s'il a un clan), 
                        # on l'ajoute à la file pour scanner SES adversaires plus tard.
                        # Cela permet de rester dans le "Haut Ladder".
                        if trophies >= MIN_TROPHIES_TO_SCAN:
                            scan_queue.append(opp_tag)
                            # print(f"   -> Ajouté à la file (niv {trophies})")
                    
                    # Pause très courte pour respecter l'API (Rate Limit)
                    time.sleep(0.05)

        # Pause entre chaque scan de journal de combat complet
        time.sleep(0.1)

        # Sécurité anti-crash si la liste devient vide (peu probable en haut niveau)
        if len(scan_queue) == 0:
            print("File d'attente vide. Fin du scan.")
            break

# --- LANCEMENT ---
if __name__ == "__main__":
    try:
        start_snowball(SEED_PLAYER_TAG)
    except KeyboardInterrupt:
        print("\n🛑 Script arrêté par l'utilisateur.")