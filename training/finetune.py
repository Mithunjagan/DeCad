#!/usr/bin/env python3
"""GPU-only Qwen-VL LoRA training; fail before downloading weights on unsupported hosts."""
from __future__ import annotations
import argparse,hashlib,json,sys,time
from pathlib import Path

def read_records(path,root):
 records=[json.loads(line) for line in path.read_text().splitlines() if line.strip()]
 for record in records:
  image=(root/record['image']).resolve()
  if not image.is_relative_to(root.resolve()) or not image.is_file():raise ValueError('Missing or unsafe image path.')
  if hashlib.sha256(image.read_bytes()).hexdigest()!=record['image_sha256']:raise ValueError('Dataset image checksum mismatch.')
  if not record.get('netlist_equivalence_verified'):raise ValueError('A training sample has unverified pin connectivity.')
  if record.get('image_source_review')!='verified':raise ValueError('Source image/netlist fidelity requires explicit annotation review before training.')
 return records

def main(args):
 if (args.output/'adapter').exists():raise SystemExit('Adapter output already exists. Choose a new output directory to preserve trained weights.')
 if not 1<=args.epochs<=100:raise SystemExit('Epochs must be between 1 and 100.')
 profiles=json.loads(Path(__file__).with_name('profiles.json').read_text())
 profile=profiles[args.profile]
 if args.model and args.model!=profile['model']:raise SystemExit('The selected model must match its bounded training profile.')
 args.model=profile['model']
 root=args.dataset.resolve()
 try:train=read_records(root/'train.jsonl',root);validation=read_records(root/'validation.jsonl',root);test=read_records(root/'test.jsonl',root)
 except (ValueError,OSError) as e:raise SystemExit('Dataset preflight rejected: '+str(e)+' No weights downloaded.')
 groups=[{r['group'] for r in rows} for rows in [train,validation,test]]
 if any(groups[i]&groups[j] for i in range(3) for j in range(i)):raise SystemExit('Circuit-family leakage across splits.')
 if len(train)<100 or not validation or not test:raise SystemExit('Training is not release-ready: need at least 100 verified training pairs and separate validation/test circuit groups. No weights downloaded.')
 try:import torch
 except ImportError:raise SystemExit('Install training/requirements-gpu.txt in a separate CUDA environment. No weights downloaded.')
 if not torch.cuda.is_available():raise SystemExit('Fine-tuning requires a separate CUDA GPU. This launcher does not train on a low-memory user machine.')
 # T4-class GPUs lack BF16; they train in FP16 with FP32 LoRA weights and loss scaling.
 bf16=torch.cuda.is_bf16_supported()
 if not bf16 and not profile.get('fp16_allowed'):raise SystemExit('This BF16 training profile requires a compatible CUDA GPU (use the 7b-t4 profile on a T4). No weights downloaded.')
 compute_dtype=torch.bfloat16 if bf16 else torch.float16
 if args.init_adapter:
  config=json.loads((args.init_adapter/'adapter_config.json').read_text())
  if config.get('base_model_name_or_path')!=args.model:raise SystemExit(f"Adapter was trained on {config.get('base_model_name_or_path')}; choose a profile using that base model.")
 free,_=torch.cuda.mem_get_info()
 if free<profile['minimum_free_gib']*1024**3:raise SystemExit(f"At least {profile['minimum_free_gib']} GiB free GPU memory is required for preflight. No weights downloaded.")
 torch.set_num_threads(2)
 torch.cuda.reset_peak_memory_stats()
 started=time.monotonic()
 fingerprint=hashlib.sha256(b'\n'.join((root/name).read_bytes() for name in ['train.jsonl','validation.jsonl','test.jsonl'])).hexdigest()
 smoke_path=args.output/'smoke-report.json'
 if args.smoke_test:smoke_path.unlink(missing_ok=True)
 if args.profile in ('3b-8gb','7b-t4') and not args.smoke_test:
  try:smoke=json.loads(smoke_path.read_text())
  except (OSError,ValueError):raise SystemExit(f'Run --smoke-test on this GPU with this dataset before a {args.profile} training run.')
  if not smoke_matches(smoke,args.profile,fingerprint,torch.cuda.get_device_name()) or smoke.get('profile_settings')!=profile:raise SystemExit('Smoke report does not match this profile, dataset and GPU, or has insufficient memory headroom.')
 from PIL import Image
 from transformers import AutoProcessor,AutoModelForImageTextToText,BitsAndBytesConfig,Trainer,TrainingArguments
 from peft import LoraConfig,PeftModel,get_peft_model,prepare_model_for_kbit_training
 sys.path.insert(0,str(Path(__file__).resolve().parent))
 from prompts import SYSTEM,USER
 processor=AutoProcessor.from_pretrained(args.model,trust_remote_code=False,min_pixels=128*28*28,max_pixels=profile['image_tokens']*28*28)
 model=AutoModelForImageTextToText.from_pretrained(args.model,trust_remote_code=False,use_safetensors=True,quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=compute_dtype),device_map={'':'cuda:0'})
 model=prepare_model_for_kbit_training(model)
 # Continue from the supplied adapter when given; otherwise start a new LoRA.
 if args.init_adapter:model=PeftModel.from_pretrained(model,str(args.init_adapter),is_trainable=True)
 else:model=get_peft_model(model,LoraConfig(r=profile['rank'],lora_alpha=profile['alpha'],lora_dropout=.05,target_modules=['q_proj','k_proj','v_proj','o_proj'],task_type='CAUSAL_LM'))
 model.config.use_cache=False
 if not bf16:
  for parameter in model.parameters():
   if parameter.requires_grad:parameter.data=parameter.data.float()
 for name,parameter in model.named_parameters():
  if '.visual.' in name or '.vision_tower.' in name:parameter.requires_grad=False
 class Pairs(torch.utils.data.Dataset):
  def __init__(self,records):self.records=records
  def __len__(self):return len(self.records)
  def __getitem__(self,index):return self.records[index]
 def collate(rows):
  if len(rows)!=1:raise ValueError('This bounded profile uses one image per microbatch.')
  row=rows[0];image=Image.open(root/row['image']).convert('RGB');prompt=[{'role':'system','content':SYSTEM},{'role':'user','content':[{'type':'image'},{'type':'text','text':USER}]}]
  full=prompt+[{'role':'assistant','content':json.dumps(row['circuit'])}]
  text=processor.apply_chat_template(full,tokenize=False,add_generation_prompt=False);prefix=processor.apply_chat_template(prompt,tokenize=False,add_generation_prompt=True)
  encoded=processor(text=[text],images=[image],return_tensors='pt');prefix_tokens=processor(text=[prefix],images=[image],return_tensors='pt')['input_ids'].shape[1]
  labels=encoded['input_ids'].clone();labels[:,:prefix_tokens]=-100
  if processor.tokenizer.pad_token_id is not None:labels[encoded['input_ids']==processor.tokenizer.pad_token_id]=-100
  if encoded['input_ids'].shape[1]>profile['sequence_tokens']:raise ValueError('Sample exceeds profile token budget. Use a larger profile or reviewed smaller circuit; targets are never truncated.')
  encoded['labels']=labels;return encoded
 args.output.mkdir(parents=True,exist_ok=True)
 settings=TrainingArguments(output_dir=str(args.output),per_device_train_batch_size=1,per_device_eval_batch_size=1,gradient_accumulation_steps=1 if args.smoke_test else 8,num_train_epochs=args.epochs,max_steps=1 if args.smoke_test else -1,learning_rate=1e-4 if args.init_adapter else 2e-4,bf16=bf16,fp16=not bf16,gradient_checkpointing=True,eval_strategy='no' if args.smoke_test else 'epoch',save_strategy='no' if args.smoke_test else 'epoch',save_total_limit=2,report_to='none',remove_unused_columns=False,dataloader_num_workers=0,seed=42)
 # Exercise the longest annotation during smoke testing, not an arbitrary easy pair.
 training_rows=[max(train,key=lambda row:len(json.dumps(row['circuit'])))] if args.smoke_test else train
 trainer=Trainer(model=model,args=settings,train_dataset=Pairs(training_rows),eval_dataset=Pairs(validation),data_collator=collate)
 try:
  trainer.train()
 except torch.cuda.OutOfMemoryError:
  (args.output/'memory-failure.json').write_text(json.dumps({'status':'out_of_memory','profile':args.profile,'gpu':torch.cuda.get_device_name(),'dataset_sha256':fingerprint}))
  raise SystemExit('GPU memory exhausted. Training stopped; this configuration is not approved for this GPU.')
 peak=torch.cuda.max_memory_reserved();total=torch.cuda.get_device_properties(0).total_memory
 report={'status':'smoke_passed' if args.smoke_test else 'trained_not_release_approved','profile':args.profile,'profile_settings':profile,'base_model':args.model,'gpu':torch.cuda.get_device_name(),'dataset_sha256':fingerprint,'peak_reserved_bytes':peak,'gpu_total_bytes':total,'headroom_bytes':min(total-peak,torch.cuda.mem_get_info()[0]),'elapsed_seconds':round(time.monotonic()-started,2),'training_pairs':len(train),'validation_pairs':len(validation),'held_out_pairs':len(test),'note':'One smoke step is not a full-run fit or accuracy guarantee. Held-out graph evaluation remains required.'}
 if args.smoke_test:
  if report['headroom_bytes']<768*1024**2:report['status']='insufficient_headroom'
  smoke_path.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
  if report['status']!='smoke_passed':raise SystemExit('Less than 768 MiB GPU headroom remains; do not start this training profile.')
  return
 report['validation_metrics']=trainer.evaluate();model.save_pretrained(args.output/'adapter');processor.save_pretrained(args.output/'adapter')
 (args.output/'training-report.json').write_text(json.dumps(report,indent=2))

def smoke_matches(report,profile,fingerprint,gpu):
 return report.get('status')=='smoke_passed' and report.get('profile')==profile and report.get('dataset_sha256')==fingerprint and report.get('gpu')==gpu and report.get('headroom_bytes',0)>=768*1024**2

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model');p.add_argument('--profile',choices=['7b','7b-t4','3b-8gb'],default='7b');p.add_argument('--init-adapter',type=Path,help='Continue training from an existing PEFT adapter folder.');p.add_argument('--smoke-test',action='store_true');p.add_argument('--epochs',type=int,default=3);a=p.parse_args();main(a)
