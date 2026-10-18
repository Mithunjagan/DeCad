# Lists every package of the given Capture libraries, one tab-separated line each: library path, package, sections, PCB footprint.
# Usage: tclsh orcad_index.tcl <orDb dll> <output.tsv> <library.olb> ...
load [lindex $argv 0] DboTclWriteBasic
proc S {c} {return [DboTclHelper_sGetConstCharPtr $c]}
set s [DboTclHelper_sCreateSession]
set st [DboState]
set out [open [lindex $argv 1] w]
fconfigure $out -encoding utf-8
foreach f [lrange $argv 2 end] {
 set lib [$s GetLib [DboTclHelper_sMakeCString $f] $st]
 if {$lib == "NULL"} {continue}
 set pi [$lib NewPackagesIter $st]
 set p [$pi NextPackage $st]
 while {$p != "NULL"} {
  set name [DboTclHelper_sMakeCString]; $p GetName $name
  set di [$p NewDevicesIter $st]; set n 0
  while {[$di NextDevice $st] != "NULL"} {incr n}
  delete_DboPackageDevicesIter $di
  set fp [DboTclHelper_sMakeCString]; $p GetPCBFootprint $fp
  puts $out "$f\t[S $name]\t$n\t[S $fp]"
  set p [$pi NextPackage $st]
 }
 delete_DboLibPackagesIter $pi
 $s RemoveLib $lib
}
close $out
