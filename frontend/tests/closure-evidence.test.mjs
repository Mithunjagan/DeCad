import test from 'node:test';
import assert from 'node:assert/strict';
import {circuitErrors,evidenceText} from '../app/review-model.mjs';

test('provisional and inferred terminal evidence survives review validation',()=>{
  for(const source of ['provisional_stub','implicit_passive_terminal']){
    const circuit={components:[{ref:'R1',value:'1k'}],nets:[{name:'REVIEW_R1',nodes:[{ref:'R1',pin:'1',confidence:.35,source}]}]};
    assert.deepEqual(circuitErrors(circuit),[]);
  }
  assert.match(evidenceText({source:'provisional_stub',confidence:.35}),/Provisional stub.*confirm number and net/);
});
