<#
.SYNOPSIS
    Script de automação de compilação do LoTra para Windows Standalone (.exe).
.DESCRIPTION
    Invoca o compilador Python build_windows.py, garantindo ambiente,
    empacotamento de assets e testes pós-compilação.
#>

param(
    [ValidateSet("onefile", "onedir")]
    [string]$Mode = "onefile",
    [switch]$NoVerify
)

$ErrorActionPreference = "Stop"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host "   Iniciando Compilador LoTra para Windows (.exe)                       " -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

$python = "python"
try {
    & $python --version
} catch {
    Write-Error "Python não encontrado no PATH do sistema. Instale o Python 3.10+ para prosseguir."
    exit 1
}

# Verifica se PyInstaller está instalado
$hasPyinstaller = & $python -m pip list | Select-String "pyinstaller"
if (-not $hasPyinstaller) {
    Write-Host "[INFO] Instalando PyInstaller..." -ForegroundColor Yellow
    & $python -m pip install pyinstaller
}

$buildArgs = @("build_windows.py", "--mode", $Mode)
if ($NoVerify) {
    $buildArgs += "--no-verify"
}

Write-Host "[INFO] Executando build_windows.py..." -ForegroundColor Green
& $python @buildArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[SUCESSO] LoTra compilado com sucesso!" -ForegroundColor Green
    Write-Host "Executável disponível em: $scriptDir\dist\LoTra.exe" -ForegroundColor Green
} else {
    Write-Error "Falha na compilação do LoTra (Exit code: $LASTEXITCODE)"
}
