'use strict';
const productName = navigator.language.toLowerCase().startsWith('ko') ? '날도와줘' : 'DailyHelpMe!!';
document.querySelector('meta[name="apple-mobile-web-app-title"]').content = productName;
document.querySelector('meta[name="application-name"]').content = productName;
if (productName === 'DailyHelpMe!!') document.querySelector('link[rel="manifest"]').href = '/manifest-en.webmanifest';
const themeLink = document.createElement('link');
themeLink.rel = 'stylesheet';
document.head.append(themeLink);
const avatar = node('img');
avatar.className = 'companion-avatar';
avatar.alt = '';
document.querySelector('#app header .brand').before(avatar);
const appearanceForm = node('form');
const nameField = node('input');
nameField.maxLength = 30;
nameField.setAttribute('aria-label', '챗봇 이름');
const colorField = node('input');
colorField.type = 'color';
colorField.setAttribute('aria-label', '테마색');
const saveAppearance = node('button', '이름 · 테마 적용');
appearanceForm.append(nameField, colorField, saveAppearance);
$('settings').querySelector('h1').after(node('h2', '이름 · 테마'), appearanceForm,
  node('p', '챗봇 이미지는 맥 앱 설정에서 바꿀 수 있어요.', 'muted'));
let appearanceSnapshot = '', appearanceDirty = false;
nameField.oninput = colorField.oninput = () => appearanceDirty = true;
appearanceForm.onsubmit = async event => {
  event.preventDefault();
  if (await mutate('/api/appearance', {name: nameField.value, color: colorField.value})) {
    appearanceDirty = false;
    toast('이름과 테마를 적용했어요.');
  }
};
function renderAppearance() {
  const settings = state.appearance;
  if (!settings) return;
  if (!appearanceDirty) { nameField.value = settings.name; colorField.value = settings.color; }
  const snapshot = JSON.stringify(settings);
  if (snapshot === appearanceSnapshot) return;
  appearanceSnapshot = snapshot;
  document.title = '날도와줘 · DailyHelpMe!!';
  $('memory-heading').textContent = settings.name + '이(가) 기억하는 나';
  $('thinking').textContent = settings.name + '이(가) 답장을 생각하고 있어요…';
  document.querySelectorAll('.brand').forEach(element => element.textContent = settings.name);
  document.querySelectorAll('#messages .assistant > small').forEach(element => element.textContent = settings.name);
  avatar.src = '/api/avatar?v=' + encodeURIComponent(settings.avatar);
  themeLink.href = '/api/theme.css?v=' + encodeURIComponent(settings.color);
}
const renderBeforeAppearance = render;
render = function() { renderBeforeAppearance(); renderAppearance(); };
// Messages can re-render independently while the appearance stays the same.
const messagesBeforeAppearance = renderMessages;
renderMessages = function(...args) {
  messagesBeforeAppearance(...args);
  document.querySelectorAll('#messages .assistant > small').forEach(element => element.textContent = state.appearance?.name || '봉고캣');
};
renderAppearance();
