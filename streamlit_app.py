import streamlit as st
import requests
import time
import csv
import os
import pandas as pd
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Clash Royale Recruiter", page_icon="⚔️", layout="wide")

st.title("⚔️ Clash Royale - Recruteur de Talents")
st.markdown("""
Cette application permet de trouver des joueurs **sans clan** correspondant à vos critères de trophées.
""")

# --- SIDEBAR : CONFIGURATION ---
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API", type="password", help="Obtenez votre clé sur developer.clashroyale.com")
    
    st.subheader("🎯 Filtres")
    min_trophies = st.number_input("Trophées Min", value=7500, step=100)
    max_trophies = st.number_input("Trophées Max", value=11000, step=100)
    
    st.subheader("🌍 Localisation")
    only_french = st.checkbox("🇫🇷 Recruter uniquement français", value=False, help="Filtre les joueurs ayant affronté des clans français récemment.")
    
    st.subheader("🏁 Objectif")
    limit_recruits = st.number_input("Nombre de recrues à trouver", value=100, min_value=1, max_value=500)
    
    st.subheader("🌱 Point de départ")
    seed_tag = st.text_input("Tag Joueur Initial", value="#989R2RPQ")

    max_workers = st.slider("Vitesse (Threads)", 1, 10, 5)

# --- INITIALISATION DE L'ÉTAT ---
if 'players_found' not in st.session_state:
    st.session_state.players_found = []
if 'scanning' not in st.session_state:
    st.session_state.scanning = False

def start_scanning():
    st.session_state.scanning = True
    st.session_state.players_found = []

def stop_scanning():
    st.session_state.scanning = False

# --- LOGIQUE API ---
BASE_URL = "https://api.clashroyale.com/v1"

def get_headers(key):
    return {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json"
    }

def get_player_detail(session, player_tag, headers):
    clean_tag = player_tag.replace("#", "%23")
    url = f"{BASE_URL}/players/{clean_tag}"
    try:
        resp = session.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None

def get_battle_log(session, player_tag, headers):
    clean_tag = player_tag.replace("#", "%23")
    url = f"{BASE_URL}/players/{clean_tag}/battlelog"
    try:
        resp = session.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        return []
    except:
        return []

def is_french_relevance(battle_log):
    """
    Vérifie si le joueur semble être dans la sphère française.
    On regarde la localisation des clans de ses adversaires ou coéquipiers.
    Code France dans l'API : 57000087
    """
    fr_signals = 0
    for battle in battle_log:
        # Check opponent clan
        opponents = battle.get('opponent', [])
        for opp in opponents:
            clan = opp.get('clan')
            if clan:
                # Malheureusement le battlelog court ne donne pas la localisation du clan
                # mais on peut filtrer par les noms de clans contenant "FR", "France", etc.
                clan_name = clan.get('name', '').lower()
                if any(x in clan_name for x in ["fr ", " fr", "france", "français"]):
                    fr_signals += 1
    return fr_signals > 0

# --- INTERFACE PRINCIPALE ---
col1, col2 = st.columns([1, 3])

with col1:
    st.button("🚀 Lancer la recherche", use_container_width=True, disabled=st.session_state.scanning, on_click=start_scanning)
    st.button("🛑 Arrêter", use_container_width=True, disabled=not st.session_state.scanning, on_click=stop_scanning)

results_container = st.empty()
progress_bar = st.progress(0)
status_text = st.empty()

if st.session_state.scanning:
    if not api_key:
        st.error("Veuillez saisir votre clé API dans la barre latérale.")
        st.session_state.scanning = False
    else:
        
        headers = get_headers(api_key)
        session = requests.Session()
        
        queue = deque([seed_tag])
        visited = {seed_tag}
        found_count = 0
        scanned_count = 0
        
        # Préparation du CSV
        csv_filename = "recrues_clash_streamlit.csv"
        # Utilisation de la virgule pour éviter le ParserError
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Tag", "Nom", "Trophées", "Lien RoyaleAPI"])

        while queue and st.session_state.scanning and found_count < limit_recruits:
            current_tag = queue.popleft()
            battles = get_battle_log(session, current_tag, headers)
            
            new_tags = []
            for b in battles:
                opps = b.get('opponent', [])
                for o in opps:
                    tag = o.get('tag')
                    if tag and tag not in visited:
                        visited.add(tag)
                        new_tags.append(tag)
            
            if not new_tags:
                continue
            
            # Correction : on ajoute les nouveaux tags à la file pour continuer la recherche
            queue.extend(new_tags)
                
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(get_player_detail, session, t, headers): t for t in new_tags}
                for future in as_completed(futures):
                    if not st.session_state.scanning: break
                    
                    p_data = future.result()
                    scanned_count += 1
                    
                    if p_data:
                        trophies = p_data.get('trophies', 0)
                        has_clan = 'clan' in p_data
                        
                        # Filtre de base
                        if not has_clan and min_trophies <= trophies <= max_trophies:
                            
                            # Filtre Français (optionnel)
                            is_fr = True
                            if only_french:
                                # On récupère son battle log pour checker la pertinence FR
                                p_battles = get_battle_log(session, p_data['tag'], headers)
                                is_fr = is_french_relevance(p_battles)
                            
                            if is_fr:
                                found_count += 1
                                p_tag = p_data['tag']
                                p_name = p_data['name']
                                st.session_state.players_found.append({
                                    "Tag": p_tag,
                                    "Nom": p_name,
                                    "Trophées": trophies,
                                    "Lien": f"https://royaleapi.com/player/{p_tag.replace('#', '')}"
                                })
                                
                                # Sauvegarde CSV
                                with open(csv_filename, 'a', newline='', encoding='utf-8') as f:
                                    writer = csv.writer(f)
                                    writer.writerow([p_tag, p_name, trophies, f"https://royaleapi.com/player/{p_tag.replace('#', '')}"])
                                
                    # Update UI
                    status_text.text(f"Scannés: {scanned_count} | Trouvés: {found_count}/{limit_recruits}")
                    progress_bar.progress(min(found_count / limit_recruits, 1.0))
                    
                    if found_count >= limit_recruits:
                        st.session_state.scanning = False
                        break
            
            # Affichage en temps réel
            df = pd.DataFrame(st.session_state.players_found)
            results_container.dataframe(df, use_container_width=True)
            
            # Pause pour rate limit
            time.sleep(0.1)

        st.session_state.scanning = False
        if found_count >= limit_recruits:
            st.success(f"Terminé ! {found_count} recrues trouvées.")
            with open(csv_filename, 'rb') as f:
                st.download_button("📥 Télécharger le CSV", f, file_name=csv_filename, mime="text/csv")

# Affichage permanent si pas en train de scanner
if not st.session_state.scanning and st.session_state.players_found:
    df = pd.DataFrame(st.session_state.players_found)
    results_container.dataframe(df, use_container_width=True)
    if os.path.exists("recrues_clash_streamlit.csv"):
        with open("recrues_clash_streamlit.csv", 'rb') as f:
            st.download_button("📥 Télécharger le CSV final", f, file_name="recrues_clash_streamlit.csv", mime="text/csv")
