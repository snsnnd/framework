# Auto-retry flashing via both OpenOCD and pyocd until one succeeds.
$log = "D:\framework\hwtest_g431\flash_watchdog.log"
$ocd = "D:\framework\hwtest_g431\tools\xpack-openocd-0.12.0-7\bin\openocd.exe"
$py  = "$env:USERPROFILE\.local\bin\pyocd.exe"
$elf = "D:\framework\hwtest_g431\build\hwtest.elf"
$pack = "D:\STM32\Packages\Keil\STM32G4xx_DFP\2.2.0"
"watchdog v2 start $(Get-Date)" | Out-File $log -Encoding UTF8

for ($i = 1; $i -le 60; $i++) {
    $ts = Get-Date -Format 'HH:mm:ss'

    # dongle present? (pyocd list)
    $lst = & $py list 2>&1 | Out-String
    if ($lst -notmatch 'DAPLINK|CMSIS-DAP') {
        "[$ts] attempt $i : dongle not enumerated yet" | Out-File $log -Append -Encoding UTF8
        Start-Sleep -Seconds 30
        continue
    }

    # openocd attempt
    $out = & $ocd -c "adapter driver cmsis-dap" -c "cmsis-dap vid_pid 0x0d28 0x0204" `
        -c "adapter speed 300" -f target/stm32g4x.cfg `
        -c "program $elf verify reset exit" 2>&1 | Out-String
    "[$ts] attempt $i openocd: $($out -replace '\r?\n',' | ' -replace '\s+',' ')" | Out-File $log -Append -Encoding UTF8
    if ($out -match 'Verified OK') {
        "SUCCESS via openocd attempt $i" | Out-File $log -Append -Encoding UTF8; exit 0
    }

    # pyocd attempt (pack = extracted DFP dir with .pdsc)
    $out2 = & $py flash --pack $pack -t stm32g431rbtx $elf 2>&1 | Out-String
    "[$ts] attempt $i pyocd: $($out2 -replace '\r?\n',' | ' -replace '\s+',' ')" | Out-File $log -Append -Encoding UTF8
    if ($out2 -match 'Programmed|flash done|Successfully|Applied') {
        "SUCCESS via pyocd attempt $i" | Out-File $log -Append -Encoding UTF8; exit 0
    }

    Start-Sleep -Seconds 30
}
"TIMEOUT $(Get-Date)" | Out-File $log -Append -Encoding UTF8
exit 1
