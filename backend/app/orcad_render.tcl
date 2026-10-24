# Reopens a saved Capture design and prints its drawing for the in-app preview.
# Usage: tclsh orcad_render.tcl <orDb dll> <design.dsn>
# Output (Tcl lists, page coordinates are Capture units of 1/100 inch):
#   PAGE <name> <width> <height>
#   PART <ref> <value> <x> <y> <rotation> <mirror> <base ref>   followed by its symbol vectors in symbol coordinates:
#   V LINE x1 y1 x2 y2 | V BOX x1 y1 x2 y2 | V ELLIPSE x1 y1 x2 y2 | V ARC x1 y1 x2 y2 sx sy ex ey | V POLY closed x y x y ...
#   PIN <ref> <number> <name> <hotspot x> <hotspot y> <start x> <start y> <dot> <clock>
#   WIRE x1 y1 x2 y2 | ALIAS <name> x y | GLOBAL <name> x y
load [lindex $argv 0] DboTclWriteBasic
proc S {c} {return [DboTclHelper_sGetConstCharPtr $c]}
proc X {p} {return [DboTclHelper_sGetCPointX $p]}
proc Y {p} {return [DboTclHelper_sGetCPointY $p]}
proc R {r} {
 set a [DboTclHelper_sGetCRectTopLeft $r]; set b [DboTclHelper_sGetCRectBottomRight $r]
 return [list [X $a] [Y $a] [X $b] [Y $b]]
}
set s [DboTclHelper_sCreateSession]
set st [DboState]
set library_mode [expr {[lindex $argv 1] eq "--library"}]
if {!$library_mode} {
 set d [$s GetDesignAndSchematics [DboTclHelper_sMakeCString [lindex $argv 1]] $st]
 if {$d == "NULL"} {puts "ERROR cannot open design"; exit 2}
}

proc points {iter} {
 set out {}
 set pt [DboTclHelper_sMakeCPoint 0 0]
 for {set i 0} {$i < 2000} {incr i} {
  set r [$iter Next $pt]
  if {[$r Code] != 0} {break}
  lappend out [X $pt] [Y $pt]
 }
 return $out
}

proc vectors {part} {
 global st
 set vi [$part NewVectorsIter $st $::IterDefs_ALL]
 set v [$vi NextVector $st]
 while {$v != "NULL"} {
  set t [$v GetObjectType]
  if {$t == $::DboBaseObject_LINE} {
   set l [DboVectorToDboLine $v]
   puts [list V LINE {*}[list [X [$l GetStart $st]] [Y [$l GetStart $st]] [X [$l GetEnd $st]] [Y [$l GetEnd $st]]]]
  } elseif {$t == $::DboBaseObject_BOX} {
   set b [DboVectorToDboBox $v]
   set a [$b GetUpperLeft $st]; set c [$b GetLowerRight $st]
   puts [list V BOX [X $a] [Y $a] [X $c] [Y $c]]
  } elseif {$t == $::DboBaseObject_ELLIPSE} {
   puts [list V ELLIPSE {*}[R [[DboVectorToDboEllipse $v] GetBoundingBox]]]
  } elseif {$t == $::DboBaseObject_ARC} {
   set a [DboVectorToDboArc $v]
   puts [list V ARC {*}[R [$a GetBoundingBox]] [X [$a GetStart $st]] [Y [$a GetStart $st]] [X [$a GetEnd $st]] [Y [$a GetEnd $st]]]
  } elseif {$t == $::DboBaseObject_POLYGON} {
   puts [list V POLY 1 {*}[points [[DboVectorToDboPolygon $v] NewPointsIter $st]]]
  } elseif {$t == $::DboBaseObject_POLYLINE} {
   puts [list V POLY 0 {*}[points [[DboVectorToDboPolyline $v] NewPointsIter $st]]]
  } elseif {$t == $::DboBaseObject_BEZIER} {
   puts [list V POLY 0 {*}[points [[DboVectorToDboBezier $v] NewPointsIter $st]]]
  }
  set v [$vi NextVector $st]
 }
}

