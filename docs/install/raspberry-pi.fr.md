# Installation sur un Raspberry Pi (borne TV)

[English](raspberry-pi.md) · [Svenska](raspberry-pi.sv.md) · [中文](raspberry-pi.zh.md) · [हिन्दी](raspberry-pi.hi.md) · [Español](raspberry-pi.es.md) · **Français** · [العربية](raspberry-pi.ar.md) · [বাংলা](raspberry-pi.bn.md) · [Português](raspberry-pi.pt.md) · [Русский](raspberry-pi.ru.md) · [اردو](raspberry-pi.ur.md)

[Windows](windows.fr.md) · [Linux](linux.fr.md) · [Retour au README](../../README.fr.md)

Résultat : le Pi démarre directement sur le chronomètre à la télé, sans connexion au clavier. Le cœur du chronomètre
tourne comme service en arrière-plan et maintient feux et son même si le programme d'affichage redémarre.

**Cible testée :** Raspberry Pi 2 Model B, Raspberry Pi OS Lite 32 bits (Trixie), téléviseur HDMI. D'autres modèles de Pi
devraient fonctionner mais ne sont pas testés. Durée : environ 30 minutes.

> Le détail de ce que configure l'installeur : [deployment.md](../deployment.md) (en anglais).

## Ce qu'il vous faut

- Un Raspberry Pi avec son alimentation, une carte microSD (8 Go ou plus), un câble HDMI et un téléviseur ou moniteur
- Un ordinateur pour préparer la carte, et une connexion réseau pour le Pi (le câble est le plus simple) pendant l'installation
- Facultatif : la carte ESP32 feux/corne sur un port USB, un clavier USB ou une télécommande de présentation

## 1. Écrire le système sur la carte

1. Sur votre ordinateur, installez **Raspberry Pi Imager** depuis <https://www.raspberrypi.com/software/>.
2. Choisissez votre modèle de Pi, puis *Operating System → Raspberry Pi OS (other) → **Raspberry Pi OS Lite (32-bit)***.
3. Choisissez la carte SD, cliquez sur *Next*, puis *Edit settings* (personnalisation du système) et réglez :
   - un **nom d'hôte** (par exemple `archerytimer`) ainsi qu'un **nom d'utilisateur et un mot de passe** (retenez-les ;
     cet utilisateur devient l'utilisateur de la borne),
   - votre **Wi-Fi** si vous n'utilisez pas de câble, et votre fuseau horaire,
   - *Services → Enable SSH*.
4. Écrivez la carte, placez-la dans le Pi, branchez HDMI et réseau, puis mettez sous tension. Patientez quelques minutes
   pour le premier démarrage.

## 2. Se connecter

Depuis votre ordinateur (Windows 10/11 et Linux disposent de `ssh`) :

```bash
ssh <username>@archerytimer.local
```

(Si le nom n'est pas trouvé, utilisez l'adresse IP du Pi indiquée par votre box ou routeur.) Vous pouvez aussi brancher
un clavier au Pi et vous connecter sur la télé.

## 3. Télécharger le projet

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> ~/ArcheryTimer
cd ~/ArcheryTimer
```

## 4. Lancer l'installeur

```bash
sudo bash scripts/install_pi.sh
```

Cela prend plusieurs minutes. Il installe les paquets nécessaires, copie le programme dans `/opt/archerytimer`,
configure le service en arrière-plan, active la surcouche d'affichage GPU et fait en sorte que le Pi se connecte seul
sur la première console et y lance le chronomètre. Quand c'est fini, redémarrez :

```bash
sudo reboot
```

Après le redémarrage, le chronomètre apparaît tout seul sur la télé. Utilisez la souris ou le clavier (Espace = gros
bouton, Esc = arrêt d'urgence).

Options : `--no-ui` pour un boîtier feux/son sans écran, `--user NAME` pour choisir l'utilisateur de la borne. Lancez
`scripts/install_pi.sh --help` pour la liste.

## 5. Brancher les feux et la corne (facultatif)

Branchez la carte ESP32 sur un port USB du Pi. Elle est trouvée automatiquement (l'utilisateur de la borne est déjà dans
le groupe `dialout`). L'état s'affiche dans le menu matériel du programme. Pour flasher une nouvelle carte, voir le
[guide de flashage](../flashing.md) (en anglais) ; les sources du firmware sont dans [`firmware/`](../../firmware/).

## Réglages

Les options de démarrage supplémentaires se trouvent dans deux petits fichiers. Modifiez-les avec `sudo nano` :

| Fichier | Sert à | Exemple |
| --- | --- | --- |
| `/etc/archerytimer/core.env` | le cœur en arrière-plan | `CORE_ARGS="--no-audio"` |
| `/etc/archerytimer/ui.env` | l'affichage | `UI_ARGS="--lang sv --profile audience"` |

Pour appliquer : `sudo systemctl restart archerytimer-core`, et redémarrez (ou fermez la session de la console) pour
l'affichage. Pour utiliser plusieurs Pi ensemble (un leader, des suiveurs), voir [cluster.md](../cluster.md) (en anglais).

## Mise à jour

```bash
cd ~/ArcheryTimer && git pull && sudo bash scripts/install_pi.sh && sudo reboot
```

Vos réglages et les fichiers de `/etc/archerytimer` sont conservés.

**Depuis un ordinateur Windows**, sans git sur le Pi : `.\scripts\deploy_to_pi.ps1 -Pi username@archerytimer.local`
(copie le projet et lance l'installeur ; ajoutez `-Reboot` pour redémarrer ensuite).

## Obtenir un shell normal sur la télé

La borne occupe la première console du Pi. Pour travailler sur le Pi lui-même, connectez-vous en **SSH** depuis un autre
ordinateur, ou créez le fichier `~/.no-kiosk` (`touch ~/.no-kiosk`) et redémarrez pour obtenir une invite ordinaire.
Supprimez le fichier et redémarrez pour retrouver le chronomètre.

## Dépannage

| Problème | Que faire |
| --- | --- |
| Écran noir après le redémarrage | Attendez 1 à 2 minutes après la mise sous tension. Vérifiez le HDMI. Si cela persiste, connectez-vous en SSH, lancez `journalctl -u archerytimer-core -n 50` et regardez `~/.local/share/archerytimer/logs/ui.log` |
| L'écran reste noir seulement si la télé est allumée après le Pi | Ajoutez `hdmi_force_hotplug=1` à `/boot/firmware/config.txt` et redémarrez |
| L'affichage marche mais « pas de connexion au cœur » | `systemctl status archerytimer-core` ; redémarrez-le avec `sudo systemctl restart archerytimer-core` |
| Pas de feux/corne | Vérifiez que le câble USB transmet des données ; `ls /dev/ttyACM* /dev/ttyUSB*` doit afficher un périphérique |
| Vérifier l'environnement | `/opt/archerytimer/.venv/bin/python /opt/archerytimer/scripts/env_probe.py` |
| Tout supprimer | `sudo bash scripts/uninstall_pi.sh` (conserve vos réglages) |

Journaux en direct : `journalctl -u archerytimer-core -f`. Plus de détails internes : [deployment.md](../deployment.md) (en anglais).
