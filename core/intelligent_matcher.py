import re
import difflib
from typing import List, Dict, Any, Optional, Tuple

DISTRICT_ALIASES = {
    "asifabad": ["komarambheem", "komarambheemasifabad", "kumbheemasifabad", "asifabad", "kb asifabad"],
    "mancherial": ["mancherial", "manchiryala", "mancheriyal"],
    "peddapally": ["peddapally", "peddapalli"],
    "bhupapally": ["bhupapally", "bhupalpally", "jayashankar", "jayashankarbhupalpally", "jsbhupalpally"],
    "mulugu": ["mulugu", "mulug"],
    "adilabad": ["adilabad"],
    "nirmal": ["nirmal"],
    "nizamabad": ["nizamabad"],
    "jagitial": ["jagitial", "jagityal", "jagtial"],
    "kamareddy": ["kamareddy", "kamareddi"],
    "siddipet": ["siddipet"],
    "medak": ["medak"],
    "rajannasiricilla": ["rajanna", "sircilla", "siricilla", "rajannasircilla", "rajannasiricilla"],
    "karimnagar": ["karimnagar"],
    "warangal": ["warangal", "warangalurban", "warangalrural"],
    "hanumakonda": ["hanumakonda", "hanamkonda"],
    "mahabubabad": ["mahabubabad", "mahbubabad"],
    "khammam": ["khammam"],
    "kothagudem": ["kothagudem", "bhadradri", "bhadradrikothagudem"],
    "nalgonda": ["nalgonda"],
    "yadadribhuvanagiri": ["yadadri", "bhuvanagiri", "bhongir", "yadadribhongir", "yadadribhuvanagiri"],
    "suryapet": ["suryapet", "suryapeta"],
    "janagaon": ["janagaon", "jangaon"],
    "rangareddy": ["rangareddy", "rangareddi", "rr district", "k.v.ranga reddy"],
    "medchalmalkajgiri": ["medchal", "malkajgiri", "medchalmalkajgiri"],
    "vikarabad": ["vikarabad"],
    "sangareddy": ["sangareddy", "sangareddi"],
    "mahabubnagar": ["mahabubnagar", "mahbubnagar", "palamuru"],
    "narayanapet": ["narayanapet", "narayanpet"],
    "wanaparthy": ["wanaparthy", "vanaparthy", "wanaparthi", "vanaparthi"],
    "nagarkurnool": ["nagarkurnool", "nagarkurnul"],
    "jogulambagadwal": ["gadwal", "jogulamba", "jogulambagadwal"]
}

NOISE_WORDS = {
    "mandal", "mdl", "m", "village", "vill", "vlg", "v", "dist", "district",
    "dt", "gp", "gram", "panchayat", "revenue", "rev", "r", "u", "rural",
    "urban", "bk", "kd", "kalan", "khurd", "buzurg", "proper", "thanda", "tanda",
    "majra", "h/o", "ho", "shivar", "forest", "rf", "div", "division"
}

def clean_text(text: str) -> str:
    """Normalize text by removing punctuation, parenthetical remarks, and common noise words."""
    if not text:
        return ""
    s = str(text).lower().strip()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[\/\-\._,;:|]", " ", s)
    tokens = s.split()
    tokens = [t for t in tokens if t not in NOISE_WORDS]
    return " ".join(tokens)

def phonetic_key(text: str) -> str:
    """Standardize Telugu English transliterations."""
    s = clean_text(text)
    s = re.sub(r"[^a-z]", "", s)
    s = s.replace("w", "v")
    s = s.replace("ee", "i")
    s = s.replace("oo", "u")
    s = s.replace("ou", "au")
    s = s.replace("th", "t")
    s = s.replace("dh", "d")
    s = s.replace("bh", "b")
    s = s.replace("kh", "k")
    s = s.replace("gh", "g")
    s = s.replace("ph", "p")
    s = s.replace("ch", "c")
    s = s.replace("sh", "s")
    s = s.replace("zh", "j")
    s = re.sub(r"(.)\1+", r"\1", s)
    if s.endswith("pally") or s.endswith("palli") or s.endswith("pali"):
        s = s[:-5] + "pal"
    elif s.endswith("puram") or s.endswith("poor") or s.endswith("pur"):
        s = s[:-4] + "pur"
    elif s.endswith("guda") or s.endswith("gudem"):
        s = s[:-4] + "gud"
    return s

def match_district_name(raw_name: str, standard_districts: List[str]) -> Optional[str]:
    """Intelligently matches a raw district name against the 32 official district names."""
    if not raw_name:
        return None
    raw_clean = re.sub(r"[^a-z]", "", str(raw_name).lower())
    
    for std in standard_districts:
        std_clean = re.sub(r"[^a-z]", "", std.lower())
        if raw_clean == std_clean:
            return std
        aliases = DISTRICT_ALIASES.get(std_clean, [])
        for alias in aliases:
            if alias in raw_clean or raw_clean in alias:
                return std
                
    matches = difflib.get_close_matches(raw_name, standard_districts, n=1, cutoff=0.55)
    return matches[0] if matches else None

def calculate_name_similarity(name1: str, name2: str) -> float:
    s1, s2 = str(name1).strip().lower(), str(name2).strip().lower()
    if s1 == s2:
        return 1.0
        
    c1, c2 = clean_text(s1), clean_text(s2)
    if c1 and c1 == c2:
        return 0.98
        
    pk1, pk2 = phonetic_key(s1), phonetic_key(s2)
    if pk1 and pk1 == pk2:
        return 0.95
        
    t1, t2 = set(c1.split()), set(c2.split())
    if t1 and t2 and (t1.issubset(t2) or t2.issubset(t1)):
        return 0.90
        
    sm_clean = difflib.SequenceMatcher(None, c1, c2).ratio()
    sm_phonetic = difflib.SequenceMatcher(None, pk1, pk2).ratio() if pk1 and pk2 else 0.0
    
    return max(sm_clean, sm_phonetic)
