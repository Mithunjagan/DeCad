import test from 'node:test';
import assert from 'node:assert/strict';
import {renameComponent,removeComponent,circuitErrors,boardErrors,editNetEvidence,confirmHotspot} from '../app/review-model.mjs';
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

const scored={components:[{ref:'R1',value:'10k'}],nets:[{name:'DATA',confidence:.7,source:'erc_healed',nodes:[{ref:'R1',pin:'1',confidence:.7,source:'erc_healed'}]}],review_hotspots:[{id:'r1',ref:'R1',pin:'1',bbox:[10,20,30,40],page:1,source_width:100,source_height:100,confidence:.7,source:'erc_healed',reason:'Recovered pin',reviewed:false}]};
test('one click confirms a source region without changing scores or connections',()=>{const found=confirmHotspot(scored,'r1');assert.equal(found.review_hotspots[0].reviewed,true);assert.equal(found.review_hotspots[0].confidence,.7);assert.deepEqual(found.nets,scored.nets);assert.equal(scored.review_hotspots[0].reviewed,false);});
test('manual net edits clear automatic evidence and mark only affected regions stale',()=>{const found=editNetEvidence(scored,0,{...scored.nets[0],name:'MANUAL'});assert.equal(found.nets[0].confidence,null);assert.equal(found.nets[0].nodes[0].source,null);assert.equal(found.review_hotspots[0].stale,true);assert.equal(scored.nets[0].confidence,.7);});
test('renaming scopes source region references and deletion removes obsolete regions',()=>{assert.equal(renameComponent(scored,0,'R9').review_hotspots[0].ref,'R9');assert.equal(removeComponent(scored,0).review_hotspots.length,0);});
test('invalid confidence and region coordinates block applying raw JSON',()=>{const invalid=structuredClone(scored);invalid.nets[0].confidence=Infinity;invalid.review_hotspots[0].bbox=[0,0,150,40];assert.match(circuitErrors(invalid).join(' '),/between 0 and 1/);assert.match(circuitErrors(invalid).join(' '),/inside their image/);assert.deepEqual(circuitErrors(scored),[]);});
