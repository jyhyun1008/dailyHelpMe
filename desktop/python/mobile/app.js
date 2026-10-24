function itemTitle(item){return item.title+(item.subtask_total?' ('+(item.subtask_done||0)+'/'+item.subtask_total+')':'');}
function appendMessageText(bubble,message) {
  const text=message.content;
  if(message.role!=='assistant'){bubble.textContent=text;return;}
  const pattern=/\[([^\]\n]{1,180})\]\((https?:\/\/[^\s<>()]+)\)/g;
  let start=0;
  for(const match of text.matchAll(pattern)){
    let url;try{url=new URL(match[2]);}catch{continue;}
    if(!['http:','https:'].includes(url.protocol))continue;
    bubble.append(document.createTextNode(text.slice(start,match.index)));
    const link=node('a',match[1]);link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';bubble.append(link);start=match.index+match[0].length;
  }
  bubble.append(document.createTextNode(text.slice(start)));
}
'use strict';
const $ = id => document.getElementById(id);
const dayNames = [...'일월화수목금토'];
let state = {items:[],messages:[],busy:false,profile:'',now:new Date().toISOString(),error:''};
let tab = new URLSearchParams(location.search).get('tab') || localStorage.getItem('doa-tab') || 'today';
let selected = kstDate(new Date()), month = selected.slice(0,7), editing = null, previousTab = 'tasks';
let messageSnapshot = '', profileDirty = false, polling = false, statusTimer;
const kinds = {schedule:'일정',todo:'데드라인',routine:'루틴',bucket:'버킷리스트'};
function node(tag, text, cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
function kstDate(date) { return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(date); }
function weekday(date) { return new Date(date+'T12:00:00+09:00').getUTCDay(); }
function routineDay() { return kstDate(new Date(new Date(state.now).getTime()-5*3600000)); }
function done(item) { return !!item.done || item.kind==='routine' && item.completed_day===routineDay(); }
function atTime(item) { if(item.kind==='routine')return item.time; if(!item.at)return null; const t=item.at.slice(11,16); return item.kind==='schedule'&&t==='05:01'||item.kind==='todo'&&t==='23:59'?null:t; }
function forDate(date) { return state.items.filter(item=>item.kind==='routine'?item.days.includes(weekday(date)):item.at?.slice(0,10)===date).sort((a,b)=>(atTime(a)||'').localeCompare(atTime(b)||'')); }
function detail(item) { if(item.kind==='routine')return (item.days.length===7?'매일':item.days.map(d=>dayNames[d]).join('·'))+' · '+item.time; if(item.at)return (item.carryover?(item.kind==='todo'?'원래 마감 ':'원래 일정 '):'')+item.at.slice(0,10).replaceAll('-','.')+(atTime(item)?' · '+atTime(item):''); return item.kind==='bucket'?'언젠가 하고 싶은 일':'날짜 미정'; }
function toast(text) { $('status').textContent=text; $('status').hidden=false; clearTimeout(statusTimer); statusTimer=setTimeout(()=>$('status').hidden=true,6500); }
async function api(path,data) { const options={credentials:'same-origin',cache:'no-store'}; if(data!==undefined){options.method='POST';options.headers={'Content-Type':'application/json'};options.body=JSON.stringify(data);} const response=await fetch(path,options); const body=await response.json(); if(response.status===401){$('pair').hidden=false;$('app').hidden=true;} if(!response.ok)throw new Error(body.error||'요청을 처리하지 못했어요.'); return body; }
function showTab(next) { if(next==='calendar'&&tab!=='calendar'&&tab!=='editor')calendarMode(false); if(tab==='diary'&&next!=='diary')saveDiary(); if(next==='diary'){if(diaryView==='list')loadDiaryList();else if(!diaryDirty)loadDiary();} if(!['today','chat','calendar','tasks','settings','editor','diary'].includes(next))next='today'; tab=next; document.querySelectorAll('.page').forEach(page=>page.hidden=page.id!==next); document.querySelectorAll('nav button').forEach(button=>button.classList.toggle('active',button.dataset.tab===next)); if(next!=='editor')localStorage.setItem('doa-tab',next); window.scrollTo(0,0); if(next==='chat')requestAnimationFrame(()=>window.scrollTo(0,document.body.scrollHeight)); }
function card(item) { const row=node('div',undefined,'card '+item.kind+(done(item)?' completed':'')); const toggle=node('button',done(item)?'✓':'','toggle'); toggle.type='button';toggle.setAttribute('aria-label',done(item)?'완료 취소':'완료');toggle.disabled=state.busy; toggle.onclick=()=>mutate('/api/toggle',{id:item.id}); const description=node('button',undefined,'description');description.type='button';description.append(node('span',itemTitle(item),'title'),node('small',detail(item)));description.onclick=()=>openEditor(item);row.append(toggle,description);return row; }
function list(container, items, empty='등록된 일정이 없어요.') { container.replaceChildren();if(!items.length)container.append(node('p',empty,'muted'));items.forEach(item=>container.append(card(item))); }
function renderToday() { const date=kstDate(new Date(state.now));$('today-date').textContent=date.replaceAll('-','.')+' '+dayNames[weekday(date)]+'요일';const items=state.todayItems||forDate(date);const carried=items.filter(item=>item.carryover).sort((a,b)=>a.at.localeCompare(b.at));const untimed=items.filter(item=>!item.carryover&&!atTime(item));const timed=items.filter(item=>!item.carryover&&atTime(item));const timeline=$('timeline');timeline.replaceChildren();if(!items.length)timeline.append(node('p','조금 여유로운 하루예요.','muted'));if(carried.length){timeline.append(node('p','이전 미완료','section-label'));carried.forEach(item=>timeline.append(card(item)));}if(untimed.length){timeline.append(node('p','시간 미정','section-label'));untimed.forEach(item=>timeline.append(card(item)));}if(timed.length){timeline.append(node('p','타임라인','section-label'));timed.forEach(item=>{const row=node('div',undefined,'timeline-row');row.append(node('time',atTime(item)),card(item));timeline.append(row);});} }
function renderMessages(prepend=false) { $('more').hidden=!state.hasMoreMessages; const snapshot=JSON.stringify(state.messages);if(snapshot===messageSnapshot)return;const oldHeight=document.body.scrollHeight,oldScroll=window.scrollY;const follow=window.scrollY+innerHeight>=oldHeight-150;const container=$('messages');container.replaceChildren();let date='';state.messages.forEach(message=>{const next=message.created_at.slice(0,10);if(next!==date){container.append(node('div',next.replaceAll('-','.'),'date-label'));date=next;}const row=node('div',undefined,'message '+message.role);if(message.role==='assistant')row.append(node('small',state.appearance?.name||'봉고캣'));const bubble=node('div',undefined,'bubble');appendMessageText(bubble,message);bubble.ondblclick=()=>mutate('/api/confirm',{id:message.id});const mark=node('button',message.bookmarked?'★':'☆','bookmark'+(message.bookmarked?' on':''));mark.type='button';mark.setAttribute('aria-label',message.bookmarked?'북마크 해제':'북마크');mark.onclick=()=>mutate('/api/bookmark',{id:message.id});const meta=node('time',message.created_at.slice(11,16)+(message.confirmed?' · 확인':''));meta.append(mark);row.append(bubble,meta);for(const item of message.created_items||[]){const link=node('button',undefined,'created-item');link.type='button';link.disabled=!item.available;link.append(node('small',item.available?'일정이 생성됐어요 · 상세 보기 ›':'삭제된 일정'),node('span',item.title));link.onclick=()=>{const current=state.items.find(entry=>entry.id===item.id);if(current)openEditor(current);else toast('삭제된 일정이에요.');};row.append(link);}container.append(row);});messageSnapshot=snapshot;if(tab==='chat')requestAnimationFrame(()=>window.scrollTo(0,prepend?oldScroll+document.body.scrollHeight-oldHeight:follow?document.body.scrollHeight:oldScroll)); }
function renderCalendar() { const [year,m]=month.split('-').map(Number);$('month').textContent=year+'년 '+m+'월';const first=new Date(Date.UTC(year,m-1,1));first.setUTCDate(1-first.getUTCDay());const grid=$('days');grid.replaceChildren();for(let i=0;i<42;i++){const day=new Date(first);day.setUTCDate(day.getUTCDate()+i);const iso=day.toISOString().slice(0,10);const button=node('button',undefined,(iso.slice(0,7)!==month?'outside ':'')+(iso===selected?'selected':''));button.setAttribute('aria-label',iso);button.setAttribute('aria-pressed',String(iso===selected));button.append(node('span',String(day.getUTCDate()),'number'));const dots=node('span',undefined,'dots');[...new Set(forDate(iso).filter(item=>!item.done).map(item=>item.kind))].slice(0,3).forEach(kind=>dots.append(node('i',undefined,'dot '+kind)));button.append(dots);button.onclick=()=>{selected=iso;month=iso.slice(0,7);renderCalendar();};grid.append(button);}$('selected-day').textContent=selected.slice(5).replace('-','월 ')+'일 '+dayNames[weekday(selected)]+'요일';list($('day-items'),forDate(selected)); if(weekMode)renderWeek(); }
let bookmarkSnapshot='';
function renderBookmarks() { const bookmarks=state.bookmarks||[];const snapshot=JSON.stringify([bookmarks,state.appearance?.name]);if(snapshot===bookmarkSnapshot)return;bookmarkSnapshot=snapshot;$('bookmark-summary').textContent='★ 북마크 '+bookmarks.length+'개';const container=$('bookmark-list');container.replaceChildren();if(!bookmarks.length)container.append(node('p','대화에서 말풍선 옆 ☆를 눌러 북마크해보세요.','muted'));bookmarks.forEach(bookmark=>{const entry=node('div',undefined,'bookmark-entry');const head=node('small',(bookmark.role==='user'?'나':state.appearance?.name||'봉고캣')+' · '+bookmark.created_at.slice(0,16).replace('T',' ').replaceAll('-','.'));const remove=node('button','해제');remove.type='button';remove.onclick=()=>mutate('/api/bookmark',{id:bookmark.id});head.append(remove);entry.append(head,node('p',bookmark.content));container.append(entry);}); }
function render(prepend=false) { renderPush(); renderBookmarks(); $('web-search').checked=state.webSearchEnabled!==false; $('diary-generate').disabled=state.busy;$('draft-status').textContent=(state.diaryDraft?state.diaryDraft.date+' · ':'')+(state.diaryDraftStatus||'');$('draft-panel').hidden=!state.diaryDraft;if($('draft-preview').value!==(state.diaryDraft?.content||''))$('draft-preview').value=state.diaryDraft?.content||''; renderToday();renderMessages(prepend);renderCalendar();const kind=$('filter').value;list($('task-items'),state.items.filter(item=>(!kind||kind===item.kind)&&($('done').checked||!done(item))),'떠오르는 할 일을 적어두세요.');$('thinking').hidden=!state.busy;$('send').disabled=state.busy;$('retry').hidden=!state.error;$('retry').disabled=state.busy;document.querySelectorAll('[data-new],#new-on-date,#edit-form button,#delete-item,#profile-form button').forEach(button=>button.disabled=state.busy);if(!profileDirty)$('profile').value=state.profile;if(state.error)$('thinking').hidden=true;$('chat-error').textContent=state.error||'';$('chat-error').hidden=!state.error;$('push-error').textContent=state.pushError||'';$('push-error').hidden=!state.pushError; }
async function refresh(prepend=false) {
  if(polling)return;
  polling=true;$('more').disabled=true;
  try {
    const before=prepend?state.messages[0]?.id:null;
    const incoming=await api('/api/state'+(before?'?before='+before:''));
    if(prepend) {
      state={...incoming,messages:[...incoming.messages,...state.messages]};
    } else {
      const first=incoming.messages[0]?.id;
      const older=first?state.messages.filter(message=>message.id<first):[];
      state={...incoming,messages:[...older,...incoming.messages],hasMoreMessages:older.length?state.hasMoreMessages:incoming.hasMoreMessages};
    }
    $('pair').hidden=true;$('app').hidden=false;render(prepend);
  } catch(error) {
    if(!$('app').hidden)toast('맥에 연결하지 못했어요. Tailscale과 맥 앱을 확인해주세요.');
  } finally { polling=false;$('more').disabled=false; }
}
async function mutate(path,data) { try{await api(path,data);await refresh();return true;}catch(error){toast(error.message);return false;} }
function editorFields() { const kind=$('edit-kind').value;const dated=kind==='schedule'||kind==='todo'&&$('has-date').checked;$('deadline-row').hidden=kind!=='todo';$('date-row').hidden=!dated;$('all-day-row').hidden=!dated;$('time-row').hidden=kind!=='routine'&&(!dated||$('all-day').checked);$('repeat-row').hidden=kind!=='routine'; }
function openEditor(item=null,kind='schedule') { if(state.busy&&!item){toast('답장을 받은 뒤 추가해주세요.');return;}previousTab=tab;editing=item;$('edit-heading').textContent=item?'할 일 수정':'새로운 할 일';$('edit-title').value=item?.title||'';$('edit-kind').value=item?.kind||kind;$('edit-kind').disabled=!!item;$('has-date').checked=!!item?.at;$('edit-date').value=item?.at?.slice(0,10)||(tab==='calendar'?selected:kstDate(new Date(state.now)));$('all-day').checked=!item||!atTime(item);$('edit-time').value=atTime(item||{})||'09:00';$('delete-item').hidden=!item;$('delete-item').textContent='삭제';$('delete-item').dataset.confirm='';$('repeat-days').replaceChildren();dayNames.forEach((name,i)=>{const label=node('label',name);const box=document.createElement('input');box.type='checkbox';box.value=String(i);box.checked=item?item.days.includes(i):true;label.append(box);$('repeat-days').append(label);});editorFields();showTab('editor'); }
$('pair-form').onsubmit=async event=>{event.preventDefault();try{await api('/api/pair',{code:$('code').value});$('code').value='';await refresh();showTab(tab);}catch(error){toast(error.message);}};
$('chat-form').onsubmit=async event=>{event.preventDefault();const text=$('message').value.trim();if(!text||state.busy)return;if(await mutate('/api/chat',{text}))$('message').value='';};
$('message').onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();$('chat-form').requestSubmit();}};
$('retry').onclick=()=>mutate('/api/retry',{});
$('more').onclick=()=>refresh(true);
$('profile').oninput=()=>profileDirty=true;
$('profile-form').onsubmit=async event=>{event.preventDefault();if(await mutate('/api/profile',{profile:$('profile').value})){profileDirty=false;toast('기억을 저장했어요.');}};
$('edit-kind').onchange=editorFields;$('has-date').onchange=editorFields;$('all-day').onchange=editorFields;
$('cancel-edit').onclick=()=>showTab(previousTab);
$('edit-form').onsubmit=async event=>{event.preventDefault();const kind=$('edit-kind').value;const time=$('edit-time').value;const dated=kind==='schedule'||kind==='todo'&&$('has-date').checked;const operation={action:editing?'update':'add',kind,id:editing?.id||null,title:$('edit-title').value,at:dated?$('edit-date').value+'T'+($('all-day').checked?(kind==='todo'?'23:59':'05:01'):time)+':00+09:00':null,days:kind==='routine'?[...document.querySelectorAll('#repeat-days input:checked')].map(box=>Number(box.value)):null,time:kind==='routine'?time:null};if(await mutate('/api/item',{operation}))showTab(previousTab);};
$('delete-item').onclick=async()=>{if(!$('delete-item').dataset.confirm){$('delete-item').dataset.confirm='1';$('delete-item').textContent='한 번 더 누르면 삭제돼요';return;}if(await mutate('/api/delete',{id:editing.id}))showTab(previousTab);};
$('logout').onclick=async()=>{if(await mutate('/api/logout',{})){state={items:[],messages:[],profile:'',busy:false};messageSnapshot='';location.reload();}};
function moveMonth(delta) { if(weekMode){selected=addDays(selected,delta*7);month=selected.slice(0,7);renderCalendar();return;} const [year,m]=month.split('-').map(Number);month=new Date(Date.UTC(year,m-1+delta,1)).toISOString().slice(0,7);renderCalendar(); }
$('prev').onclick=()=>moveMonth(-1);$('next').onclick=()=>moveMonth(1);$('cal-today').onclick=()=>{selected=kstDate(new Date(state.now));month=selected.slice(0,7);renderCalendar();};
$('filter').onchange=render;$('done').onchange=render;$('settings-open').onclick=()=>showTab('settings');
document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>showTab(button.dataset.tab));document.querySelectorAll('[data-new]').forEach(button=>button.onclick=()=>openEditor(null,button.dataset.new));$('new-on-date').onclick=()=>openEditor();
function keyBytes(value){const text=atob(value.replaceAll('-','+').replaceAll('_','/'));return Uint8Array.from(text,char=>char.charCodeAt(0));}
let pushBusy=false;
function renderPush() {
  const enabled=state.pushSubscribed===true&&'Notification'in window&&Notification.permission==='granted';
  $('push').hidden=enabled;$('push-test').hidden=!enabled;
  $('push').disabled=pushBusy;$('push-test').disabled=pushBusy;
  $('push-help').textContent=enabled?'이 기기의 알림이 켜졌어요.':matchMedia('(display-mode: standalone)').matches?'아래 버튼을 눌러 알림을 허용해주세요.':'Safari에서 공유 → 홈 화면에 추가 후 홈 화면 앱을 열어주세요.';
}
async function registerPush(requestPermission=false) {
  if(!isSecureContext)throw new Error('알림은 Tailscale HTTPS 주소에서 켤 수 있어요.');
  if(!('serviceWorker'in navigator)||!('PushManager'in window)||!('Notification'in window))throw new Error('아이폰·아이패드는 홈 화면에 추가한 뒤 그 앱에서 다시 열어주세요.');
  if(requestPermission&&await Notification.requestPermission()!=='granted')throw new Error('기기 설정에서 알림을 허용해주세요.');
  if(Notification.permission!=='granted')return;
  await navigator.serviceWorker.register('/sw.js');
  const registration=await navigator.serviceWorker.ready;
  const {publicKey}=await api('/api/push/key');
  let subscription=await registration.pushManager.getSubscription();
  const key=keyBytes(publicKey);
  if(subscription?.options.applicationServerKey&&String(new Uint8Array(subscription.options.applicationServerKey))!==String(key)){await subscription.unsubscribe();subscription=null;}
  if(!subscription&& !requestPermission)return;
  subscription=subscription||await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:key});
  await api('/api/push/subscribe',{subscription:subscription.toJSON()});
  state.pushSubscribed=true;renderPush();
}
$('push').onclick=async()=>{pushBusy=true;renderPush();try{await registerPush(true);toast('알림을 켰어요. 테스트 알림으로 확인해보세요.');await refresh();}catch(error){toast(error.message);}finally{pushBusy=false;renderPush();}};
$('push-test').onclick=async()=>{pushBusy=true;renderPush();try{await api('/api/push/test',{});toast('테스트 알림을 요청했어요.');}catch(error){toast(error.message);}finally{await refresh();pushBusy=false;renderPush();}};
let weekScrollReady=false;
let weekMode=false;
function addDays(day, delta){const d=new Date(day+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+delta);return d.toISOString().slice(0,10);}
function renderWeek(){const oldTop=$('week-view').scrollTop,oldLeft=$('week-view').scrollLeft;const start=addDays(selected,-weekday(selected));$('month').textContent=start.slice(5).replace('-','.')+' – '+addDays(start,6).slice(5).replace('-','.');const grid=node('div',undefined,'week-grid');grid.append(node('span','시간','week-sticky'));for(let i=0;i<7;i++){const day=addDays(start,i);const b=node('button',dayNames[i]+' '+Number(day.slice(-2)),'week-sticky');b.onclick=()=>{selected=day;renderCalendar();};grid.append(b);}grid.append(node('small','시간 미지정','week-untimed-label'));for(let i=0;i<7;i++){const cell=node('div');forDate(addDays(start,i)).filter(item=>!atTime(item)).forEach(item=>{const b=node('button',itemTitle(item),'week-event '+item.kind);b.onclick=()=>openEditor(item);cell.append(b);});grid.append(cell);}for(let h=0;h<24;h++){grid.append(node('small',String(h).padStart(2,'0')+':00'));for(let i=0;i<7;i++){const cell=node('div');forDate(addDays(start,i)).filter(item=>atTime(item)&&Number(atTime(item).slice(0,2))===h).forEach(item=>{const b=node('button',atTime(item)+' '+itemTitle(item),'week-event '+item.kind);b.onclick=()=>openEditor(item);cell.append(b);});grid.append(cell);}}$('week-view').replaceChildren(grid);$('week-view').scrollTop=weekScrollReady?oldTop:Math.max(0,(new Date(state.now).getUTCHours()+9)%24-3)*50;weekScrollReady=true;$('week-view').scrollLeft=oldLeft;}
function calendarMode(weekly){if(!weekly)weekScrollReady=false;weekMode=weekly;localStorage.setItem('doa-week',weekly?'1':'0');$('month-view').hidden=weekly;$('week-view').hidden=!weekly;$('prev').setAttribute('aria-label',weekly?'이전 주':'이전 달');$('next').setAttribute('aria-label',weekly?'다음 주':'다음 달');renderCalendar();}
$('month-mode').onclick=()=>calendarMode(false);$('week-mode').onclick=()=>calendarMode(true);
let diaryView='list',diaryDay=kstDate(new Date()),diaryLoaded=false,diaryDirty=false,diaryTimer,diaryQueue=Promise.resolve(),diaryRevision=0;
$('diary-date').value=diaryDay;
function diaryFields(disabled){['diary-title','diary-weather','diary-mood','diary-tags','diary-content','diary-save'].forEach(id=>$(id).disabled=disabled);}
function fillChoice(select,placeholder,options,value){select.replaceChildren(node('option',placeholder));select.firstChild.value='';[...options,...(value&&!options.includes(value)?[value]:[])].forEach(option=>select.append(node('option',option)));select.value=value;}
function setDiaryView(view){diaryView=view;$('diary-browse').hidden=view!=='list';$('diary-editor').hidden=view!=='editor';window.scrollTo(0,0);}
async function loadDiaryList(){try{const tag=$('diary-tag-filter').value;const {entries,tags}=await api('/api/diary/list'+(tag?'?tag='+encodeURIComponent(tag):''));const filter=$('diary-tag-filter');filter.replaceChildren(node('option','모든 태그'));filter.firstChild.value='';tags.forEach(([name,count])=>{const option=node('option','#'+name+'  ('+count+')');option.value=name;filter.append(option);});filter.value=tags.some(([name])=>name===tag)?tag:'';filter.hidden=!tags.length;const container=$('diary-entries');container.replaceChildren();if(!entries.length)container.append(node('p','아직 쓴 일기가 없어요. ＋를 눌러 날짜를 고르고 써보세요.','muted'));entries.forEach(entry=>{const card=node('button',undefined,'diary-entry');card.type='button';const icons=[entry.weather,entry.mood].filter(Boolean).map(value=>value.split(' ')[0]).join(' ');card.append(node('small',entry.date.replaceAll('-','.')+' '+dayNames[weekday(entry.date)]+(icons?'   '+icons:'')),node('strong',entry.title||'제목 없음'));if(entry.preview)card.append(node('span',entry.preview+(entry.preview.length>=90?'…':'')));if(entry.tags.length)card.append(node('span',entry.tags.map(tag=>'#'+tag).join(' '),'entry-tags'));card.onclick=()=>openDiary(entry.date);container.append(card);});}catch(error){toast(error.message);}}
async function openDiary(day){if(diaryDirty&&!(await saveDiary()))return false;diaryDay=day;$('diary-date').value=day;setDiaryView('editor');await loadDiary();return true;}
async function loadDiary(){diaryLoaded=false;diaryFields(true);try{const {entry,weathers,moods}=await api('/api/diary?date='+diaryDay);$('diary-title').value=entry?.title||'';$('diary-content').value=entry?.content||'';fillChoice($('diary-weather'),'날씨',weathers,entry?.weather||'');fillChoice($('diary-mood'),'기분',moods,entry?.mood||'');$('diary-tags').value=(entry?.tags||[]).join(', ');diaryLoaded=true;diaryDirty=false;diaryFields(false);$('diary-status').textContent=entry?'저장된 일기':'오늘의 이야기를 적어보세요.';$('diary-delete').dataset.confirm='';$('diary-delete').textContent='이 날짜 일기 삭제';}catch(error){toast(error.message);}}
function saveDiary(){if(!diaryLoaded)return Promise.resolve(false);clearTimeout(diaryTimer);if(!diaryDirty)return diaryQueue;const revision=diaryRevision;const data={date:diaryDay,title:$('diary-title').value,content:$('diary-content').value,weather:$('diary-weather').value,mood:$('diary-mood').value,tags:$('diary-tags').value};diaryQueue=diaryQueue.then(async()=>{try{await api('/api/diary',data);if(revision===diaryRevision){diaryDirty=false;$('diary-status').textContent='맥에 저장했어요.';}return true;}catch(error){$('diary-status').textContent='저장하지 못했어요. 연결을 확인하고 다시 저장해주세요.';return false;}});return diaryQueue;}
function diaryChanged(){diaryDirty=true;diaryRevision++;$('diary-status').textContent='저장 중…';clearTimeout(diaryTimer);diaryTimer=setTimeout(saveDiary,700);}
$('diary-title').oninput=diaryChanged;$('diary-tags').oninput=diaryChanged;$('diary-weather').onchange=diaryChanged;$('diary-mood').onchange=diaryChanged;$('diary-content').oninput=diaryChanged;$('diary-save').onclick=saveDiary;
$('diary-new').onclick=async()=>{if(await openDiary(kstDate(new Date()))){$('diary-date').focus();try{$('diary-date').showPicker();}catch{}}};
$('diary-back').onclick=async()=>{if(diaryDirty&&!(await saveDiary()))return;setDiaryView('list');await loadDiaryList();};
$('diary-tag-filter').onchange=loadDiaryList;
$('diary-date').onchange=async()=>{const next=$('diary-date').value;if(!next)return;if(diaryDirty&&!(await saveDiary())){$('diary-date').value=diaryDay;return;}diaryDay=next;await loadDiary();};
$('diary-delete').onclick=async()=>{if(!$('diary-delete').dataset.confirm){$('diary-delete').dataset.confirm='1';$('diary-delete').textContent='한 번 더 누르면 삭제돼요';return;}clearTimeout(diaryTimer);await diaryQueue;try{await api('/api/diary/delete',{date:diaryDay});diaryDirty=false;setDiaryView('list');await loadDiaryList();}catch(error){toast(error.message);}};
document.querySelectorAll('a[download]').forEach(link=>link.onclick=async event=>{event.preventDefault();if(diaryDirty&&!(await saveDiary()))return;location.assign(link.href);});
$('diary-generate').onclick=async()=>{if(diaryDirty&&!(await saveDiary()))return;await mutate('/api/diary/draft',{date:diaryDay});};
$('draft-apply').onclick=async()=>{if(diaryDirty&&!(await saveDiary()))return;const day=state.diaryDraft?.date;if(await mutate('/api/diary/draft/apply',{})){if(day){diaryDay=day;$('diary-date').value=day;}setDiaryView('editor');await loadDiary();}};
$('draft-dismiss').onclick=()=>mutate('/api/diary/draft/dismiss',{});
window.addEventListener('beforeunload',event=>{if(diaryDirty){event.preventDefault();event.returnValue='';}});
calendarMode(weekMode);
if('serviceWorker'in navigator){navigator.serviceWorker.register('/sw.js').catch(()=>{});navigator.serviceWorker.addEventListener('message',event=>{if(event.data?.type==='open-chat'){showTab('chat');refresh();}});}
renderPush();
registerPush().then(()=>refresh()).catch(()=>{});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});window.addEventListener('online',()=>refresh());setInterval(()=>{if(!document.hidden&&!$('app').hidden)refresh();},2500);showTab(tab);refresh();

$('calendar-diary').onclick=async()=>{if(diaryDirty&&!(await saveDiary())){showTab('diary');return;}diaryDay=selected;$('diary-date').value=selected;diaryLoaded=false;setDiaryView('editor');showTab('diary');};

$('web-search').onchange=async()=>{if(!await mutate('/api/search/settings',{enabled:$('web-search').checked}))$('web-search').checked=state.webSearchEnabled!==false;};
