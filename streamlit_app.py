import streamlit as st
import requests
import time
import pandas as pd
from collections import deque

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Clash Royale Recruiter",
    page_icon="👑",
    layout="wide"
)

# --- FONCTIONS API ---
def get_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

def get_battle_log(player_tag, token):
    """Récupère les derniers combats"""
    clean_tag = player_tag.replace("#", "%23")
    url = f"https://api.clashroyale.com/v1/players/{clean_tag}/battlelog"
    try:
        response = requests.get(url, headers=get_headers(token), timeout=5)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def get_player_detail(player_tag, token):
    """Récupère les détails précis"""
    clean_tag = player_tag.replace("#", "%23")
    url = f"https://api.clashroyale.com/v1/players/{clean_tag}"
    try:
        response = requests.get(url, headers=get_headers(token), timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

# --- STATE MANAGEMENT ---
if 'scanning' not in st.session_state:
    st.session_state.scanning = False
if 'results' not in st.session_state:
    st.session_state.results = []

def toggle_scan():
    st.session_state.scanning = not st.session_state.scanning

# --- INTERFACE UTILISATEUR ---
st.title("👑 Clash Royale - Chasseur de Recrues")
st.markdown("Ce scanner utilise la méthode **Snowball** pour trouver des joueurs sans clan à haut niveau.")

# 1. BARRE LATÉRALE (Configuration)
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Champ pour le token
    DEFAULT_TOKEN = "" # Laisser vide pour sécurité, l'utilisateur doit le mettre
    api_token = st.text_input("Clé API (Token)", value=DEFAULT_TOKEN, type="password", help="Collez votre clé API Developer ici.")
    
    st.divider()
    
    seed_tag = st.text_input("Tag du joueur 'Graine'", "#989R2RPQ")
    
    st.subheader("🎯 Cibles")
    min_trophies = st.number_input("Trophées Min", value=7500, step=100)
    max_trophies = st.number_input("Trophées Max", value=11000, step=100)
    
    st.subheader("🕷️ Paramètres du Crawler")
    min_scan_quality = st.number_input("Qualité Scan (Min Trophées)", value=7000, help="Ne scanne pas les adversaires en dessous de ce score.")
    max_results = st.number_input("Arrêter après X recrues", value=50, step=10)
    
    st.divider()
    
    # Bouton Start/Stop
    if st.session_state.scanning:
        st.button("🛑 ARRÊTER", on_click=toggle_scan, type="secondary", use_container_width=True)
    else:
        st.button("🚀 LANCER LA RECHERCHE", on_click=toggle_scan, type="primary", use_container_width=True)

# 2. ZONE PRINCIPALE - Métriques
col1, col2, col3 = st.columns(3)
with col1:
    metric_scanned = st.empty()
with col2:
    metric_found = st.empty()
with col3:
    status_text = st.empty()

st.divider()

# Résultats et Logs
col_res, col_logs = st.columns([2, 1])

with col_res:
    st.subheader("� Résultats")
    results_placeholder = st.empty()

with col_logs:
    st.subheader("📜 Logs")
    logs_container = st.empty()

# --- LOGIQUE PRINCIPALE ---
if st.session_state.scanning:
    if not api_token:
        st.error("⚠️ Veuillez entrer une clé API valide dans la barre latérale.")
        st.session_state.scanning = False
    else:
        # Initialisation des variables
        scan_queue = deque([seed_tag])
        visited_tags = set([seed_tag])
        
        # On reprend les résultats existants si on veut accumuler, 
        # mais ici on reset à chaque lancement pour simplifier la logique Snowball
        found_players = [] 
        logs = []
        
        scanned_count = 0
        found_count = 0
        
        status_text.info("🔄 Scan en cours...")
        metric_scanned.metric("Profils Analysés", 0)
        metric_found.metric("✅ Recrues Trouvées", 0)

        try:
            while len(scan_queue) > 0 and found_count < max_results:
                if not st.session_state.scanning:
                    break
                
                current_tag = scan_queue.popleft()
                
                # Update Logs
                logs.append(f"🔍 Analyse: {current_tag}")
                if len(logs) > 15: logs.pop(0)
                logs_container.code("\n".join(logs), language="text")
                
                battles = get_battle_log(current_tag, api_token)
                
                for battle in battles:
                    if not st.session_state.scanning: break
                    
                    opponents = battle.get('opponent', [])
                    
                    for opp in opponents:
                        opp_tag = opp['tag']

                        if opp_tag not in visited_tags:
                            visited_tags.add(opp_tag)
                            scanned_count += 1
                            metric_scanned.metric("Profils Analysés", scanned_count)
                            
                            player_data = get_player_detail(opp_tag, api_token)
                            
                            if player_data:
                                trophies = player_data.get("trophies", 0)
                                has_clan = "clan" in player_data
                                name = player_data.get("name", "Unknown")
                                
                                # CRITÈRE DE RECRUTEMENT
                                if not has_clan and min_trophies <= trophies <= max_trophies:
                                    found_count += 1
                                    metric_found.metric("✅ Recrues Trouvées", found_count)
                                    
                                    clean_tag_link = opp_tag.replace("#", "")
                                    new_player = {
                                        "Nom": name,
                                        "Trophées": trophies,
                                        "Tag": opp_tag,
                                        "Lien RoyaleAPI": f"https://royaleapi.com/player/{clean_tag_link}",
                                    }
                                    found_players.append(new_player)
                                    st.session_state.results = found_players # Save to state
                                    
                                    # Mise à jour Tableau
                                    df = pd.DataFrame(found_players)
                                    results_placeholder.dataframe(
                                        df,
                                        column_config={
                                            "Lien RoyaleAPI": st.column_config.LinkColumn("Lien"),
                                        },
                                        use_container_width=True,
                                        hide_index=True
                                    )

                                    if found_count >= max_results:
                                        break
                                
                                # CRITÈRE DE CONTINUATION (SNOWBALL)
                                if trophies >= min_scan_quality:
                                    scan_queue.append(opp_tag)
                            
                            time.sleep(0.05) # Rate limit
                    
                    if found_count >= max_results:
                        break
                
                time.sleep(0.1)

            st.session_state.scanning = False
            status_text.success("Terminé !")
            
        except Exception as e:
            st.error(f"Erreur: {e}")
            st.session_state.scanning = False

# Export (quand le scan est fini ou arrêté)
if st.session_state.results:
    st.divider()
    df_final = pd.DataFrame(st.session_state.results)
    csv = df_final.to_csv(index=False).encode('utf-8')
    st.download_button(
        "� Télécharger la liste (CSV)",
        csv,
        "recrues.csv",
        "text/csv",
        type="primary"
    )