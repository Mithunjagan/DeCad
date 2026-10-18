import struct
import pytest
from app.waveforms import raw_waveform,csv_waveform
from app.engine import OperationError
from test_operations import client,create

@pytest.mark.parametrize('encoding',['utf-8','utf-16-le'])
@pytest.mark.parametrize('mode',['Values','Binary','FastAccess'])
def test_real_transient_formats(encoding,mode):
 header='Title: Exported transient\nPlotname: Transient Analysis\nFlags: real'+(' fastaccess' if mode=='FastAccess' else '')+'\nNo. Variables: 3\nNo. Points: 2\nVariables:\n\t0\ttime\ttime\n\t1\tV(in)\tvoltage\n\t2\tV(out)\tvoltage\n'+('Values' if mode=='Values' else 'Binary')+':\n'
 if mode=='Values':payload='0\t0\n\t5\n\t2.5\n1\t0.001\n\t5\n\t2.5\n'.encode(encoding)
 elif mode=='FastAccess':payload=struct.pack('<2d4f',0,.001,5,5,2.5,2.5)
 else:payload=struct.pack('<dffdff',0,5,2.5,.001,5,2.5)
 result=raw_waveform(header.encode(encoding)+payload)
 assert result['data'][-1]['t_us']==1000
 assert result['data'][-1]['signals']['V(out)']==2.5
 assert result['source_verified'] is False

@pytest.mark.parametrize('data',[b'time,V(out)\n0,nan\n',b'time,V(out)\n1,3\n0,2\n',b'time,V(out)\n0,2,3\n'])
def test_malformed_csv(data):
 with pytest.raises(OperationError):csv_waveform(data)

def test_import_endpoint(client):
 create(client,'ExternalWaveform')
 response=client.post('/projects/ExternalWaveform/waveforms/import?name=result.csv',content=b'time,V(in),V(out)\n0,5,2.5\n0.001,5,2.5\n')
 assert response.status_code==200,response.text
 assert response.json()['data'][1]['vout']==2.5
 assert client.post('/projects/ExternalWaveform/waveforms/import?name=result.csv',content=b'bad').status_code==422

def test_raw_current_is_not_plotted_as_voltage():
 header='Flags: real\nNo. Variables: 3\nNo. Points: 1\nVariables:\n0 time time\n1 V(out) voltage\n2 I(V1) current\nValues:\n0 0\n2.5\n-0.00025\n'
 parsed=raw_waveform(header.encode())
 assert parsed['data'][0]['vout']==2.5
 assert parsed['signals']==['V(out)']
 assert parsed['ignored_non_voltage_signals']==['I(V1)']

def test_csv_named_signals_override_order():
 parsed=csv_waveform(b'time,V(out),V(in)\n0,2.5,5\n')
 assert parsed['data'][0]['vout']==2.5
 assert parsed['data'][0]['vin']==5
