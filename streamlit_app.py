import streamlit as st
import requests
import time
import pandas as pd
from collections import deque

# Configuration de la page
st.set_page_config(page_title="Clash Royale Recruiter", page_icon="⚔️", layout="wide")

st.title("⚔️ Recruteur Clash Royale")
st.markdown("Trouvez des joueurs **sans clan** en explorant l'historique des combats.")

# --- Sidebar : Configuration ---
with st.sidebar:
    st.header("⚙️ Paramètres")
    api_key = st.text_input("Clé API Clash Royale", type="password", help="Créez une clé sur https://developer.clashroyale.com")
    
    st.subheader("🎯 Cible")
    min_trophies = st.number_input("Trophées minimum", value=5000, step=100)
    limit = st.number_input("Nombre de joueurs à trouver", value=50, min_value=1, max_value=200)
    
    st.subheader("🌱 Point de départ")
    seed_tag = st.text_input("Tag du joueur initial", value="#989R2RPQ", help="Le script commencera à fouiller à partir de ce joueur.")

# --- Gestion des Stats API ---
if 'api_stats' not in st.session_state:
    st.session_state.api_stats = {
        'requests': 0,
        'success': 0,
        'rate_limits': 0,
        'errors': 0
    }

def update_stats(status_code):
    st.session_state.api_stats['requests'] += 1
    if status_code == 200:
        st.session_state.api_stats['success'] += 1
    elif status_code == 429:
        st.session_state.api_stats['rate_limits'] += 1
    else:
        st.session_state.api_stats['errors'] += 1

def reset_stats():
    st.session_state.api_stats = {
        'requests': 0,
        'success': 0,
        'rate_limits': 0,
        'errors': 0
    }

# --- Fonctions API ---
def get_headers(api_key):
    return {"Authorization": f"Bearer {api_key}"}

def clean_tag(tag):
    return tag.replace("#", "").upper()

def get_player(tag, api_key):
    url = f"https://api.clashroyale.com/v1/players/%23{clean_tag(tag)}"
    try:
        response = requests.get(url, headers=get_headers(api_key), timeout=5)
        update_stats(response.status_code)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            time.sleep(1) # Petit temps d'attente si rate limit
            return None
        return None
    except:
        st.session_state.api_stats['errors'] += 1
        return None

def get_battle_log(tag, api_key):
    url = f"https://api.clashroyale.com/v1/players/%23{clean_tag(tag)}/battlelog"
    try:
        response = requests.get(url, headers=get_headers(api_key), timeout=5)
        update_stats(response.status_code)
        
        if response.status_code == 200:
            return response.json()
        
        # Si rate limit sur battlelog, on attend aussi
        if response.status_code == 429:
             time.sleep(1)
             
        return []
    except:
        st.session_state.api_stats['errors'] += 1
        return []

# --- État de l'application ---
if 'found_players' not in st.session_state:
    st.session_state.found_players = []
if 'scanning' not in st.session_state:
    st.session_state.scanning = False

def toggle_scan():
    st.session_state.scanning = not st.session_state.scanning
    if st.session_state.scanning:
        # Reset si on relance une recherche propre
        if len(st.session_state.found_players) >= limit:
             st.session_state.found_players = []
             reset_stats()

# --- Interface Principale ---
col1, col2 = st.columns([1, 4])
with col1:
    btn_label = "🛑 Arrêter" if st.session_state.scanning else "🚀 Lancer la recherche"
    st.button(btn_label, on_click=toggle_scan, use_container_width=True)

# Affichage des Stats API
stats_container = st.container()
with stats_container:
    cols = st.columns(4)
    cols[0].metric("🌐 Requêtes Total", st.session_state.api_stats['requests'])
    cols[1].metric("✅ Succès", st.session_state.api_stats['success'])
    cols[2].metric("⚠️ Rate Limits (429)", st.session_state.api_stats['rate_limits'], 
                   delta_color="inverse" if st.session_state.api_stats['rate_limits'] > 0 else "normal")
    cols[3].metric("❌ Erreurs", st.session_state.api_stats['errors'],
                   delta_color="inverse" if st.session_state.api_stats['errors'] > 0 else "normal")

