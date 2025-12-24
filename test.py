import streamlit as st
import requests
import time
import pandas as pd
import os
import json
import plotly.express as px
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
if 'clan_members' not in st.session_state:
    st.session_state.clan_members = []

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
        print("DEBUG: Missing bot_token or chat_id")
        return False
    
    # Escape special Markdown characters in names
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
    
    # Limite Telegram: 4096 chars
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
        print(f"DEBUG Telegram: status={r.status_code}, response={r.text[:200]}")
        return r.status_code == 200
    except Exception as e:
        print(f"DEBUG Telegram error: {e}")
        return False

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
    use_history = st.checkbox("Ignorer joueurs déjà trouvés", value=True, help="Ne pas afficher les joueurs déjà trouvés lors de précédentes recherches")
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

    # --- SNOWBALL LOGIC ---
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
                
                # Collecter tous les tags
                tags_to_check = []
                for battle in battles:
                    for opp in battle.get('opponent', []):
                        tag = opp['tag']
                        if tag not in visited:
                            visited.add(tag)
                            tags_to_check.append(tag)
                
                # Traitement PARALLELE
                if tags_to_check and st.session_state.scanning:
                    with ThreadPoolExecutor(max_workers=workers) as executor:
                        futures = {executor.submit(get_player, tag): tag for tag in tags_to_check}
                        
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
                                        # Vérifier l'historique
                                        if use_history and tag in history:
                                            continue  # Déjà trouvé avant, on skip
                                        
                                        clean_tag = tag.replace('#', '')
                                        
                                        # Données supplémentaires
                                        best_trophies = player.get("bestTrophies", 0)
                                        fav_card = player.get("currentFavouriteCard", {}).get("name", "N/A")
                                        
                                        # Récupérer la date du dernier combat
                                        player_battles = get_battle_log(tag)
                                        if player_battles:
                                            last_battle = player_battles[0].get("battleTime", "N/A")
                                            # Format: 20231222T153500.000Z -> 2023-12-22
                                            if last_battle != "N/A":
                                                last_battle = f"{last_battle[0:4]}-{last_battle[4:6]}-{last_battle[6:8]}"
                                        else:
                                            last_battle = "N/A"
                                        
                                        found.append({
                                            "Nom": player["name"],
                                            "Trophées": trophies,
                                            "Best": best_trophies,
                                            "Carte Fav": fav_card,
                                            "Dernière Partie": last_battle,
                                            "Tag": tag,
                                            "Lien CR": f"clashroyale://playerInfo%3Fid={clean_tag}",
                                            "RoyaleAPI": f"https://royaleapi.com/player/{clean_tag}"
                                        })
                                        
                                        # Telegram notification tous les X joueurs
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
                    
                    # Update UI
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
            
            # Sauvegarder dans l'historique
            if found:
                new_tags = {p['Tag'] for p in found}
                updated_history = history.union(new_tags)
                save_history(updated_history)
            
            # Envoyer les derniers joueurs restants
            if telegram_chat_id and len(found) > st.session_state.last_notified:
                remaining = found[st.session_state.last_notified:]
                send_telegram(telegram_token, telegram_chat_id, remaining)
            
            if found:
                st.success(f"🎉 Terminé ! {len(found)} recrues trouvées. ({len(history) + len(found)} en historique)")
                df = pd.DataFrame(found)
                st.download_button("📥 Télécharger CSV", df.to_csv(index=False), "recrues.csv", "text/csv")
            else:
                st.warning("Aucune recrue trouvée.")

    # Afficher résultats existants si on ne scanne pas
    elif st.session_state.found:
        results_area.dataframe(st.session_state.found, use_container_width=True)
        df = pd.DataFrame(st.session_state.found)
        st.download_button("📥 Télécharger CSV", df.to_csv(index=False), "recrues.csv", "text/csv")

