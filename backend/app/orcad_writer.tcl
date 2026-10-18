# Builds a native OrCAD Capture design through Capture's own database API (orDb_Dll_Tcl64).
# Usage: tclsh orcad_writer.tcl <orDb dll> <data.tcl>
# data.tcl defines: design_path, components {{ref value olb package {pin net ...} footprint x y} ...}
# (footprint may be empty: the part keeps its library default; x y empty: grid placement).
# Each used package section is placed; every connected pin gets a short wire stub carrying a net alias.
load [lindex $argv 0] DboTclWriteBasic
source [lindex $argv 1]

proc C {t} {return [DboTclHelper_sMakeCString $t]}
proc S {c} {return [DboTclHelper_sGetConstCharPtr $c]}
proc P {x y} {return [DboTclHelper_sMakeCPoint [expr {int($x)}] [expr {int($y)}]]}
proc fail {msg} {puts "ERROR $msg"; exit 3}

set s [DboTclHelper_sCreateSession]
set st [DboState]
set d [$s CreateDesign $st [C $design_path] [C SCHEMATIC1]]
if {$d == "NULL" || [$st Code] != 0} {fail "cannot create design"}
set sch [$d GetSchematic [C SCHEMATIC1] $st]
set pg [$sch NewPage $st [C PAGE1]]
if {$pg == "NULL"} {fail "cannot create page"}
set font [DboTclHelper_sMakeLOGFONT]
array set libs {}

proc lib_for {path} {
 global s st libs
 if {![info exists libs($path)]} {
  set lib [$s GetLib [C $path] $st]
  if {$lib == "NULL"} {fail "library not found: $path"}
  set libs($path) $lib
 }
 return $libs($path)
}

# Physical pin numbers of one package section (device).
proc device_pins {lib dev} {
 global st
 set cell [DboTclHelper_sMakeCString]; $dev GetCellName $cell
 set part [$lib GetPart [C "[S $cell].Normal"] $st]
 if {$part == "NULL"} {return [list NULL {}]}
 set it [$part NewPinsIter $st]; set n 0
 while {[$it NextPin $st] != "NULL"} {incr n}
 set pins {}
 for {set i 0} {$i < $n} {incr i} {
  set num [DboTclHelper_sMakeCString]; $dev GetPinNumber $i $num; lappend pins [S $num]
 }
 return [list $part $pins]
}

# Parts with no installed Capture package get a generated symbol in a design-local library:
# a rectangular body with the pins the source uses, laid out like a DIP (1..n/2 left, rest right).
proc make_symbol {libpath pkgname prefix pins} {
 global s st
 if {[file exists $libpath]} {set lib [$s GetLib [C $libpath] $st]} else {set lib [$s CreateLib [C $libpath] $st]}
 if {$lib == "NULL"} {fail "cannot create library $libpath"}
 set pkg [$lib NewPackage [C $pkgname] $st]
 if {$pkg == "NULL" || [$st Failed]} {fail "cannot create package $pkgname"}
 $pkg SetReferenceTemplate [C $prefix]
 set cell [$lib NewCell [C $pkgname] $st]
 set part [$lib NewPart [C "$pkgname.Normal"] $st]
 if {$part == "NULL" || [$st Failed]} {fail "cannot create part $pkgname"}
 $cell AddPart $part
 set n [llength $pins]
 set left [expr {($n + 1) / 2}]; set right [expr {$n - $left}]
 set rows [expr {max($left, $right, 1)}]
 set longest 1; foreach p $pins {set longest [expr {max($longest, [string length $p])}]}
 set w [expr {max(60, int(ceil((40 + 12 * $longest) / 10.0)) * 10)}]
 set h [expr {($rows + 1) * 10}]
 $part SetBoundingBox [DboTclHelper_sMakeCRect -30 0 [expr {$w + 30}] $h]
 $part SetReference [C $prefix]
 $part SetPartValue [C $pkgname]
 $part SetCellPtr $cell
 $part SetPackagePtr $pkg
 $part NewBox $st [P 0 0] [P $w $h]
 set dev [$pkg NewDevice [C ""] 0 $cell $st]
 if {$dev == "NULL" || [$st Failed]} {fail "cannot create device for $pkgname"}
 for {set i 0} {$i < $n} {incr i} {
  set num [lindex $pins $i]
  if {$i < $left} {
   set yy [expr {($i + 1) * 10}]; set p0 [P 0 $yy]; set hp [P -30 $yy]
  } else {
   # right side counts upward from the bottom, as on a DIP package
   set yy [expr {($right - ($i - $left)) * 10}]; set p0 [P $w $yy]; set hp [P [expr {$w + 30}] $yy]
  }
  set pin [$part NewSymbolPinScalar $st [C $num] $::DboValue_IO $p0 $hp 1 $i]
  if {$pin == "NULL" || [$st Failed]} {fail "cannot create pin $num on $pkgname"}
  $pin SetIsLong 1
  $dev NewPinNumber [C $num] [DboTclHelper_sMakeInt $i]
 }
 $lib SavePackageAll $pkg
 set r [$s SaveLib $lib]
 if {[$r Failed]} {fail "cannot save library $libpath"}
 puts "GENERATED $pkgname [llength $pins] pins"
}
if {[info exists generate]} {
 foreach g $generate {lassign $g glib gpkg gprefix gpins; make_symbol $glib $gpkg $gprefix $gpins}
}

