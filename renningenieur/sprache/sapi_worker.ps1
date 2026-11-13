# Sprachausgabe ueber Windows SAPI. Wird von stimmen.py gestartet.
#
# Protokoll: Pro Zeile auf der Standardeingabe kommt ein Text als Base64
# (UTF-8). Nach dem Sprechen wird "OK" ausgegeben.
#
# Mit -Liste werden nur die vorhandenen Stimmen und Ausgabegeraete gezeigt.
param(
    [string]$Stimme = "",
    [string]$Geraet = "",
    [int]$Tempo = 0,
    [int]$Lautstaerke = 100,
    [switch]$Liste
)

$ErrorActionPreference = "Stop"
$sapi = New-Object -ComObject SAPI.SpVoice

if ($Liste) {
    Write-Output "Stimmen:"
    foreach ($v in $sapi.GetVoices()) {
        $sprache = $v.GetAttribute("Language")
        Write-Output ("  " + $v.GetDescription() + "  [Sprache " + $sprache + "]")
    }
    Write-Output "Ausgabegeraete:"
    foreach ($o in $sapi.GetAudioOutputs()) {
        Write-Output ("  " + $o.GetDescription())
    }
    exit 0
}

# Stimme waehlen: Namensteil aus der Konfiguration, sonst erste deutsche
# Stimme (Sprachkennung 407 = Deutsch/Deutschland, C07 = Oesterreich,
# 807 = Schweiz).
$gewaehlt = $null
foreach ($v in $sapi.GetVoices()) {
    if ($Stimme -ne "") {
        if ($v.GetDescription() -like ("*" + $Stimme + "*")) { $gewaehlt = $v; break }
    } else {
        $sprache = $v.GetAttribute("Language")
        if ($sprache -match "(^|;)(407|C07|807)(;|$)") { $gewaehlt = $v; break }
    }
}
if ($gewaehlt -ne $null) {
    $sapi.Voice = $gewaehlt
    [Console]::Error.WriteLine("Stimme: " + $gewaehlt.GetDescription())
} else {
    [Console]::Error.WriteLine("Keine passende Stimme gefunden - nehme die Windows-Standardstimme.")
}

if ($Geraet -ne "") {
    $gefunden = $false
    foreach ($o in $sapi.GetAudioOutputs()) {
        if ($o.GetDescription() -like ("*" + $Geraet + "*")) {
            $sapi.AudioOutput = $o
            $gefunden = $true
            [Console]::Error.WriteLine("Ausgabe: " + $o.GetDescription())
            break
        }
    }
    if (-not $gefunden) {
        [Console]::Error.WriteLine("Ausgabegeraet '" + $Geraet + "' nicht gefunden - nehme das Standardgeraet.")
    }
}

$sapi.Rate = [Math]::Max(-10, [Math]::Min(10, $Tempo))
$sapi.Volume = [Math]::Max(0, [Math]::Min(100, $Lautstaerke))

[Console]::Out.WriteLine("BEREIT")
[Console]::Out.Flush()

while ($true) {
    $zeile = [Console]::In.ReadLine()
    if ($zeile -eq $null) { break }
    $zeile = $zeile.Trim()
    if ($zeile -eq "") { continue }
    try {
        $text = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($zeile))
        [void]$sapi.Speak($text, 0)
        [Console]::Out.WriteLine("OK")
    } catch {
        [Console]::Out.WriteLine("FEHLER " + $_.Exception.Message)
    }
    [Console]::Out.Flush()
}
