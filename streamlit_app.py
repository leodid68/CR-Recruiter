import streamlit as st
import requests
import time
import csv
import os
from collections import deque

# --- PAGE CONFIG ---
st.set_page_config(page_title="CR Recruiter", page_icon="👑", layout="wide")
st.title("👑 Clash Royale Recruiter")

# --- SIDEBAR CONFIG ---
with st.sidebar:
    st.header("⚙️ Configuration")
    api_token = st.text_input("Clé API", type="password")
    seed_tag = st.text_input("Tag Graine", value="#989R2RPQ")
    
    st.subheader("🎯 Filtres")
    min_trophies = st.number_input("Trophées Min", value=7500, step=100)
    max_trophies = st.number_input("Trophées Max", value=11000, step=100)
    min_scan = st.number_input("Qualité Scan", value=7000, step=100)
    objectif = st.number_input("Objectif Recrues", value=50, step=10)
    
    start = st.button("🚀 Lancer", type="primary", use_container_width=True)

# --- API FUNCTIONS ---
def get_headers():
    return {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}

def get_battle_log(tag):
    url = f"https://api.clashroyale.com/v1/players/{tag.replace('#', '%23')}/battlelog"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        return r.json() if r.status_code == 200 else []
    except:
        return []

def get_player(tag):
    url = f"https://api.clashroyale.com/v1/players/{tag.replace('#', '%23')}"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        return r.json() if r.status_code == 200 else None
    except:
        return None

# --- MAIN UI ---
col1, col2 = st.columns(2)
metric_scanned = col1.empty()
metric_found = col2.empty()

log_area = st.empty()
results_area = st.empty()

# --- SNOWBALL LOGIC ---
if start:
    if not api_token:
        st.error("⚠️ Entrez votre clé API")
    else:
        queue = deque([seed_tag])
        visited = {seed_tag}
        found = []
        scanned = 0
        
        metric_scanned.metric("🔍 Scannés", 0)
        metric_found.metric("✅ Trouvés", 0)
        log_area.info("Démarrage...")

        while queue and len(found) < objectif:
            current = queue.popleft()
            battles = get_battle_log(current)
            
            for battle in battles:
                for opp in battle.get('opponent', []):
                    tag = opp['tag']
                    if tag not in visited:
                        visited.add(tag)
                        scanned += 1
                        metric_scanned.metric("🔍 Scannés", scanned)
                        
                        player = get_player(tag)
                        if player:
                            trophies = player.get("trophies", 0)
                            has_clan = "clan" in player
                            
                            # Recrue ?
                            if not has_clan and min_trophies <= trophies <= max_trophies:
                                found.append({
                                    "Nom": player["name"],
                                    "Trophées": trophies,
                                    "Tag": tag,
                                    "Lien": f"https://royaleapi.com/player/{tag.replace('#','')}"
                                })
                                metric_found.metric("✅ Trouvés", len(found))
                                results_area.dataframe(found, use_container_width=True)
                                
                                if len(found) >= objectif:
                                    break
                            
                            # Snowball
                            if trophies >= min_scan:
                                queue.append(tag)
                        
                        time.sleep(0.05)
                
                if len(found) >= objectif:
                    break
            
            if scanned % 20 == 0:
                log_area.info(f"⏳ {scanned} profils analysés... (file: {len(queue)})")
            
            time.sleep(0.1)
        
        st.success(f"🎉 Terminé ! {len(found)} recrues trouvées.")
        
        # Export CSV
        if found:
            import pandas as pd
            df = pd.DataFrame(found)
            st.download_button("� Télécharger CSV", df.to_csv(index=False), "recrues.csv", "text/csv")