import socket
import random
import logging
import os
import time
import threading
from typing import Optional, List, Dict, Any
import requests

try:
    import socks  # noqa: F401
except ImportError:
    pass

logger = logging.getLogger("VarinSniper.Proxy")

class Proxy:
    """Enhanced proxy with scoring, health tracking, and better management"""
    
    def __init__(self, host: str, port: int, proxy_type: str = "http", 
                 username: Optional[str] = None, password: Optional[str] = None):
        self.host = host
        self.port = port
        self.proxy_type = proxy_type.lower().strip()
        self.username = username.strip() if username else None
        self.password = password.strip() if password else None
        self.alive = True
        self.last_check = 0.0
        self.fail_count = 0
        self.success_count = 0
        self.score = 100.0  # Quality score 0-100
        self.latency = 0.0
        self.last_used = 0.0
        self._lock = threading.Lock()
    
    def __repr__(self) -> str:
        if self.username and self.password:
            return f"{self.proxy_type}://{self.username}:{self.password}@{self.host}:{self.port}"
        return f"{self.proxy_type}://{self.host}:{self.port}"
    
    def __str__(self) -> str:
        return f"{self.host}:{self.port} ({self.proxy_type})"
    
    def _get_proxies(self) -> Dict[str, str]:
        """Convert proxy to requests format"""
        if self.proxy_type in ("socks5", "socks4"):
            auth = ""
            if self.username and self.password:
                auth = f"{self.username}:{self.password}@"
            scheme = self.proxy_type
            proxy_url = f"{scheme}://{auth}{self.host}:{self.port}"
            return {
                "http": proxy_url,
                "https": proxy_url,
            }
        else:  # http/https
            auth = ""
            if self.username and self.password:
                auth = f"{self.username}:{self.password}@"
            proxy_url = f"http://{auth}{self.host}:{self.port}"
            return {
                "http": proxy_url,
                "https": proxy_url,
            }
    
    def check_alive(self, test_url: str = "https://api.mojang.com/users/profiles/minecraft/testuser123") -> bool:
        """Check if proxy is alive with latency measurement"""
        with self._lock:
            try:
                proxies = self._get_proxies()
                start = time.time()
                response = requests.get(test_url, proxies=proxies, timeout=6, 
                                      headers={"User-Agent": "Mozilla/5.0"})
                self.latency = time.time() - start
                if response.status_code < 500:
                    self.alive = True
                    self.success_count += 1
                    self.fail_count = max(0, self.fail_count - 1)
                    # Update score
                    if self.latency < 1.0:
                        self.score = min(100.0, self.score + 2)
                    elif self.latency < 3.0:
                        self.score = min(100.0, self.score + 1)
                    else:
                        self.score = max(50.0, self.score - 1)
                else:
                    self.alive = False
                    self.fail_count += 1
                    self.score = max(0.0, self.score - 10)
                self.last_check = time.time()
                return self.alive
            except Exception as e:
                self.alive = False
                self.fail_count += 1
                self.score = max(0.0, self.score - 15)
                self.last_check = time.time()
                self.latency = 0.0
                logger.debug(f"Proxy {self.host}:{self.port} failed: {e}")
                return False
    
    def mark_used(self):
        """Mark proxy as used"""
        self.last_used = time.time()
    
    def mark_success(self):
        """Mark successful request through this proxy"""
        self.success_count += 1
        self.score = min(100.0, self.score + 1)
    
    def mark_failure(self):
        """Mark failed request through this proxy"""
        self.fail_count += 1
        self.score = max(0.0, self.score - 5)
        if self.fail_count >= 5:
            self.alive = False
    
    def should_remove(self) -> bool:
        """Check if proxy should be auto-removed"""
        if self.fail_count >= 10:
            return True
        if self.score < 20 and self.success_count > 0:
            return True
        if not self.alive and self.fail_count >= 3:
            return True
        return False
    
    def get_info(self) -> str:
        status = "ALIVE" if self.alive else "DEAD"
        return f"{self.host}:{self.port} | {status} | Score:{self.score:.0f} | F:{self.fail_count}/S:{self.success_count} | {self.latency:.2f}s"

