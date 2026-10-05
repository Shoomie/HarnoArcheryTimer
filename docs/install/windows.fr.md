# Installation sous Windows 10/11

[English](windows.md) · [Svenska](windows.sv.md) · [中文](windows.zh.md) · [हिन्दी](windows.hi.md) · [Español](windows.es.md) · **Français** · [العربية](windows.ar.md) · [বাংলা](windows.bn.md) · [Português](windows.pt.md) · [Русский](windows.ru.md) · [اردو](windows.ur.md)

[Linux](linux.fr.md) · [Raspberry Pi](raspberry-pi.fr.md) · [Retour au README](../../README.fr.md)

Durée : environ 10 minutes. Une connexion internet n'est nécessaire que pour la première installation.

## 1. Installer Python

1. Allez sur <https://www.python.org/downloads/> et téléchargez le dernier Python 3 (3.9 ou plus récent).
2. Lancez l'installeur. **Cochez « Add python.exe to PATH »** sur le premier écran, puis cliquez sur *Install Now*.

## 2. Télécharger le projet

Au choix :

- **ZIP (le plus simple) :** sur la page GitHub, cliquez sur **Code → Download ZIP**, puis faites un clic droit sur le
  fichier et choisissez *Extraire tout*. Placez le dossier à un endroit simple, par exemple `C:\ArcheryTimer`.
- **Git :** `git clone <repository-url> C:\ArcheryTimer`

## 3. Installation (une seule fois)

Ouvrez le dossier du projet et **double-cliquez sur `scripts\setup_windows.bat`**. Il crée un environnement Python privé
dans `.venv` et installe ce dont le chronomètre a besoin. Attendez l'affichage de « Done ».

Si Windows SmartScreen signale le fichier, choisissez *Informations complémentaires → Exécuter quand même* (c'est un
simple script texte que vous pouvez lire dans le Bloc-notes).

## 4. Démarrer le chronomètre

Double-cliquez sur **`scripts\start_windows.bat`**. Une fenêtre avec le chronomètre s'ouvre.

- Pas encore de matériel de feux ? Lancez-le depuis un terminal avec `scripts\start_windows.bat --no-serial` pour une démo.
- Plein écran sur un téléviseur : `scripts\start_windows.bat -- --fullscreen`
- Interface en suédois : `scripts\start_windows.bat -- --lang sv` (la langue se change aussi dans le menu des réglages)
- Second moniteur pour le public, sans commandes : `scripts\start_windows.bat -- --profile audience --display 1`

(Pour créer un raccourci sur le bureau : clic droit sur `start_windows.bat` → *Envoyer vers → Bureau (créer un raccourci)*.)

Touches : **Espace** = le gros bouton, **P** = pause, **Esc** = arrêt d'urgence. Voir le
[README](../../README.fr.md).

## 5. Brancher les feux et la corne (facultatif)

Branchez la carte ESP32 sur un port USB. Le programme la trouve tout seul. Sinon :

1. Ouvrez *Gestionnaire de périphériques → Ports (COM et LPT)* et notez le port, par exemple `COM7`.
2. Démarrez avec `scripts\start_windows.bat --serial-port COM7`.

Certaines cartes bon marché ont besoin d'un pilote USB-série (CH340 ou CP210x) ; si aucun port COM n'apparaît, installez
le pilote du fabricant de la puce. Le firmware de la carte est dans [`firmware/`](../../firmware/) ; pour flasher une
nouvelle carte, suivez le [guide de flashage](../flashing.md) (en anglais).

## Mise à jour

Téléchargez le nouveau ZIP (ou `git pull`) et relancez `scripts\setup_windows.bat`. Vos réglages sont conservés dans
votre profil utilisateur (`%LOCALAPPDATA%\archerytimer`), pas dans le dossier du projet.

## Dépannage

| Problème | Que faire |
| --- | --- |
| « Python was not found » | Réinstallez Python en cochant *Add python.exe to PATH*, ou relancez l'installation après avoir redémarré le PC |
| La fenêtre s'ouvre puis se ferme | Lancez `scripts\start_windows.bat` depuis un terminal (`cmd`) pour voir le message d'erreur |
| L'état du matériel indique « pas de feux » | Vérifiez le câble USB (il doit transmettre des données), le port, le pilote ; voir l'étape 5 |
| Journaux | `%LOCALAPPDATA%\archerytimer\logs` (collez ce chemin dans l'Explorateur de fichiers) |
