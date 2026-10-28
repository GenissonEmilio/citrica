param([long]$WindowHandle, [string]$FileName, [string]$FileStem)
Add-Type -AssemblyName UIAutomationClient
$elementRoot = [System.Windows.Automation.AutomationElement]::FromHandle([IntPtr]$WindowHandle)
$fileCondition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::NameProperty, $FileName)
$stemCondition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::NameProperty, $FileStem)
$nameCondition = [System.Windows.Automation.OrCondition]::new($fileCondition, $stemCondition)
$elements = $elementRoot.FindAll([System.Windows.Automation.TreeScope]::Descendants, $nameCondition)
$candidates = @()
foreach ($element in $elements) {
    try {
        $state = $element.Current
        if (($state.Name -eq $FileName -or $state.Name -eq $FileStem) -and -not $state.IsOffscreen) {
            # Hidden extensions can give a source DOCX and its previous PDF
            # output the same visible name. COM selected the exact filesystem
            # item; locate that selected UIA item rather than the first stem.
            $selection = $element.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
            if (-not $selection.Current.IsSelected) { continue }
            $rectangle = $state.BoundingRectangle
            if ($rectangle.Width -gt 5 -and $rectangle.Height -gt 5) {
                $candidates += [PSCustomObject]@{x=$rectangle.X; y=$rectangle.Y;
                    width=$rectangle.Width; height=$rectangle.Height;
                    type=$state.ControlType.ProgrammaticName}
            }
        }
    } catch { }
}
if ($candidates.Count -eq 0) { throw "O arquivo selecionado não foi localizado na interface do Explorer." }
$candidates | Sort-Object @{Expression={if ($_.type -eq 'ControlType.Text') {0} else {1}}} |
    Select-Object -First 1 | ConvertTo-Json -Compress
