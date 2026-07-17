$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*uvicorn*app:app*" }

if ($procs) {
    foreach ($p in $procs) {
        # Arreter un processus parent peut deja avoir arrete ses enfants : on ignore
        # silencieusement l'erreur si le processus n'existe plus au moment du Stop-Process.
        if (Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue) {
            Write-Host "Arret du processus $($p.ProcessId)..."
            Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "Serveur arrete."
} else {
    Write-Host "Aucun serveur trouve."
}
