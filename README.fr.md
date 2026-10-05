# Archery Timer (chronomètre de tir à l'arc)

[English](README.md) · [Svenska](README.sv.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · **Français** · [العربية](README.ar.md) · [বাংলা](README.bn.md) · [Português](README.pt.md) · [Русский](README.ru.md) · [اردو](README.ur.md)

Un chronomètre de tir à l'arc open source. Il gère le temps de tir en compétition et à l'entraînement, l'affiche sur un
téléviseur ou un moniteur et pilote des feux tricolores et une corne de brume par USB. Conçu pour un petit club de tir
à l'arc et utilisé par des bénévoles : l'écran n'a qu'un seul bouton évident pour la suite et un arrêt d'urgence
toujours visible.

- Fonctionne sur **Windows 10/11**, **Linux**, **Raspberry Pi** (2B et plus, en borne TV) et macOS.
- Interface en anglais (par défaut) et en suédois.
- Le chronomètre, les feux et le son continuent de fonctionner même si l'affichage plante.
- Carte ESP32 facultative pour les feux et la corne, seconds écrans facultatifs et plusieurs appareils sur un même réseau.

> **Avant une compétition officielle :** les temps dans `config/` sont **provisoires**, ce ne sont pas des règles
> confirmées de World Archery / SBF. Vérifiez-les avec le règlement en vigueur et modifiez les fichiers TOML (les clubs
> peuvent ajouter leurs propres préréglages sans toucher au code). Le système a été testé de bout en bout sur un PC
> Windows, un PC Linux et un Raspberry Pi 2B avec des modules ESP32-C3 et WROOM-32D. Pas encore couverts : un essai
> continu de 4 heures, les cartes ESP32-S3 et les tests radio longue portée.

## Conduire une séance

1. Lancez le programme (voir Installation ci-dessous). Appuyez sur **Espace** ou sur le gros bouton : la configuration
   s'ouvre.
2. Choisissez une fiche (par exemple *Indoor 18 m*), les lignes et le nombre de volées, puis démarrez.
3. Le gros bouton indique toujours la suite : démarrer la volée, volée suivante, reprendre. **P** met en pause. **Esc**
   est l'arrêt d'urgence : feux rouges et silence, toujours en un seul appui, sans confirmation.

L'écran montre un grand feu (avec un symbole, pas seulement une couleur), le compte à rebours, la volée et la ligne,
ainsi que l'état du matériel en mots simples.

## Installation

Choisissez votre système. Chaque guide va pas à pas de zéro jusqu'au chronomètre en marche.

| Système | Guide | Version courte |
| --- | --- | --- |
| **Windows 10/11** | [docs/install/windows.fr.md](docs/install/windows.fr.md) | Installer Python, télécharger le projet, double-cliquer sur `scripts\setup_windows.bat`, puis `scripts\start_windows.bat` |
| **Linux** (et macOS) | [docs/install/linux.fr.md](docs/install/linux.fr.md) | `scripts/setup_desktop.sh`, puis `scripts/start.sh` |
| **Raspberry Pi** (borne TV) | [docs/install/raspberry-pi.fr.md](docs/install/raspberry-pi.fr.md) | Flasher Pi OS Lite, `git clone`, `sudo scripts/install_pi.sh`, redémarrer |

### Démarrage rapide (tout ordinateur, sans matériel)

1. Installez **Python 3.9 ou plus récent** ([python.org](https://www.python.org/downloads/) ; sous Linux en général
   `sudo apt install python3 python3-venv python3-pip`).
2. Téléchargez le projet : sur GitHub, cliquez sur **Code → Download ZIP** et décompressez, ou
   `git clone <repository-url>`.
3. Dans le dossier du projet, lancez une fois le script d'installation, puis le script de démarrage :

   | | Installation (une fois) | Démarrage |
   | --- | --- | --- |
   | Windows | `scripts\setup_windows.bat` | `scripts\start_windows.bat --no-serial` |
   | Linux / macOS | `scripts/setup_desktop.sh` | `scripts/start.sh --no-serial` |

   `--no-serial` signifie « aucun matériel de feux branché ». Retirez-le quand une carte ESP32 est branchée ; le
   programme la trouve tout seul.

### Commandes

| Touche | Action |
| --- | --- |
| **Espace** / Entrée | Le gros bouton : la suite logique (ouvrir la configuration, démarrer la volée, ...) |
| **P** | Pause / reprise |
| **Esc** | **Arrêt d'urgence** : feux rouges et silence, toujours en un seul appui |
| S | Arrêter la volée |
| N / Retour arrière | Phase suivante / retour (pendant 5 secondes après Arrêter ou Suivant, Retour s'affiche *Annuler*) |
| M / F1 | Menu : nouvelle séance, minuteries, réglages, état du matériel, réseau, son, quitter |

Tout fonctionne aussi à la souris. Les télécommandes de présentation et les pédales qui se comportent comme un clavier
fonctionnent également, de même que les boutons des modules ESP32. Liste complète : [docs/ui.md](docs/ui.md) (en anglais).

### Options de démarrage utiles

Ajoutez-les après le script de démarrage, les options d'affichage après `--` :

```text
scripts/start.sh --no-serial                      démo sans matériel
scripts/start.sh --serial-port COM7               choisir soi-même le port USB (Linux : /dev/ttyACM0)
scripts/start.sh -- --fullscreen --lang sv        plein écran, interface en suédois
scripts/start.sh -- --profile audience --display 1   écran public sur le second moniteur, sans commandes
```

Sous Windows, utilisez `scripts\start_windows.bat` au lieu de `scripts/start.sh`.

## Feux, corne et autres appareils

La documentation technique est en anglais. Les guides d'installation existent en 11 langues.

| Je veux... | Lire |
| --- | --- |
| Brancher des feux tricolores et une corne (carte ESP32, câblage, broches) | [docs/firmware.md](docs/firmware.md) |
| Flasher un module ESP32 (Windows, Linux, macOS ; aucun compilateur nécessaire) | [docs/flashing.md](docs/flashing.md) : `scripts\flash.bat` ou `sh scripts/flash.sh` |
| Régler la corne et les haut-parleurs, test du son | [docs/audio.md](docs/audio.md) |
| Utiliser plusieurs écrans, PC ou Pi comme un seul chronomètre (LAN ou radio) | [docs/cluster.md](docs/cluster.md) |
| Boîtiers lumineux sans fil et boutons à distance | [docs/mesh.md](docs/mesh.md) |

## Documentation

| | |
| --- | --- |
| [docs/README.md](docs/README.md) | Index de toute la documentation |
| [docs/install/](docs/install/) | Guides d'installation (11 langues) |
| [docs/ui.md](docs/ui.md) | Écrans, touches, profils d'affichage |
| [docs/protocol.md](docs/protocol.md) · [docs/ipc.md](docs/ipc.md) | Protocole série USB ; protocole du cœur vers l'affichage |
| [docs/deployment.md](docs/deployment.md) · [docs/benchmarks.md](docs/benchmarks.md) | Fonctionnement interne du Raspberry Pi ; mesures de temps et d'affichage |
| [structure.md](structure.md) | Où se trouve chaque chose dans le code source |

## Organisation du dépôt

```text
src/archerytimer/   le programme (service cœur, client d'interface, matériel, audio, IPC)
config/             séquences de temps et préréglages (TOML, provisoires)
locales/            tous les textes de l'interface, en.toml et sv.toml
assets/             police (Inter, OFL)
firmware/           firmware ESP32 (PlatformIO), images précompilées, vecteurs de test partagés
scripts/            scripts d'installation/démarrage, installeur Raspberry Pi, menu de flashage, mesures de performance
docs/               documentation
tests/  tools/      suite de tests, simulateur de réseau maillé
```

## Développement

```bash
python -m venv .venv
# Windows : .venv\Scripts\activate      Linux/macOS : source .venv/bin/activate
pip install -e ".[dev]"
pytest                          # tests (certains sont ignorés sous Windows)
ruff check . && ruff format --check .
mypy
```

Pour traduire la documentation ou l'interface, voir [CONTRIBUTING.md](CONTRIBUTING.md). Règles et architecture du
projet : [CLAUDE.md](CLAUDE.md). Mesures : [docs/benchmarks.md](docs/benchmarks.md).

## Licence

MIT (voir [LICENSE](LICENSE)) : libre d'utiliser, copier, modifier, partager et vendre, à toute fin et partout. Les
contributions sont les bienvenues sous la même licence. Les éléments tiers gardent leurs propres licences ouvertes,
listées dans [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) (par exemple la police Inter, `assets/fonts/OFL.txt`).
