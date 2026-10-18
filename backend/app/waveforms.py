"""Read bounded, uncompressed real transient RAW/CSV results from external simulators."""
from __future__ import annotations
import csv,io,math,re,struct
from .engine import OperationError

LIMIT=20000

def result(names,rows,source):
 if not rows:raise OperationError('The waveform contains no samples.')
 if len(rows)>LIMIT:raise OperationError('Waveform imports are limited to 20,000 points.')
 if not all(all(math.isfinite(x) for x in row) for row in rows):raise OperationError('Waveform contains non-finite values.')
 if any(rows[i][0]<rows[i-1][0] for i in range(1,len(rows))):raise OperationError('Compressed or non-monotonic waveform time is not supported. Export an uncompressed transient with plotwinsize=0.')
 aliases={re.sub(r'^v\((.*)\)$',r'\1',name.lower()):name for name in names}
 input_name=aliases.get('vin',aliases.get('in',names[0]));output_name=aliases.get('vout',aliases.get('out',names[-1]))
 points=[]
 for row in rows[::max(1,math.ceil(len(rows)/1000))]:
  signals=dict(zip(names,row[1:]));points.append({'t_us':row[0]*1e6,'signals':signals,'vin':signals[input_name],'vout':signals[output_name]})
 return {'title':'Imported transient waveform','solver':source,'signals':names,'data':points,'original_samples':len(rows),'source_verified':False,'display_signals':{'vin':input_name,'vout':output_name}}

def csv_waveform(data):
 try:
  table=csv.reader(io.StringIO(data.decode('utf-8-sig')))
  header=next(table,[])
  if len(header)<2 or header[0].strip().lower() not in ['time','t','time(s)','time (s)']:raise ValueError('First column must be time in seconds.')
  names=[x.strip() for x in header[1:]]
  if not all(names) or len(set(names))!=len(names) or len(names)>256:raise ValueError('Invalid signal names.')
  rows=[]
  for row in table:
   if not any(row):continue
   if len(rows)>=LIMIT:raise ValueError('Waveform imports are limited to 20,000 points.')
   if len(row)!=len(names)+1:raise ValueError('Inconsistent columns.')
   rows.append(list(map(float,row)))
  return result(names,rows,'external_csv')
 except OperationError:raise
 except Exception as e:raise OperationError('Invalid waveform CSV: '+str(e)[:200]) from e

def raw_waveform(data):
 marker=None
 for encoding in ['utf-16-le','utf-8']:
  for kind in ['Binary','Values']:
   for newline in ['\r\n','\n']:
    key=(kind+':'+newline).encode(encoding);index=data.find(key)
    if index>=0:marker=(encoding,kind,index,index+len(key));break
   if marker:break
  if marker:break
 if not marker:raise OperationError('RAW file has no supported Values/Binary section.')
 encoding,kind,index,start=marker
 try:
  header=data[:index].decode(encoding).lstrip('\ufeff');fields={}
  for line in header.splitlines():
   if ':' in line:
    key,value=line.split(':',1);fields[key.strip().lower()]=value.strip()
  nv=int(fields['no. variables']);np=int(fields['no. points']);flags=fields.get('flags','').lower()
  if 'complex' in flags or nv<2 or nv>257 or np<1 or np>LIMIT:raise ValueError('Only bounded real transient data is supported.')
  variables=[]
  for line in header.split('Variables:',1)[1].splitlines():
   match=re.match(r'\s*\d+\s+(\S+)\s+(\S+)',line)
   if match:variables.append((match[1],match[2]))
  if len(variables)!=nv or variables[0][0].lower()!='time':raise ValueError('First RAW variable must be time.')
  names=[v[0] for v in variables[1:]]
  if len(set(names))!=len(names):raise ValueError('Duplicate RAW signal names.')
  payload=data[start:];rows=[]
  if kind=='Values':
   lines=iter(line.split() for line in io.StringIO(payload.decode(encoding)) if line.strip())
   try:
    for i in range(np):
     first=next(lines)
     if len(first)!=2 or int(first[0])!=i:raise ValueError('Invalid RAW point index.')
     row=[float(first[1])]
     for j in range(1,nv):
      value=next(lines)
      if len(value)!=1:raise ValueError('Invalid RAW signal value.')
      row.append(float(value[0]))
     rows.append(row)
   except StopIteration:raise ValueError('RAW sample count does not match its header.')
   if next(lines,None) is not None:raise ValueError('RAW sample count does not match its header.')
  else:
   doubles='double' in flags or len(payload)==np*nv*8
   stride=nv*8 if doubles else 8+(nv-1)*4
   if len(payload)!=np*stride:raise ValueError('RAW binary size mismatch or compressed data. Export with plotwinsize=0.')
   if 'fastaccess' in flags:
    times=struct.unpack_from('<'+str(np)+'d',payload,0);values=[];offset=np*8
    for _ in range(nv-1):
     code='d' if doubles else 'f';values.append(struct.unpack_from('<'+str(np)+code,payload,offset));offset+=np*(8 if doubles else 4)
    rows=[[times[i]]+[v[i] for v in values] for i in range(np)]
   else:
    fmt='<'+('d'*nv if doubles else 'd'+'f'*(nv-1));rows=[list(struct.unpack_from(fmt,payload,i*stride)) for i in range(np)]
  selected=[i for i,(_,unit) in enumerate(variables) if i>0 and unit.lower()=='voltage']
  if not selected:raise ValueError('This voltage scope requires at least one voltage channel.')
  output=result([variables[i][0] for i in selected],[[row[0]]+[row[i] for i in selected] for row in rows],'external_spice_raw')
  output['ignored_non_voltage_signals']=[name for name,unit in variables[1:] if unit.lower()!='voltage']
  return output
 except OperationError:raise
 except Exception as e:raise OperationError('Invalid RAW waveform: '+str(e)[:200]) from e