if {$library_mode} {
 foreach {path package} [lrange $argv 2 end] {
  set lib [$s GetLib [DboTclHelper_sMakeCString $path] $st]
  if {$lib eq "NULL"} {continue}
  set pkg [$lib GetPackage [DboTclHelper_sMakeCString $package] $st]
  if {$pkg eq "NULL"} {continue}
  set di [$pkg NewDevicesIter $st];set dev [$di NextDevice $st];set section 0
  while {$dev ne "NULL"} {
   set cell [DboTclHelper_sMakeCString];$dev GetCellName $cell
   set part [$lib GetPart [DboTclHelper_sMakeCString "[S $cell].Normal"] $st]
   if {$part ne "NULL"} {
    puts [list SYMBOL $path $package $section]
    vectors $part
    set pi [$part NewPinsIter $st];set pin [$pi NextPin $st];set index 0
    while {$pin ne "NULL"} {
     set number [DboTclHelper_sMakeCString];$dev GetPinNumber $index $number
     set name [DboTclHelper_sMakeCString];$pin GetName $name
     set hs [$pin GetHotSpot $st];set so [$pin GetStartPoint $st]
     puts [list SYMBOLPIN [S $number] [S $name] [X $hs] [Y $hs] [X $so] [Y $so]]
     incr index;set pin [$pi NextPin $st]
    }
    catch {delete_DboSymbolPinsIter $pi}
   }
   incr section;set dev [$di NextDevice $st]
  }
  delete_DboPackageDevicesIter $di
 }
 puts DONE;exit 0
}
set vi [$d NewViewsIter $st $::IterDefs_SCHEMATICS]
set view [$vi NextView $st]
while {$view != "NULL"} {
 set sch [DboViewToDboSchematic $view]
 set pgi [$sch NewPagesIter $st]
 set pg [$pgi NextPage $st]
 while {$pg != "NULL"} {
  set n [DboTclHelper_sMakeCString]; $pg GetName $n
  puts [list PAGE [S $n] [$pg GetPageWidth] [$pg GetPageHeight]]
  set ii [$pg NewPartInstsIter $st]
  set inst [$ii NextPartInst $st]
  while {$inst != "NULL"} {
   set pl [DboPartInstToDboPlacedInst $inst]
   if {$pl != "NULL"} {
    set ref [DboTclHelper_sMakeCString]; $pl GetReferenceDesignator $ref
    set val [DboTclHelper_sMakeCString]; $pl GetPartValue $val
    set loc [$pl GetLocation $st]
    set base [DboTclHelper_sMakeCString]; $pl GetReference $base
    puts [list PART [S $ref] [S $val] [X $loc] [Y $loc] [$pl GetRotation $st] [$pl GetMirror $st] [S $base]]
    set displayValue [$pl GetDisplayProp [DboTclHelper_sMakeCString Value] $st]
    if {$displayValue ne "NULL"} {puts [list DISPLAY Value [S $val]]}
    set part [$pl GetPart $st]
    if {$part != "NULL"} {catch {vectors $part}}
    set pi [$pl NewPinsIter $st]
    set pin [$pi NextPin $st]
    while {$pin != "NULL"} {
     set num [DboTclHelper_sMakeCString]; $pin GetPinNumber $num
     set nm [DboTclHelper_sMakeCString]; $pin GetPinName $nm
     set hs [$pin GetOffsetHotSpot $st]; set so [$pin GetOffsetStartPoint $st]
     set dot 0; set clk 0
     catch {set dot [$pin GetIsDot $st]}; catch {set clk [$pin GetIsClock $st]}
     puts [list PIN [S $ref] [S $num] [S $nm] [X $hs] [Y $hs] [X $so] [Y $so] $dot $clk]
     set pin [$pi NextPin $st]
    }
    delete_DboPartInstPinsIter $pi
   }
   set inst [$ii NextPartInst $st]
  }
  delete_DboPagePartInstsIter $ii
  set wi [$pg NewWiresIter $st]
  set w [$wi NextWire $st]
  while {$w != "NULL"} {
   set a [$w GetStartPoint $st]; set b [$w GetEndPoint $st]
   puts [list WIRE [X $a] [Y $a] [X $b] [Y $b]]
   set ji [$w NewJunctionsIter $st]
   while {[set junction [$ji NextJunction $st]] ne "NULL"} {
    puts [list JUNCTION [X $junction] [Y $junction]]
   }
   delete_DboWireJunctionsIter $ji
   set ai [$w NewAliasesIter $st]
   set al [$ai NextAlias $st]
   while {$al != "NULL"} {
    set an [DboTclHelper_sMakeCString]; $al GetName $an
    set p [$al GetLocation $st]
    puts [list ALIAS [S $an] [X $p] [Y $p]]
    set al [$ai NextAlias $st]
   }
   delete_DboWireAliasesIter $ai
   set w [$wi NextWire $st]
  }
  delete_DboPageWiresIter $wi
  set gi [$pg NewGlobalsIter $st]
  set g [$gi NextGlobal $st]
  while {$g != "NULL"} {
   set gn [DboTclHelper_sMakeCString]; $g GetName $gn
   set p [$g GetLocation $st]
   puts [list GLOBAL [S $gn] [X $p] [Y $p]]
   set g [$gi NextGlobal $st]
  }
  delete_DboPageGlobalsIter $gi
  set pg [$pgi NextPage $st]
 }
 delete_DboSchematicPagesIter $pgi
 set view [$vi NextView $st]
}
puts DONE
