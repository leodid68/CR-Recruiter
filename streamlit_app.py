import streamlit as st
import pandas as pd
import requests
import csv
import json
import io
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="Clash Royale Recruiter", page_icon="⚔️", layout="wide")

st.title("⚔️ Clash Royale - Recruteur de Talents")
st.markdown("Trouvez des joueurs **sans clan** avec notre algorithme de recherche avancé.")

# --- API FUNCTIONS ---
BASE_URL = "https://api.clashroyale.com/v1"

def get_headers(key):
    return {"Authorization": f"Bearer {key}", "Accept": "application/json"}

def get_player_detail(session, player_tag, headers):
    clean_tag = player_tag.replace("#", "%23")
    url = f"{BASE_URL}/players/{clean_tag}"
    try:
        resp = session.get(url, headers=headers, timeout=5)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 429:
            time.sleep(1)
            return get_player_detail(session, player_tag, headers)
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
        elif resp.status_code == 429:
            time.sleep(1)
            return get_battle_log(session, player_tag, headers)
        return []
    except:
        return []

def is_french_relevance(battle_log):
    fr_signals = 0
    for battle in battle_log:
        for opp in battle.get('opponent', []):
            clan = opp.get('clan')
            if clan:
                clan_name = clan.get('name', '').lower()
                if any(x in clan_name for x in ["fr ", " fr", "france", "français"]):
                    fr_signals += 1
    return fr_signals > 0

# --- SIDEBAR : CONFIGURATION ---
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API", type="password", help="Obtenez votre clé sur developer.clashroyale.com")
    
    st.subheader("🎯 Filtres de Base")
    min_trophies = st.number_input("Trophées Min", value=80, step=100)
    max_trophies = st.number_input("Trophées Max", value=15000, step=100)
    
    st.subheader("🔬 Filtres Avancés")
    max_inactive = st.number_input("Inactif max (jours)", value=30, min_value=1, max_value=365, 
                                   help="Joueurs actifs dans les X derniers jours")
    
    st.subheader("🌍 Localisation")
    only_french = st.checkbox("🇫🇷 Francophones uniquement", value=False)
    
    st.subheader("🏁 Objectif")
    limit_recruits = st.number_input("Nombre de recrues", value=100, min_value=1, max_value=1000)
    
    st.subheader("🌱 Point de départ")
    seed_tag = st.text_input("Tag Joueur Initial", value="#989R2RPQ")
    
    st.subheader("⚡ Performance")
    max_workers = st.slider("Threads parallèles", 5, 20, 10)

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

# --- MAIN INTERFACE ---
col_btn1, col_btn2, col_spacer = st.columns([1, 1, 3])
with col_btn1:
    st.button("🚀 Lancer", use_container_width=True, disabled=st.session_state.scanning, on_click=start_scanning)
with col_btn2:
    st.button("🛑 Arrêter", use_container_width=True, disabled=not st.session_state.scanning, on_click=stop_scanning)

# Stats Dashboard
stats_cols = st.columns(5)
scanned_metric = stats_cols[0].empty()
found_metric = stats_cols[1].empty()
rate_metric = stats_cols[2].empty()
speed_metric = stats_cols[3].empty()
queue_metric = stats_cols[4].empty()

progress_bar = st.progress(0)
status_text = st.empty()
results_container = st.empty()
export_container = st.container()

# --- SCANNING LOGIC ---
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
        start_time = time.time()
        
        while queue and st.session_state.scanning and found_count < limit_recruits:
            # Get batch of tags to process
            batch_tags = []
            for _ in range(min(max_workers * 2, len(queue))):
                if queue:
                    batch_tags.append(queue.popleft())
            
            if not batch_tags:
                break
            
            # Parallel fetch player details
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(get_player_detail, session, t, headers): t for t in batch_tags}
                
                for future in as_completed(futures):
                    if not st.session_state.scanning or found_count >= limit_recruits:
                        break
                    
                    tag = futures[future]
                    p_data = future.result()
                    scanned_count += 1
                    
                    if p_data:
                        trophies = p_data.get('trophies', 0)
                        has_clan = 'clan' in p_data
                        
                        # Check basic filters
                        if not has_clan and min_trophies <= trophies <= max_trophies:
                            # Check French filter
                            is_fr = True
                            if only_french:
                                p_battles = get_battle_log(session, tag, headers)
                                is_fr = is_french_relevance(p_battles)
                            
                            if is_fr:
                                found_count += 1
                                st.session_state.players_found.append({
                                    "Tag": p_data['tag'],
                                    "Nom": p_data.get('name', 'Unknown'),
                                    "Trophées": trophies,
                                    "Niveau": p_data.get('expLevel', 1),
                                    "Lien": f"https://royaleapi.com/player/{p_data['tag'].replace('#', '')}"
                                })
                        
                        # Get battle log for new tags
                        battles = get_battle_log(session, tag, headers)
                        for b in battles:
                            for team in ['team', 'opponent']:
                                for p in b.get(team, []):
                                    new_tag = p.get('tag')
                                    if new_tag and new_tag not in visited:
                                        visited.add(new_tag)
                                        queue.append(new_tag)
                    
                    # Update stats
                    elapsed = max(0.1, (time.time() - start_time) / 60)
                    scanned_metric.metric("📊 Scannés", scanned_count)
                    found_metric.metric("✅ Trouvés", found_count)
                    rate_metric.metric("📈 Taux", f"{(found_count/max(1,scanned_count)*100):.1f}%")
                    speed_metric.metric("⚡ Vitesse", f"{scanned_count/elapsed:.0f}/min")
                    queue_metric.metric("📋 File", len(queue))
                    
                    progress_bar.progress(min(found_count / limit_recruits, 1.0))
                    status_text.text(f"🔍 Recherche... {found_count}/{limit_recruits} recrues")
            
            # Update display
            if st.session_state.players_found:
                df = pd.DataFrame(st.session_state.players_found)
                results_container.dataframe(df, use_container_width=True, hide_index=True)
        
        st.session_state.scanning = False
        st.success(f"✨ Terminé ! {found_count} recrues trouvées.")
        st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state.players_found and not st.session_state.scanning:
    df = pd.DataFrame(st.session_state.players_found)
    st.subheader(f"📋 Recrues trouvées ({len(st.session_state.players_found)})")
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    with export_container:
        st.subheader("💾 Exporter les résultats")
        col_csv, col_json, col_excel = st.columns(3)
        
        with col_csv:
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            st.download_button("📥 CSV", csv_buffer.getvalue(), file_name="recrues.csv", mime="text/csv", use_container_width=True)
        
        with col_json:
            json_str = json.dumps(st.session_state.players_found, ensure_ascii=False, indent=2)
            st.download_button("📥 JSON", json_str, file_name="recrues.json", mime="application/json", use_container_width=True)
        
        with col_excel:
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False, engine='openpyxl')
            st.download_button("📥 Excel", excel_buffer.getvalue(), file_name="recrues.xlsx", 
                             mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
