import streamlit as st
import requests
import time
import pandas as pd
import os
import json
import plotly.express as px
from datetime import datetime
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- HISTORY MANAGEMENT ---
HISTORY_FILE = "recruiter_history.json"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_history(tags):
    with open(HISTORY_FILE, 'w') as f:
        json.dump(list(tags), f)

def clear_history():
    if os.path.exists(HISTORY_FILE):
        os.remove(HISTORY_FILE)
    return set()

# --- PAGE CONFIG ---
st.set_page_config(page_title="CR Recruiter", page_icon="👑", layout="wide")
st.title("👑 Clash Royale Recruiter")

# --- SESSION STATE ---
if 'scanning' not in st.session_state:
    st.session_state.scanning = False
if 'found' not in st.session_state:
    st.session_state.found = []
if 'last_notified' not in st.session_state:
    st.session_state.last_notified = 0

def start_scan():
    st.session_state.scanning = True
    st.session_state.found = []
    st.session_state.last_notified = 0

def stop_scan():
    st.session_state.scanning = False

# --- TELEGRAM ---
def send_telegram(bot_token, chat_id, players):
    """Envoie une liste de joueurs via Telegram avec liens CR"""
    if not bot_token or not chat_id:
        return False
    
    def escape_md(text):
        for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
            text = text.replace(char, '\\' + char)
        return text
    
    message = "🎯 Nouvelles Recrues CR !\n"
    message += "━━━━━━━━━━━━━━━━━━\n\n"
    
    for i, p in enumerate(players, 1):
        clean_tag = p['Tag'].replace('#', '')
        name = escape_md(str(p.get('Nom', 'Unknown')))
        message += f"{i}. {name}\n"
        message += f"   🏆 {p.get('Trophées', 0)} (Best: {p.get('Best', 'N/A')})\n"
        message += f"   🃏 {p.get('Carte Fav', 'N/A')}\n"
        message += f"   📅 {p.get('Dernière Partie', 'N/A')}\n"
        message += f"   👤 https://royaleapi.com/player/{clean_tag}\n"
        message += "──────────────────\n"
    
    if len(message) > 4000:
        message = message[:4000] + "\n... (tronqué)"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True
    }
    
    try:
        r = requests.post(url, data=data, timeout=10)
        return r.status_code == 200
    except:
        return False

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

def get_clan(tag):
    url = f"https://api.clashroyale.com/v1/clans/{tag.replace('#', '%23')}"
    try:
        r = requests.get(url, headers=get_headers(), timeout=10)
        return r.json() if r.status_code == 200 else None
    except:
        return None

# --- SIDEBAR CONFIG ---
with st.sidebar:
    st.header("⚙️ Configuration")
    api_token = st.text_input("Clé API CR", type="password")
    seed_tag = st.text_input("Tag Graine", value="#989R2RPQ")
    
    st.subheader("🎯 Filtres")
    min_trophies = st.number_input("Trophées Min", value=7500, step=100)
    max_trophies = st.number_input("Trophées Max", value=11000, step=100)
    min_scan = st.number_input("Qualité Scan", value=7000, step=100)
    objectif = st.number_input("Objectif Recrues", value=50, step=10)
    
    st.subheader("⚡ Performance")
    workers = st.slider("Workers parallèles", 1, 10, 5)
    
    st.divider()
    
    # --- TELEGRAM CONFIG ---
    st.subheader("📱 Telegram")
    telegram_token = st.text_input("Bot Token", value="8532137772:AAGcnzo6D5rDleWEc0hPb-BdlS4lg1hrBF8", type="password")
    telegram_chat_id = st.text_input("Chat ID", value="-1003643661262")
    telegram_batch = st.number_input("Notifier tous les X joueurs", value=20, min_value=5, step=5)
    
    st.divider()
    
    # --- HISTORIQUE ---
    st.subheader("📜 Historique")
    use_history = st.checkbox("Ignorer joueurs déjà trouvés", value=True)
    history = load_history()
    st.caption(f"{len(history)} joueurs en historique")
    if st.button("🗑️ Vider l'historique"):
        clear_history()
        st.success("Historique vidé !")
        st.rerun()
    
    st.divider()
    
    # Boutons Start/Stop
    col_start, col_stop = st.columns(2)
    with col_start:
        st.button("🚀 Lancer", on_click=start_scan, type="primary", use_container_width=True, disabled=st.session_state.scanning)
    with col_stop:
        st.button("🛑 Stop", on_click=stop_scan, type="secondary", use_container_width=True, disabled=not st.session_state.scanning)

# --- TABS ---
tab_scan, tab_stats, tab_clan, tab_analysis = st.tabs(["🔍 Recherche", "📊 Statistiques", "🏰 Mon Clan", "🕹️ Analyse Joueur"])

