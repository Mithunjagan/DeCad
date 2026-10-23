import test from 'node:test';
import assert from 'node:assert/strict';
import {netGeometry} from '../app/source-net.mjs';
import {mergeNets,splitPin,renameComponent,removeComponent} from '../app/review-model.mjs';

test('net overlay inverts source transform, scopes pages and excludes buses',()=>{
 const graph={image_metadata:{pages:[{page:2,references:{U1:'U_P2_1'},metadata:{source_size:[100,50],source_affine:[[2,0,0],[0,2,0]],
  pin_anchors:[{ref:'U1',pin:'1',x:40,y:30,physical_net:7}],wires:[{id:1,p0:[40,30],p1:[80,30],traced_physical_net:7},{id:2,p0:[40,30],p1:[90,30],traced_physical_net:7,bus:true}]}}]}};
 const net={nodes:[{ref:'U_P2_1',pin:'1'}]};
 assert.deepEqual(netGeometry(graph,net,2),{pins:[{ref:'U_P2_1',pin:'1',at:[20,30]}],segments:[{id:1,a:[20,30],b:[40,30]}]});
 assert.deepEqual(netGeometry(graph,net,1),{pins:[],segments:[]});
 assert.deepEqual(netGeometry(graph,{...net,metadata:{evidence_stale:true}},2),{pins:[],segments:[]});
});

test('split and merge update physical membership and invalidate old confidence',()=>{
 const graph={components:[{ref:'U1',value:'X'}],nets:[{name:'A',confidence:.9,nodes:[{ref:'U1',pin:'1'},{ref:'U1',pin:'2'}]},{name:'B',nodes:[{ref:'U1',pin:'3'}]}]};
 const split=splitPin(graph,0,1);assert.equal(split.nets.length,3);assert.equal(split.nets[2].nodes[0].pin,'2');
 const merged=mergeNets(split,2,1);assert.equal(merged.nets.length,2);assert.deepEqual(merged.nets[1].nodes.map(p=>p.pin),['3','2']);
 assert.equal(merged.nets[1].confidence,null);assert.equal(graph.nets[0].nodes.length,2);
});

test('reference edits preserve unassigned inventory and remove deleted physical pins',()=>{
 const graph={components:[{ref:'U1',value:'X'}],nets:[],physical_pins:[{ref:'U1',pin:'15',used:true,metadata:{td9_attributes:{NodeName:'U1_15'}}}]};
 const renamed=renameComponent(graph,0,'U2');assert.equal(renamed.physical_pins[0].ref,'U2');assert.equal(renamed.physical_pins[0].metadata.td9_attributes.NodeName,'U2_15');
 assert.equal(removeComponent(renamed,0).physical_pins.length,0);
});
