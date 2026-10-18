// A copied chat label is metadata, not part of an executable circuit command.
export function resolveChatRequest(message, attachments, files) {
  let text=message.trim(),names=[...attachments];
  const marker=text.match(/\s*\[Attached:\s*(.*?)\]\s*$/i);
  if(marker){
    const available=new Set(files.map(p=>p.replaceAll('\\','/')).filter(p=>p.startsWith('references/')).map(p=>p.slice(11)));
    const mentioned=available.has(marker[1].trim())?[marker[1].trim()]:marker[1].split(',').map(s=>s.trim());
    if(mentioned.some(name=>!name||(!available.has(name)&&!names.includes(name))))throw Error('Attach the source file again. The copied attachment label does not identify a file in this project.');
    names=[...names,...mentioned];text=text.slice(0,marker.index).trim();
  }
  if(names.some(name=>!name||/[\\/]/.test(name)))throw Error('Choose a source attachment from this project.');
  return {text:text||(names.length?'Analyze the attached schematic and create a design':''),attachments:[...new Set(names)]};
}

export function requestErrorSummary(message){
  if(message.startsWith('Unsupported command.'))return 'Request not applied. Attach a schematic or use a supported circuit command.';
  return message.length>220?message.slice(0,217)+'…':message;
}
