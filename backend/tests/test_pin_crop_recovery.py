from types import SimpleNamespace
from app.pin_crop_recovery import recover


def test_clipped_invalid_pin_needs_both_readers_and_preserves_labels():
    edges = [(n, n, n, 0, 0, 1, 'U1') for n in range(10)]
    reads = {n: (str(n+1), ['DATA'+str(n)]*2) for n in range(9)}
    reads[9] = ('68', ['ADDA2', 'ADDA2'])
    calls = []
    def reader(page,x,y,ux,uy,ch,side,audit):
        calls.append(ch)
        if ch == 10:
            audit['primary'] = ('68', .53)
            return '68', ['ADDA2']*2
        audit.update(primary=('38',.99), secondary=('38',.99))
        return '38', ['ADDA2']*2
    pins = frozenset(str(n) for n in range(1,41))
    assert recover(SimpleNamespace(soft=None),edges,reads,{'U1':'CHIP'},10,reader,numbers=lambda _:pins)==[('U1','68','38')]
    assert reads[9] == ('38', ['ADDA2','ADDA2'])
    assert all(reads[n][0] == str(n+1) for n in range(9))
    assert set(calls) == {10,10.4,10.8}


def test_disagreement_existing_destination_and_soft_images_are_rejected():
    edges = [(n,n,n,0,0,1,'U1') for n in range(10)]
    original = {n:(str(n+1),['D'+str(n)]*2) for n in range(9)}
    original[9] = ('68',['D9']*2)
    pins = frozenset(str(n) for n in range(1,41))
    for destination,second,soft in [('38','39',None),('2','2',None),('38','38',True)]:
        reads = dict(original)
        def reader(page,x,y,ux,uy,ch,side,audit):
            if ch==10:
                audit['primary']=('68',.5)
                return '68',['D9']*2
            audit.update(primary=(destination,.99),secondary=(second,.99))
            return destination,['D9']*2
        assert not recover(SimpleNamespace(soft=soft),edges,reads,{'U1':'CHIP'},10,reader,numbers=lambda _:pins)
        assert reads==original
