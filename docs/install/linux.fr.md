# Installation sous Linux de bureau (et macOS)

[English](linux.md) · [Svenska](linux.sv.md) · [中文](linux.zh.md) · [हिन्दी](linux.hi.md) · [Español](linux.es.md) · **Français** · [العربية](linux.ar.md) · [বাংলা](linux.bn.md) · [Português](linux.pt.md) · [Русский](linux.ru.md) · [اردو](linux.ur.md)

[Windows](windows.fr.md) · [Raspberry Pi](raspberry-pi.fr.md) · [Retour au README](../../README.fr.md)

Pour un Raspberry Pi qui démarre directement sur le chronomètre, utilisez plutôt le [guide Raspberry Pi](raspberry-pi.fr.md).
Cette page concerne un PC ou portable Linux ordinaire avec un bureau (testé sur la famille Debian/Ubuntu ; les autres
fonctionnent s'ils ont Python 3.9+).

## 1. Installer les prérequis

Debian / Ubuntu / Mint :

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libsdl2-2.0-0
```

Fedora : `sudo dnf install git python3 python3-pip SDL2`. Arch : `sudo pacman -S git python sdl2`.

macOS : installez Python 3 depuis <https://www.python.org/downloads/> (ou `brew install python`).

## 2. Télécharger le projet

```bash
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

Pas de git ? Téléchargez le ZIP depuis la page GitHub (**Code → Download ZIP**) et décompressez-le.

## 3. Installation (une seule fois)

```bash
scripts/setup_desktop.sh
```

Cela crée un environnement privé dans `.venv` et y installe le chronomètre. Si le script n'est pas exécutable, lancez-le
avec `bash scripts/setup_desktop.sh`.

## 4. Démarrer le chronomètre

```bash
scripts/start.sh
```

- Démo sans matériel de feux : `scripts/start.sh --no-serial`
- Plein écran : `scripts/start.sh -- --fullscreen`
- Interface en suédois : `scripts/start.sh -- --lang sv` (la langue se change aussi dans le menu des réglages)
- Écran public sur le second moniteur, sans commandes : `scripts/start.sh -- --profile audience --display 1`

Touches : **Espace** = le gros bouton, **P** = pause, **Esc** = arrêt d'urgence. Voir le
[README](../../README.fr.md).

## 5. Brancher les feux et la corne (facultatif)

1. Rien à faire à la main : `scripts/setup_desktop.sh` (étape 3) a déjà donné à cet ordinateur l'accès à la carte
   (groupe série plus une règle udev qui tient aussi ModemManager à l'écart ; il demande votre mot de passe une fois ;
   `--no-system` l'ignore) et `scripts/start.sh` fonctionne sans fermer la session. Si vous l'avez ignoré, lancez
   `sudo usermod -aG dialout $USER` puis reconnectez-vous.

2. Branchez la carte ESP32. Elle est trouvée automatiquement. Pour choisir le port vous-même, repérez-le avec
   `ls /dev/ttyACM* /dev/ttyUSB*` et démarrez avec `scripts/start.sh --serial-port /dev/ttyACM0`.

Le firmware de la carte est dans [`firmware/`](../../firmware/) ; pour flasher une nouvelle carte, suivez le
[guide de flashage](../flashing.md) (en anglais).

## Mise à jour

```bash
cd ~/ArcheryTimer && git pull && scripts/setup_desktop.sh
```

Les réglages sont conservés dans `~/.local/share/archerytimer` (macOS : `~/Library/Application Support/archerytimer`).

## Dépannage

| Problème | Que faire |
| --- | --- |
| `venv failed` | `sudo apt install python3-venv` puis relancez l'installation |
| Pas de fenêtre / erreur SDL | Lancez-le dans une session de bureau (pas par un simple SSH) ; installez `libsdl2-2.0-0` |
| « Permission denied » sur le port série | Étape 5 : groupe `dialout`, puis déconnexion et reconnexion |
| Pas de son sur les haut-parleurs du PC | Vérifiez le périphérique de sortie dans les réglages du son du programme ; ALSA/PulseAudio doit d'abord fonctionner pour les autres applications |
| Journaux | `~/.local/share/archerytimer/logs/` |
