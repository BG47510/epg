#!/usr/bin/env python3
import gzip
import lzma
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import os

# --- CONFIGURATION DES CHEMINS ---
# On définit le dossier où se trouve le script pour que les fichiers soient créés au même endroit
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNELS_FILE = os.path.join(BASE_DIR, "channels.txt") # Fichier contenant les IDs à garder
URLS_FILE = os.path.join(BASE_DIR, "urls.txt")         # Fichier contenant les URLs sources
OUTPUT_FILE = os.path.join(BASE_DIR, "filtered_epg.xml") # Nom du fichier de sortie
DAYS_AHEAD = 3 # Nombre de jours de programmes à conserver dans le futur

def indent(elem, level=0):
    """
    Ajoute des sauts de ligne et des espaces au XML pour qu'il soit lisible par un humain.
    (Fonction de 'Pretty-print' récursive)
    """
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for sub_elem in elem:
            indent(sub_elem, level + 1)
        if not sub_elem.tail or not sub_elem.tail.strip():
            sub_elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def load_list(filename):
    """Charge les données d'un fichier texte (IDs ou URLs) en ignorant les commentaires."""
    if not os.path.exists(filename):
        print(f"Erreur : Le fichier {filename} est introuvable.")
        return []
    with open(filename, "r", encoding="utf-8") as f:
        # On garde les lignes non vides qui ne commencent pas par #
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]

def get_stream(url):
    """Télécharge l'URL et retourne un flux décompressé selon l'extension."""
    headers = {'User-Agent': 'Mozilla/5.0'} # Simule un navigateur pour éviter les blocages
    resp = requests.get(url, stream=True, timeout=60, headers=headers)
    resp.raise_for_status() # Lève une erreur si le téléchargement échoue (ex: 404)
    
    low_url = url.lower()
    if low_url.endswith(".gz"):
        return gzip.GzipFile(fileobj=resp.raw) # Flux Gzip
    elif low_url.endswith(".xz"):
        return lzma.LZMAFile(resp.raw)         # Flux XZ (Rytec)
    else:
        return resp.raw                        # Flux XML brut

def parse_to_utc(date_str):
    """
    Convertit la date XMLTV (ex: 20260330150000 +0200) en objet datetime UTC.
    Cela permet de comparer les programmes venant de sources avec des fuseaux différents.
    """
    try:
        parts = date_str.split()
        time_part = parts[0][:12] # On garde YYYYMMDDHHMM (12 caractères)
        dt = datetime.strptime(time_part, "%Y%m%d%H%M")
        
        if len(parts) > 1:
            tz = parts[1] # ex: +0200
            sign = 1 if tz[0] == "+" else -1
            hours = int(tz[1:3])
            minutes = int(tz[3:5])
            # On ajuste l'heure pour obtenir le temps universel (UTC)
            return dt - timedelta(hours=sign*hours, minutes=sign*minutes)
        return dt
    except:
        return None

def filter_epg():
    """Fonction principale de filtrage et de fusion."""
    # Chargement des configurations
    target_ids = set(load_list(CHANNELS_FILE))
    urls = load_list(URLS_FILE)
    
    if not target_ids or not urls:
        print("Erreur : Les fichiers de configuration sont vides.")
        return

    # Dates de référence en UTC
    now_utc = datetime.utcnow()
    limit_utc = now_utc + timedelta(days=DAYS_AHEAD)

    # Création de la racine XML du nouveau fichier
    new_root = ET.Element("tv", {"generator-info-name": "PythonEPGFilter_UTC"})
    
    seen_channels = set()  # Pour éviter de dupliquer les balises <channel>
    seen_programs = set()  # Clé unique : (ID_chaine, Heure_UTC) pour éviter les doublons

    print("--- Démarrage du traitement ---")

    for url in urls:
        print(f"Analyse de la source : {url} ...", end=" ", flush=True)
        try:
            stream = get_stream(url)
            tree = ET.parse(stream) # Analyse le flux XML
            root = tree.getroot()

            # 1. Traitement des définitions de CHAÎNES (<channel>)
            for channel in root.findall("channel"):
                c_id = channel.get("id")
                # Si l'ID est dans notre liste et n'a pas encore été ajouté
                if c_id in target_ids and c_id not in seen_channels:
                    new_root.append(channel)
                    seen_channels.add(c_id)

            # 2. Traitement de la GRILLE HORAIRE (<programme>)
            p_added = 0
            for prog in root.findall("programme"):
                c_id = prog.get("channel")
                start_raw = prog.get("start")
                
                if c_id in target_ids and start_raw:
                    dt_utc = parse_to_utc(start_raw)
                    
                    if dt_utc:
                        # Création de la clé de dédoublonnage basée sur l'instant T réel
                        unique_key = (c_id, dt_utc)

                        if unique_key not in seen_programs:
                            # On ne garde que les programmes de -6h (pour le direct) jusqu'à la limite
                            if (now_utc - timedelta(hours=6)) <= dt_utc <= limit_utc:
                                new_root.append(prog)
                                seen_programs.add(unique_key)
                                p_added += 1
            
            print(f"OK (+{p_added} programmes uniques)")

        except Exception as e:
            print(f"ERREUR : {e}")

    # --- SAUVEGARDE ET FINALISATION ---
    if len(seen_programs) > 0:
        print("\n--- Finalisation du fichier ---")
        
        # Application de la mise en page (indentation)
        indent(new_root)
        
        # Écriture du fichier XML final
        new_tree = ET.ElementTree(new_root)
        with open(OUTPUT_FILE, "wb") as f:
            new_tree.write(f, encoding="UTF-8", xml_declaration=True)
        
        # Création de la version compressée .gz pour l'IPTV
        with open(OUTPUT_FILE, 'rb') as f_in:
            with gzip.open(OUTPUT_FILE + ".gz", 'wb') as f_out:
                f_out.writelines(f_in)
        
        print(f"Succès ! Fichier généré : {OUTPUT_FILE}.gz")
        print(f"Total : {len(seen_channels)} chaînes et {len(seen_programs)} programmes.")
    else:
        print("\nAucun programme trouvé. Vérifiez les IDs dans channels.txt.")

if __name__ == "__main__":
    filter_epg()
