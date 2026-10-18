import test from 'node:test';
import assert from 'node:assert/strict';
import {resolveChatRequest} from '../app/chat-request.mjs';
test('copied attachment labels resolve only existing project files',()=>{
 assert.deepEqual(resolveChatRequest('create a design [Attached: Sample 1.jpg.jpeg]',[],['references/Sample 1.jpg.jpeg']),{text:'create a design',attachments:['Sample 1.jpg.jpeg']});
 assert.deepEqual(resolveChatRequest('create a design [Attached: Sample 1.jpg.jpeg]',[],['references\\Sample 1.jpg.jpeg']),{text:'create a design',attachments:['Sample 1.jpg.jpeg']});
 assert.throws(()=>resolveChatRequest('create a design [Attached: other.jpg]',[],['references/Sample 1.jpg.jpeg']),/Attach the source file again/);
});
test('attachment retry retains canonical filename and avoids duplicate attachments',()=>{
 const attachments=['one.png'];assert.deepEqual(resolveChatRequest('analyze [Attached: one.png]',attachments,[]),{text:'analyze',attachments:['one.png']});assert.deepEqual(attachments,['one.png']);
 assert.throws(()=>resolveChatRequest('analyze',['../other.png'],[]),/Choose a source/);
});
