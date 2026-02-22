# XMLTV EPG Filter & Merger

Dernière mise à jour : [Version 1.0](https://github.com/BG47510/epg/blob/main/b02/script_xml.sh)

Ce script Bash permet de récupérer, filtrer et fusionner plusieurs sources de guides de programmes TV (EPG) au format XMLTV. Il est idéal pour alléger vos fichiers EPG en ne conservant que les chaînes qui vous intéressent et en limitant la fenêtre temporelle des programmes.

## ✨ Fonctionnalités

- **Multi-sources** : Télécharge des fichiers XML ou compressés (.gz) depuis plusieurs URLs.
- **Filtrage précis** : Ne conserve que les IDs de chaînes spécifiés dans un fichier de configuration.
- **Fenêtre temporelle** : Supprime automatiquement les programmes passés et limite les programmes futurs à 3 jours (configurable).
- **Dédoublonnage intelligent** : Évite les doublons de programmes (même chaîne, même heure) lors de la fusion de plusieurs sources.
- **Optimisation** : Génère un fichier final compressé (.xml.gz) pour économiser de la bande passante.

## 🛠️ Prérequis

Le script repose sur deux outils standards sous Linux :

- `curl` : Pour le téléchargement des sources.
- `xmlstarlet` : Pour le traitement et le filtrage des données XML.

Pour les installer sur Debian/Ubuntu :

```bash
sudo apt-get install -y xmlstarlet
```

## 🚀 Installation et Utilisation

1. Cloner le dépôt

```bash
git clone https://github.com/BG47510/epg.git cd votre-repo chmod +x script_xml.sh
```

2. Configuration

Créez deux fichiers texte dans le même répertoire que le script :

`channels.txt` : Listez les IDs des chaînes à conserver (un par ligne).

```
TF1.fr
France2.fr
M6.fr 
```

`urls.txt` : Listez les URLs de vos sources XMLTV.

```
https://exemple.com/epg_complet.xml
https://autre-source.org/guide.xml.gz 
```

3. Exécution

Lancez simplement le script :

```bash
./script_xml.sh
```

Le fichier final sera généré sous le nom `filtered_epg.xml.gz`.

## ⚙️ Détails techniques

1.Processus de filtrage

Le script utilise XPath via xmlstarlet pour effectuer les opérations suivantes en une seule passe par source :

- Suppression des chaînes (<channel>) non listées.
- Suppression des programmes (<programme>) des chaînes non listées.
- Nettoyage des programmes déjà terminés.
- Limitation aux programmes des 3 prochains jours

2.Logique de fusion

Lors de la fusion, le script identifie les doublons en créant une clé unique basée sur l'ID de la chaîne et l'heure de début du programme (channel + start), garantissant un fichier propre même si vos sources se recoupent.

## 📝 Licence

Ce projet est sous licence MIT. Libre à vous de l'utiliser et de le modifier.

