# Capture serial console output from the DAPLink CDC port into a log file.
# Usage: pwsh -File capture_serial.ps1 -Port COM5 -Baud 115200 -Out capture.log -Seconds 25
param(
    [string]$Port = "COM5",
    [int]$Baud = 115200,
    [string]$Out = "capture.log",
    [int]$Seconds = 25
)

$ErrorActionPreference = "Stop"
try {
    $sp = New-Object System.IO.Ports.SerialPort $Port, $Baud, 'None', 8, 'One'
    $sp.ReadTimeout = 200
    $sp.Open()
} catch {
    Write-Output "PORT-OPEN-FAILED: $($_.Exception.Message)"
    exit 1
}

Write-Output "CAPTURE-START port=$Port baud=$Baud seconds=$Seconds"
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$log = New-Object System.Collections.Generic.List[string]
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
    try {
        $line = $sp.ReadLine()
        $log.Add($line)
        Write-Output $line
    } catch [TimeoutException] {
    } catch {
        break
    }
}
$sp.Close()
$log | Set-Content -Encoding UTF8 $Out
Write-Output "CAPTURE-DONE lines=$($log.Count) out=$Out"
