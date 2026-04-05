# AWS配置前の軽量クリーニング用 PowerShell
# 実行場所: リポジトリ直下

Write-Host 'Cleaning __pycache__ and .pyc files...'
Get-ChildItem -Path . -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem -Path . -Recurse -File -Include '*.pyc' | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host 'Removing known backup file if exists...'
Get-ChildItem -Path . -Recurse -File | Where-Object { $_.Name -like 'legacy_runtime -*.py' } | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host 'Done.'
