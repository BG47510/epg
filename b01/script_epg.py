import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import gzip
import shutil
import io
import lzma

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNELS_FILE = os.path.join(SCRIPT_DIR, "channels.txt")
URLS_FILE = os.path.join(SCRIPT_DIR, "urls.txt")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "epg.xml.gz")

# Chargement du mapping
ID_MAP = {}
CHANNEL_IDS = []

with open(CHANNELS_FILE, 'r') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            old_id, new_id = map(str.strip, line.split(',', 1))
            if old_id and new_id:
                ID_MAP[old_id] = new_id
                CHANNEL_IDS.append(old_id)
        except ValueError:
            print(f"Erreur de format dans la ligne : {line}.")

NOW = datetime.now().strftime("%Y%m%d%H%M")
LIMIT = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d%H%M")

print("--- Démarrage du traitement ---")

CHANNELS_FILLED = {}
count = 0
output_lines = []

with open(URLS_FILE, 'r') as f:
    URLs = [line.strip() for line in f if line.strip() and not line.startswith('#')]

for url in URLs:
    count += 1
    print(f"Source {count} : {url}")

    try:
        response = requests.get(url, timeout=10)
    except Exception as e:
        print(f"Erreur HTTP pour {url} : {e}")
        continue

    if response.status_code != 200:
        print(f"Erreur lors de la récupération de {url} (status {response.status_code}).")
        continue

    # Préparer le buffer de contenu
    content = io.BytesIO(response.content)

    # Décompression conditionnelle pour .gz et .xz
    try:
        if url.endswith('.gz'):
            with gzip.GzipFile(fileobj=content) as gz:
                content = io.BytesIO(gz.read())
        elif url.endswith('.xz'):
            content = io.BytesIO(lzma.decompress(content.getvalue()))
        else:
            content = io.BytesIO(content.getvalue())
    except Exception as e:
        print(f"Erreur de décompression pour {url} : {e}")
        continue

    try:
        tree = ET.parse(content)
        root = tree.getroot()

        ids_in_source = [channel.attrib['id'] for channel in root.findall('channel')]
        found_new_content = False

        for old_id in ids_in_source:
            new_id = ID_MAP.get(old_id)
            if new_id and new_id not in CHANNELS_FILLED:
                CHANNELS_FILLED[new_id] = True
                found_new_content = True

        if found_new_content:
            seen = {}
            # Suppression des canaux non requis
            for channel in list(root.findall('channel')):
                if all(channel.attrib['id'] != old_id for old_id in ids_in_source):
                    root.remove(channel)

            # Suppression des programmes hors limites
            for programme in list(root.findall('programme')):
                stop = programme.attrib.get('stop', '')
                start = programme.attrib.get('start', '')
                if (start and start > LIMIT) or (stop and stop < NOW):
                    root.remove(programme)

            for channel in root.findall('channel'):
                old_id = channel.attrib.get('id')
                if old_id in ID_MAP:
                    channel.attrib['id'] = ID_MAP[old_id]
                    line = ET.tostring(channel, encoding='utf-8', xml_declaration=False).decode().strip()
                    if line:
                        output_lines.append(line)

            # Écriture des programmes
            for programme in root.findall('programme'):
                old_id = programme.attrib.get('channel')
                if old_id in ID_MAP:
                    new_id = ID_MAP[old_id]
                    programme.attrib['channel'] = new_id
                    key = f"{new_id}_{programme.attrib.get('start','')}"
                    if key not in seen:
                        seen[key] = True
                        line = ET.tostring(programme, encoding='utf-8', xml_declaration=False).decode().strip()
                        if line:
                            output_lines.append(line)

    except ET.ParseError as e:
        print(f"Erreur lors du parsing de {url} : {e}")

# Écriture finale
print("Assemblage du fichier final...")

with gzip.open(OUTPUT_FILE, 'wt', encoding='utf-8') as output_file:
    output_file.write('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n')
    output_file.write('\n'.join(output_lines) + '\n')
    output_file.write('</tv>\n')

print(f"SUCCÈS : {OUTPUT_FILE} généré.")
