#!/usr/bin/env python3
import gzip
import lzma
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os

# --- CONFIGURATION DYNAMIQUE DES CHEMINS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNELS_FILE = os.path.join(BASE_DIR, "channels.txt")
URLS_FILE = os.path.join(BASE_DIR, "urls.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "filtered_epg.xml")
DAYS_AHEAD = 3

def indent(elem, level=0):
    """Fonction pour ajouter des retours à la ligne et des espaces (Pretty-print)."""
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def load_list(filename):
    if not os.path.exists(filename):
        print(f"Erreur : {filename} introuvable.")
        return []
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_stream(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, stream=True, timeout=60, headers=headers)
    resp.raise_for_status()
    if url.lower().endswith(".gz"):
        return gzip.GzipFile(fileobj=resp.raw)
    elif url.lower().endswith(".xz"):
        return lzma.LZMAFile(resp.raw)
    else:
        return resp.raw

def parse_to_utc(date_str):
    try:
        parts = date_str.split()
        time_part = parts[0][:12]
        dt = datetime.strptime(time_part, "%Y%m%d%H%M")
        if len(parts) > 1:
            tz = parts[1]
            sign = 1 if tz[0] == "+" else -1
            hours = int(tz[1:3])
            minutes = int(tz[3:5])
            return dt - timedelta(hours=sign*hours, minutes=sign*minutes)
        return dt
    except:
        return None

def filter_epg():
    target_ids = set(load_list(CHANNELS_FILE))
    urls = load_list(URLS_FILE)
    
    if not target_ids or not urls:
        print("Erreur : Configuration vide.")
        return

    now_utc = datetime.utcnow()
    limit_utc = now_utc + timedelta(days=DAYS_AHEAD)
    new_root = ET.Element("tv", {"generator-info-name": "PythonEPGFilter_UTC"})
    
    seen_channels = set()
    seen_programs = set()

    print("--- Démarrage du filtrage ---")

    for url in urls:
        print(f"Analyse : {url} ...", end=" ", flush=True)
        try:
            stream = get_stream(url)
            tree = ET.parse(stream)
            root = tree.getroot()

            # 1. CHANNELS
            for channel in root.findall("channel"):
                c_id = channel.get("id")
                if c_id in target_ids and c_id not in seen_channels:
                    new_root.append(channel)
                    seen_channels.add(c_id)

            # 2. PROGRAMMES
            p_added = 0
            for prog in root.findall("programme"):
                c_id = prog.get("channel")
                start_raw = prog.get("start")
                if c_id in target_ids and start_raw:
                    dt_utc = parse_to_utc(start_raw)
                    if dt_utc:
                        unique_key = (c_id, dt_utc)
                        if unique_key not in seen_programs:
                            if (now_utc - timedelta(hours=6)) <= dt_utc <= limit_utc:
                                new_root.append(prog)
                                seen_programs.add(unique_key)
                                p_added += 1
            print(f"OK (+{p_added})")
        except Exception as e:
            print(f"ERREUR : {e}")

    # --- SAUVEGARDE AVEC INDENTATION ---
    if len(seen_programs) > 0:
        # On applique l'indentation à l'arbre complet
        indent(new_root)
        
        new_tree = ET.ElementTree(new_root)
        with open(OUTPUT_FILE, "wb") as f:
            new_tree.write(f, encoding="UTF-8", xml_declaration=True)
        
        with open(OUTPUT_FILE, 'rb') as f_in:
            with gzip.open(OUTPUT_FILE + ".gz", 'wb') as f_out:
                f_out.writelines(f_in)
        
        print(f"\nSuccès : {OUTPUT_FILE}.gz créé avec mise en page propre.")
    else:
        print("\nAucun programme trouvé.")

if __name__ == "__main__":
    filter_epg()
