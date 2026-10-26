param([long]$WindowHandle, [string]$FileName, [string]$FileStem)
Add-Type -AssemblyName UIAutomationClient
$elementRoot = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle)
$elements = $elementRoot.FindAll([System.Windows.Automation.TreeScope]::Descendants,
    [System.Windows.Automation.Condition]::TrueCondition)
$candidates = @()
foreach ($element in $elements) {
    try {
        $state = $element.Current
        if (($state.Name -eq $FileName -or $state.Name -eq $FileStem) -and -not $state.IsOffscreen) {
            $rectangle = $state.BoundingRectangle
            if ($rectangle.Width -gt 5 -and $rectangle.Height -gt 5) {
                $candidates += [PSCustomObject]@{x=$rectangle.X; y=$rectangle.Y;
                    width=$rectangle.Width; height=$rectangle.Height;
                    type=$state.ControlType.ProgrammaticName}
            }
        }
    } catch { }
}
if ($candidates.Count -eq 0) { throw "O arquivo de teste não foi localizado na interface do Explorer." }
$candidates | Sort-Object @{Expression={if ($_.type -eq 'ControlType.Text') {0} else {1}}} |
    Select-Object -First 1 | ConvertTo-Json -Compress
