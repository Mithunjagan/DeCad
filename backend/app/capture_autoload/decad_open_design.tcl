# DeCad: open the generated schematic page when DeCad launches OrCAD Capture.
# Installed by DeCad into %USERPROFILE%\cdssetup\OrCAD_Capture\tclscripts\capAutoLoad (Capture sources it
# at startup). It acts only when Capture starts in a folder holding the one-shot marker decad_open.txt
# ("<schematic> <page>"), which DeCad writes just before it launches Capture; any other launch is untouched.
namespace eval ::decadOpen {
 variable marker [file join [pwd] decad_open.txt]
 variable logfile [file join [pwd] decad_open.log]
}

proc ::decadOpen::log {msg} {
 catch {set f [open $::decadOpen::logfile a]; puts $f "[clock format [clock seconds] -format %H:%M:%S] $msg"; close $f}
}

proc ::decadOpen::try {schematic page n} {
 set design ""
 catch {set design [GetActivePMDesign]}
 if {$design eq "" || $design eq "NULL"} {
  if {$n < 90} {after 1000 [list ::decadOpen::try $schematic $page [expr {$n + 1}]]} else {::decadOpen::log "project did not open"}
  return
 }
 if {[catch {
  SelectPMItem $schematic
  SelectPMItem "$schematic/$page"
  OPage $schematic $page
  ZoomAll
 } err]} {
  ::decadOpen::log "attempt $n: $err"
  if {$n < 90} {after 1000 [list ::decadOpen::try $schematic $page [expr {$n + 1}]]}
  return
 }
 ::decadOpen::log "opened $schematic/$page"
}

if {[file exists $::decadOpen::marker]} {
 set ::decadOpen::target {SCHEMATIC1 PAGE1}
 catch {set f [open $::decadOpen::marker r]; set ::decadOpen::target [string trim [read $f]]; close $f}
 file delete -force $::decadOpen::marker
 ::decadOpen::log "Capture started for [pwd]; opening $::decadOpen::target"
 after 1500 [list ::decadOpen::try [lindex $::decadOpen::target 0] [lindex $::decadOpen::target 1] 0]
}
