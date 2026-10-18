# Prints the physical pins of Capture packages: "<package>\t<pin number>\t<pin name>" per pin.
# Usage: tclsh orcad_pins.tcl <orDb dll> <library.olb> <package> [<library.olb> <package> ...]
load [lindex $argv 0] DboTclWriteBasic
proc S {c} {return [DboTclHelper_sGetConstCharPtr $c]}
set s [DboTclHelper_sCreateSession]
set st [DboState]
foreach {path name} [lrange $argv 1 end] {
 set lib [$s GetLib [DboTclHelper_sMakeCString $path] $st]
 if {$lib == "NULL"} {continue}
 set pkg [$lib GetPackage [DboTclHelper_sMakeCString $name] $st]
 if {$pkg == "NULL"} {continue}
 set di [$pkg NewDevicesIter $st]
 set dev [$di NextDevice $st]
 while {$dev != "NULL"} {
  set cell [DboTclHelper_sMakeCString]; $dev GetCellName $cell
  set part [$lib GetPart [DboTclHelper_sMakeCString "[S $cell].Normal"] $st]
  if {$part != "NULL"} {
   set it [$part NewPinsIter $st]; set i 0
   set pin [$it NextPin $st]
   while {$pin != "NULL"} {
    set num [DboTclHelper_sMakeCString]; $dev GetPinNumber $i $num
    set pname [DboTclHelper_sMakeCString]; $pin GetName $pname
    puts "$name\t[S $num]\t[S $pname]"
    incr i; set pin [$it NextPin $st]
   }
  }
  set dev [$di NextDevice $st]
 }
}
puts DONE
