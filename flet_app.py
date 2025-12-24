import flet as ft
import requests
import threading
import json
import os
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# --- CONSTANTS ---
HISTORY_FILE = "recruiter_history.json"

# --- HISTORY MANAGEMENT ---
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

# --- TELEGRAM ---
def send_telegram(bot_token, chat_id, players):
    if not bot_token or not chat_id:
        return False
    
    message = "🎯 Nouvelles Recrues CR !\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, p in enumerate(players, 1):
        clean_tag = p['Tag'].replace('#', '')
        message += f"{i}. {p['Nom']}\n"
        message += f"   🏆 {p['Trophées']} (Best: {p.get('Best', 'N/A')})\n"
        message += f"   👤 https://royaleapi.com/player/{clean_tag}\n\n"
    
    if len(message) > 4000:
        message = message[:4000] + "\n... (tronqué)"
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": message, "disable_web_page_preview": True}, timeout=10)
        return r.status_code == 200
    except:
        return False

# --- API FUNCTIONS ---
class ClashAPI:
    def __init__(self, api_token):
        self.api_token = api_token
        self.headers = {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}
    
    def get_battle_log(self, tag):
        url = f"https://api.clashroyale.com/v1/players/{tag.replace('#', '%23')}/battlelog"
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            return r.json() if r.status_code == 200 else []
        except:
            return []
    
    def get_player(self, tag):
        url = f"https://api.clashroyale.com/v1/players/{tag.replace('#', '%23')}"
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            return r.json() if r.status_code == 200 else None
        except:
            return None
    
    def get_clan(self, tag):
        url = f"https://api.clashroyale.com/v1/clans/{tag.replace('#', '%23')}"
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            return r.json() if r.status_code == 200 else None
        except:
            return None

