# Copies every package used in a Capture design (.DSN) into a new symbol library (.OLB), so the parts of
# any existing design can be reused by generated designs. Package footprints come along.
# Usage: tclsh orcad_extract.tcl <orDb dll> <design.dsn> <output.olb>
# Output: "PKG <package> <source library> <PCB footprint>" per copied package, then "SAVED <n>".
load [lindex $argv 0] DboTclWriteBasic
proc C {t} {return [DboTclHelper_sMakeCString $t]}
proc S {c} {return [DboTclHelper_sGetConstCharPtr $c]}
set s [DboTclHelper_sCreateSession]
set st [DboState]
set d [$s GetDesignAndSchematics [C [lindex $argv 1]] $st]
if {$d == "NULL"} {puts "ERROR cannot open design (not a Capture .DSN, or saved by a newer Capture)"; exit 2}
set out [lindex $argv 2]
file delete -force $out
set lib [$s CreateLib [C $out] $st]
if {$lib == "NULL"} {puts "ERROR cannot create library $out"; exit 3}
array set done {}
set vi [$d NewViewsIter $st $::IterDefs_SCHEMATICS]
while {[set v [$vi NextView $st]] ne "NULL"} {
 set sch [DboViewToDboSchematic $v]
 set pgi [$sch NewPagesIter $st]
 while {[set pg [$pgi NextPage $st]] ne "NULL"} {
  set ii [$pg NewPartInstsIter $st]
  while {[set inst [$ii NextPartInst $st]] ne "NULL"} {
   set pl [DboPartInstToDboPlacedInst $inst]
   if {$pl eq "NULL"} continue
   set pkg [$pl GetPackage $st]
   set name [C ""]; $pl GetSourcePackageName $name; set name [S $name]
   if {$pkg eq "NULL" || $name eq "" || [info exists done($name)]} continue
   set copy [$lib CopyPackageAll $pkg [C $name] $st]
   if {$copy eq "NULL" || [$st Code] != 0} {puts "WARN cannot copy $name"; continue}
   # designs often carry the footprint on the placed part, not the package: keep it with the package
   set have [C ""]; $copy GetPCBFootprint $have
   set inst_fp [C ""]; $pl GetPCBFootprint $inst_fp
   if {[S $have] eq "" && [S $inst_fp] ne ""} {$copy SetPCBFootprint [C [S $inst_fp]]}
   $lib SavePackageAll $copy
   set done($name) 1
   set src [C ""]; $pl GetSourceLibName $src
   set fp [C ""]; $copy GetPCBFootprint $fp
   puts [list PKG $name [S $src] [S $fp]]
  }
  delete_DboPagePartInstsIter $ii
 }
 delete_DboSchematicPagesIter $pgi
}
if {[array size done] == 0} {puts "ERROR the design has no placed parts to extract"; exit 4}
set r [$s SaveLib $lib]
if {[$r Code] != 0} {puts "ERROR cannot save library $out"; exit 5}
puts "SAVED [array size done]"
