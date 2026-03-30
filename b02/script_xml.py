import gzip
import lzma
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os

# --- CONFIGURATION ---
CHANNELS_FILE = "channels.txt"  # Un ID par ligne
URLS_FILE = "urls.txt"          # Une URL par ligne (.xml, .gz ou .xz)
OUTPUT_FILE = "filtered_epg.xml"
DAYS_AHEAD = 3  # Nombre de jours de programme à conserver

def load_list(filename):
    """Charge une liste depuis un fichier en ignorant les commentaires."""
    if not os.path.exists(filename):
        print(f"Erreur : {filename} introuvable.")
        return []
    with open(filename, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_stream(url):
    """Récupère le flux de données selon l'extension du fichier."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, stream=True, timeout=60, headers=headers)
    resp.raise_for_status()
    
    if url.lower().endswith(".gz"):
        return gzip.GzipFile(fileobj=resp.raw)
    elif url.lower().endswith(".xz"):
        return lzma.LZMAFile(resp.raw)
    else:
        # Traitement direct du XML brut
        return resp.raw

def filter_epg():
    target_ids = set(load_list(CHANNELS_FILE))
    urls = load_list(URLS_FILE)
    
    if not target_ids or not urls:
        print("Erreur : Listes de chaînes ou d'URLs vides.")
        return

    # Date actuelle et limite pour le filtrage temporel
    now = datetime.now()
    limit = now + timedelta(days=DAYS_AHEAD)

    # Création de la racine du nouveau fichier XMLTV
    new_root = ET.Element("tv", {"generator-info-name": "PythonEPGFilter"})
    
    seen_channels = set()
    seen_programs = set() # Stocke des tuples (channel_id, start_time_normalized)

    print(f"--- Démarrage du filtrage ---")

    for url in urls:
        print(f"Analyse de : {url} ...", end=" ", flush=True)
        try:
            stream = get_stream(url)
            # Chargement du XML en mémoire (incrémental pour les gros fichiers)
            tree = ET.parse(stream)
            root = tree.getroot()

            # 1. Extraction des balises <channel> (Nom, Logo, etc.)
            chan_count = 0
            for channel in root.findall("channel"):
                c_id = channel.get("id")
                if c_id in target_ids and c_id not in seen_channels:
                    new_root.append(channel)
                    seen_channels.add(c_id)
                    chan_count += 1

            # 2. Extraction des balises <programme> (Grille horaire)
            prog_count = 0
            for prog in root.findall("programme"):
                c_id = prog.get("channel")
                start_raw = prog.get("start") # Format attendu : YYYYMMDDHHMMSS...
                
                if c_id in target_ids and start_raw:
                    # Normalisation : on garde YYYYMMDDHHMM (12 caractères)
                    start_norm = start_raw[:12]
                    key = (c_id, start_norm)

                    # Conversion en objet date pour le filtrage temporel
                    try:
                        prog_date = datetime.strptime(start_norm, "%Y%m%d%H%M")
                        
                        # Dédoublonnage + Filtrage 3 jours
                        if key not in seen_programs and now <= prog_date <= limit:
                            new_root.append(prog)
                            seen_programs.add(key)
                            prog_count += 1
                    except ValueError:
                        continue # Format de date invalide
            
            print(f"OK ({chan_count} ch / {prog_count} prog)")

        except Exception as e:
            print(f"ERREUR : {e}")

    # --- SAUVEGARDE ET COMPRESSION ---
    if len(seen_programs) > 0:
        print(f"--- Écriture du fichier final ---")
        
        # On trie un peu le XML pour plus de propreté (Optionnel)
        new_tree = ET.ElementTree(new_root)
        
        # Écriture du XML brut
        with open(OUTPUT_FILE, "wb") as f:
            new_tree.write(f, encoding="UTF-8", xml_declaration=True)
        
        # Compression en .gz pour l'IPTV
        with open(OUTPUT_FILE, 'rb') as f_in:
            with gzip.open(OUTPUT_FILE + '.gz', 'wb') as f_out:
                f_out.writelines(f_in)
        
        print(f"Succès ! Fichier créé : {OUTPUT_FILE}.gz")
        print(f"Total : {len(seen_channels)} chaînes et {len(seen_programs)} programmes.")
    else:
        print("Aucun programme trouvé. Vérifiez les IDs dans channels.txt.")

if __name__ == "__main__":
    filter_epg()
