# Dedicated Windows VM/CI helper. It addresses only the specified GUI process.
# Product controls are exercised through standard UI Automation, without hooks.
param(
    [Parameter(Mandatory=$true)][int]$GuiProcessId,
    [ValidateSet('dump','find','invoke','select','setvalue','toggle','focus')][string]$Operation='dump',
    [string]$Name='',
    [string]$ControlType='',
    [string]$AutomationId='',
    [string]$ClassName='',
    [string]$Value='',
    [int]$Index=0
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$scope=[System.Windows.Automation.TreeScope]::Descendants
$condition=[System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty,$GuiProcessId)
$elements=[System.Windows.Automation.AutomationElement]::RootElement.FindAll($scope,$condition)
$controls=[Collections.Generic.List[object]]::new()
foreach($element in $elements) {
    try {
        $current=$element.Current
        if($Name -and $current.Name -ne $Name) { continue }
        if($ControlType -and $current.ControlType.ProgrammaticName -ne "ControlType.$ControlType") { continue }
        # Qt exposes an objectName as the last component of its UIA path.
        # Keep exact full paths accepted, and match only a complete final
        # component when the caller supplies a public objectName.
        if($AutomationId -and $current.AutomationId -ne $AutomationId -and
           -not $current.AutomationId.EndsWith('.'+$AutomationId,[StringComparison]::Ordinal)) { continue }
        if($ClassName -and $current.ClassName -ne $ClassName) { continue }
        $controls.Add($element)
    } catch [System.Windows.Automation.ElementNotAvailableException] { continue }
}
function Describe($element) {
    $current=$element.Current
    $rectangle=$current.BoundingRectangle
    $description=[ordered]@{
        name=$current.Name; type=$current.ControlType.ProgrammaticName;
        class=$current.ClassName; automation_id=$current.AutomationId;
        enabled=$current.IsEnabled; offscreen=$current.IsOffscreen;
        x=$rectangle.X; y=$rectangle.Y; width=$rectangle.Width; height=$rectangle.Height;
        patterns=@($element.GetSupportedPatterns() | ForEach-Object { $_.ProgrammaticName })
    }
    $pattern=$null
    if($element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$pattern)) {
        $description.value=$pattern.Current.Value
    } elseif($element.TryGetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern,[ref]$pattern)) {
        $description.value=$pattern.Current.Value
    }
    if($element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern,[ref]$pattern)) {
        $description.toggle=$pattern.Current.ToggleState.ToString()
    }
    if($element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern,[ref]$pattern)) {
        $description.selected=$pattern.Current.IsSelected
    }
    return $description
}
if($Operation -eq 'dump') {
    if($controls.Count -gt 500) { throw 'Refusing an unbounded UI tree; scope the process/Name filter.' }
    $items=@(foreach($element in $controls) { Describe $element })
    ConvertTo-Json -InputObject $items -Depth 5 -Compress
    exit 0
}
if($Index -lt 0 -or $Index -ge $controls.Count) {
    throw "Expected matching control at index $Index; found $($controls.Count)."
}
$target=$controls[$Index]
if($Operation -ne 'find' -and (-not $target.Current.IsEnabled -or $target.Current.IsOffscreen)) {
    throw 'The specified control must be enabled and visible before sending input.'
}
switch($Operation) {
    'find' { }
    'invoke' {
        $pattern=$target.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern)
        $pattern.Invoke()
    }
    'select' {
        $pattern=$target.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
        $pattern.Select()
    }
    'toggle' {
        $pattern=$target.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern)
        $pattern.Toggle()
    }
    'focus' { $target.SetFocus() }
    'setvalue' {
        $pattern=$null
        if($target.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern,[ref]$pattern)) {
            $pattern.SetValue($Value)
        } else {
            $pattern=$target.GetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern)
            $number=[double]::Parse($Value,[Globalization.CultureInfo]::InvariantCulture)
            $pattern.SetValue($number)
        }
    }
}
Describe $target | ConvertTo-Json -Depth 5 -Compress
