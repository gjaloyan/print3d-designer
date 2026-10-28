param([string]$Video, [string]$OutDir, [int]$Count = 12)
# Extract evenly spaced frames from a video with the built-in Windows.Media.Editing API.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [type]$type) {
    $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result
}
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Editing.MediaComposition, Windows.Media.Editing, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Editing.MediaClip, Windows.Media.Editing, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.ImageStream, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Video)) ([Windows.Storage.StorageFile])
$clip = Await ([Windows.Media.Editing.MediaClip]::CreateFromFileAsync($file)) ([Windows.Media.Editing.MediaClip])
$comp = New-Object Windows.Media.Editing.MediaComposition
try { $comp.Clips.Append($clip) } catch { [System.Collections.Generic.ICollection[Windows.Media.Editing.MediaClip]].GetMethod("Add").Invoke($comp.Clips, @($clip)) }
$dur = $clip.OriginalDuration.TotalSeconds
"duration {0:N1} s" -f $dur
New-Item -ItemType Directory -Force $OutDir | Out-Null
for ($i = 0; $i -lt $Count; $i++) {
    $t = [TimeSpan]::FromSeconds(($dur * ($i + 0.5)) / $Count)
    $img = Await ($comp.GetThumbnailAsync($t, 1600, 0, [Windows.Media.Editing.VideoFramePrecision]::NearestFrame)) ([Windows.Graphics.Imaging.ImageStream])
    $src = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($img)
    $path = Join-Path $OutDir ("frame_{0:D2}_{1:N0}s.jpg" -f $i, $t.TotalSeconds)
    $dst = [System.IO.File]::Create($path); $src.CopyTo($dst); $dst.Close(); $src.Close()
    $path
}
