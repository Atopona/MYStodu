param(
  [string]$Gguf = "",
  [string]$Mmproj = "",
  [string]$Repo = "",
  [switch]$SkipLlama
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ToolsDir = Join-Path $Root "tools"
$LlamaDir = Join-Path $ToolsDir "llama.cpp"
$ModelDir = Join-Path $Root "models\llm"
$DownloadDir = Join-Path $Root ".tmp\llm-downloads"

New-Item -ItemType Directory -Force -Path $LlamaDir, $ModelDir, $DownloadDir | Out-Null

function Write-Step([string]$Text) {
  Write-Host "[setup_llm] $Text" -ForegroundColor Green
}

function Invoke-Download([string]$Url, [string]$Dest) {
  $headers = @{}
  if ($env:HF_TOKEN) {
    $headers["Authorization"] = "Bearer $env:HF_TOKEN"
  }
  Write-Step "downloading $Url"
  Invoke-WebRequest -Uri $Url -OutFile $Dest -Headers $headers -UseBasicParsing
}

function Save-Source([string]$Source, [string]$DestDir) {
  if (-not $Source) { return "" }
  if (Test-Path -LiteralPath $Source) {
    $dest = Join-Path $DestDir (Split-Path -Leaf $Source)
    if ((Resolve-Path -LiteralPath $Source).Path -ne (Resolve-Path -LiteralPath $dest -ErrorAction SilentlyContinue).Path) {
      Copy-Item -LiteralPath $Source -Destination $dest -Force
    }
    return $dest
  }
  if ($Source -match "^https?://") {
    $name = [System.IO.Path]::GetFileName(([Uri]$Source).AbsolutePath)
    if (-not $name) { throw "Cannot infer filename from $Source" }
    $dest = Join-Path $DestDir $name
    if (-not (Test-Path -LiteralPath $dest)) {
      Invoke-Download $Source $dest
    } else {
      Write-Step "using existing $dest"
    }
    return $dest
  }
  $candidate = Join-Path $DestDir $Source
  if (Test-Path -LiteralPath $candidate) {
    return $candidate
  }
  throw "Model source not found: $Source"
}

function Get-LatestLlamaAssetUrl() {
  Write-Step "checking latest llama.cpp release"
  $release = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest" -Headers @{ "User-Agent" = "CinematicConsoleSetup" }
  $assets = @($release.assets)
  $preferred = $assets |
    Where-Object { $_.name -match "\.zip$" -and $_.name -match "(win|windows)" -and $_.name -match "(cuda|cu[0-9])" -and $_.name -match "(x64|x86_64|amd64)" } |
    Select-Object -First 1
  if (-not $preferred) {
    $preferred = $assets |
      Where-Object { $_.name -match "\.zip$" -and $_.name -match "(win|windows)" -and $_.name -match "(x64|x86_64|amd64)" } |
      Select-Object -First 1
  }
  if (-not $preferred) {
    throw "Could not find a Windows llama.cpp zip asset in the latest release."
  }
  return $preferred.browser_download_url
}

function Install-LlamaCpp() {
  $server = Join-Path $LlamaDir "llama-server.exe"
  if (Test-Path -LiteralPath $server) {
    Write-Step "llama-server.exe already exists"
    return $server
  }
  $url = Get-LatestLlamaAssetUrl
  $zip = Join-Path $DownloadDir "llama.cpp-windows.zip"
  Invoke-Download $url $zip
  Write-Step "extracting llama.cpp"
  Expand-Archive -LiteralPath $zip -DestinationPath $LlamaDir -Force
  $found = Get-ChildItem -LiteralPath $LlamaDir -Recurse -Filter "llama-server.exe" | Select-Object -First 1
  if (-not $found) {
    throw "llama-server.exe was not found after extracting the llama.cpp package."
  }
  if ($found.FullName -ne $server) {
    Copy-Item -LiteralPath $found.FullName -Destination $server -Force
  }
  return $server
}

function Resolve-HfSelection([string]$RepoId) {
  if (-not $RepoId) {
    $RepoId = $env:CC_LLM_REPO
  }
  if (-not $RepoId) {
    $RepoId = "SulphurAI/Sulphur-2-Prompt-Enhancer-GGUF"
  }

  Write-Step "scanning Hugging Face repo $RepoId"
  $headers = @{}
  if ($env:HF_TOKEN) {
    $headers["Authorization"] = "Bearer $env:HF_TOKEN"
  }
  try {
    $model = Invoke-RestMethod -Uri "https://huggingface.co/api/models/$RepoId" -Headers $headers
  } catch {
    throw "Could not scan $RepoId. Pass exact URLs: setup_llm.bat -Gguf <url> -Mmproj <url>, or set CC_LLM_REPO."
  }
  $files = @($model.siblings | ForEach-Object { $_.rfilename }) | Where-Object { $_ -match "\.gguf$" }
  $main = $files |
    Where-Object { $_ -notmatch "mmproj" -and $_ -match "(Q4_K_M|q4_k_m|Q5_K_M|q5_k_m|f16|F16|bf16|BF16)" } |
    Select-Object -First 1
  if (-not $main) {
    $main = $files | Where-Object { $_ -notmatch "mmproj" } | Select-Object -First 1
  }
  $proj = $files | Where-Object { $_ -match "mmproj" } | Select-Object -First 1
  if (-not $main -or -not $proj) {
    throw "Repo $RepoId does not expose both a main GGUF and an mmproj GGUF. Pass exact URLs instead."
  }
  return @{
    Gguf = "https://huggingface.co/$RepoId/resolve/main/$main"
    Mmproj = "https://huggingface.co/$RepoId/resolve/main/$proj"
  }
}

if (-not $SkipLlama) {
  $llamaServer = Install-LlamaCpp
} else {
  $llamaServer = Join-Path $LlamaDir "llama-server.exe"
}

if (-not $Gguf -or -not $Mmproj) {
  $picked = Resolve-HfSelection $Repo
  if (-not $Gguf) { $Gguf = $picked.Gguf }
  if (-not $Mmproj) { $Mmproj = $picked.Mmproj }
}

$ggufPath = Save-Source $Gguf $ModelDir
$mmprojPath = Save-Source $Mmproj $ModelDir

$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $py)) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd) {
    $py = $cmd.Source
  } else {
    $cmd = Get-Command py -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source }
  }
}

if ($py -and (Test-Path -LiteralPath $py)) {
  Write-Step "writing console settings"
  $env:CC_LLAMA_SERVER = "tools\llama.cpp\llama-server.exe"
  $env:CC_LLM_GGUF = Split-Path -Leaf $ggufPath
  $env:CC_LLM_MMPROJ = Split-Path -Leaf $mmprojPath
  & $py -c "from backend import db; import os; db.update_settings({'llama_server_path': os.environ['CC_LLAMA_SERVER'], 'llm_gguf': os.environ['CC_LLM_GGUF'], 'llm_mmproj': os.environ['CC_LLM_MMPROJ'], 'llm_mode': 'managed'}); print('settings updated')"
} else {
  Write-Host "[setup_llm] Python not found; set these in Settings manually:" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "llama-server: $llamaServer"
Write-Host "GGUF:         $(Split-Path -Leaf $ggufPath)"
Write-Host "mmproj:       $(Split-Path -Leaf $mmprojPath)"
Write-Host ""
Write-Host "Open the console Settings panel and click start / restart llm if it is not already green."
