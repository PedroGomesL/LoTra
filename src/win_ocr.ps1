param(
    [string]$ImagePath
)

try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8

    Add-Type -AssemblyName System.Runtime.WindowsRuntime

    [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
    [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
    [Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType = WindowsRuntime] | Out-Null

    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.ContainsGenericParameters
    })[0]

    function Await($asyncOp, $resType) {
        $method = $asTaskGeneric.MakeGenericMethod($resType)
        $task = $method.Invoke($null, @($asyncOp))
        $task.Wait()
        return $task.Result
    }

    $swTotal = [System.Diagnostics.Stopwatch]::StartNew()

    $absPath = [System.IO.Path]::GetFullPath($ImagePath)
    $fileOp = [Windows.Storage.StorageFile]::GetFileFromPathAsync($absPath)
    $file = Await $fileOp ([Windows.Storage.StorageFile])

    $streamOp = $file.OpenAsync([Windows.Storage.FileAccessMode]::Read)
    $stream = Await $streamOp ([Windows.Storage.Streams.IRandomAccessStream])

    $decoderOp = [Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)
    $decoder = Await $decoderOp ([Windows.Graphics.Imaging.BitmapDecoder])

    $bmpOp = $decoder.GetSoftwareBitmapAsync()
    $bmp = Await $bmpOp ([Windows.Graphics.Imaging.SoftwareBitmap])

    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
    if ($null -eq $engine) {
        $langs = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
        if ($langs.Count -gt 0) {
            $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($langs[0])
        }
    }

    $swInference = [System.Diagnostics.Stopwatch]::StartNew()
    $ocrOp = $engine.RecognizeAsync($bmp)
    $ocrResult = Await $ocrOp ([Windows.Media.Ocr.OcrResult])
    $swInference.Stop()
    $swTotal.Stop()

    # Sanitiza caracteres de controle que invalidam parsers de JSON padrão
    $rawText = $ocrResult.Text
    if ($rawText) {
        $rawText = [System.Text.RegularExpressions.Regex]::Replace($rawText, "[\x00-\x08\x0B\x0C\x0E-\x1F]", " ")
    }

    $output = @{
        Text = $rawText
        InferenceMs = $swInference.Elapsed.TotalMilliseconds
        ElapsedMs = $swTotal.Elapsed.TotalMilliseconds
        Success = $true
    }
    $output | ConvertTo-Json -Compress
} catch {
    @{
        Text = ""
        InferenceMs = 0
        ElapsedMs = 0
        Success = $false
        Error = $_.Exception.Message
    } | ConvertTo-Json -Compress
}
