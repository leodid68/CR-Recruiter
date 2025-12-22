"""
Player Scanner Module
Async BFS traversal with configurable filters.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Set
from datetime import datetime, timedelta
import time

from api import ClashRoyaleAPI


@dataclass
class ScanFilters:
    """Configurable filters for player scanning."""
    min_trophies: int = 80
    max_trophies: int = 15000
    require_no_clan: bool = True
    min_level: Optional[int] = None
    max_level: Optional[int] = None
    max_inactive_days: Optional[int] = None  # Based on last battle
    only_french: bool = False


@dataclass
class ScanStats:
    """Real-time scanning statistics."""
    start_time: float = field(default_factory=time.time)
    scanned: int = 0
    found: int = 0
    queue_size: int = 0
    errors: int = 0
    
    @property
    def elapsed_minutes(self) -> float:
        return (time.time() - self.start_time) / 60
    
    @property
    def scans_per_minute(self) -> float:
        if self.elapsed_minutes < 0.1:
            return 0
        return self.scanned / self.elapsed_minutes
    
    @property
    def success_rate(self) -> float:
        if self.scanned == 0:
            return 0
        return (self.found / self.scanned) * 100


@dataclass
class FoundPlayer:
    """Represents a found recruit."""
    tag: str
    name: str
    trophies: int
    level: int
    last_battle: Optional[datetime] = None
    
    @property
    def royaleapi_link(self) -> str:
        return f"https://royaleapi.com/player/{self.tag.replace('#', '')}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "Tag": self.tag,
            "Nom": self.name,
            "Trophées": self.trophies,
            "Niveau": self.level,
            "Lien": self.royaleapi_link
        }


class PlayerScanner:
    """
    Async player scanner with BFS traversal.
    Reports progress via callbacks for UI integration.
    """
    
    def __init__(
        self,
        api: ClashRoyaleAPI,
        filters: ScanFilters,
        on_player_found: Optional[Callable[[FoundPlayer], None]] = None,
        on_stats_update: Optional[Callable[[ScanStats], None]] = None,
        batch_size: int = 20
    ):
        self.api = api
        self.filters = filters
        self.on_player_found = on_player_found
        self.on_stats_update = on_stats_update
        self.batch_size = batch_size
        
        self.stats = ScanStats()
        self.visited: Set[str] = set()
        self.queue: deque = deque()
        self.found_players: List[FoundPlayer] = []
        self._running = False
    
    def stop(self):
        """Stop the scanner."""
        self._running = False
    
    def _matches_filters(self, player: Dict[str, Any], battles: List[Dict]) -> bool:
        """Check if player matches all filters."""
        trophies = player.get('trophies', 0)
        has_clan = 'clan' in player
        level = player.get('expLevel', 1)
        
        # Trophy filter
        if not (self.filters.min_trophies <= trophies <= self.filters.max_trophies):
            return False
        
        # Clan filter
        if self.filters.require_no_clan and has_clan:
            return False
        
        # Level filter
        if self.filters.min_level and level < self.filters.min_level:
            return False
        if self.filters.max_level and level > self.filters.max_level:
            return False
        
        # Activity filter (based on most recent battle)
        if self.filters.max_inactive_days and battles:
            try:
                last_battle_str = battles[0].get('battleTime', '')
                if last_battle_str:
                    last_battle = datetime.strptime(last_battle_str[:15], '%Y%m%dT%H%M%S')
                    days_inactive = (datetime.utcnow() - last_battle).days
                    if days_inactive > self.filters.max_inactive_days:
                        return False
            except:
                pass
        
        # French filter
        if self.filters.only_french:
            fr_signals = 0
            for battle in battles:
                for opp in battle.get('opponent', []):
                    clan = opp.get('clan')
                    if clan:
                        clan_name = clan.get('name', '').lower()
                        if any(x in clan_name for x in ["fr ", " fr", "france", "français"]):
                            fr_signals += 1
            if fr_signals == 0:
                return False
        
        return True
    
    def _extract_tags_from_battles(self, battles: List[Dict]) -> List[str]:
        """Extract all player tags from battle log."""
        tags = []
        for battle in battles:
            for team in ['team', 'opponent']:
                for player in battle.get(team, []):
                    tag = player.get('tag')
                    if tag and tag not in self.visited:
                        tags.append(tag)
        return tags
    
    async def _process_player(self, tag: str) -> Optional[FoundPlayer]:
        """Process a single player."""
        player, battles = await self.api.get_player_with_battles(tag)
        
        if not player:
            self.stats.errors += 1
            return None
        
        self.stats.scanned += 1
        
        # Add new tags to queue
        new_tags = self._extract_tags_from_battles(battles)
        for new_tag in new_tags:
            if new_tag not in self.visited:
                self.visited.add(new_tag)
                self.queue.append(new_tag)
        
        # Check filters
        if self._matches_filters(player, battles):
            self.stats.found += 1
            
            # Parse last battle time
            last_battle = None
            if battles:
                try:
                    last_battle_str = battles[0].get('battleTime', '')[:15]
                    last_battle = datetime.strptime(last_battle_str, '%Y%m%dT%H%M%S')
                except:
                    pass
            
            return FoundPlayer(
                tag=player['tag'],
                name=player.get('name', 'Unknown'),
                trophies=player.get('trophies', 0),
                level=player.get('expLevel', 1),
                last_battle=last_battle
            )
        
        return None
    
    async def scan(self, seed_tag: str, limit: int = 100) -> List[FoundPlayer]:
        """
        Start scanning from seed player.
        Returns list of found players.
        """
        self._running = True
        self.stats = ScanStats()
        self.visited = {seed_tag}
        self.queue = deque([seed_tag])
        self.found_players = []
        
        while self._running and self.queue and len(self.found_players) < limit:
            # Process batch
            batch_tags = []
            for _ in range(min(self.batch_size, len(self.queue))):
                if self.queue:
                    batch_tags.append(self.queue.popleft())
            
            if not batch_tags:
                break
            
            # Process all in parallel
            tasks = [self._process_player(tag) for tag in batch_tags]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, FoundPlayer):
                    self.found_players.append(result)
                    if self.on_player_found:
                        self.on_player_found(result)
            
            # Update stats
            self.stats.queue_size = len(self.queue)
            if self.on_stats_update:
                self.on_stats_update(self.stats)
        
        self._running = False
        return self.found_players
