# Reopens a saved Capture design and prints its connectivity for independent verification.
# Usage: tclsh orcad_dump.tcl <orDb dll> <design.dsn>
# Output: "PART <ref> <section ref> <value> <PCB footprint>" and "PIN <ref> <pin> <net>" lines, then DONE.
load [lindex $argv 0] DboTclWriteBasic
proc S {c} {return [DboTclHelper_sGetConstCharPtr $c]}
set s [DboTclHelper_sCreateSession]
set st [DboState]
set d [$s GetDesignAndSchematics [DboTclHelper_sMakeCString [lindex $argv 1]] $st]
if {$d == "NULL"} {puts "ERROR cannot open design"; exit 2}
set vi [$d NewViewsIter $st $::IterDefs_SCHEMATICS]
set v [$vi NextView $st]
while {$v != "NULL"} {
 set sch [DboViewToDboSchematic $v]
 set pgi [$sch NewPagesIter $st]
 set pg [$pgi NextPage $st]
 while {$pg != "NULL"} {
  set ii [$pg NewPartInstsIter $st]
  set inst [$ii NextPartInst $st]
  while {$inst != "NULL"} {
   set pl [DboPartInstToDboPlacedInst $inst]
   if {$pl != "NULL"} {
    set ref [DboTclHelper_sMakeCString]; $pl GetReference $ref
    set sec [DboTclHelper_sMakeCString]; $pl GetReferenceDesignator $sec
    set val [DboTclHelper_sMakeCString]; $pl GetPartValue $val
    set fp [DboTclHelper_sMakeCString]; $pl GetPCBFootprint $fp
    puts [list PART [S $ref] [S $sec] [S $val] [S $fp]]
    set pi [$pl NewPinsIter $st]
    set pin [$pi NextPin $st]
    while {$pin != "NULL"} {
     set num [DboTclHelper_sMakeCString]; $pin GetPinNumber $num
     set net [$pin GetNet $st]
     set name ""
     if {$net != "NULL"} {set c [DboTclHelper_sMakeCString]; $net GetNetName $c; set name [S $c]}
     puts [list PIN [S $ref] [S $num] $name]
     set pin [$pi NextPin $st]
    }
    delete_DboPartInstPinsIter $pi
   }
   set inst [$ii NextPartInst $st]
  }
  delete_DboPagePartInstsIter $ii
  set pg [$pgi NextPage $st]
 }
 delete_DboSchematicPagesIter $pgi
 set v [$vi NextView $st]
}
puts DONE
