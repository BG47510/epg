#!/bin/bash

# Aller au répertoire du script pour éviter les erreurs de chemin
cd "$(dirname "$0")" || exit 1

# ==============================================================================
# CONFIGURATION
# ==============================================================================
CHANNELS_FILE="channels.txt"
URLS_FILE="urls.txt"
OUTPUT_FILE="filtered_epg.xml"
TEMP_DIR="./temp_epg"

# Vérification des dépendances (commandes nécessaires)
for cmd in curl xmlstarlet xz gunzip awk; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "Erreur : La commande '$cmd' est requise mais n'est pas installée."
        exit 1
    fi
done

# Vérification des fichiers d'entrée
if [[ ! -f "$CHANNELS_FILE" ]] || [[ ! -f "$URLS_FILE" ]]; then
    echo "Erreur : $CHANNELS_FILE ou $URLS_FILE introuvable."
    exit 1
fi

# Nettoyage et création du dossier temporaire
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Chargement des données (ignore les commentaires et lignes vides)
mapfile -t CHANNEL_IDS < <(grep -vE '^\s*(#|$)' "$CHANNELS_FILE")
mapfile -t URLS < <(grep -vE '^\s*(#|$)' "$URLS_FILE")

# Paramètres de filtrage temporel (Aujourd'hui à +3 jours)
NOW=$(date +%Y%m%d%H%M)
LIMIT=$(date -d "+3 days" +%Y%m%d%H%M)

# Construction du filtre XPath pour les IDs de chaînes
xpath_filter=""
for id in "${CHANNEL_IDS[@]}"; do
    xpath_filter+="@id='$id' or "
done
xpath_filter="${xpath_filter% or }"

echo "--- Étape 1 : Téléchargement et filtrage individuel ---"

count=0
for url in "${URLS[@]}"; do
    # Nettoyage de l'URL (caractères invisibles Windows)
    url=$(echo "$url" | tr -d '\r' | xargs)
    [[ -z "$url" ]] && continue
    
    count=$((count + 1))
    RAW_FILE="$TEMP_DIR/raw_$count.xml"
    echo "Source $count : $url"

    # Téléchargement avec gestion des formats (GZ, XZ, Brut)
    if [[ "$url" == *.gz ]]; then
        curl -sL --connect-timeout 15 --max-time 120 --fail "$url" | gunzip > "$RAW_FILE" 2>/dev/null
    elif [[ "$url" == *.xz ]]; then
        curl -sL --connect-timeout 15 --max-time 120 --fail "$url" | xz -d > "$RAW_FILE" 2>/dev/null
    else
        curl -sL --connect-timeout 15 --max-time 120 --fail "$url" > "$RAW_FILE" 2>/dev/null
    fi

    # Si le fichier existe, on filtre immédiatement pour économiser de la place
    if [[ -s "$RAW_FILE" ]]; then
        xmlstarlet ed \
            -d "/tv/channel[not($xpath_filter)]" \
            -d "/tv/programme[not(parent::tv/channel[@id=current()/@channel]) and not(contains('$xpath_filter', @channel))]" \
            -d "/tv/programme[substring(@stop,1,12) < '$NOW']" \
            -d "/tv/programme[substring(@start,1,12) > '$LIMIT']" \
            "$RAW_FILE" > "$TEMP_DIR/src_$count.xml" 2>/dev/null
        rm -f "$RAW_FILE"
    else
        echo "   -> Échec ou fichier vide."
    fi
done

# ==============================================================================
# Étape 2 : Fusion finale et suppression des doublons
# ==============================================================================
echo "--- Étape 2 : Fusion et dédoublonnage intelligent ---"

# 1. En-tête XML
echo '<?xml version="1.0" encoding="UTF-8"?>' > "$OUTPUT_FILE"
echo '<tv generator-info-name="CustomEPGFilter">' >> "$OUTPUT_FILE"

# 2. CHANNELS (Noms et logos des chaînes)
echo "Traitement des chaînes..."
xmlstarlet sel -t -c "/tv/channel" "$TEMP_DIR"/*.xml 2>/dev/null | \
    awk 'BEGIN { RS="</channel>"; ORS="" } 
    { 
        if (match($0, /id="([^"]+)"/, a)) { 
            id=a[1]; 
            if (!seen_chan[id]++) print $0 "</channel>\n" 
        } 
    }' >> "$OUTPUT_FILE"

# 3. PROGRAMMES (La grille horaire avec dédoublonnage strict)
echo "Traitement des programmes (Dédoublonnage)..."
xmlstarlet sel -t -c "/tv/programme" "$TEMP_DIR"/*.xml 2>/dev/null | \
    awk 'BEGIN { RS="</programme>"; ORS="" } 
    { 
        # On extrait l ID de la chaine et les 12 premiers chiffres de l heure (YYYYMMDDHHMM)
        if (match($0, /channel="([^"]+)"/, c) && match($0, /start="([0-9]{12})/, s)) {
            key = c[1] "_" s[1]
            if (!seen_prog[key]++) {
                # On aplatit les retours à la ligne internes pour un XML propre
                gsub(/\r?\n/, " ", $0)
                print $0 "</programme>\n"
            }
        }
    }' >> "$OUTPUT_FILE"

# 4. Fin du XML
echo '</tv>' >> "$OUTPUT_FILE"

# Nettoyage final
rm -rf "$TEMP_DIR"

# ==============================================================================
# Étape 3 : Finalisation
# ==============================================================================
if [ -s "$OUTPUT_FILE" ]; then
    SIZE=$(du -sh "$OUTPUT_FILE" | cut -f1)
    echo "SUCCÈS : $OUTPUT_FILE généré ($SIZE)."
    echo "Compression en cours..."
    gzip -f "$OUTPUT_FILE"
    echo "TERMINÉ : ${OUTPUT_FILE}.gz est prêt."
else
    echo "ERREUR : Le fichier final est vide. Vérifiez vos IDs dans $CHANNELS_FILE."
fi