status_container = st.empty()
results_container = st.empty()
progress_bar = st.empty()

# --- Logique de Scan ---
if st.session_state.scanning:
    if not api_key:
        st.error("⚠️ Veuillez entrer une clé API valide dans la barre latérale.")
        st.session_state.scanning = False
    else:
        # Initialisation
        queue = deque([seed_tag])
        visited = {seed_tag}
        scanned_count = 0
        
        status_container.info(f"🔍 Démarrage de l'analyse via {seed_tag}...")
        
        while queue and st.session_state.scanning and len(st.session_state.found_players) < limit:
            current_tag = queue.popleft()
            
            # --- 1. ANALYSE DU JOUEUR (Est-ce une recrue ?) ---
            player_data = get_player(current_tag, api_key)
            scanned_count += 1
            
            if player_data:
                # Critères : Pas de clan ET Trophées suffisants
                has_clan = 'clan' in player_data
                trophies = player_data.get('trophies', 0)
                
                if not has_clan and trophies >= min_trophies:
                    st.session_state.found_players.append({
                        "Tag": player_data['tag'],
                        "Nom": player_data['name'],
                        "Trophées": trophies,
                        "Niveau": player_data.get('expLevel', '?'),
                        "Lien": f"https://royaleapi.com/player/{clean_tag(player_data['tag'])}"
                    })
            
            # --- 2. EFFET BOULE DE NEIGE (On cherche de nouveaux joueurs via son historique) ---
            battles = get_battle_log(current_tag, api_key)
            
            # DEBUG
            if not battles and st.session_state.api_stats['rate_limits'] > 5:
                 status_container.warning(f"⚠️ Trop de Rate Limits ! L'API bloque les requêtes. Pause nécessaire.")

            for battle in battles:
                # Récupérer tous les participants (équipe et adversaires)
                participants = battle.get('team', []) + battle.get('opponent', [])
                for p in participants:
                    p_tag = p.get('tag')
                    if p_tag and p_tag not in visited:
                        visited.add(p_tag)
                        queue.append(p_tag)
            
            # Mise à jour de l'affichage
            found_count = len(st.session_state.found_players)
            
            # Update metrics directly in the loop to allow live view
            with stats_container:
                 # Hack to force refresh of metrics without full rerun (Streamlit quirks)
                 # But standard rerun loop handles this usually. 
                 # We rely on the implicit cycle.
                 pass

            status_container.markdown(f"""
                **État de la recherche :**
                - 🕵️ Joueurs scannés : `{scanned_count}`
                - 📥 File d'attente : `{len(queue)}`
                - ✅ **Trouvés : {found_count} / {limit}**
            """)
            
            if found_count > 0:
                progress_bar.progress(min(found_count / limit, 1.0))
                df = pd.DataFrame(st.session_state.found_players)
                results_container.dataframe(
                    df, 
                    column_config={"Lien": st.column_config.LinkColumn("Profil RoyaleAPI")},
                    use_container_width=True
                )

            # Petit délai pour éviter de spammer l'API
            time.sleep(0.1)
        
        if len(st.session_state.found_players) >= limit:
            st.success("🎉 Recherche terminée ! Objectif atteint.")
            st.session_state.scanning = False
        elif not queue:
            st.warning("Plus de joueurs trouvés dans le réseau exploré.")
            st.session_state.scanning = False

# --- Affichage Final & Export ---
if not st.session_state.scanning and st.session_state.found_players:
    st.divider()
    st.subheader("📋 Résultats Finaux")
    df = pd.DataFrame(st.session_state.found_players)
    st.dataframe(
        df, 
        column_config={"Lien": st.column_config.LinkColumn("Profil RoyaleAPI")},
        use_container_width=True
    )
    
    # Export CSV
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Télécharger la liste (CSV)",
        data=csv,
        file_name="recrues_sans_clan.csv",
        mime="text/csv",
    )
