# Copy the project to the Pi and install/update it (run in PowerShell on Windows).
#   .\scripts\deploy_to_pi.ps1 -Pi pi@192.168.1.50 [-Reboot]
param(
    [Parameter(Mandatory = $true)][string]$Pi,
    [switch]$Reboot
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$tar = Join-Path $env:TEMP "archerytimer.tar"
tar --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=.mypy_cache `
    --exclude=.ruff_cache --exclude=firmware -cf $tar -C $root .
scp $tar "${Pi}:/tmp/archerytimer.tar"
$cmd = "rm -rf ~/HarnoArcheryTimer && mkdir ~/HarnoArcheryTimer && tar -xf /tmp/archerytimer.tar -C ~/HarnoArcheryTimer && cd ~/HarnoArcheryTimer && sudo bash scripts/install_pi.sh"
if ($Reboot) { $cmd += " && sudo reboot" }
ssh -t $Pi $cmd
