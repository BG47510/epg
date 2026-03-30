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

def filter_epg():
    target_ids = set(load_list(CHANNELS_FILE))
    urls = load_list(URLS_FILE)
    
    if not target_ids or not urls:
        print("Listes vides. Vérifiez channels.txt et urls.txt.")
        return

    now = datetime.now()
    limit = now + timedelta(days=DAYS_AHEAD)

    new_root = ET.Element("tv", {"generator-info-name": "PythonEPGFilter"})
    
    seen_channels = set()
    seen_programs = set() # Contiendra la clé unique (id_chaine, heure_debut_courte)

    print(f"--- Démarrage du filtrage ---")

    for url in urls:
        print(f"Traitement : {url} ...", end=" ", flush=True)
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
                    # NORMALISATION CRITIQUE :
                    # On ne prend que les 12 premiers caractères (YYYYMMDDHHMM)
                    # On ignore les secondes et le fuseau horaire (+0200)
                    start_key = start_raw[:12]
                    
                    # Clé unique composée de l'ID de la chaîne + Heure de début courte
                    unique_key = (c_id, start_key)

                    if unique_key not in seen_programs:
                        try:
                            # Filtrage temporel (optionnel mais recommandé)
                            prog_date = datetime.strptime(start_key, "%Y%m%d%H%M")
                            if now - timedelta(hours=2) <= prog_date <= limit:
                                new_root.append(prog)
                                seen_programs.add(unique_key)
                                p_added += 1
                        except ValueError:
                            continue
            print(f"OK (+{p_added} programmes)")

        except Exception as e:
            print(f"ERREUR : {e}")

    # Sauvegarde
    if seen_programs:
        new_tree = ET.ElementTree(new_root)
        with open(OUTPUT_FILE, "wb") as f:
            new_tree.write(f, encoding="UTF-8", xml_declaration=True)
        
        # Compression GZ
        with open(OUTPUT_FILE, 'rb') as f_in:
            with gzip.open(OUTPUT_FILE + ".gz", 'wb') as f_out:
                f_out.writelines(f_in)
        print(f"Succès : {OUTPUT_FILE}.gz créé.")
    else:
        print("Aucun programme trouvé.")

if __name__ == "__main__":
    filter_epg()
