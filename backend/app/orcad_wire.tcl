# Adds routed wires and net labels to a saved Capture design (second pass after orcad_writer.tcl).
# Usage: tclsh orcad_wire.tcl <orDb dll> <data.tcl>
# data.tcl defines: design_path, wires {{x1 y1 x2 y2 alias ax ay} ...} (alias may be empty),
# and optionally page_w page_h to enlarge the page.
load [lindex $argv 0] DboTclWriteBasic
source [lindex $argv 1]

proc C {t} {return [DboTclHelper_sMakeCString $t]}
proc P {x y} {return [DboTclHelper_sMakeCPoint [expr {int($x)}] [expr {int($y)}]]}
proc fail {msg} {puts "ERROR $msg"; exit 3}

set s [DboTclHelper_sCreateSession]
set st [DboState]
set d [$s GetDesignAndSchematics [C $design_path] $st]
if {$d == "NULL"} {fail "cannot open design"}
set sch [$d GetSchematic [C SCHEMATIC1] $st]
if {$sch == "NULL"} {fail "no SCHEMATIC1"}
set pgi [$sch NewPagesIter $st]
set pg [$pgi NextPage $st]
delete_DboSchematicPagesIter $pgi
if {$pg == "NULL"} {fail "no page"}
set font [DboTclHelper_sMakeLOGFONT [C Arial] 16 0 0 0 400 0 0 0 0 7 0 1 16]
set n 0
foreach w $wires {
 lassign $w x1 y1 x2 y2 alias ax ay
 set wire [$pg NewWireScalar $st [P $x1 $y1] [P $x2 $y2]]
 if {$wire == "NULL"} {fail "wire failed at $x1,$y1"}
 if {$alias ne ""} {
  $wire NewAlias $st [C $alias] [P $ax $ay] $font $::DboValue_NOROTATION $::DboValue_DEFAULT_OBJECT_COLOR
 }
 incr n
}
if {[info exists page_w]} {$pg SetPageSizeInfo $page_w $page_h 10 0}
# Evaluate connectivity before applying explicit source dots; page evaluation
# otherwise removes intentional two-arm source junction markers.
catch {DboTclHelper_sEvalPage $pg}
if {[info exists junctions]} {
 foreach point $junctions {
  lassign $point x y
  set wi [$pg NewWiresIter $st]
  while {[set wire [$wi NextWire $st]] ne "NULL"} {
   set a [$wire GetStartPoint $st];set b [$wire GetEndPoint $st]
   set ax [DboTclHelper_sGetCPointX $a];set ay [DboTclHelper_sGetCPointY $a]
   set bx [DboTclHelper_sGetCPointX $b];set by [DboTclHelper_sGetCPointY $b]
   if {($ax==$bx && $x==$ax && $y>=min($ay,$by) && $y<=max($ay,$by)) || ($ay==$by && $y==$ay && $x>=min($ax,$bx) && $x<=max($ax,$bx))} {
    $wire NewJunction [P $x $y]
   }
  }
  delete_DboPageWiresIter $wi
 }
}
set wi [$pg NewWiresIter $st]; set loose 0
while {[set w [$wi NextWire $st]] ne "NULL"} {if {[$w GetNet $st] eq "NULL"} {incr loose}}
if {$loose} {fail "$loose wires have no net after page evaluation; Capture would reject them"}
set r [$sch SavePage $pg]
if {[$r Code] != 0} {fail "page save failed"}
$s MarkAllLibForSave $d
set r [$s SaveDesign $d]
if {[$r Code] != 0} {fail "save failed"}
puts "WIRED $n"
