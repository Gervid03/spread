# Chat with a Carbon agent on the swarm VM, one line per turn:  .\scripts\chat.ps1 chat-a
# Each message is its own short SSH call, and the agent's turn runs detached on the VM, so a dropped connection loses
# nothing: type /last to see the last answer again. /quit leaves.
param([Parameter(Mandatory = $true)][string]$Name)
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$key = Join-Path $HOME ".ssh\verda_spread"
$ssh = @("-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=8", "-i", $key, "ops@34.51.182.19")
Write-Host "Chat with $Name (Gemini 4 Carbon, worktree ~/spread-wt/$Name). /last shows the last answer again, /quit leaves." -ForegroundColor Cyan
while ($true) {
    Write-Host ""
    $line = Read-Host "$Name you"
    if ($line -eq "/quit") { break }
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line -eq "/last") { ssh @ssh "sudo -u lab -H bash /home/lab/chat-turn.sh $Name --last"; continue }
    Write-Host "($Name is working; this can take a few minutes)" -ForegroundColor DarkGray
    $line | ssh @ssh "sudo -u lab -H bash /home/lab/chat-turn.sh $Name"
    if ($LASTEXITCODE -ne 0) { Write-Host "(connection dropped; the turn goes on on the VM: type /last in a minute)" -ForegroundColor Yellow }
}
