# Deploy to Remote Server (ser6)
$Server = "elliot@ser6"
$LocalPath = Get-Location

Write-Host "Starting deployment to $Server..." -ForegroundColor Cyan

# 1. Prep: Clean old artifacts
if (Test-Path "deploy.tar.gz") { Remove-Item "deploy.tar.gz" }

# 2. Compress Project Files
Write-Host "Compressing project files..."
$TempDir = "deploy_temp"
if (Test-Path $TempDir) { Remove-Item $TempDir -Recurse -Force }
New-Item -ItemType Directory -Path $TempDir | Out-Null

$ItemsToCopy = @("app", "deployment", "migrations", ".env", "Dockerfile", "docker-compose.prod.yml", "requirements.txt", "wsgi.py", "celery_worker.py", "gunicorn_config.py")
foreach ($Item in $ItemsToCopy) {
    Copy-Item -Path "$LocalPath\$Item" -Destination "$TempDir" -Recurse -Force
}

New-Item -ItemType Directory -Path "$TempDir\instance" | Out-Null
Copy-Item -Path "$LocalPath\instance\scheduler.db" -Destination "$TempDir\instance\scheduler.db" -Force

Write-Host "Creating archive..."
tar -czf deploy.tar.gz -C $TempDir .
Remove-Item $TempDir -Recurse -Force

# 3. SCP Files (Archive + Setup Script)
Write-Host "Uploading files..." -ForegroundColor Yellow
# We copy the tarball AND the setup script
scp deploy.tar.gz "${LocalPath}\deployment\remote_setup.sh" "${Server}:~/"

# 4. SSH and Run Setup Script
Write-Host "Executing remote setup..." -ForegroundColor Green
$SshCmd = "chmod +x ~/remote_setup.sh && ./remote_setup.sh"
ssh $Server $SshCmd

# 5. Cleanup
Remove-Item "deploy.tar.gz"

Write-Host "Deployment Complete!" -ForegroundColor Cyan
