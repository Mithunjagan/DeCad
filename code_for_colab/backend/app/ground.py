"""Select one reference net without silently shorting distinct named rails."""
def reference_name(names):
 names=list(names)
 for preferred in ['GND','0','GROUND','VSS']:
  if preferred in names:return preferred
  for name in names:
   if name.upper()==preferred:return name
 return None
