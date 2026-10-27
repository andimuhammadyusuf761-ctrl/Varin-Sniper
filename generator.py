"""Username generator untuk 3-char dan 4-char combos dengan priority scoring."""
import itertools
import random
import string
from typing import List, Set

ALLOWED = string.ascii_lowercase + string.digits + "_"
LOWERCASE = string.ascii_lowercase
DIGITS = string.digits

def random_combo(length: int) -> str:
    return "".join(random.choice(ALLOWED) for _ in range(length))

def enumerate_full(length: int, chars: str = LOWERCASE) -> List[str]:
    return ["".join(t) for t in itertools.product(chars, repeat=length)]

def _calculate_priority_score(name: str) -> int:
    """Calculate priority score - higher = more desirable"""
    score = 0
    length = len(name)
    
    # All same char (aaa, bbb) - highest priority
    if len(set(name)) == 1:
        score += 1000
    
    # Very few unique chars
    elif len(set(name)) == 2:
        score += 500
        # Check patterns
        if name[0] == name[1] or name[1] == name[2] or (length == 4 and (name[2] == name[3] or name[0] == name[2])):
            score += 100
    
    # Has repeated chars
    for i in range(len(name) - 1):
        if name[i] == name[i + 1]:
            score += 50
    
    # All letters (no numbers/underscore) slightly preferred
    if all(c.islower() for c in name):
        score += 30
    
    # Shorter in general same length but just in case
    # Palindromes
    if name == name[::-1]:
        score += 80
    
    # Common patterns
    if length == 3:
        # x_x style less common but check
        if name[0] != name[1] and name[1] != name[2] and name[0] != name[2]:
            if any(c in 'aeiou' for c in name):  # has vowel
                score += 20
    elif length == 4:
        if name[0:2] == name[2:4]:  # abab, aabb
            score += 150
        elif name[0] == name[1] and name[2] == name[3]:  # aabb
            score += 200
        elif name[0] == name[2] and name[1] == name[3]:  # abab
            score += 180
    
    return score

def enumerate_ordered(length: int, use_all_chars: bool = False) -> List[str]:
    """Full enumeration ordered by priority"""
    chars = LOWERCASE if not use_all_chars else ALLOWED
    names = enumerate_full(length, chars)
    # Sort by priority score desc, then alphabetically
    names.sort(key=lambda s: (-_calculate_priority_score(s), s))
    return names

def generate_random(count: int, length: int, allowed_chars: str = None) -> List[str]:
    if allowed_chars is None:
        allowed_chars = ALLOWED
    seen: Set[str] = set()
    out: List[str] = []
    max_attempts = count * 100
    attempts = 0
    while len(out) < count and attempts < max_attempts:
        name = "".join(random.choice(allowed_chars) for _ in range(length))
        if name not in seen and 3 <= len(name) <= 16:
            seen.add(name)
            out.append(name)
        attempts += 1
    return out

def generate_smart_random(count: int, length: int) -> List[str]:
    """Generate with higher chance for good patterns"""
    seen: Set[str] = set()
    out: List[str] = []
    strategies = []
    
    # Weight strategies
    if length == 3:
        strategies = [
            (lambda: random.choice(LOWERCASE)*3, 0.15),  # aaa
            (lambda: random.choice(LOWERCASE)*2 + random.choice(LOWERCASE), 0.10),  # aab
            (lambda: random.choice(LOWERCASE) + random.choice(LOWERCASE)*2, 0.10),  # abb
            (lambda: random.choice(LOWERCASE) + random.choice(LOWERCASE) + random.choice(LOWERCASE), 0.65),  # normal
        ]
    elif length == 4:
        strategies = [
            (lambda: random.choice(LOWERCASE)*2 + random.choice(LOWERCASE)*2, 0.15),  # aabb
            (lambda: random.choice(LOWERCASE)*4, 0.10),  # aaaa
            (lambda: random.choice(LOWERCASE)+random.choice(LOWERCASE)+random.choice(LOWERCASE)+random.choice(LOWERCASE), 0.75),
        ]
    
    attempts = 0
    while len(out) < count and attempts < count * 200:
        if strategies and random.random() < 0.4:
            # Pick strategy
            r = random.random()
            cum = 0
            for func, prob in strategies:
                cum += prob
                if r <= cum:
                    name = func()
                    break
            else:
                name = random_combo(length)
        else:
            name = random_combo(length)
        
        if name not in seen and all(c.isalnum() or c == '_' for c in name):
            seen.add(name)
            out.append((name, _calculate_priority_score(name)))
        attempts += 1
    
    # Sort by priority
    out.sort(key=lambda x: -x[1])
    return [n[0] for n in out]

def pattern_combo(pattern: str) -> str:
    """Generate from pattern: x=letter, d=digit, u/_=underscore, a=any"""
    out = []
    for ch in pattern.lower():
        if ch == 'x':
            out.append(random.choice(LOWERCASE))
        elif ch == 'd':
            out.append(random.choice(DIGITS))
        elif ch in ('u', '_'):
            out.append('_')
        elif ch == 'a':
            out.append(random.choice(ALLOWED))
        elif ch.isalpha():
            out.append(random.choice(LOWERCASE) if ch.islower() else ch.lower())
        elif ch.isdigit():
            out.append(ch)
        else:
            continue
    return ''.join(out)

def generate_pattern(patterns: List[str], count: int) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    valid_patterns = [p for p in patterns if p.strip()]
    if not valid_patterns:
        return out
    attempts = 0
    while len(out) < count and attempts < count * 50:
        p = random.choice(valid_patterns)
        name = pattern_combo(p)
        if name and 3 <= len(name) <= 16 and name not in seen and all(c.isalnum() or c == '_' for c in name):
            seen.add(name)
            out.append(name)
        attempts += 1
    return out

def get_pattern_examples() -> List[str]:
    return ["_dd", "x_x", "xd_", "_x_", "dd_", "xxx", "x_d", "a_a", "xx_", "__d"]

if __name__ == "__main__":
    print("Smart 3L:", generate_smart_random(10, 3))
    print("Smart 4L:", generate_smart_random(10, 4))
    print("Pattern _dd:", generate_pattern(["_dd"], 5))
    print("Full 3L ordered first 5:", enumerate_ordered(3)[:5])
