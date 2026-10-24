# Update only PCB footprint properties in a saved design. Callers work on a copy.
# Usage: tclsh orcad_footprints.tcl <orDb dll> <design.dsn> <assignments.tcl>
load [lindex $argv 0] DboTclWriteBasic
proc C {s} {return [DboTclHelper_sMakeCString $s]}
proc S {c} {return [DboTclHelper_sGetConstCharPtr $c]}
source [lindex $argv 2]
set session [DboTclHelper_sCreateSession]
set st [DboState]
set design [$session GetDesignAndSchematics [C [lindex $argv 1]] $st]
if {$design eq "NULL"} {puts "ERROR cannot open design"; exit 2}
set vi [$design NewViewsIter $st $::IterDefs_SCHEMATICS]
set count 0
while {[set view [$vi NextView $st]] ne "NULL"} {
 set schematic [DboViewToDboSchematic $view]
 set pi [$schematic NewPagesIter $st]
 while {[set page [$pi NextPage $st]] ne "NULL"} {
  set ii [$page NewPartInstsIter $st]
  while {[set instance [$ii NextPartInst $st]] ne "NULL"} {
   set part [DboPartInstToDboPlacedInst $instance]
   if {$part eq "NULL"} {continue}
   set ref [C ""]; $part GetReference $ref
   set key [S $ref]
   if {[dict exists $footprints $key]} {
    $part SetPCBFootprint [C [dict get $footprints $key]]
    incr count
   }
  }
  delete_DboPagePartInstsIter $ii
  set result [$schematic SavePage $page]
  if {[$result Failed]} {puts "ERROR cannot save footprint properties"; exit 2}
 }
 delete_DboSchematicPagesIter $pi
}
set result [$session SaveDesign $design]
if {[$result Failed]} {puts "ERROR cannot save design"; exit 2}
puts "UPDATED $count"
