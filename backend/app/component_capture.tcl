# Read-only Capture library adapter. No Save/New/Edit operations on source libraries.
# tclsh component_capture.tcl DLL library.olb [package]
load [lindex $argv 0] DboTclWriteBasic
proc C {s} {return [DboTclHelper_sMakeCString $s]}
proc S {s} {return [DboTclHelper_sGetConstCharPtr $s]}
proc X {p} {return [DboTclHelper_sGetCPointX $p]}
proc Y {p} {return [DboTclHelper_sGetCPointY $p]}
set session [DboTclHelper_sCreateSession]
set st [DboState]
set lib [$session GetLib [C [lindex $argv 1]] $st]
if {$lib == "NULL"} {puts "ERROR cannot open Capture library"; exit 2}
set wanted [lindex $argv 2]
set packages [$lib NewPackagesIter $st]
set pkg [$packages NextPackage $st]
while {$pkg != "NULL"} {
 set name [C ""]; $pkg GetName $name; set name [S $name]
 if {$wanted == "" || $wanted == $name} {
  set fp [C ""]; $pkg GetPCBFootprint $fp
  puts [list PACKAGE $name [S $fp]]
  if {$wanted != ""} {
   set devices [$pkg NewDevicesIter $st]; set dev [$devices NextDevice $st]; set unit 0
   while {$dev != "NULL"} {
    incr unit
    set cell [C ""]; $dev GetCellName $cell
    set part [$lib GetPart [C "[S $cell].Normal"] $st]
    if {$part != "NULL"} {
     foreach propertyName {MPN {Manufacturer Part Number} Description Datasheet {Data Sheet} Package} {
      set propertyValue [C ""]
      if {![catch {$part GetEffectivePropStringValue [C $propertyName] $propertyValue}]} {
       if {[S $propertyValue] ne ""} {puts [list PROPERTY $propertyName [S $propertyValue]]}
      }
     }
     set vectors [$part NewVectorsIter $st $::IterDefs_ALL]
     set v [$vectors NextVector $st]
     while {$v != "NULL"} {
      set type [$v GetObjectType]
      if {$type == $::DboBaseObject_LINE} {
       set line [DboVectorToDboLine $v]
       set a [$line GetStart $st]; set b [$line GetEnd $st]
       puts [list VECTOR $unit LINE [X $a] [Y $a] [X $b] [Y $b]]
      } elseif {$type == $::DboBaseObject_BOX} {
       set box [DboVectorToDboBox $v]
       set a [$box GetUpperLeft $st]; set b [$box GetLowerRight $st]
       puts [list VECTOR $unit BOX [X $a] [Y $a] [X $b] [Y $b]]
      } else {
       puts [list UNSUPPORTED_VECTOR $unit $type]
      }
      set v [$vectors NextVector $st]
     }
     delete_DboGraphicObjectVectorsIter $vectors
     set pins [$part NewPinsIter $st]; set pin [$pins NextPin $st]; set index 0
     while {$pin != "NULL"} {
      set number [C ""]; $dev GetPinNumber $index $number
      set pname [C ""]; $pin GetName $pname
      set hp [$pin GetHotSpot $st]; set sp [$pin GetStartPoint $st]
      set type [$pin GetPinType $st]
      set electrical unspecified
      foreach {constant label} {DBO_IN input DBO_OUT output IO bidirectional HIZ tri_state PAS passive POWER power_in OC open_collector OE open_emitter} {
       if {[info exists ::DboValue_$constant] && $type == [set ::DboValue_$constant]} {set electrical $label; break}
      }
      puts [list PIN $unit [S $number] [S $pname] [X $hp] [Y $hp] [X $sp] [Y $sp] $electrical $type]
      incr index; set pin [$pins NextPin $st]
     }
     delete_DboSymbolPinsIter $pins
    }
    set dev [$devices NextDevice $st]
   }
   delete_DboPackageDevicesIter $devices
  }
 }
 set pkg [$packages NextPackage $st]
}
delete_DboLibPackagesIter $packages
$session RemoveLib $lib
puts DONE
