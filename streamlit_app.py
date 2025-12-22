import streamlit as st
import pandas as pd
import asyncio
import csv
import json
import io
import time
from datetime import datetime

from api import ClashRoyaleAPI
from scanner import PlayerScanner, ScanFilters, FoundPlayer, ScanStats

# --- PAGE CONFIG ---
st.set_page_config(page_title="Clash Royale Recruiter", page_icon="⚔️", layout="wide")

st.title("⚔️ Clash Royale - Recruteur de Talents")
st.markdown("Trouvez des joueurs **sans clan** avec notre algorithme de recherche avancé.")

# --- SIDEBAR : CONFIGURATION ---
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("Clé API", type="password", help="Obtenez votre clé sur developer.clashroyale.com")
    
    st.subheader("🎯 Filtres de Base")
    min_trophies = st.number_input("Trophées Min", value=80, step=100)
    max_trophies = st.number_input("Trophées Max", value=15000, step=100)
    
    st.subheader("🔬 Filtres Avancés")
    col1, col2 = st.columns(2)
    with col1:
        min_level = st.number_input("Niveau Min", value=1, min_value=1, max_value=50)
    with col2:
        max_level = st.number_input("Niveau Max", value=50, min_value=1, max_value=50)
    
    max_inactive = st.number_input("Inactif max (jours)", value=30, min_value=1, max_value=365, 
                                   help="Joueurs actifs dans les X derniers jours")
    
    st.subheader("🌍 Localisation")
    only_french = st.checkbox("🇫🇷 Francophones uniquement", value=False)
    
    st.subheader("🏁 Objectif")
    limit_recruits = st.number_input("Nombre de recrues", value=100, min_value=1, max_value=1000)
    
    st.subheader("🌱 Point de départ")
    seed_tag = st.text_input("Tag Joueur Initial", value="#989R2RPQ")
    
    st.subheader("⚡ Performance")
    concurrency = st.slider("Requêtes parallèles", 5, 50, 20)

# --- SESSION STATE ---
if 'players_found' not in st.session_state:
    st.session_state.players_found = []
if 'scanning' not in st.session_state:
    st.session_state.scanning = False
if 'stats' not in st.session_state:
    st.session_state.stats = None

def start_scanning():
    st.session_state.scanning = True
    st.session_state.players_found = []
    st.session_state.stats = None

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
stats_placeholders = {
    "scanned": stats_cols[0].empty(),
    "found": stats_cols[1].empty(),
    "rate": stats_cols[2].empty(),
    "speed": stats_cols[3].empty(),
    "queue": stats_cols[4].empty()
}

# Progress
progress_bar = st.progress(0)
status_text = st.empty()

# Results
results_container = st.container()

# Export section
export_container = st.container()


async def run_scan():
    """Run the async scanner."""
    filters = ScanFilters(
        min_trophies=min_trophies,
        max_trophies=max_trophies,
        require_no_clan=True,
        min_level=min_level if min_level > 1 else None,
        max_level=max_level if max_level < 50 else None,
        max_inactive_days=max_inactive,
        only_french=only_french
    )
    
    found_list = []
    
    def on_found(player: FoundPlayer):
        found_list.append(player.to_dict())
        st.session_state.players_found = found_list.copy()
    
    def on_stats(stats: ScanStats):
        st.session_state.stats = stats
        # Update UI
        stats_placeholders["scanned"].metric("📊 Scannés", stats.scanned)
        stats_placeholders["found"].metric("✅ Trouvés", stats.found)
        stats_placeholders["rate"].metric("📈 Taux", f"{stats.success_rate:.1f}%")
        stats_placeholders["speed"].metric("⚡ Vitesse", f"{stats.scans_per_minute:.0f}/min")
        stats_placeholders["queue"].metric("📋 File", stats.queue_size)
        
        progress_bar.progress(min(stats.found / limit_recruits, 1.0))
        status_text.text(f"Recherche en cours... {stats.found}/{limit_recruits} recrues trouvées")
    
    async with ClashRoyaleAPI(api_key, max_concurrent=concurrency) as api:
        scanner = PlayerScanner(
            api=api,
            filters=filters,
            on_player_found=on_found,
            on_stats_update=on_stats,
            batch_size=concurrency
        )
        
        # Check periodically if we should stop
        scan_task = asyncio.create_task(scanner.scan(seed_tag, limit_recruits))
        
        while not scan_task.done():
            if not st.session_state.scanning:
                scanner.stop()
                break
            await asyncio.sleep(0.1)
        
        try:
            await scan_task
        except:
            pass
    
    st.session_state.scanning = False
    return found_list


# --- SCANNING LOGIC ---
if st.session_state.scanning:
    if not api_key:
        st.error("Veuillez saisir votre clé API dans la barre latérale.")
        st.session_state.scanning = False
    else:
        # Run async scan
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(run_scan())
            st.session_state.players_found = [p.to_dict() if hasattr(p, 'to_dict') else p for p in results]
        finally:
            loop.close()
        
        st.success(f"✨ Terminé ! {len(st.session_state.players_found)} recrues trouvées.")
        st.rerun()

# --- DISPLAY RESULTS ---
if st.session_state.players_found:
    with results_container:
        st.subheader(f"📋 Recrues trouvées ({len(st.session_state.players_found)})")
        df = pd.DataFrame(st.session_state.players_found)
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    with export_container:
        st.subheader("💾 Exporter les résultats")
        col_csv, col_json, col_excel = st.columns(3)
        
        # CSV Export
        with col_csv:
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            st.download_button(
                "📥 Télécharger CSV",
                csv_buffer.getvalue(),
                file_name="recrues_clash.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        # JSON Export
        with col_json:
            json_str = json.dumps(st.session_state.players_found, ensure_ascii=False, indent=2)
            st.download_button(
                "📥 Télécharger JSON",
                json_str,
                file_name="recrues_clash.json",
                mime="application/json",
                use_container_width=True
            )
        
        # Excel Export
        with col_excel:
            excel_buffer = io.BytesIO()
            df.to_excel(excel_buffer, index=False, engine='openpyxl')
            st.download_button(
                "📥 Télécharger Excel",
                excel_buffer.getvalue(),
                file_name="recrues_clash.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