class ProxyManager:
    """Advanced proxy manager with scoring and rotation"""
    
    def __init__(self):
        self.proxies: List[Proxy] = []
        self._lock = threading.Lock()
        self._current_index = 0
    
    @staticmethod
    def load_from_file(filepath: str) -> List[Proxy]:
        """Load proxies from file with support for multiple formats"""
        if not os.path.exists(filepath):
            logger.warning(f"Proxy file not found: {filepath}")
            return []
        
        proxies: List[Proxy] = []
        seen = set()
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Try different formats
                    proxy = None
                    # Format: socks5://user:pass@host:port
                    if '://' in line:
                        try:
                            from urllib.parse import urlparse
                            parsed = urlparse(line)
                            proxy_type = parsed.scheme if parsed.scheme else 'http'
                            host = parsed.hostname
                            port = parsed.port
                            username = parsed.username
                            password = parsed.password
                            if host and port:
                                key = f"{host}:{port}"
                                if key not in seen:
                                    proxy = Proxy(host, port, proxy_type, username, password)
                                    seen.add(key)
                        except Exception:
                            pass
                    
                    # Format: type:host:port:user:pass or host:port:user:pass
                    if proxy is None:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            proxy_type = 'http'
                            idx = 0
                            if parts[0].lower() in ('http', 'socks4', 'socks5'):
                                proxy_type = parts[0].lower()
                                idx = 1
                            try:
                                host = parts[idx]
                                port = int(parts[idx + 1])
                                username = parts[idx + 2] if len(parts) > idx + 2 else None
                                password = parts[idx + 3] if len(parts) > idx + 3 else None
                                key = f"{host}:{port}"
                                if key not in seen and host and port > 0:
                                    proxy = Proxy(host, port, proxy_type, username, password)
                                    seen.add(key)
                            except (ValueError, IndexError) as e:
                                logger.debug(f"Invalid proxy format line {line_num}: {line} - {e}")
                    
                    if proxy:
                        proxies.append(proxy)
            
            logger.info(f"Loaded {len(proxies)} proxies from {filepath}")
            return proxies
        except IOError as e:
            logger.error(f"Failed to load proxies: {e}")
            return []
    
    def test_all(self, max_threads: int = 20) -> Dict[str, int]:
        """Test all proxies concurrently"""
        with self._lock:
            proxies = list(self.proxies)
        
        if not proxies:
            return {"alive": 0, "dead": 0, "total": 0}
        
        threads = []
        for p in proxies:
            t = threading.Thread(target=p.check_alive, daemon=True)
            t.start()
            threads.append(t)
            if len(threads) >= max_threads:
                for th in threads:
                    th.join(timeout=7)
                threads = []
        
        for th in threads:
            th.join(timeout=7)
        
        alive = sum(1 for p in self.proxies if p.alive)
        dead = len(self.proxies) - alive
        return {"alive": alive, "dead": dead, "total": len(self.proxies)}
    
    def get_best_proxy(self) -> Optional[Proxy]:
        """Get best proxy based on score and availability"""
        with self._lock:
            alive_proxies = [p for p in self.proxies if p.alive and p.score > 20]
            if not alive_proxies:
                # Fallback to any alive
                alive_proxies = [p for p in self.proxies if p.alive]
            if not alive_proxies:
                return None
            # Sort by score desc, then latency asc
            alive_proxies.sort(key=lambda x: (-x.score, x.latency))
            proxy = alive_proxies[0]
            proxy.mark_used()
            return proxy
    
    def rotate_proxy(self) -> Optional[Proxy]:
        """Round-robin rotation"""
        with self._lock:
            alive_proxies = [p for p in self.proxies if p.alive]
            if not alive_proxies:
                return None
            proxy = alive_proxies[self._current_index % len(alive_proxies)]
            self._current_index += 1
            proxy.mark_used()
            return proxy
    
    def auto_clean(self) -> int:
        """Remove bad proxies automatically"""
        with self._lock:
            before = len(self.proxies)
            self.proxies = [p for p in self.proxies if not p.should_remove()]
            removed = before - len(self.proxies)
            if removed > 0:
                logger.info(f"Auto-removed {removed} bad proxies")
            return removed
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            alive = sum(1 for p in self.proxies if p.alive)
            total = len(self.proxies)
            avg_score = sum(p.score for p in self.proxies) / total if total > 0 else 0
            return {
                "total": total,
                "alive": alive,
                "dead": total - alive,
                "avg_score": round(avg_score, 1)
            }

# Backward compatibility
def load_from_file(filepath: str) -> List[Proxy]:
    return ProxyManager.load_from_file(filepath)

def rotate(proxies: List[Proxy]) -> Proxy:
    alive = [p for p in proxies if p.alive]
    if not alive:
        return random.choice(proxies) if proxies else None
    return random.choice(alive)
