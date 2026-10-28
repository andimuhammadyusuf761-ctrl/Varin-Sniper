import os
import json
import random
import string
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional

# Setup logging with better formatting
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler("sniper.log", encoding="utf-8"),
        logging.StreamHandler()
    ],
)
for _h in logging.root.handlers:
    if isinstance(_h, logging.FileHandler):
        _h.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", datefmt="%H:%M:%S"))

logger = logging.getLogger("VarinSniper")

class ConfigManager:
    """Advanced configuration manager with validation"""
    DEFAULT_CONFIG = {
        "threads": 15,
        "delay": 2.0,
        "timeout": 10.0,
        "proxy_enabled": False,
        "proxy_rotate": True,
        "proxy_file": "proxies.txt",
        "auto_remove_bad_proxies": True,
        "proxy_test_timeout": 5,
        "sound_notifications": False,
        "auto_claim": False,
        "watch_mode": True,
        "stealth_mode": True,
        "adaptive_rate": True,
        "language": "en",
        "wallpaper_3d": True,
        "effects_3d": True,
        "gen_mode": "rarest",
        "gen_consonants_only": False,
        "max_retries": 3,
        "claim_max_accounts": 0,
        "discord_webhook_url": "",
        "notify_on_available": True,
        "notify_on_claimed": True,
        "use_discord_webhook": False,
        "min_delay": 0.5,
        "max_delay": 30.0,
        "jitter_factor": 0.3,
        "connection_pool_size": 10,
        "user_agent_rotation": True,
    }
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self._lock = threading.Lock()
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                config = self.DEFAULT_CONFIG.copy()
                config.update(user_config)
                # Validate
                config = self._validate_config(config)
                return config
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load config: {e}, using defaults")
                return self.DEFAULT_CONFIG.copy()
        else:
            self.save_config(self.DEFAULT_CONFIG)
            return self.DEFAULT_CONFIG.copy()
    
    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        # Clamp values
        config["threads"] = max(1, min(int(config.get("threads", 15)), 100))
        config["delay"] = max(0.1, min(float(config.get("delay", 2.0)), 60.0))
        config["timeout"] = max(1, min(float(config.get("timeout", 10.0)), 60.0))
        config["min_delay"] = max(0.1, min(float(config.get("min_delay", 0.5)), 10.0))
        config["max_delay"] = max(1, min(float(config.get("max_delay", 30.0)), 120.0))
        return config
    
    def save_config(self, config: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            if config is None:
                config = self.config
            try:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=4)
                logger.debug(f"Config saved to {self.config_path}")
            except IOError as e:
                logger.error(f"Failed to save config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self.config[key] = value
    
    def update(self, updates: Dict[str, Any]) -> None:
        with self._lock:
            self.config.update(updates)
            self.config = self._validate_config(self.config)

# Global config instance
_config_manager = ConfigManager()

def load_config(config_path: str = "config.json") -> dict:
    """Load configuration from JSON file"""
    global _config_manager
    if _config_manager.config_path != config_path:
        _config_manager = ConfigManager(config_path)
    return _config_manager.config

def save_config(config_path: str, config: dict) -> None:
    """Save configuration to JSON file"""
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        logger.debug(f"Config saved to {config_path}")
    except IOError as e:
        logger.error(f"Failed to save config: {e}")

def save_current_config(config: Optional[Dict[str, Any]] = None) -> None:
    """Simpan config global (ConfigManager) ke disk.

    Satu jalur tulis untuk GUI: memakai lock yang sama dan path yang sama
    dengan saat config dibaca, sehingga setting yang diubah di UI benar-benar
    tersimpan (bukan hanya berubah di memori).
    """
    if config is not None:
        _config_manager.config = config
    _config_manager.save_config()


def load_names_from_file(filepath: str) -> List[str]:
    """Load usernames from a text file, one per line"""
    names = []
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        return names
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip().lower()
                if name and 3 <= len(name) <= 16 and all(c.isalnum() or c == '_' for c in name):
                    names.append(name)
        # Remove duplicates while preserving order
        seen = set()
        unique_names = []
        for n in names:
            if n not in seen:
                seen.add(n)
                unique_names.append(n)
        logger.info(f"Loaded {len(unique_names)} unique names from {filepath}")
        return unique_names
    except IOError as e:
        logger.error(f"Failed to load names from {filepath}: {e}")
        return names

def save_names_to_file(names: List[str], filepath: str) -> None:
    """Save a list of names to a text file, one per line"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            for name in names:
                f.write(name + "\n")
        logger.info(f"Saved {len(names)} names to {filepath}")
    except IOError as e:
        logger.error(f"Failed to save names to {filepath}: {e}")

def format_time(seconds: float) -> str:
    """Format seconds into human-readable time"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}h {mins}m {secs}s"

def format_uptime(seconds: float) -> str:
    """Format uptime in HH:MM:SS"""
    hours = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}"

def append_to_file(filepath: str, line: str) -> bool:
    """Append a line to file safely"""
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return True
    except IOError as e:
        logger.error(f"Failed to append to {filepath}: {e}")
        return False

class StatsTracker:
    """Thread-safe statistics tracker"""
    def __init__(self):
        self.total_checked = 0
        self.available = 0
        self.taken = 0
        self.claimed = 0
        self.errors = 0
        self.rate_limited = 0
        self.start_time = time.time()
        self.lock = threading.Lock()
    
    def increment(self, category: str) -> None:
        with self.lock:
            if category == "total" or category == "checked":
                self.total_checked += 1
            elif category == "available":
                self.available += 1
            elif category == "taken":
                self.taken += 1
            elif category == "claimed":
                self.claimed += 1
            elif category == "errors" or category == "error":
                self.errors += 1
            elif category == "rate_limited" or category == "ratelimit":
                self.rate_limited += 1
    
    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            elapsed = time.time() - self.start_time
            success_rate = (self.claimed / self.available * 100) if self.available > 0 else 0.0
            return {
                "total_checked": self.total_checked,
                "available": self.available,
                "taken": self.taken,
                "claimed": self.claimed,
                "errors": self.errors,
                "rate_limited": self.rate_limited,
                "elapsed": elapsed,
                "uptime": format_uptime(elapsed),
                "success_rate": round(success_rate, 2),
                "checks_per_sec": round(self.total_checked / elapsed, 2) if elapsed > 0 else 0.0,
            }
    
    def reset(self) -> None:
        with self.lock:
            self.total_checked = 0
            self.available = 0
            self.taken = 0
            self.claimed = 0
            self.errors = 0
            self.rate_limited = 0
            self.start_time = time.time()

def send_discord_webhook(webhook_url: str, title: str, description: str, color: int = 0x00ff88) -> bool:
    """Send notification to Discord webhook"""
    if not webhook_url:
        return False
    try:
        import requests
        data = {
            "embeds": [{
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }]
        }
        response = requests.post(webhook_url, json=data, timeout=10)
        return response.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Failed to send Discord webhook: {e}")
        return False