with tab_stats:
    st.subheader("📊 Statistiques des Recrues")
    
    if st.session_state.found:
        df = pd.DataFrame(st.session_state.found)
        
        # Métriques principales
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("📊 Total", len(df))
        col2.metric("🏆 Moyenne", f"{df['Trophées'].mean():.0f}")
        col3.metric("📈 Médiane", f"{df['Trophées'].median():.0f}")
        col4.metric("⭐ Max", df['Trophées'].max())
        
        st.divider()
        
        # Histogramme par tranches de 250 trophées
        st.subheader("Distribution des Trophées (par tranche de 250)")
        
        # Créer les bins de 9000 à 15500 par pas de 250
        bins = list(range(9000, 15750, 250))
        labels = [f"{b}-{b+249}" for b in bins[:-1]]
        
        df['Tranche'] = pd.cut(df['Trophées'], bins=bins, labels=labels, include_lowest=True)
        distribution = df['Tranche'].value_counts().sort_index()
        
        st.bar_chart(distribution)
        
        # Stats détaillées
        st.subheader("Détails")
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("Min", df['Trophées'].min())
            st.metric("Écart-type", f"{df['Trophées'].std():.0f}")
        with col_b:
            st.metric("Q1 (25%)", f"{df['Trophées'].quantile(0.25):.0f}")
            st.metric("Q3 (75%)", f"{df['Trophées'].quantile(0.75):.0f}")
    else:
        st.info("Lancez une recherche pour voir les statistiques.")

with tab_clan:
    st.subheader("🏰 Dashboard du Clan")
    
    clan_tag = st.text_input("Tag du Clan", value="#GPYQUC8U")
    
    if st.button("📊 Charger les données", type="primary"):
        clan_data = get_clan(clan_tag)
        
        if clan_data:
            # Infos générales
            st.markdown(f"### {clan_data.get('name', 'N/A')} `{clan_data.get('tag', '')}`")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("👥 Membres", f"{len(clan_data.get('memberList', []))}/50")
            col2.metric("🏆 Trophées Requis", clan_data.get('requiredTrophies', 0))
            col3.metric("🎖️ Score Guerre", clan_data.get('clanWarTrophies', 0))
            col4.metric("💰 Dons/semaine", clan_data.get('donationsPerWeek', 0))
            
            st.divider()
            
            # Liste des membres
            members = clan_data.get('memberList', [])
            if members:
                member_data = []
                progress_bar = st.progress(0, text="Chargement des activités...")
                
                for idx, m in enumerate(members):
                    # Récupérer l'activité via battlelog
                    battles = get_battle_log(m.get('tag', ''))
                    
                    if battles:
                        last_battle_time = battles[0].get('battleTime', '')
                        if last_battle_time:
                            # Format: 20231222T153500.000Z
                            from datetime import datetime
                            try:
                                battle_date = datetime.strptime(last_battle_time[:15], '%Y%m%dT%H%M%S')
                                days_ago = (datetime.now() - battle_date).days
                                last_battle = battle_date.strftime('%Y-%m-%d %H:%M')
                                
                                # Status d'activité
                                if days_ago == 0:
                                    status = "🟢 Actif"
                                elif days_ago <= 1:
                                    status = "🟡 Hier"
                                elif days_ago <= 3:
                                    status = "🟠 3 jours"
                                elif days_ago <= 7:
                                    status = "🔴 7 jours"
                                else:
                                    status = f"⚫ {days_ago}j"
                            except:
                                last_battle = "N/A"
                                days_ago = 999
                                status = "❓"
                        else:
                            last_battle = "N/A"
                            days_ago = 999
                            status = "❓"
                    else:
                        last_battle = "Privé"
                        days_ago = 999
                        status = "🔒"
                    
                    member_data.append({
                        "Nom": m.get('name', ''),
                        "Rôle": m.get('role', '').replace('coLeader', 'Co-Leader').replace('elder', 'Aîné').replace('member', 'Membre').replace('leader', 'Chef'),
                        "Trophées": m.get('trophies', 0),
                        "Dons": m.get('donations', 0),
                        "Reçus": m.get('donationsReceived', 0),
                        "Dernière Partie": last_battle,
                        "Inactif (j)": days_ago if days_ago < 999 else "N/A",
                        "Statut": status,
                        "Tag": m.get('tag', '')
                    })
                    
                    progress_bar.progress((idx + 1) / len(members), text=f"Analyse {idx+1}/{len(members)}...")
                    time.sleep(0.05)
                
                progress_bar.empty()
                
                # Sauvegarder les membres pour l'onglet Analyse
                st.session_state.clan_members = member_data
                
                df_members = pd.DataFrame(member_data)
                
                # Stats du clan
                st.subheader("📈 Statistiques")
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("🏆 Trophées Moyen", f"{df_members['Trophées'].mean():.0f}")
                col_b.metric("💝 Dons Moyen", f"{df_members['Dons'].mean():.1f}")
                col_c.metric("⭐ Meilleur", df_members['Trophées'].max())
                
                st.divider()
                
                # Top Donateurs
                st.subheader("🏅 Top 5 Donateurs")
                top_donors = df_members.nlargest(5, 'Dons')[['Nom', 'Dons', 'Rôle']]
                st.dataframe(top_donors, use_container_width=True, hide_index=True)
                
                # Membres avec 0 dons
                zero_dons = df_members[df_members['Dons'] == 0]
                if len(zero_dons) > 0:
                    st.subheader(f"⚠️ Membres sans dons ({len(zero_dons)})")
                    st.dataframe(zero_dons[['Nom', 'Trophées', 'Statut', 'Rôle']], use_container_width=True, hide_index=True)
                
                # Membres inactifs (7+ jours)
                inactive = df_members[df_members['Inactif (j)'].apply(lambda x: isinstance(x, int) and x >= 7)]
                if len(inactive) > 0:
                    st.subheader(f"🔴 Membres inactifs 7+ jours ({len(inactive)})")
                    st.dataframe(inactive[['Nom', 'Dernière Partie', 'Inactif (j)', 'Dons', 'Rôle']], use_container_width=True, hide_index=True)
                
                
                # Liste complète
                st.subheader("👥 Liste Complète")
                st.dataframe(df_members, use_container_width=True, hide_index=True)
                
                # Export
                csv = df_members.to_csv(index=False).encode('utf-8')
                st.download_button("📥 Exporter CSV", csv, "clan_members.csv", "text/csv")
        else:
            st.error("Impossible de charger les données du clan. Vérifiez le tag et votre clé API.")