with tab_scan:
    # Métriques
    col1, col2, col3, col4 = st.columns(4)
    metric_scanned = col1.empty()
    metric_found = col2.empty()
    metric_queue = col3.empty()
    metric_telegram = col4.empty()
    
    log_area = st.empty()
    results_area = st.empty()

    if st.session_state.scanning:
        if not api_token:
            st.error("⚠️ Entrez votre clé API")
            st.session_state.scanning = False
        else:
            queue = deque([seed_tag])
            visited = {seed_tag}
            found = []
            scanned = 0
            metric_scanned.metric("🔍 Scannés", 0)
            metric_found.metric("✅ Trouvés", 0)
            metric_queue.metric("📋 File", 1)
            metric_telegram.metric("📱 Notifs", 0)
            log_area.info(f"Démarrage avec {workers} workers...")
            notif_count = 0

            while queue and len(found) < objectif and st.session_state.scanning:
                current = queue.popleft()
                battles = get_battle_log(current)
                tags_to_check = []
                for battle in battles:
                    for opp in battle.get('opponent', []):
                        tag = opp['tag']
                        if tag not in visited:
                            visited.add(tag)
                            tags_to_check.append(tag)
                
                if tags_to_check and st.session_state.scanning:
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        futures = {executor.submit(get_player, t): t for t in tags_to_check}
                        for future in as_completed(futures):
                            if len(found) >= objectif or not st.session_state.scanning:
                                break
                            tag = futures[future]
                            scanned += 1
                            try:
                                player = future.result()
                                if player:
                                    trophies = player.get("trophies", 0)
                                    has_clan = "clan" in player
                                    if not has_clan and min_trophies <= trophies <= max_trophies:
                                        if use_history and tag in history:
                                            continue
                                        clean_tag = tag.replace('#', '')
                                        best_trophies = player.get("bestTrophies", 0)
                                        fav_card = player.get("currentFavouriteCard", {}).get("name", "N/A")
                                        player_battles = get_battle_log(tag)
                                        last_battle = "N/A"
                                        if player_battles:
                                            lb_time = player_battles[0].get("battleTime", "N/A")
                                            if lb_time != "N/A":
                                                last_battle = f"{lb_time[0:4]}-{lb_time[4:6]}-{lb_time[6:8]}"
                                        
                                        found.append({
                                            "Nom": player["name"], "Trophées": trophies, "Best": best_trophies,
                                            "Carte Fav": fav_card, "Dernière Partie": last_battle, "Tag": tag,
                                            "Lien CR": f"clashroyale://playerInfo%3Fid={clean_tag}",
                                            "RoyaleAPI": f"https://royaleapi.com/player/{clean_tag}"
                                        })
                                        
                                        if telegram_chat_id and len(found) >= st.session_state.last_notified + telegram_batch:
                                            batch_start = st.session_state.last_notified
                                            batch_end = len(found)
                                            players_to_send = found[batch_start:batch_end]
                                            if send_telegram(telegram_token, telegram_chat_id, players_to_send):
                                                notif_count += 1
                                                st.session_state.last_notified = batch_end
                                                metric_telegram.metric("📱 Notifs", notif_count)
                                    
                                    if trophies >= min_scan:
                                        queue.append(tag)
                            except:
                                pass
                    metric_scanned.metric("🔍 Scannés", scanned)
                    metric_found.metric("✅ Trouvés", len(found))
                    metric_queue.metric("📋 File", len(queue))
                    if found:
                        results_area.dataframe(found, use_container_width=True)
                        st.session_state.found = found
                log_area.info(f"⏳ {scanned} profils analysés... (file: {len(queue)})")
                time.sleep(0.05)
            
            st.session_state.scanning = False
            st.session_state.found = found
            if found:
                new_tags = {p['Tag'] for p in found}
                updated_history = history.union(new_tags)
                save_history(updated_history)
            if telegram_chat_id and len(found) > st.session_state.last_notified:
                remaining = found[st.session_state.last_notified:]
                send_telegram(telegram_token, telegram_chat_id, remaining)
            if found:
                st.success(f"🎉 Terminé ! {len(found)} recrues trouvées.")
                df = pd.DataFrame(found)
                st.download_button("📥 Télécharger CSV", df.to_csv(index=False), "recrues.csv", "text/csv")
    elif st.session_state.found:
        results_area.dataframe(st.session_state.found, use_container_width=True)

with tab_stats:
    st.subheader("📊 Statistiques des Recrues")
    if st.session_state.found:
        df = pd.DataFrame(st.session_state.found)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📊 Total", len(df))
        col2.metric("🏆 Moyenne", f"{df['Trophées'].mean():.0f}")
        col3.metric("📈 Médiane", f"{df['Trophées'].median():.0f}")
        col4.metric("⭐ Max", df['Trophées'].max())
        st.divider()
        st.subheader("Distribution des Trophées")
        bins = list(range(9000, 15750, 250))
        labels = [f"{b}-{b+249}" for b in bins[:-1]]
        df['Tranche'] = pd.cut(df['Trophées'], bins=bins, labels=labels, include_lowest=True)
        st.bar_chart(df['Tranche'].value_counts().sort_index())
    else:
        st.info("Lancez une recherche pour voir les statistiques.")

