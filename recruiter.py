import requests
import time
import csv
import argparse
import sys
from collections import deque

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
        elif resp.status_code == 429:
            print(f"\n[!] Rate limited. Sleeping 5s...")
            time.sleep(5)
            return get_player_detail(session, player_tag, headers)
        return None
    except Exception as e:
        print(f"\n[!] Error fetching {player_tag}: {e}")
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

def main():
    parser = argparse.ArgumentParser(description="Clash Royale Talent Recruiter")
    parser.add_argument("--tag", type=str, required=True, help="Seed player tag (e.g. #989R2RPQ)")
    parser.add_argument("--key", type=str, required=True, help="Your Clash Royale API Key")
    parser.add_argument("--min", type=int, default=80, help="Min trophies (default: 80)")
    parser.add_argument("--max", type=int, default=15000, help="Max trophies (default: 15000)")
    parser.add_argument("--limit", type=int, default=100, help="Number of recruits to find")
    parser.add_argument("--output", type=str, default="recruits.csv", help="Output CSV filename")
    
    args = parser.parse_args()
    
    headers = get_headers(args.key)
    session = requests.Session()
    
    queue = deque([args.tag])
    visited = {args.tag}
    found_count = 0
    scanned_count = 0
    
    print(f"🚀 Starting recruitment from {args.tag}...")
    print(f"🎯 Criteria: {args.min}-{args.max} trophies, NO clan.")
    print(f"💾 Saving to {args.output}\n")
    
    # Initialize CSV
    with open(args.output, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Tag", "Name", "Trophies", "RoyaleAPI Link"])

    try:
        while queue and found_count < args.limit:
            current_tag = queue.popleft()
            scanned_count += 1
            
            # 1. Fetch player details to check if they match criteria
            p_data = get_player_detail(session, current_tag, headers)
            if p_data:
                trophies = p_data.get('trophies', 0)
                has_clan = 'clan' in p_data
                name = p_data.get('name', 'Unknown')
                
                status = "❌"
                if not has_clan and args.min <= trophies <= args.max:
                    found_count += 1
                    status = "✅ FOUND"
                    # Save to CSV
                    with open(args.output, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        link = f"https://royaleapi.com/player/{current_tag.replace('#', '')}"
                        writer.writerow([current_tag, name, trophies, link])
                
                # Print progress
                sys.stdout.write(f"\r[#{scanned_count}] {current_tag} ({trophies}🏆): {status} | Total: {found_count}/{args.limit} ")
                sys.stdout.flush()

            # 2. Get battle log to find more players
            battles = get_battle_log(session, current_tag, headers)
            for b in battles:
                # Add opponents and teammates to queue
                participants = []
                for team in ['team', 'opponent']:
                    participants.extend(b.get(team, []))
                
                for p in participants:
                    p_tag = p.get('tag')
                    if p_tag and p_tag not in visited:
                        visited.add(p_tag)
                        queue.append(p_tag)
            
            # Small sleep to respect API (adjustable)
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user.")
    
    print(f"\n\n✨ Done! Found {found_count} players. Data saved to {args.output}")

if __name__ == "__main__":
    main()
