#Requires -Version 5.1
<#
.SYNOPSIS
Read-only comparison of a USB disk's image-sized prefix against a local image.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Image,

    [Parameter(Mandatory = $true)]
    [ValidateRange(0, 65535)]
    [int]$DiskNumber
)

$ErrorActionPreference = 'Stop'

function Get-PrefixSha256 {
    param(
        [System.IO.Stream]$Stream,
        [long]$Length
    )
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        $buffer = New-Object byte[] (4 * 1024 * 1024)
        $remaining = $Length
        while ($remaining -gt 0) {
            $count = [int][Math]::Min($buffer.Length, $remaining)
            $read = $Stream.Read($buffer, 0, $count)
            if ($read -eq 0) {
                throw "Unexpected end of input with $remaining bytes remaining."
            }
            $null = $hasher.TransformBlock($buffer, 0, $read, $buffer, 0)
            $remaining -= $read
        }
        $null = $hasher.TransformFinalBlock([byte[]]@(), 0, 0)
        return ([BitConverter]::ToString($hasher.Hash)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $hasher.Dispose()
    }
}

$imageFile = Get-Item -LiteralPath $Image
if ($imageFile -isnot [System.IO.FileInfo] -or $imageFile.Length -le 0) {
    throw 'Image must be an existing nonempty regular file.'
}
if (($imageFile.Length % 512) -ne 0) {
    throw 'The image length must be a multiple of the disk sector size (512 bytes).'
}
$disk = Get-Disk -Number $DiskNumber
if ($disk.BusType -ne 'USB' -or $disk.IsBoot -or $disk.IsSystem) {
    throw 'Refusing any disk that is not USB or contains the running boot/system.'
}
if ($disk.Size -lt $imageFile.Length) {
    throw 'The USB disk is smaller than the image.'
}
$device = "\\.\PhysicalDrive$DiskNumber"
Write-Host "Reading USB disk $DiskNumber ($($disk.FriendlyName)); no data will be written."
Write-Host "Comparing exactly $($imageFile.Length) bytes from offset zero."
$source = $null
$usb = $null
try {
    $source = [System.IO.File]::Open(
        $imageFile.FullName, [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read
    )
    $usb = [System.IO.File]::Open(
        $device, [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite
    )
    $imageHash = Get-PrefixSha256 -Stream $source -Length $imageFile.Length
    $usbHash = Get-PrefixSha256 -Stream $usb -Length $imageFile.Length
    [pscustomobject]@{
        DiskNumber = $DiskNumber
        ComparedBytes = $imageFile.Length
        ImageSha256 = $imageHash
        UsbPrefixSha256 = $usbHash
        Match = ($imageHash -eq $usbHash)
    }
    if ($imageHash -ne $usbHash) {
        throw 'USB contents do not match the image. Do not boot this copy.'
    }
}
finally {
    if ($null -ne $usb) { $usb.Dispose() }
    if ($null -ne $source) { $source.Dispose() }
}
