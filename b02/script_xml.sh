#!/bin/bash

# Aller au répertoire du script
cd "$(dirname "$0")" || exit 1

# ==============================================================================
# CONFIGURATION
# ==============================================================================
CHANNELS_FILE="channels.txt"
URLS_FILE="urls.txt"

# Vérification des dépendances nécessaires
for cmd in curl xmlstarlet xz gunzip; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Erreur : La commande '$cmd' est requise mais n'est pas installée."
        exit 1
    fi
done

# Vérification des fichiers de configuration
for f in "$CHANNELS_FILE" "$URLS_FILE"; do
    if [[ ! -f "$f" ]]; then
        echo "Erreur : Le fichier $f est introuvable."
        exit 1
    fi
done

# Lecture des fichiers : ignore les lignes vides et les commentaires (#)
mapfile -t CHANNEL_IDS < <(grep -vE '^\s*(#|$)' "$CHANNELS_FILE")
mapfile -t URLS < <(grep -vE '^\s*(#|$)' "$URLS_FILE")

OUTPUT_FILE="filtered_epg.xml"
TEMP_DIR="./temp_epg"
mkdir -p "$TEMP_DIR"

# ==============================================================================
# PARAMÈTRES TEMPORELS
# ==============================================================================
NOW=$(date +%Y%m%d%H%M)
LIMIT=$(date -d "+3 days" +%Y%m%d%H%M)

# Construction des filtres XPath
xpath_channels=""
xpath_progs=""
for id in "${CHANNEL_IDS[@]}"; do
    xpath_channels+="@id='$id' or "
    xpath_progs+="@channel='$id' or "
done
xpath_channels="${xpath_channels% or }"
xpath_progs="${xpath_progs% or }"

echo "--- Démarrage du traitement ---"

# ==============================================================================
# 1. RÉCUPÉRATION ET FILTRAGE INDIVIDUEL
# ==============================================================================
count=0
for url in "${URLS[@]}"; do
    url=$(echo "$url" | tr -d '\r' | xargs)
    [[ -z "$url" ]] && continue

    count=$((count + 1))
    echo "Source $count : $url"
    
    RAW_FILE="$TEMP_DIR/raw_$count.xml"
    
    # --- MODIFICATION ICI : Gestion des formats GZ, XZ et XML brut ---
    if [[ "$url" == *.gz ]]; then
        curl -sL --connect-timeout 10 --max-time 60 --fail "$url" | gunzip > "$RAW_FILE" 2>/dev/null
    elif [[ "$url" == *.xz ]]; then
        # Décompression du format XZ
        curl -sL --connect-timeout 10 --max-time 60 --fail "$url" | xz -d > "$RAW_FILE" 2>/dev/null
    else
        curl -sL --connect-timeout 10 --max-time 60 --fail "$url" > "$RAW_FILE" 2>/dev/null
    fi

    # On vérifie si le fichier a été créé et n'est pas vide
    if [[ -s "$RAW_FILE" ]]; then
        # Traitement XML
        if ! xmlstarlet ed \
            -d "/tv/channel[not($xpath_channels)]" \
            -d "/tv/programme[not($xpath_progs)]" \
            -d "/tv/programme[substring(@stop,1,12) < '$NOW']" \
            -d "/tv/programme[substring(@start,1,12) > '$LIMIT']" \
            "$RAW_FILE" > "$TEMP_DIR/src_$count.xml" 2>/dev/null; then
            echo "Attention : Erreur de structure XML pour la source $count"
        fi
        rm -f "$RAW_FILE"
    else
        echo "Attention : Source $count injoignable ou format invalide (Timeout/404)"
    fi
done

# ==============================================================================
# 2. FUSION ET DÉDOUBLONNAGE
# ==============================================================================
echo "Fusion et suppression des doublons..."

echo '<?xml version="1.0" encoding="UTF-8"?><tv>' > "$OUTPUT_FILE"

# A. Chaînes
xmlstarlet sel -t -c "/tv/channel" "$TEMP_DIR"/*.xml 2>/dev/null | \
    awk '!x[$0]++' >> "$OUTPUT_FILE"

# B. Programmes avec dédoublonnage intelligent
xmlstarlet sel -t -c "/tv/programme" "$TEMP_DIR"/*.xml 2>/dev/null | \
    awk '
    BEGIN { RS="</programme>"; FS="<programme " }
    {
        if (match($0, /channel="([^"]+)"/, c) && match($0, /start="([^"]+)"/, s)) {
            key = c[1] s[1]
            if (!seen[key]++) {
                print $0 "</programme>"
            }
        }
    }' >> "$OUTPUT_FILE"

echo '</tv>' >> "$OUTPUT_FILE"

# ==============================================================================
# NETTOYAGE ET FINALISATION
# ==============================================================================
rm -rf "$TEMP_DIR"

if [ -s "$OUTPUT_FILE" ]; then
    SIZE=$(du -sh "$OUTPUT_FILE" | cut -f1)
    echo "SUCCÈS : Fichier $OUTPUT_FILE créé ($SIZE)."
    echo "Compression du fichier final..."
    gzip -f "$OUTPUT_FILE"
    echo "Terminé : ${OUTPUT_FILE}.gz prêt."
else
    echo "ERREUR : Le fichier final est vide."
    rm -f "$OUTPUT_FILE"
fi
