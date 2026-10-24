from app.orcad_source_layout import prepare,verify_positions


def source_graph():
    return {'components': [{'ref':'C1','value':'100n','x':.5,'y':.5}],
            'nets':[{'name':'A','nodes':[{'ref':'C1','pin':'1'}]},
                    {'name':'B','nodes':[{'ref':'C1','pin':'2'}]}],
            'image_metadata': {'width':1000,'character_height':16,
                               'pin_anchors':[{'ref':'C1','pin':'1','x':500,'y':490,'body':[490,492,510,498]},
                                              {'ref':'C1','pin':'2','x':500,'y':500,'body':[490,492,510,498]}]}}


def test_small_source_capacitor_keeps_outward_pin_directions_and_orientation():
    graph = source_graph()
    drawing, symbols, report = prepare(graph,scale=1200)
    pins = symbols['C1']['pins']
    assert pins[0][2] > pins[0][4] and pins[1][2] < pins[1][4]
    assert pins[0][3] == pins[1][3]  # vertical source leads retained
    assert report['source_geometry_components'] == ['C1']
    assert drawing is not graph and graph['components'][0]['x'] == .5


def test_source_layout_reports_missing_and_conflicting_geometry():
    graph = source_graph()
    graph['components'].append({'ref':'C2','value':'100n','x':.7,'y':.7})
    for number in ('1','2'):
        graph['nets'].append({'name':'OTHER'+number,'nodes':[{'ref':'C2','pin':number}]})
    _,symbols,report = prepare(graph,scale=1200)
    assert 'C2' not in symbols and 'C2' in report['fallback_components']
    graph['image_metadata']['pin_anchors'] += [dict(p,ref='C2') for p in graph['image_metadata']['pin_anchors']]
    _,symbols,report = prepare(graph,scale=1200)
    assert len(symbols) == 1 and report['fallback_components'] == ['C2']


def test_catalog_inventory_and_measured_leads_produce_an_amplifier_triangle():
    anchors = [('1',90,120),('2',90,180),('3',130,90),('4',130,210),('5',210,150)]
    graph = {'components':[{'ref':'U1','value':'amplifier'}],
             'nets':[{'name':'N'+pin,'nodes':[{'ref':'U1','pin':pin}]} for pin,_,_ in anchors],
             'image_metadata':{'width':1000,'pin_anchors':[
                 {'ref':'U1','pin':pin,'x':x,'y':y,'body':[100,100,200,200]} for pin,x,y in anchors]}}
    _,symbols,_ = prepare(graph,scale=1200)
    assert symbols['U1']['shape'] == 'amplifier'
    assert len(symbols['U1']['vectors']) == 3
    assert {pin[0] for pin in symbols['U1']['pins']} == {'1','2','3','4','5'}


def test_lone_passive_anchor_cannot_turn_a_nearby_ic_contour_into_a_resistor():
    graph = source_graph()
    graph['components'][0]['ref'] = 'R7'
    graph['nets'] = [{'name':'A','nodes':[{'ref':'R7','pin':'1'}]}]
    graph['image_metadata']['pin_anchors'] = [
        {'ref':'R7','pin':'1','x':500,'y':490,'body':[400,400,600,900]}]
    _,symbols,report = prepare(graph,scale=1200)
    assert not symbols and report['fallback_components'] == ['R7']


def test_split_ic_retains_both_source_bodies_instead_of_an_averaged_body():
    graph = {'components':[{'ref':'U1','value':'BUFFER'}],
             'nets':[{'name':'A','nodes':[{'ref':'U1','pin':'1'},{'ref':'U1','pin':'2'}]}],
             'image_metadata':{'width':1000,'pin_anchors':[
                 {'ref':'U1','pin':'1','x':90,'y':150,'body':[100,100,200,200]},
                 {'ref':'U1','pin':'2','x':410,'y':150,'body':[300,100,400,200]}]}}
    _,symbols,_ = prepare(graph,scale=1200)
    assert symbols['U1']['shape'] == 'split package'
    assert len(symbols['U1']['vectors']) == 2
    assert symbols['U1']['vectors'][0][3] < symbols['U1']['vectors'][1][1]


def test_distributed_connector_terminals_stay_at_their_source_positions():
    graph = source_graph()
    graph['components'][0]['ref']='P2'
    for net in graph['nets']:
        net['nodes'][0]['ref']='P2'
    for anchor in graph['image_metadata']['pin_anchors']:
        anchor['ref']='P2';anchor.pop('body')
    _,symbols,report=prepare(graph,scale=1200)
    assert symbols['P2']['shape']=='source ports'
    assert report['source_port_components']==['P2']
    cx,cy=symbols['P2']['center']
    page={'parts':[{'base':'P2','pins':[{'number':p[0],'hx':cx+p[3],'hy':cy+p[4]} for p in symbols['P2']['pins']]}]}
    assert verify_positions(symbols,page)['passed']
    page['parts'][0]['pins'][0]['hx']+=20
    assert not verify_positions(symbols,page)['passed']
