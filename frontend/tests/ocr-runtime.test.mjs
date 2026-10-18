import test from 'node:test';
import assert from 'node:assert/strict';
import {ocrRuntimeLabel} from '../app/ocr-runtime.mjs';

test('GPU configuration never claims verified or active CUDA',()=>{
  assert.match(ocrRuntimeLabel({requested:'cuda',worker_configured:true,state:'idle'}),/not yet verified/);
  assert.equal(ocrRuntimeLabel({device:'cuda',gpu_verified:true,state:'completed'},true),'Preparing recognition');
  assert.equal(ocrRuntimeLabel({requested:'cpu',state:'idle'}),'CPU recognition selected');
});
test('live execution labels distinguish CUDA OCR, CPU tracing and runtime errors',()=>{
  assert.equal(ocrRuntimeLabel({device:'cuda',gpu_verified:true,state:'running',stage:'wiring'},true),'CUDA OCR · tracing connections');
  assert.equal(ocrRuntimeLabel({device:'cpu',state:'running'}),'CPU recognition running');
  assert.equal(ocrRuntimeLabel({device:'cuda',gpu_verified:true,state:'failed'}),'OCR runtime failed');
});