# Placement: a part with a source position (tx ty, page units) goes there, moved to the nearest free
# spot when its pins, stubs and labels would overlap a part already placed; parts without one fill a grid.
set x 200; set y 200; set rowh 0; set maxw 0; set maxh 0
set width_limit [expr {max(3000, int(sqrt([llength $components]) * 700))}]
set placed {}; set items {}; set pending {}
set source_mode [info exists source_width]
if {$source_mode} {set width_limit [expr {$source_width - 300}]}
set bottom_strip 0
# Row layout (layout "rows"): tx is the part's row on the source sheet; parts are packed left to right in
# source order with even gaps that leave channels for the wires, rows stacked top to bottom.
set rowmode [expr {[info exists layout] && $layout eq "rows"}]
set wiring [expr {[info exists nostubs] && $nostubs}]
set gapx 300; set gapy 260; set margin 300; set wrapw 7000
set cur_row ""; set cx $margin; set rowtop $margin; set rowbottom $margin
set offsets {}
for {set i -30} {$i <= 30} {incr i} {for {set j -30} {$j <= 30} {incr j} {lappend offsets [list [expr {hypot($i * 1.0, $j * 1.0)}] [expr {$i * 50}] [expr {$j * 50}]]}}
set offsets [lsort -real -index 0 $offsets]
proc pin_extent {inst} {
 global st
 set minx 1e9; set maxx -1e9; set miny 1e9; set maxy -1e9
 set pi [$inst NewPinsIter $st]
 while {[set pin [$pi NextPin $st]] ne "NULL"} {
  set hs [$pin GetOffsetHotSpot $st]
  set hx [DboTclHelper_sGetCPointX $hs]; set hy [DboTclHelper_sGetCPointY $hs]
  set minx [expr {min($minx,$hx)}]; set maxx [expr {max($maxx,$hx)}]
  set miny [expr {min($miny,$hy)}]; set maxy [expr {max($maxy,$hy)}]
 }
 delete_DboPartInstPinsIter $pi
 if {$minx > $maxx} {set minx 0; set maxx 0; set miny 0; set maxy 0}
 return [list $minx $miny $maxx $maxy]
}
proc move_inst {inst dx dy} {
 global st
 if {$dx == 0 && $dy == 0} {return}
 set loc [$inst GetLocation $st]
 $inst SetLocation [P [expr {[DboTclHelper_sGetCPointX $loc] + $dx}] [expr {[DboTclHelper_sGetCPointY $loc] + $dy}]]
}
# Compaction (compact 1): keep the source arrangement but close the empty space. Parts slide left, then
# up, each stopping a channel's width from the parts beside it in that direction; a part never passes a
# neighbour it faces, so left/right and above/below order is kept and no two keep-out boxes overlap.
proc compact_pass {items axis gap margin} {
 # items: {inst box} with box {x0 y0 x1 y1}; axis 0 slides left, 1 slides up. Returns the moved items.
 set lo $axis; set hi [expr {$axis + 2}]; set olo [expr {1 - $axis}]; set ohi [expr {3 - $axis}]
 set done {}
 foreach it [lsort -real -index [list 1 $lo] $items] {
  lassign $it inst box
  set to $margin
  foreach d $done {
   set b [lindex $d 1]
   # facing: the two boxes share some extent across the sliding direction (plus half a channel)
   if {[lindex $b $olo] < [lindex $box $ohi] + $gap / 2 && [lindex $box $olo] < [lindex $b $ohi] + $gap / 2} {
    set to [expr {max($to, [lindex $b $hi] + $gap)}]
   }
  }
  set shift [expr {int(round(($to - [lindex $box $lo]) / 10.0)) * 10}]
  if {$shift > 0} {set shift 0}           ;# compaction never pushes a part away from the origin
  if {$axis == 0} {move_inst $inst $shift 0} else {move_inst $inst 0 $shift}
  set nb $box
  lset nb $lo [expr {[lindex $box $lo] + $shift}]; lset nb $hi [expr {[lindex $box $hi] + $shift}]
  lappend done [list $inst $nb]
 }
 return $done
}
proc overlaps {r} {
 global placed
 lassign $r a b c d
 if {$a < 20 || $b < 20} {return 1}
 foreach q $placed {lassign $q e f g h; if {$a < $g && $e < $c && $b < $h && $f < $d} {return 1}}
 return 0
}
foreach comp $components {
 lassign $comp ref value olb pkgname pinnets footprint tx ty
 set lib [lib_for $olb]
 set pkg [$lib GetPackage [C $pkgname] $st]
 if {$pkg == "NULL"} {fail "package $pkgname not in $olb ($ref)"}
 array unset want; array set want $pinnets
 # Choose the package sections that carry the pins this component uses.
 set sections {}
 set di [$pkg NewDevicesIter $st]; set dev [$di NextDevice $st]
 while {$dev != "NULL"} {
  lassign [device_pins $lib $dev] part pins
  set hit 0; foreach p $pins {if {[info exists want($p)]} {set hit 1}}
  if {$hit} {lappend sections [list $dev $part]}
  set dev [$di NextDevice $st]
 }
 delete_DboPackageDevicesIter $di
 if {[llength $sections] == 0} {
  # Unconnected component: still place its first section.
  set dev [$pkg GetDevice 0 $st]; lassign [device_pins $lib $dev] part pins; lappend sections [list $dev $part]
 }
 foreach sec $sections {
  lassign $sec dev part
  set positioned [expr {$tx ne "" && !$rowmode}]
  if {$rowmode} {
   if {$tx ne $cur_row} {
    if {$cur_row ne ""} {set rowtop [expr {$rowbottom + $gapy}]}
    set cur_row $tx; set cx $margin
   } elseif {$cx > $wrapw} {
    set rowtop [expr {$rowbottom + $gapy}]; set cx $margin
   }
   set px $cx; set py $rowtop
  } elseif {$positioned} {set px $tx; set py $ty} else {
   if {$source_mode && !$bottom_strip} {
    if {[info exists compact] && $compact} {
     # compacted: start right of the sheet in one row; the left/up passes slide them into free space
     set x [expr {$source_width + 300}]; set y $margin; set rowh 0; set bottom_strip 1; set width_limit 1000000000
    } else {
     set x $margin; set y [expr {max($maxh + 300, $source_height - 300)}]; set rowh 0; set bottom_strip 1
    }
   }
   set px $x; set py $y
  }
  set inst [$pg NewPlacedInst $st [C $ref] [C $pkgname] $part $dev [P $px $py]]
  if {$inst == "NULL" || [$st Code] != 0} {fail "cannot place $ref ($pkgname)"}
  $inst SetReference [C $ref]
  if {$value ne ""} {$inst SetPartValue [C $value]}
  if {$footprint ne ""} {$inst SetPCBFootprint [C $footprint]}
  # Keep-out box: pins plus room for the 30-unit stubs and their net labels.
  lassign [pin_extent $inst] minx miny maxx maxy
  if {$positioned} {
   # Source positions describe the body's centre, not the library's instance origin.
   set dx [expr {int(round(($tx - ($minx + $maxx) / 2.0) / 10.0)) * 10}]
   set dy [expr {int(round(($ty - ($miny + $maxy) / 2.0) / 10.0)) * 10}]
   set px [expr {$px + $dx}]; set py [expr {$py + $dy}]
   $inst SetLocation [P $px $py]
   lassign [pin_extent $inst] minx miny maxx maxy
  }
  set box [list [expr {$minx - 120}] [expr {$miny - 50}] [expr {$maxx + 120}] [expr {$maxy + 50}]]
  if {$rowmode} {
   set dx [expr {int(round(($cx - [lindex $box 0]) / 10.0)) * 10}]; set dy [expr {int(round(($rowtop - [lindex $box 1]) / 10.0)) * 10}]
   if {$dx != 0 || $dy != 0} {
    $inst SetLocation [P [expr {$px + $dx}] [expr {$py + $dy}]]
    lassign [pin_extent $inst] minx miny maxx maxy
    set box [list [expr {$minx - 120}] [expr {$miny - 50}] [expr {$maxx + 120}] [expr {$maxy + 50}]]
   }
   set cx [expr {[lindex $box 2] + $gapx}]; set rowbottom [expr {max($rowbottom, [lindex $box 3])}]
  }
  if {$positioned} {
   set found 0
   foreach o $offsets {
    lassign $o _ dx dy
    set r [list [expr {[lindex $box 0] + $dx}] [expr {[lindex $box 1] + $dy}] [expr {[lindex $box 2] + $dx}] [expr {[lindex $box 3] + $dy}]]
    if {![overlaps $r]} {set found 1; break}
   }
   if {!$found} {
    # Exhausting the local search must never silently place an overlapping part.
    set dx [expr {max(0, int(ceil((20 - [lindex $box 0]) / 10.0)) * 10)}]
    set dy [expr {int(ceil(($maxh + 100 - [lindex $box 1]) / 10.0)) * 10}]
    set r [list [expr {[lindex $box 0] + $dx}] [expr {[lindex $box 1] + $dy}] [expr {[lindex $box 2] + $dx}] [expr {[lindex $box 3] + $dy}]]
   }
   if {$dx != 0 || $dy != 0} {
    $inst SetLocation [P [expr {$px + $dx}] [expr {$py + $dy}]]
    lassign [pin_extent $inst] minx miny maxx maxy
   }
   set box $r
  }
  lappend placed $box
  lappend items [list $inst $box]
  lappend pending [list $inst $ref $pinnets]   ;# stubs are drawn once every part has its final place
  set maxw [expr {max($maxw, [lindex $box 2])}]; set maxh [expr {max($maxh, [lindex $box 3])}]
  if {!$positioned && !$rowmode} {
   set cw [expr {$maxx - $minx + 300}]; set chh [expr {$maxy - $miny + 200}]
   set rowh [expr {max($rowh,$chh)}]
   set x [expr {$x + $cw}]
   if {$x > $width_limit} {set x 200; set y [expr {$y + $rowh}]; set rowh 0}
  }
 }
}
set maxh [expr {max($maxh, $y + $rowh)}]
set compacted [expr {[info exists compact] && $compact && !$rowmode && [llength $items] > 1}]
if {$compacted} {
 # Channels between keep-out boxes (which already hold stubs and labels): room for routed wires.
 set cgx [expr {[info exists compact_gapx] ? $compact_gapx : 150}]; set cgy [expr {[info exists compact_gapy] ? $compact_gapy : 120}]
 foreach round {1 2} {                  ;# a second round fills holes the first one opened
  set items [compact_pass $items 0 $cgx $margin]
  set items [compact_pass $items 1 $cgy $margin]
 }
 set maxw 0; set maxh 0
 foreach it $items {set b [lindex $it 1]; set maxw [expr {max($maxw, [lindex $b 2])}]; set maxh [expr {max($maxh, [lindex $b 3])}]}
}
foreach p $pending {
 lassign $p inst ref pinnets
 if {$wiring} {break}          ;# wires and labels are added by orcad_wire.tcl after routing
 array unset want; array set want $pinnets
 set pi [$inst NewPinsIter $st]; set pin [$pi NextPin $st]; set stubs {}
 while {$pin != "NULL"} {
  set num [DboTclHelper_sMakeCString]; $pin GetPinNumber $num; set num [S $num]
  set hs [$pin GetOffsetHotSpot $st]; set so [$pin GetOffsetStartPoint $st]
  set hx [DboTclHelper_sGetCPointX $hs]; set hy [DboTclHelper_sGetCPointY $hs]
  if {[info exists want($num)]} {
   lappend stubs [list $num $hx $hy [expr {$hx - [DboTclHelper_sGetCPointX $so]}] [expr {$hy - [DboTclHelper_sGetCPointY $so]}]]
  }
  set pin [$pi NextPin $st]
 }
 delete_DboPartInstPinsIter $pi
 foreach stub $stubs {
  lassign $stub num hx hy dx dy
  set len [expr {max(abs($dx),abs($dy))}]; if {$len == 0} {set dx -1; set dy 0; set len 1}
  set ex [expr {$hx + 30*$dx/$len}]; set ey [expr {$hy + 30*$dy/$len}]
  set w [$pg NewWireScalar $st [P $hx $hy] [P $ex $ey]]
  if {$w == "NULL"} {fail "wire failed $ref.$num"}
  $w NewAlias $st [C $want($num)] [P $ex $ey] $font $::DboValue_NOROTATION $::DboValue_DEFAULT_OBJECT_COLOR
  puts "STUB $ref $num $want($num)"
 }
}
set pw [expr {(int(max($maxw, 1000) / 100) + 3) * 100}]
set ph [expr {(int(max($maxh, 800) / 100) + 3) * 100}]
if {$source_mode && !$compacted} {
 set pw [expr {max($pw, $source_width)}]; set ph [expr {max($ph, $source_height)}]
 if {$pw * 1.0 / $ph < $source_aspect} {
  set pw [expr {int(ceil($ph * $source_aspect / 100.0)) * 100}]
 } else {set ph [expr {int(ceil($pw / $source_aspect / 100.0)) * 100}]}
}
$pg SetPageSizeInfo $pw $ph 10 0
# Wires made through the API carry no net until the page is evaluated; Capture rejects such
# wires on load ("Page Read Error: Wire read failure"). Evaluating the page builds the nets the
# way Capture's own editor does. Outside Capture it reports a missing GUI hook
# (::orCAPCM_IMPL::SetCapCMState) and carries on; defining that hook makes it crash.
catch {DboTclHelper_sEvalPage $pg}
set wi [$pg NewWiresIter $st]; set loose 0
while {[set w [$wi NextWire $st]] ne "NULL"} {if {[$w GetNet $st] eq "NULL"} {incr loose}}
if {$loose} {fail "$loose wires have no net after page evaluation; Capture would reject them"}
set r [$sch SavePage $pg]
if {[$r Code] != 0} {fail "page save failed"}
$s MarkAllLibForSave $d
set r [$s SaveDesign $d]
if {[$r Code] != 0} {fail "save failed"}
puts "SAVED $design_path page=${pw}x${ph}"