def main(page: ft.Page):
    page.title = "👑 CR Recruiter"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 20
    page.window.width = 1400
    page.window.height = 900
    page.scroll = ft.ScrollMode.AUTO
    
    # --- STATE ---
    api = None
    scanning = False
    found_players = []
    clan_members = []
    history = load_history()
    
    # --- CONFIG FIELDS ---
    api_key_field = ft.TextField(label="Clé API Clash Royale", password=True, width=500)
    seed_tag_field = ft.TextField(label="Tag Graine", value="#989R2RPQ", width=150)
    min_trophies_field = ft.TextField(label="Min Trophées", value="7500", width=100)
    max_trophies_field = ft.TextField(label="Max Trophées", value="11000", width=100)
    min_scan_field = ft.TextField(label="Qualité Scan", value="7000", width=100)
    objectif_field = ft.TextField(label="Objectif", value="50", width=80)
    workers_field = ft.Slider(min=1, max=10, value=5, divisions=9, label="{value} workers", width=200)
    
    # Telegram config
    telegram_token_field = ft.TextField(label="Telegram Bot Token", value="8532137772:AAGcnzo6D5rDleWEc0hPb-BdlS4lg1hrBF8", password=True, width=400)
    telegram_chat_id_field = ft.TextField(label="Telegram Chat ID", value="-1003643661262", width=200)
    telegram_batch_field = ft.TextField(label="Notifier tous les X", value="20", width=100)
    
    # History toggle
    use_history_checkbox = ft.Checkbox(label=f"Ignorer joueurs déjà trouvés ({len(history)} en historique)", value=True)
    
    # Status & Progress
    status_text = ft.Text("En attente...", size=14)
    progress_bar = ft.ProgressBar(visible=False, width=600)
    scanned_text = ft.Text("Scannés: 0", size=18, weight=ft.FontWeight.BOLD)
    found_text = ft.Text("Trouvés: 0", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN)
    queue_text = ft.Text("File: 0", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE)
    notif_text = ft.Text("Notifs: 0", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.PURPLE)
    
    # Results table
    results_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Nom")),
            ft.DataColumn(ft.Text("Trophées")),
            ft.DataColumn(ft.Text("Best")),
            ft.DataColumn(ft.Text("Carte Fav")),
            ft.DataColumn(ft.Text("Dernière Partie")),
            ft.DataColumn(ft.Text("Tag")),
        ],
        rows=[],
    )
    
    # --- SCAN LOGIC ---
    def run_scan(e):
        nonlocal api, scanning, found_players, history
        
        if not api_key_field.value:
            status_text.value = "⚠️ Entrez votre clé API"
            page.update()
            return
        
        api = ClashAPI(api_key_field.value)
        scanning = True
        found_players = []
        history = load_history()
        use_hist = use_history_checkbox.value
        
        min_tr = int(min_trophies_field.value)
        max_tr = int(max_trophies_field.value)
        min_scan = int(min_scan_field.value)
        objectif = int(objectif_field.value)
        workers = int(workers_field.value)
        tg_batch = int(telegram_batch_field.value)
        
        queue = deque([seed_tag_field.value])
        visited = {seed_tag_field.value}
        scanned = 0
        notif_count = 0
        last_notified = 0
        
        progress_bar.visible = True
        status_text.value = f"🔍 Recherche en cours avec {workers} workers..."
        results_table.rows.clear()
        page.update()
        
        while queue and len(found_players) < objectif and scanning:
            current = queue.popleft()
            battles = api.get_battle_log(current)
            
            tags_to_check = []
            for battle in battles:
                for opp in battle.get('opponent', []):
                    tag = opp['tag']
                    if tag not in visited:
                        visited.add(tag)
                        tags_to_check.append(tag)
            
            if tags_to_check and scanning:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {executor.submit(api.get_player, tag): tag for tag in tags_to_check}
                    
                    for future in as_completed(futures):
                        if len(found_players) >= objectif or not scanning:
                            break
                        
                        tag = futures[future]
                        scanned += 1
                        
                        try:
                            player = future.result()
                            if player:
                                trophies = player.get("trophies", 0)
                                has_clan = "clan" in player
                                
                                if not has_clan and min_tr <= trophies <= max_tr:
                                    if use_hist and tag in history:
                                        continue
                                    
                                    clean_tag = tag.replace('#', '')
                                    best = player.get("bestTrophies", 0)
                                    fav_card = player.get("currentFavouriteCard", {}).get("name", "N/A")
                                    
                                    # Get last battle
                                    player_battles = api.get_battle_log(tag)
                                    last_battle = "N/A"
                                    if player_battles:
                                        bt = player_battles[0].get("battleTime", "")
                                        if bt:
                                            last_battle = f"{bt[0:4]}-{bt[4:6]}-{bt[6:8]}"
                                    
                                    found_players.append({
                                        "Nom": player["name"],
                                        "Trophées": trophies,
                                        "Best": best,
                                        "Carte Fav": fav_card,
                                        "Dernière Partie": last_battle,
                                        "Tag": tag,
                                    })
                                    
                                    results_table.rows.append(
                                        ft.DataRow(cells=[
                                            ft.DataCell(ft.Text(player["name"])),
                                            ft.DataCell(ft.Text(str(trophies))),
                                            ft.DataCell(ft.Text(str(best))),
                                            ft.DataCell(ft.Text(fav_card)),
                                            ft.DataCell(ft.Text(last_battle)),
                                            ft.DataCell(ft.Text(tag)),
                                        ])
                                    )
                                    
                                    # Telegram notification
                                    if telegram_chat_id_field.value and len(found_players) >= last_notified + tg_batch:
                                        players_to_send = found_players[last_notified:]
                                        if send_telegram(telegram_token_field.value, telegram_chat_id_field.value, players_to_send):
                                            notif_count += 1
                                            last_notified = len(found_players)
                                            notif_text.value = f"Notifs: {notif_count}"
                                
                                if trophies >= min_scan:
                                    queue.append(tag)
                        except:
                            pass
                        
                        scanned_text.value = f"Scannés: {scanned}"
                        found_text.value = f"Trouvés: {len(found_players)}"
                        queue_text.value = f"File: {len(queue)}"
                        status_text.value = f"🔍 {scanned} profils... (file: {len(queue)})"
                        page.update()
        
        # Save history
        if found_players:
            new_tags = {p['Tag'] for p in found_players}
            save_history(history.union(new_tags))
            use_history_checkbox.label = f"Ignorer joueurs déjà trouvés ({len(history) + len(found_players)} en historique)"
        
        # Send remaining
        if telegram_chat_id_field.value and len(found_players) > last_notified:
            send_telegram(telegram_token_field.value, telegram_chat_id_field.value, found_players[last_notified:])
        
        scanning = False
        progress_bar.visible = False
        status_text.value = f"✅ Terminé ! {len(found_players)} recrues trouvées."
        page.update()
    
    def stop_scan(e):
        nonlocal scanning
        scanning = False
        status_text.value = "⏹️ Scan arrêté"
        progress_bar.visible = False
        page.update()
    
    def clear_hist(e):
        nonlocal history
        clear_history()
        history = set()
        use_history_checkbox.label = f"Ignorer joueurs déjà trouvés (0 en historique)"
        status_text.value = "🗑️ Historique vidé"
        page.update()
    
    def export_csv(e):
        if found_players:
            import csv
            with open("recrues_export.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Nom", "Trophées", "Best", "Carte Fav", "Dernière Partie", "Tag"])
                writer.writeheader()
                writer.writerows(found_players)
            status_text.value = "📥 Exporté vers recrues_export.csv"
            page.update()
    
    # --- CLAN TAB ---
    clan_tag_field = ft.TextField(label="Tag du Clan", value="#GPYQUC8U", width=200)
    clan_status = ft.Text("")
    clan_stats = ft.Row([])
    clan_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Nom")),
            ft.DataColumn(ft.Text("Trophées")),
            ft.DataColumn(ft.Text("Rôle")),
            ft.DataColumn(ft.Text("Dons")),
            ft.DataColumn(ft.Text("Dernière Partie")),
            ft.DataColumn(ft.Text("Statut")),
        ],
        rows=[],
    )
    clan_progress = ft.ProgressBar(visible=False, width=400)
    
    def load_clan(e):
        nonlocal api, clan_members
        if not api_key_field.value:
            clan_status.value = "⚠️ Entrez votre clé API d'abord"
            page.update()
            return
        
        api = ClashAPI(api_key_field.value)
        clan_data = api.get_clan(clan_tag_field.value)
        
        if clan_data:
            clan_members = []
            clan_table.rows.clear()
            clan_progress.visible = True
            clan_status.value = f"Chargement de {clan_data.get('name', '')}..."
            page.update()
            
            members = clan_data.get('memberList', [])
            for idx, m in enumerate(members):
                role = m.get('role', '').replace('coLeader', 'Co-Leader').replace('elder', 'Aîné').replace('member', 'Membre').replace('leader', 'Chef')
                
                # Get activity
                battles = api.get_battle_log(m.get('tag', ''))
                status_emoji = "🔒"
                last_battle = "Privé"
                days_ago = 999
                
                if battles:
                    bt = battles[0].get('battleTime', '')
                    if bt:
                        try:
                            b_date = datetime.strptime(bt[:15], '%Y%m%dT%H%M%S')
                            days_ago = (datetime.now() - b_date).days
                            last_battle = b_date.strftime('%Y-%m-%d')
                            if days_ago == 0: status_emoji = "🟢"
                            elif days_ago <= 1: status_emoji = "🟡"
                            elif days_ago <= 3: status_emoji = "🟠"
                            elif days_ago <= 7: status_emoji = "🔴"
                            else: status_emoji = f"⚫ {days_ago}j"
                        except:
                            pass
                
                clan_members.append({
                    "Nom": m.get('name', ''),
                    "Tag": m.get('tag', ''),
                    "Trophées": m.get('trophies', 0),
                    "Rôle": role,
                    "Dons": m.get('donations', 0),
                    "Dernière Partie": last_battle,
                    "Statut": status_emoji,
                })
                
                clan_table.rows.append(
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(m.get('name', ''))),
                        ft.DataCell(ft.Text(str(m.get('trophies', 0)))),
                        ft.DataCell(ft.Text(role)),
                        ft.DataCell(ft.Text(str(m.get('donations', 0)))),
                        ft.DataCell(ft.Text(last_battle)),
                        ft.DataCell(ft.Text(status_emoji)),
                    ])
                )
                
                clan_status.value = f"Chargement... {idx+1}/{len(members)}"
                page.update()
                time.sleep(0.05)
            
            # Stats
            total_trophies = sum(m['Trophées'] for m in clan_members)
            avg_trophies = total_trophies // len(clan_members) if clan_members else 0
            total_dons = sum(m['Dons'] for m in clan_members)
            inactive = len([m for m in clan_members if '⚫' in m['Statut'] or '🔴' in m['Statut']])
            
            clan_stats.controls = [
                ft.Container(ft.Column([ft.Text("👥"), ft.Text(f"{len(clan_members)}/50", weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.BLUE_900, padding=15, border_radius=10),
                ft.Container(ft.Column([ft.Text("🏆 Moy"), ft.Text(str(avg_trophies), weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.AMBER_900, padding=15, border_radius=10),
                ft.Container(ft.Column([ft.Text("💝 Dons"), ft.Text(str(total_dons), weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.GREEN_900, padding=15, border_radius=10),
                ft.Container(ft.Column([ft.Text("🔴 Inactifs"), ft.Text(str(inactive), weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.RED_900, padding=15, border_radius=10),
            ]
            
            # Update player dropdown
            player_dropdown.options = [ft.dropdown.Option(f"{m['Nom']} ({m['Tag']})") for m in clan_members]
            
            clan_progress.visible = False
            clan_status.value = f"✅ {clan_data.get('name', '')} - {len(clan_members)} membres"
        else:
            clan_status.value = "❌ Impossible de charger le clan"
        page.update()
    
    def export_clan_csv(e):
        if clan_members:
            import csv
            with open("clan_members.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Nom", "Tag", "Trophées", "Rôle", "Dons", "Dernière Partie", "Statut"])
                writer.writeheader()
                writer.writerows(clan_members)
            clan_status.value = "📥 Exporté vers clan_members.csv"
            page.update()
    
    # --- PLAYER ANALYSIS TAB ---
    player_dropdown = ft.Dropdown(label="Choisir un membre du clan", options=[], width=300)
    player_tag_field = ft.TextField(label="Ou entrer un Tag", value="#PL0Q8UGR", width=200)
    player_info = ft.Column([], scroll=ft.ScrollMode.AUTO)
    
    def analyze_player(e):
        nonlocal api
        if not api_key_field.value:
            player_info.controls = [ft.Text("⚠️ Entrez votre clé API d'abord")]
            page.update()
            return
        
        tag = player_tag_field.value
        if player_dropdown.value:
            tag = player_dropdown.value.split("(")[-1].replace(")", "").strip()
        
        api = ClashAPI(api_key_field.value)
        player = api.get_player(tag)
        battles = api.get_battle_log(tag)
        
        if player:
            # Profile header
            total_battles = player.get('battleCount', 0)
            total_wins = player.get('wins', 0)
            total_losses = player.get('losses', 0)
            win_rate = (total_wins / total_battles * 100) if total_battles > 0 else 0
            
            player_info.controls = [
                ft.Text(f"👤 {player.get('name', 'N/A')} {player.get('tag', '')}", size=28, weight=ft.FontWeight.BOLD),
                ft.Divider(),
                ft.Row([
                    ft.Container(ft.Column([ft.Text("🏆 Trophées"), ft.Text(str(player.get('trophies', 0)), size=24, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.BLUE_900, padding=15, border_radius=10),
                    ft.Container(ft.Column([ft.Text("⭐ Best"), ft.Text(str(player.get('bestTrophies', 0)), size=24, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.AMBER_900, padding=15, border_radius=10),
                    ft.Container(ft.Column([ft.Text("👑 Niveau"), ft.Text(str(player.get('expLevel', 0)), size=24, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.PURPLE_900, padding=15, border_radius=10),
                    ft.Container(ft.Column([ft.Text("🎯 Victoires"), ft.Text(str(total_wins), size=24, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.GREEN_900, padding=15, border_radius=10),
                    ft.Container(ft.Column([ft.Text("❌ Défaites"), ft.Text(str(total_losses), size=24, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.RED_900, padding=15, border_radius=10),
                    ft.Container(ft.Column([ft.Text("📈 Win Rate"), ft.Text(f"{win_rate:.1f}%", size=24, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.CYAN_900, padding=15, border_radius=10),
                ], spacing=10, wrap=True),
                ft.Divider(),
                ft.Row([
                    ft.Container(ft.Column([ft.Text("👑 3 Couronnes"), ft.Text(str(player.get('threeCrownWins', 0)), size=20, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.ORANGE_900, padding=15, border_radius=10),
                    ft.Container(ft.Column([ft.Text("🏅 Max Défi"), ft.Text(str(player.get('challengeMaxWins', 0)), size=20, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.PINK_900, padding=15, border_radius=10),
                    ft.Container(ft.Column([ft.Text("🎴 Cartes Défi"), ft.Text(str(player.get('challengeCardsWon', 0)), size=20, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.TEAL_900, padding=15, border_radius=10),
                    ft.Container(ft.Column([ft.Text("⚔️ Guerres"), ft.Text(str(player.get('warDayWins', 0)), size=20, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.INDIGO_900, padding=15, border_radius=10),
                    ft.Container(ft.Column([ft.Text("💰 Dons Totaux"), ft.Text(str(player.get('totalDonations', 0)), size=20, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.LIME_900, padding=15, border_radius=10),
                ], spacing=10, wrap=True),
                ft.Text(f"🃏 Carte Favorite: {player.get('currentFavouriteCard', {}).get('name', 'N/A')}", size=16),
                ft.Divider(),
            ]
            
            # Battle log analysis
            if battles:
                wins, losses, draws = 0, 0, 0
                card_stats = {}
                
                for b in battles:
                    tc = sum([p.get('crowns', 0) for p in b.get('team', [])])
                    oc = sum([p.get('crowns', 0) for p in b.get('opponent', [])])
                    outcome = "win" if tc > oc else ("loss" if tc < oc else "draw")
                    if outcome == "win": wins += 1
                    elif outcome == "loss": losses += 1
                    else: draws += 1
                    
                    for opp in b.get('opponent', []):
                        for card in opp.get('cards', []):
                            name = card.get('name')
                            if name not in card_stats:
                                card_stats[name] = {'wins': 0, 'losses': 0, 'total': 0}
                            card_stats[name]['total'] += 1
                            if outcome == "win": card_stats[name]['wins'] += 1
                            elif outcome == "loss": card_stats[name]['losses'] += 1
                
                recent_wr = (wins / (wins + losses + draws) * 100) if (wins + losses + draws) > 0 else 0
                
                player_info.controls.append(ft.Text(f"🕹️ Derniers {len(battles)} combats", size=20, weight=ft.FontWeight.BOLD))
                player_info.controls.append(ft.Row([
                    ft.Container(ft.Column([ft.Text("✅"), ft.Text(str(wins), size=20, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.GREEN_900, padding=10, border_radius=10),
                    ft.Container(ft.Column([ft.Text("❌"), ft.Text(str(losses), size=20, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.RED_900, padding=10, border_radius=10),
                    ft.Container(ft.Column([ft.Text("🟰"), ft.Text(str(draws), size=20, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.GREY_800, padding=10, border_radius=10),
                    ft.Container(ft.Column([ft.Text("📈"), ft.Text(f"{recent_wr:.1f}%", size=20, weight=ft.FontWeight.BOLD)], horizontal_alignment=ft.CrossAxisAlignment.CENTER), bgcolor=ft.Colors.CYAN_900, padding=10, border_radius=10),
                ], spacing=10))
                
                # Card matchups
                player_info.controls.append(ft.Divider())
                player_info.controls.append(ft.Text("🃏 Match-ups Cartes", size=20, weight=ft.FontWeight.BOLD))
                
                sorted_cards = sorted(card_stats.items(), key=lambda x: x[1]['total'], reverse=True)
                victims = sorted([c for c in sorted_cards if c[1]['total'] >= 2], key=lambda x: (x[1]['wins']/x[1]['total']), reverse=True)[:5]
                executioners = sorted([c for c in sorted_cards if c[1]['total'] >= 2], key=lambda x: (x[1]['wins']/x[1]['total']))[:5]
                
                matchup_row = ft.Row([
                    ft.Column([
                        ft.Text("💪 Victimes", weight=ft.FontWeight.BOLD),
                        *[ft.Text(f"{c[0]}: {c[1]['wins']}/{c[1]['total']} ({c[1]['wins']/c[1]['total']*100:.0f}%)") for c in victims]
                    ], width=300),
                    ft.Column([
                        ft.Text("⚠️ Bourreaux", weight=ft.FontWeight.BOLD),
                        *[ft.Text(f"{c[0]}: {c[1]['wins']}/{c[1]['total']} ({c[1]['wins']/c[1]['total']*100:.0f}%)") for c in executioners]
                    ], width=300),
                ], spacing=50)
                player_info.controls.append(matchup_row)
        else:
            player_info.controls = [ft.Text("❌ Joueur non trouvé")]
        page.update()
    
    # --- TABS ---
    tabs = ft.Tabs(
        selected_index=0,
        tabs=[
            ft.Tab(
                text="🔍 Recruteur",
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([api_key_field]),
                        ft.Divider(),
                        ft.Text("🎯 Filtres", weight=ft.FontWeight.BOLD),
                        ft.Row([seed_tag_field, min_trophies_field, max_trophies_field, min_scan_field, objectif_field]),
                        ft.Row([ft.Text("Workers:"), workers_field]),
                        ft.Divider(),
                        ft.Text("📱 Telegram", weight=ft.FontWeight.BOLD),
                        ft.Row([telegram_token_field, telegram_chat_id_field, telegram_batch_field]),
                        ft.Divider(),
                        ft.Row([use_history_checkbox, ft.ElevatedButton("🗑️ Vider historique", on_click=clear_hist)]),
                        ft.Divider(),
                        ft.Row([
                            ft.ElevatedButton("🚀 Lancer", on_click=lambda e: threading.Thread(target=run_scan, args=(e,)).start(), bgcolor=ft.Colors.GREEN),
                            ft.ElevatedButton("⏹️ Stop", on_click=stop_scan, bgcolor=ft.Colors.RED),
                            ft.ElevatedButton("📥 Exporter CSV", on_click=export_csv),
                        ], spacing=10),
                        ft.Row([scanned_text, found_text, queue_text, notif_text], spacing=30),
                        progress_bar,
                        status_text,
                        ft.Container(content=results_table, height=350),
                    ], spacing=10, scroll=ft.ScrollMode.AUTO),
                    padding=20,
                ),
            ),
            ft.Tab(
                text="🏰 Mon Clan",
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([clan_tag_field, ft.ElevatedButton("📊 Charger", on_click=lambda e: threading.Thread(target=load_clan, args=(e,)).start()), ft.ElevatedButton("📥 Export CSV", on_click=export_clan_csv)]),
                        clan_progress,
                        clan_status,
                        clan_stats,
                        ft.Container(content=clan_table, height=450),
                    ], spacing=10, scroll=ft.ScrollMode.AUTO),
                    padding=20,
                ),
            ),
            ft.Tab(
                text="🕹️ Analyse Joueur",
                content=ft.Container(
                    content=ft.Column([
                        ft.Row([player_dropdown, player_tag_field, ft.ElevatedButton("📈 Analyser", on_click=analyze_player)]),
                        ft.Text("💡 Chargez un clan pour avoir la liste déroulante", size=12, italic=True),
                        ft.Divider(),
                        ft.Container(content=player_info, height=600),
                    ], spacing=10, scroll=ft.ScrollMode.AUTO),
                    padding=20,
                ),
            ),
        ],
        expand=True,
    )
    
    page.add(
        ft.Text("👑 CR Recruiter", size=32, weight=ft.FontWeight.BOLD),
        tabs,
    )

ft.app(target=main)