with tab_clan:
    st.subheader("🏰 Dashboard du Clan")
    clan_tag = st.text_input("Tag du Clan", value="#GPYQUC8U")
    if st.button("📊 Charger les données"):
        clan_data = get_clan(clan_tag)
        if clan_data:
            st.markdown(f"### {clan_data.get('name', 'N/A')} `{clan_data.get('tag', '')}`")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("👥 Membres", f"{len(clan_data.get('memberList', []))}/50")
            col2.metric("🏆 Trophées Requis", clan_data.get('requiredTrophies', 0))
            col3.metric("🎖️ Score Guerre", clan_data.get('clanWarTrophies', 0))
            col4.metric("💰 Dons/semaine", clan_data.get('donationsPerWeek', 0))
            st.divider()
            members = clan_data.get('memberList', [])
            if members:
                member_data = []
                progress_bar = st.progress(0, text="Chargement des activités...")
                for idx, m in enumerate(members):
                    battles = get_battle_log(m.get('tag', ''))
                    status, last_battle, days_ago = "🔒", "Privé", 999
                    if battles:
                        lb_time = battles[0].get('battleTime', '')
                        if lb_time:
                            try:
                                b_date = datetime.strptime(lb_time[:15], '%Y%m%dT%H%M%S')
                                days_ago = (datetime.now() - b_date).days
                                last_battle = b_date.strftime('%Y-%m-%d %H:%M')
                                if days_ago == 0: status = "🟢 Actif"
                                elif days_ago <= 1: status = "🟡 Hier"
                                elif days_ago <= 3: status = "🟠 3 jours"
                                elif days_ago <= 7: status = "🔴 7 jours"
                                else: status = f"⚫ {days_ago}j"
                            except: pass
                    member_data.append({
                        "Nom": m.get('name', ''), "Rôle": m.get('role', '').replace('coLeader', 'Co-Leader').replace('elder', 'Aîné').replace('member', 'Membre').replace('leader', 'Chef'),
                        "Trophées": m.get('trophies', 0), "Dons": m.get('donations', 0), "Dernière Partie": last_battle, "Statut": status, "Inactif (j)": days_ago if days_ago < 999 else "N/A"
                    })
                    progress_bar.progress((idx + 1) / len(members))
                progress_bar.empty()
                df_m = pd.DataFrame(member_data)
                st.dataframe(df_m, use_container_width=True, hide_index=True)
                inactive = df_m[df_m['Inactif (j)'].apply(lambda x: isinstance(x, int) and x >= 7)]
                if len(inactive) > 0:
                    st.subheader(f"🔴 Membres inactifs 7+ jours ({len(inactive)})")
                    st.dataframe(inactive, use_container_width=True, hide_index=True)

with tab_analysis:
    st.subheader("🕹️ Analyse détaillée du joueur")
    analysis_tag = st.text_input("Tag du joueur à analyser", value="#PL0Q8UGR")
    if st.button("📈 Lancer l'analyse"):
        with st.spinner("Analyse en cours..."):
            battles = get_battle_log(analysis_tag)
            if battles:
                wins, losses, draws, card_stats = 0, 0, 0, {}
                for b in battles:
                    t_c = sum([p.get('crowns', 0) for p in b.get('team', [])])
                    o_c = sum([p.get('crowns', 0) for p in b.get('opponent', [])])
                    outcome = "win" if t_c > o_c else ("loss" if t_c < o_c else "draw")
                    if outcome == "win": wins += 1
                    elif outcome == "loss": losses += 1
                    else: draws += 1
                    for opp in b.get('opponent', []):
                        for card in opp.get('cards', []):
                            name = card.get('name')
                            if name not in card_stats: card_stats[name] = {'wins': 0, 'losses': 0, 'draws': 0, 'total': 0}
                            card_stats[name]['total'] += 1
                            card_stats[name][outcome + 's'] += 1
                
                total = wins + losses + draws
                wr = (wins / total) * 100 if total > 0 else 0
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("🏁 Matchs", total); col2.metric("✅ Victoires", wins); col3.metric("❌ Défaites", losses); col4.metric("📈 Win Rate", f"{wr:.1f}%")
                st.plotly_chart(px.pie(values=[wins, losses, draws], names=["Victoires", "Défaites", "Égalités"], color_discrete_sequence=["green", "red", "gray"]), use_container_width=True)
                
                rows = []
                for name, s in card_stats.items():
                    rows.append({"Carte": name, "Rencontres": s['total'], "Victoires": s['wins'], "Défaites": s['losses'], "Win Rate %": round((s['wins']/s['total'])*100, 1)})
                df_c = pd.DataFrame(rows)
                col_l, col_r = st.columns(2)
                with col_l:
                    st.write("#### 💪 Tes victimes")
                    st.dataframe(df_c[df_c['Rencontres'] >= 2].nlargest(10, 'Win Rate %'), use_container_width=True, hide_index=True)
                with col_r:
                    st.write("#### ⚠️ Tes bourreaux")
                    st.dataframe(df_c[df_c['Rencontres'] >= 2].nsmallest(10, 'Win Rate %'), use_container_width=True, hide_index=True)
            else:
                st.warning("Aucun combat trouvé.")