#!/bin/bash

# Aller au répertoire du script
cd "$(dirname "$0")" || exit 1

# ==============================================================================
# CONFIGURATION
# ==============================================================================
CHANNELS_FILE="channels.txt"
URLS_FILE="urls.txt"

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
    # On utilise des variables pour éviter les problèmes d'injection XML
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
    # On nettoie l'URL au cas où il resterait des espaces invisibles
    url=$(echo "$url" | tr -d '\r' | xargs)
    [[ -z "$url" ]] && continue

    count=$((count + 1))
    echo "Source $count : $url"
    
    RAW_FILE="$TEMP_DIR/raw_$count.xml"
    
    # Téléchargement avec timeout (10s connexion, 30s total)
    # -sL : silencieux + suit les redirections
    # --fail : ne produit rien en cas d'erreur HTTP (404, 500, etc.)
    if [[ "$url" == *.gz ]]; then
        curl -sL --connect-timeout 10 --max-time 30 --fail "$url" | gunzip > "$RAW_FILE" 2>/dev/null
    else
        curl -sL --connect-timeout 10 --max-time 30 --fail "$url" > "$RAW_FILE" 2>/dev/null
    fi

    # On vérifie si le fichier a été créé et n'est pas vide
    if [[ -s "$RAW_FILE" ]]; then
        # Traitement XML seulement si le téléchargement a réussi
        if ! xmlstarlet ed \
            -d "/tv/channel[not($xpath_channels)]" \
            -d "/tv/programme[not($xpath_progs)]" \
            -d "/tv/programme[substring(@stop,1,12) < '$NOW']" \
            -d "/tv/programme[substring(@start,1,12) > '$LIMIT']" \
            "$RAW_FILE" > "$TEMP_DIR/src_$count.xml" 2>/dev/null; then
            echo "Attention : Erreur de structure XML pour la source $count"
        fi
        # Nettoyage du fichier brut après traitement
        rm -f "$RAW_FILE"
    else
        echo "Attention : Source $count injoignable ou vide (Timeout/404)"
    fi
done

# ==============================================================================
# 2. FUSION ET DÉDOUBLONNAGE
# ==============================================================================
echo "Fusion et suppression des doublons..."

# Création du fichier final avec l'en-tête XMLTV
echo '<?xml version="1.0" encoding="UTF-8"?><tv>' > "$OUTPUT_FILE"

# A. On garde les définitions de chaînes (une seule fois par ID)
xmlstarlet sel -t -c "/tv/channel" "$TEMP_DIR"/*.xml | \
    awk '!x[$0]++' >> "$OUTPUT_FILE"

# B. On traite les programmes avec dédoublonnage intelligent
# On définit un "doublon" comme : même @channel ET même @start
xmlstarlet sel -t -c "/tv/programme" "$TEMP_DIR"/*.xml | \
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
# NETTOYAGE
# ==============================================================================
rm -rf "$TEMP_DIR"

if [ -s "$OUTPUT_FILE" ]; then
    SIZE=$(du -sh "$OUTPUT_FILE" | cut -f1)
    echo "SUCCÈS : Fichier $OUTPUT_FILE créé ($SIZE)."
else
    echo "ERREUR : Le fichier est vide."
fi

echo "Compression du fichier final..."
gzip -f "$OUTPUT_FILE"
echo "Succès : ${OUTPUT_FILE}.gz a été généré."
