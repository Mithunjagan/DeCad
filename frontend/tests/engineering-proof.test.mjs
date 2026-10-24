import test from 'node:test';
import assert from 'node:assert/strict';
import {circuitSignature,engineeringMetrics} from '../app/engineering-proof.mjs';
const circuit={components:[{ref:'R1',value:'10k'}],physical_pins:[{ref:'R1',pin:'1'},{ref:'R1',pin:'2'}],nets:[{name:'VIN',nodes:[{ref:'R1',pin:'1'}]}]};
test('unverified circuits never receive fabricated zero checks',()=>{
 const m=engineeringMetrics(circuit,null);
 assert.equal(m.pins,2);assert.equal(m.verified,false);
 assert.equal(m.loose,undefined);assert.equal(m.shorts,undefined);
});
test('scorecard uses native export counts including legal singleton stubs',()=>{
 const m=engineeringMetrics(circuit,{passed:true,routing:{wired_nets:3,named_singleton_stubs:4,endpoint_verification:{unlabelled_loose_ends:0},visible_wire_verification:{shorted_nets:[]}}});
 assert.equal(m.multi,3);assert.equal(m.stubs,4);assert.equal(m.loose,0);assert.equal(m.shorts,0);assert.equal(m.verified,true);
});
test('net edits invalidate the saved electrical proof fingerprint',()=>{
 const edited=structuredClone(circuit);edited.nets[0].nodes[0].pin='2';
 assert.notEqual(circuitSignature(edited),circuitSignature(circuit));
});
