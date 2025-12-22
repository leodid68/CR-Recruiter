import streamlit as st
import pandas as pd
import requests
import json
import io
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- PAGE CONFIG ---
st.set_page_config(page_title="Clash Royale Recruiter", page_icon="⚔️", layout="wide")

st.title("⚔️ Clash Royale - Recruteur de Talents")
st.markdown("Trouvez des joueurs **sans clan** correspondant à vos critères.")

# --- API FUNCTIONS ---
BASE_URL = "https://api.clashroyale.com/v1"

def get_headers(key):
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}

def get_player_detail(session, player_tag, headers):
    clean_tag = player_tag.replace("#", "%23")
    url = f"{BASE_URL}/players/{clean_tag}"
    try:
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            print(f"[RATE LIMIT] Waiting...")
            time.sleep(3)
            return get_player_detail(session, player_tag, headers)
        else:
            print(f"[ERROR] Player {player_tag}: status {resp.status_code}")
        return None
    except Exception as e:
        print(f"[ERROR] Player {player_tag}: {e}")
        return None

def get_battle_log(session, player_tag, headers):
    clean_tag = player_tag.replace("#", "%23")
    url = f"{BASE_URL}/players/{clean_tag}/battlelog"
    try:
        resp = session.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            print(f"[RATE LIMIT] Waiting...")
            time.sleep(3)
            return get_battle_log(session, player_tag, headers)
        else:
            print(f"[ERROR] Battlelog {player_tag}: status {resp.status_code}")
        return []
    except Exception as e:
        print(f"[ERROR] Battlelog {player_tag}: {e}")
        return []

def is_french_relevance(battle_log):
    for battle in battle_log:
        for opp in battle.get('opponent', []):
            clan = opp.get('clan')
            if clan:
                clan_name = clan.get('name', '').lower()
                if any(x in clan_name for x in ["fr ", " fr", "france", "français"]):
                    return True
    return False

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API", type="password")
    
    st.subheader("🎯 Filtres")
    min_trophies = st.number_input("Trophées Min", value=80, step=100)
    max_trophies = st.number_input("Trophées Max", value=15000, step=100)
    only_french = st.checkbox("🇫🇷 Francophones uniquement", value=False)
    
    st.subheader("🏁 Objectif")
    limit_recruits = st.number_input("Nombre de recrues", value=100, min_value=1, max_value=500)
    
    st.subheader("🌱 Point de départ")
    seed_tag = st.text_input("Tag Joueur Initial", value="#989R2RPQ")
    
    max_workers = st.slider("Vitesse (Threads)", 1, 10, 5)

# --- SESSION STATE ---
if 'players_found' not in st.session_state:
    st.session_state.players_found = []
if 'scanning' not in st.session_state:
    st.session_state.scanning = False

def start_scanning():
    st.session_state.scanning = True
    st.session_state.players_found = []

def stop_scanning():
    st.session_state.scanning = False

# --- UI ---
col1, col2 = st.columns([1, 3])
with col1:
    st.button("🚀 Lancer la recherche", use_container_width=True, disabled=st.session_state.scanning, on_click=start_scanning)
    st.button("🛑 Arrêter", use_container_width=True, disabled=not st.session_state.scanning, on_click=stop_scanning)

results_container = st.empty()
progress_bar = st.progress(0)
status_text = st.empty()