with tab_analysis:
    st.subheader("🕹️ Analyse détaillée du joueur")
    
    # Dropdown pour les membres du clan s'ils sont chargés
    if st.session_state.clan_members:
        member_options = {f"{m['Nom']} ({m['Tag']})": m['Tag'] for m in st.session_state.clan_members}
        selected_member = st.selectbox("👥 Choisir un membre du clan", options=[""] + list(member_options.keys()))
        if selected_member:
            analysis_tag = member_options[selected_member]
        else:
            analysis_tag = st.text_input("Ou entrer un Tag manuellement", value="#PL0Q8UGR")
    else:
        analysis_tag = st.text_input("Tag du joueur à analyser", value="#PL0Q8UGR")
        st.caption("💡 Chargez un clan dans l'onglet 'Mon Clan' pour avoir une liste déroulante des membres.")
    
    if st.button("📈 Lancer l'analyse", key="btn_analysis"):
        with st.spinner("Analyse en cours..."):
            player = get_player(analysis_tag)
            battles = get_battle_log(analysis_tag)
            
            if player:
                # --- PROFIL DU JOUEUR ---
                st.markdown(f"## 👤 {player.get('name', 'N/A')} `{player.get('tag', '')}`")
                
                # Métriques principales
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("🏆 Trophées", player.get('trophies', 0))
                col2.metric("⭐ Best", player.get('bestTrophies', 0))
                col3.metric("👑 Niveau", player.get('expLevel', 0))
                col4.metric("🎯 Victoires", player.get('wins', 0))
                col5.metric("❌ Défaites", player.get('losses', 0))
                
                col6, col7, col8, col9, col10 = st.columns(5)
                col6.metric("👑 3 Couronnes", player.get('threeCrownWins', 0))
                col7.metric("🏅 Max Défi", player.get('challengeMaxWins', 0))
                col8.metric("🎴 Cartes Défi", player.get('challengeCardsWon', 0))
                col9.metric("⚔️ Guerres", player.get('warDayWins', 0))
                col10.metric("💰 Dons Totaux", player.get('totalDonations', 0))
                
                fav_card = player.get('currentFavouriteCard', {}).get('name', 'N/A')
                st.info(f"🃏 **Carte Favorite:** {fav_card}")
                
                st.divider()
                
                # --- GRAPHIQUES JOUEUR ---
                st.subheader("📊 Statistiques Globales")
                
                total_battles = player.get('battleCount', 0)
                total_wins = player.get('wins', 0)
                total_losses = player.get('losses', 0)
                win_rate_global = (total_wins / total_battles * 100) if total_battles > 0 else 0
                
                col_chart1, col_chart2 = st.columns(2)
                
                with col_chart1:
                    fig_global = px.pie(
                        values=[total_wins, total_losses],
                        names=["Victoires", "Défaites"],
                        color_discrete_sequence=["#00CC66", "#FF4444"],
                        title=f"Win Rate Global: {win_rate_global:.1f}%",
                        hole=0.4
                    )
                    st.plotly_chart(fig_global, use_container_width=True)
                
                with col_chart2:
                    # Bar chart des stats
                    stats_data = {
                        "Stat": ["Victoires", "Défaites", "3 Couronnes", "Guerres Gagnées"],
                        "Valeur": [total_wins, total_losses, player.get('threeCrownWins', 0), player.get('warDayWins', 0)]
                    }
                    fig_bar = px.bar(stats_data, x="Stat", y="Valeur", color="Stat", title="Statistiques de Combat")
                    st.plotly_chart(fig_bar, use_container_width=True)
                
                st.divider()
                
                # --- ANALYSE BATTLELOG ---
                if battles:
                    st.subheader("🕹️ Analyse des 25 derniers combats")
                    
                    wins, losses, draws = 0, 0, 0
                    card_stats = {}
                    game_types = {}
                    
                    for b in battles:
                        team_crowns = sum([p.get('crowns', 0) for p in b.get('team', [])])
                        opp_crowns = sum([p.get('crowns', 0) for p in b.get('opponent', [])])
                        
                        outcome = "win" if team_crowns > opp_crowns else ("loss" if team_crowns < opp_crowns else "draw")
                        if outcome == "win": wins += 1
                        elif outcome == "loss": losses += 1
                        else: draws += 1
                        
                        # Type de partie
                        game_type = b.get('type', 'Unknown')
                        game_types[game_type] = game_types.get(game_type, 0) + 1
                        
                        for opp in b.get('opponent', []):
                            for card in opp.get('cards', []):
                                name = card.get('name')
                                if name not in card_stats:
                                    card_stats[name] = {'wins': 0, 'losses': 0, 'draws': 0, 'total': 0}
                                card_stats[name]['total'] += 1
                                if outcome == "win": card_stats[name]['wins'] += 1
                                elif outcome == "loss": card_stats[name]['losses'] += 1
                                else: card_stats[name]['draws'] += 1
                    
                    total_recent = wins + losses + draws
                    recent_wr = (wins / total_recent * 100) if total_recent > 0 else 0
                    
                    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
                    col_r1.metric("🏁 Matchs Récents", total_recent)
                    col_r2.metric("✅ Victoires", wins)
                    col_r3.metric("❌ Défaites", losses)
                    col_r4.metric("📈 Win Rate Récent", f"{recent_wr:.1f}%")
                    
                    col_pie, col_bar = st.columns(2)
                    
                    with col_pie:
                        fig_recent = px.pie(
                            values=[wins, losses, draws],
                            names=["Victoires", "Défaites", "Égalités"],
                            color_discrete_sequence=["#00CC66", "#FF4444", "#888888"],
                            title="Résultats Récents",
                            hole=0.4
                        )
                        st.plotly_chart(fig_recent, use_container_width=True)
                    
                    with col_bar:
                        if game_types:
                            fig_types = px.bar(
                                x=list(game_types.keys()),
                                y=list(game_types.values()),
                                title="Types de Parties",
                                labels={"x": "Type", "y": "Nombre"}
                            )
                            st.plotly_chart(fig_types, use_container_width=True)
                    
                    st.divider()
                    
                    # Match-ups cartes
                    st.subheader("🃏 Match-ups Cartes")
                    
                    rows = []
                    for name, s in card_stats.items():
                        wr = (s['wins'] / s['total'] * 100) if s['total'] > 0 else 0
                        rows.append({"Carte": name, "Rencontres": s['total'], "Win Rate %": round(wr, 1)})
                    
                    df_cards = pd.DataFrame(rows)
                    
                    col_v, col_b = st.columns(2)
                    with col_v:
                        st.write("#### 💪 Tes victimes")
                        st.dataframe(df_cards[df_cards['Rencontres'] >= 2].nlargest(10, 'Win Rate %'), use_container_width=True, hide_index=True)
                    with col_b:
                        st.write("#### ⚠️ Tes bourreaux")
                        st.dataframe(df_cards[df_cards['Rencontres'] >= 2].nsmallest(10, 'Win Rate %'), use_container_width=True, hide_index=True)
                else:
                    st.warning("Aucun combat trouvé dans le battle log.")
            else:
                st.error("Impossible de charger ce joueur. Vérifiez le tag.")