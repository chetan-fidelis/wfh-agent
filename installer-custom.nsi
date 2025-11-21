; Custom NSIS installer script to uninstall old WFH Agent before installing Harmony
; This script is included by electron-builder

!include "MUI2.nsh"

; Uninstall old WFH Agent if present
Function .onInit
  ; Check if old WFH Agent is installed
  ReadRegStr $0 HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\wfh-agent-desktop" "UninstallString"
  
  ${If} $0 != ""
    MessageBox MB_YESNO "Old WFH Agent found. Uninstall it before installing Harmony?" IDYES UninstallOld IDNO SkipUninstall
    
    UninstallOld:
      ; Execute the uninstaller
      ExecWait '$0 /S'
      Sleep 1000
    
    SkipUninstall:
  ${EndIf}
FunctionEnd