# --- SCANNING ---
if st.session_state.scanning:
    if not api_key:
        st.error("Veuillez saisir votre clé API.")
        st.session_state.scanning = False
    else:
        status_text.info(f"🔄 Démarrage de la recherche depuis {seed_tag}...")
        print(f"[START] Scanning from {seed_tag}")
        
        headers = get_headers(api_key)
        session = requests.Session()
        
        # Test API key first
        print(f"[TEST] Testing API key with seed player...")
        initial_battles = get_battle_log(session, seed_tag, headers)
        
        if not initial_battles:
            st.error("❌ Impossible de récupérer les données. Vérifiez votre clé API et le tag du joueur.")
            print(f"[FAIL] Could not get battle log for {seed_tag}")
            st.session_state.scanning = False
        else:
            print(f"[OK] Got {len(initial_battles)} battles from seed")
            
            queue = deque()
            visited = {seed_tag}
            found_count = 0
            scanned_count = 0
            
            # Extract initial tags from seed's battles
            for b in initial_battles:
                for team in ['team', 'opponent']:
                    for p in b.get(team, []):
                        tag = p.get('tag')
                        if tag and tag not in visited:
                            visited.add(tag)
                            queue.append(tag)
            
            print(f"[QUEUE] Initial queue: {len(queue)} players")
            status_text.info(f"🔍 {len(queue)} joueurs trouvés, début du scan...")
            
            while queue and st.session_state.scanning and found_count < limit_recruits:
                # Take batch from queue
                batch = []
                for _ in range(min(max_workers, len(queue))):
                    if queue:
                        batch.append(queue.popleft())
                
                if not batch:
                    break
                
                print(f"[BATCH] Processing {len(batch)} players...")
                
                # Process batch in parallel
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(get_player_detail, session, t, headers): t for t in batch}
                    
                    for future in as_completed(futures):
                        if not st.session_state.scanning or found_count >= limit_recruits:
                            break
                        
                        tag = futures[future]
                        p_data = future.result()
                        scanned_count += 1
                        
                        if p_data:
                            trophies = p_data.get('trophies', 0)
                            has_clan = 'clan' in p_data
                            
                            # Check filters
                            if not has_clan and min_trophies <= trophies <= max_trophies:
                                is_fr = True
                                if only_french:
                                    p_battles = get_battle_log(session, tag, headers)
                                    is_fr = is_french_relevance(p_battles)
                                
                                if is_fr:
                                    found_count += 1
                                    print(f"[FOUND] {p_data.get('name')} - {trophies} trophies")
                                    st.session_state.players_found.append({
                                        "Tag": p_data['tag'],
                                        "Nom": p_data.get('name', 'Unknown'),
                                        "Trophées": trophies,
                                        "Lien": f"https://royaleapi.com/player/{p_data['tag'].replace('#', '')}"
                                    })
                            
                            # Get battle log for more tags
                            battles = get_battle_log(session, tag, headers)
                            for b in battles:
                                for team in ['team', 'opponent']:
                                    for p in b.get(team, []):
                                        new_tag = p.get('tag')
                                        if new_tag and new_tag not in visited:
                                            visited.add(new_tag)
                                            queue.append(new_tag)
                        
                        # Update UI
                        status_text.text(f"Scannés: {scanned_count} | Trouvés: {found_count}/{limit_recruits} | File: {len(queue)}")
                        progress_bar.progress(min(found_count / limit_recruits, 1.0))
                
                # Show results
                if st.session_state.players_found:
                    df = pd.DataFrame(st.session_state.players_found)
                    results_container.dataframe(df, use_container_width=True, hide_index=True)
                
                time.sleep(0.05)
            
            st.session_state.scanning = False
            print(f"[DONE] Found {found_count} players")
            st.success(f"✨ Terminé ! {found_count} recrues trouvées.")
            st.rerun()

# --- RESULTS ---
if not st.session_state.scanning and st.session_state.players_found:
    df = pd.DataFrame(st.session_state.players_found)
    results_container.dataframe(df, use_container_width=True, hide_index=True)
    
    st.subheader("💾 Exporter")
    col_csv, col_json, col_excel = st.columns(3)
    
    with col_csv:
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button("📥 CSV", csv_buffer.getvalue(), "recrues.csv", "text/csv", use_container_width=True)
    
    with col_json:
        json_str = json.dumps(st.session_state.players_found, ensure_ascii=False, indent=2)
        st.download_button("📥 JSON", json_str, "recrues.json", "application/json", use_container_width=True)
    
    with col_excel:
        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False, engine='openpyxl')
        st.download_button("📥 Excel", excel_buffer.getvalue(), "recrues.xlsx", 
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
