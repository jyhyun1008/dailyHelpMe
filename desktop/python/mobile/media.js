'use strict';
function mediaImage(asset,kind=asset.kind){
  const wrap=node('span',undefined,'chat-art '+(kind==='sticker'?'sticker-art':'emoji-art'));
  wrap.contentEditable='false';wrap.title=asset.name;
  const image=node('img');image.src='/api/media/image/'+encodeURIComponent(asset.id);image.alt=asset.name;image.draggable=false;
  wrap.append(image);return wrap;
}
const appendBeforeMedia=appendMessageText;
function appendMediaText(bubble,message){const part=node('span');appendBeforeMedia(part,message);bubble.append(...part.childNodes);}
appendMessageText=function(bubble,message){
  if(message.sticker){bubble.classList.add('sticker-bubble');bubble.append(mediaImage(message.sticker,'sticker'));return;}
  const pattern=/:emoji_([a-f0-9]{32}):/g;let start=0;
  for(const match of message.content.matchAll(pattern)){
    const asset=(state.media||[]).find(asset=>asset.id===match[1]&&asset.kind==='emoji');
    if(!asset)continue;
    appendMediaText(bubble,{...message,content:message.content.slice(start,match.index)});
    bubble.append(mediaImage(asset));start=match.index+match[0].length;
  }
  appendMediaText(bubble,{...message,content:message.content.slice(start)});
};
// Keep the existing .value interface while showing real inline images in the composer.
const oldComposer=$('message');
const mediaComposer=node('div',undefined,'media-composer');mediaComposer.id='message';mediaComposer.contentEditable='true';
mediaComposer.setAttribute('role','textbox');mediaComposer.setAttribute('aria-label','메시지');mediaComposer.setAttribute('aria-multiline','true');mediaComposer.dataset.placeholder='메시지 보내기';
function composerText(element){
  let text='';
  element.childNodes.forEach(child=>{
    if(child.nodeType===Node.TEXT_NODE)text+=child.textContent;
    else if(child.dataset?.emojiToken)text+=child.dataset.emojiToken;
    else if(child.nodeName==='BR')text+='\n';
    else{text+=((child.nodeName==='DIV'||child.nodeName==='P')&&text&&!text.endsWith('\n')?'\n':'')+composerText(child);}
  });return text;
}
Object.defineProperty(mediaComposer,'value',{get(){return composerText(this);},set(value){this.textContent=value;}});
oldComposer.replaceWith(mediaComposer);
mediaComposer.onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('chat-form').requestSubmit();}};
mediaComposer.onpaste=event=>{event.preventDefault();document.execCommand('insertText',false,event.clipboardData.getData('text/plain'));};
let composerRange=null;
function saveComposerRange(){const selection=window.getSelection();if(selection.rangeCount&&mediaComposer.contains(selection.anchorNode))composerRange=selection.getRangeAt(0).cloneRange();}
mediaComposer.addEventListener('keyup',saveComposerRange);mediaComposer.addEventListener('mouseup',saveComposerRange);mediaComposer.addEventListener('input',saveComposerRange);
const mediaButton=node('button','☺','media-open');mediaButton.type='button';mediaButton.title='커스텀 이모지 · 스티커';mediaButton.setAttribute('aria-label','커스텀 이모지 · 스티커');$('send').before(mediaButton);
const mediaDialog=node('dialog',undefined,'media-dialog');
const mediaHeading=node('h2','이모지 · 스티커');
const mediaClose=node('button','닫기');mediaClose.type='button';mediaClose.onclick=()=>mediaDialog.close();
const mediaTabs=node('div',undefined,'media-tabs');
let mediaKind='emoji';
const mediaGrid=node('div',undefined,'media-grid');
for(const [kind,title] of [['emoji','이모지'],['sticker','스티커']]){const button=node('button',title);button.type='button';button.onclick=()=>{mediaKind=kind;renderMediaPicker();};mediaTabs.append(button);}
const mediaName=node('input');mediaName.maxLength=40;mediaName.placeholder='이미지 이름';mediaName.setAttribute('aria-label','이미지 이름');
const mediaFile=node('input');mediaFile.type='file';mediaFile.accept='image/png,image/jpeg,image/webp,image/gif';mediaFile.setAttribute('aria-label','등록할 이미지');
const mediaRegister=node('button','선택한 종류로 등록');mediaRegister.type='button';
const mediaHelp=node('p','이모지는 글 사이에 삽입 · 스티커는 AI 답장 없이 바로 전송','muted');mediaHelp.setAttribute('role','status');
mediaDialog.append(mediaHeading,mediaClose,mediaTabs,mediaGrid,mediaName,mediaFile,mediaRegister,mediaHelp);document.body.append(mediaDialog);
mediaButton.onclick=()=>{saveComposerRange();renderMediaPicker();mediaDialog.showModal();};
function insertComposerEmoji(asset){
  if(state.busy){mediaHelp.textContent='답장을 받은 뒤 이모지를 넣어주세요.';return;}
  const wrap=mediaImage(asset);wrap.dataset.emojiToken=':emoji_'+asset.id+':';
  mediaDialog.close();mediaComposer.focus();
  const range=composerRange&&mediaComposer.contains(composerRange.startContainer)?composerRange:document.createRange();
  if(!composerRange||!mediaComposer.contains(range.startContainer)){range.selectNodeContents(mediaComposer);range.collapse(false);}
  range.deleteContents();range.insertNode(wrap);range.setStartAfter(wrap);range.collapse(true);
  const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);composerRange=range.cloneRange();
}
function renderMediaPicker(){
  mediaGrid.replaceChildren();mediaTabs.querySelectorAll('button').forEach((button,index)=>button.classList.toggle('primary',(index===0)===(mediaKind==='emoji')));
  const assets=(state.media||[]).filter(asset=>asset.active&&asset.kind===mediaKind);
  if(!assets.length)mediaGrid.append(node('p','이미지를 등록해보세요.','muted'));
  for(const asset of assets){const tile=node('div',undefined,'media-tile');const button=node('button',undefined,'media-choice');button.type='button';button.setAttribute('aria-label',asset.name);button.append(mediaImage(asset),node('small',asset.name));
    button.onclick=async()=>{if(asset.kind==='emoji')insertComposerEmoji(asset);else if(await mutate('/api/sticker',{id:asset.id}))mediaDialog.close();};
    const remove=node('button','삭제','quiet');remove.type='button';remove.setAttribute('aria-label',asset.name+' 선택 목록에서 삭제');remove.onclick=async()=>{if(await mutate('/api/media/delete',{id:asset.id})){renderMediaPicker();mediaHelp.textContent='선택 목록에서 삭제했어요. 지난 대화의 이미지는 유지돼요.';}};tile.append(button,remove);mediaGrid.append(tile);
  }
}
mediaRegister.onclick=async()=>{
  const file=mediaFile.files[0];if(!file){mediaHelp.textContent='이미지를 선택해주세요.';return;}
  if(file.size>4*1024*1024){mediaHelp.textContent='이미지는 4MB 이하로 선택해주세요.';return;}
  mediaRegister.disabled=true;
  try{const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
    if(await mutate('/api/media/add',{kind:mediaKind,name:mediaName.value.trim()||file.name.replace(/\.[^.]+$/,'').slice(0,40),image:data})){mediaName.value='';mediaFile.value='';renderMediaPicker();mediaHelp.textContent='등록했어요. 이미지를 눌러 사용해보세요.';}
  }catch(error){mediaHelp.textContent='이미지를 읽지 못했어요.';}finally{mediaRegister.disabled=false;}
};
// Metadata can arrive after the first render; redraw when registrations change.
let mediaSnapshot='';const renderBeforeMedia=render;
render=function(){const snapshot=JSON.stringify(state.media||[]);if(snapshot!==mediaSnapshot){mediaSnapshot=snapshot;messageSnapshot='';}renderBeforeMedia();mediaComposer.contentEditable=state.busy?'false':'true';};
