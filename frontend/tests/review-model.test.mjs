import test from 'node:test';
import assert from 'node:assert/strict';
import {renameComponent,removeComponent,circuitErrors,boardErrors} from '../app/review-model.mjs';
const circuit={components:[{ref:'R1',value:'10k'},{ref:'R2',value:'10k'}],nets:[{name:'JOIN',nodes:[{ref:'R1',pin:'2'},{ref:'R2',pin:'1'}]},{name:'GND',nodes:[{ref:'R2',pin:'2'}]}]};
test('renaming carries every pin connection without mutating original',()=>{const result=renameComponent(circuit,1,'R9');assert.equal(result.nets[1].nodes[0].ref,'R9');assert.equal(result.nets[0].nodes[1].ref,'R9');assert.equal(circuit.components[1].ref,'R2');assert.deepEqual(circuitErrors(result),[]);});
test('removing a component removes its pins and empty nets',()=>{const result=removeComponent(circuit,1);assert.equal(result.nets.length,1);assert.deepEqual(result.nets[0].nodes,[{ref:'R1',pin:'2'}]);});
test('duplicate refs and duplicate pin membership block apply',()=>{assert.match(circuitErrors(renameComponent(circuit,1,'R1')).join(' '),/Duplicate reference/);assert.match(circuitErrors({...circuit,nets:[...circuit.nets,{name:'EXTRA',nodes:[{ref:'R1',pin:'2'}]}]}).join(' '),/assigned more than once/);});
test('unknown references and missing pin numbers block apply',()=>{assert.match(circuitErrors({...circuit,nets:[{name:'X',nodes:[{ref:'R99',pin:''}]}]}).join(' '),/unknown component/);});
test('board bounds, missing footprints and nonnumeric placement block export',()=>{const plan={width_mm:40,height_mm:30,track_width_mm:.25,clearance_mm:.2,placements:{R1:{footprint:'Resistor_SMD:R_0805_2012Metric',x_mm:10,y_mm:10,rotation_deg:0}}};assert.deepEqual(boardErrors(plan,[circuit.components[0]]),[]);assert.match(boardErrors({...plan,width_mm:11},[circuit.components[0]]).join(' '),/margin/);assert.ok(boardErrors({...plan,placements:{R1:{footprint:'',x_mm:'',y_mm:10,rotation_deg:0}}},[circuit.components[0]]).length);});

test('malformed JSON structures and invalid source positions produce validation errors',()=>{
 for(const draft of [{components:[null],nets:[]},{components:circuit.components,nets:[null]},{components:circuit.components,nets:[{name:42,nodes:[null]}]}])assert.ok(circuitErrors(draft).length);
 assert.match(circuitErrors({...circuit,components:[{ref:'R1',value:'10k',x:'bad'}]}).join(' '),/source position/);
});
