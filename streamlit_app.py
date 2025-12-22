import streamlit as st
import requests
import time
import pandas as pd
from collections import deque

st.set_page_config(page_title="Clash Royale Recruiter", page_icon="⚔️")
st.title("⚔️ Clash Royale Recruiter")

# Sidebar
with st.sidebar:
    api_key = st.text_input("Clé API", type="password")
    min_trophies = st.number_input("Trophées Min", value=80)
    max_trophies = st.number_input("Trophées Max", value=15000)
    limit = st.number_input("Nombre de recrues", value=50, min_value=1)
    seed_tag = st.text_input("Tag Initial", value="#989R2RPQ")

# State
if 'results' not in st.session_state:
    st.session_state.results = []
if 'running' not in st.session_state:
    st.session_state.running = False

# Buttons
if st.button("🚀 Lancer", disabled=st.session_state.running):
    st.session_state.running = True
    st.session_state.results = []

if st.button("🛑 Stop", disabled=not st.session_state.running):
    st.session_state.running = False

# Display
progress = st.progress(0)
status = st.empty()
table = st.empty()

# Main logic
if st.session_state.running and api_key:
    headers = {"Authorization": f"Bearer {api_key}"}
    
    queue = deque([seed_tag])
    visited = {seed_tag}
    found = 0
    scanned = 0
    
    while queue and st.session_state.running and found < limit:
        tag = queue.popleft()
        clean_tag = tag.replace("#", "%23")
        
        # Get player
        try:
            resp = requests.get(f"https://api.clashroyale.com/v1/players/{clean_tag}", headers=headers, timeout=10)
            if resp.status_code == 200:
                player = resp.json()
                scanned += 1
                
                trophies = player.get('trophies', 0)
                if 'clan' not in player and min_trophies <= trophies <= max_trophies:
                    found += 1
                    st.session_state.results.append({
                        "Tag": player['tag'],
                        "Nom": player.get('name', '?'),
                        "Trophées": trophies,
                        "Lien": f"https://royaleapi.com/player/{player['tag'].replace('#', '')}"
                    })
            elif resp.status_code == 429:
                time.sleep(2)
                queue.appendleft(tag)
                continue
        except:
            pass
        
        # Get battles for more tags
        try:
            resp = requests.get(f"https://api.clashroyale.com/v1/players/{clean_tag}/battlelog", headers=headers, timeout=10)
            if resp.status_code == 200:
                for b in resp.json():
                    for team in ['team', 'opponent']:
                        for p in b.get(team, []):
                            t = p.get('tag')
                            if t and t not in visited:
                                visited.add(t)
                                queue.append(t)
        except:
            pass
        
        # Update UI
        status.text(f"Scannés: {scanned} | Trouvés: {found}/{limit}")
        progress.progress(min(found / limit, 1.0))
        if st.session_state.results:
            table.dataframe(pd.DataFrame(st.session_state.results), hide_index=True)
        
        time.sleep(0.1)
    
    st.session_state.running = False
    st.success(f"Terminé ! {found} recrues trouvées.")
    st.rerun()

# Show results
if st.session_state.results and not st.session_state.running:
    st.dataframe(pd.DataFrame(st.session_state.results), hide_index=True)
    
    import io
    csv = io.StringIO()
    pd.DataFrame(st.session_state.results).to_csv(csv, index=False)
    st.download_button("📥 Télécharger CSV", csv.getvalue(), "recrues.csv")
