'use strict';
// Direct edits remain independent of AI and of the parent's completion state.
const subtaskSection = node('section');
subtaskSection.id = 'subtask-section';
const parentComplete = node('button', '1차 일정 완료');
parentComplete.id = 'parent-complete';
parentComplete.type = 'button';
const subtaskHeading = node('h2', '2차 일정');
const subtaskRows = node('div');
subtaskRows.id = 'subtask-items';
const subtaskInput = node('input');
subtaskInput.id = 'subtask-new';
subtaskInput.maxLength = 500;
subtaskInput.placeholder = '예: 작업을 위해 컴퓨터 켜기';
subtaskInput.setAttribute('aria-label', '새 2차 일정');
const subtaskAdd = node('button', '＋');
subtaskAdd.id = 'subtask-add';
subtaskAdd.type = 'button';
const subtaskAddRow = node('div', undefined, 'subtask-add');
subtaskAddRow.append(subtaskInput, subtaskAdd);
subtaskSection.append(parentComplete, subtaskHeading,
  node('p', '작은 단계로 나눠보세요. 변경은 바로 저장돼요. 모두 체크해도 1차 일정은 직접 완료해야 해요.', 'muted'),
  subtaskRows, subtaskAddRow);
const subtaskHelp = node('p', '1차 일정을 저장하고 다시 열면 2차 일정을 나눌 수 있어요.', 'muted');
$('edit-kind').closest('label').before(subtaskSection, subtaskHelp);
let subtaskSnapshot = '';
const originalOpenEditor = openEditor;
openEditor = function(item = null, kind = 'schedule') {
  originalOpenEditor(item, kind);
  if (state.busy && !item) return;
  parentComplete.disabled = state.busy;
  $('edit-heading').textContent = item ? '1차 일정 상세' : '새로운 1차 일정';
  subtaskSection.hidden = !item;
  subtaskHelp.hidden = !!item;
  subtaskInput.value = '';
  subtaskSnapshot = '';
  subtaskRows.replaceChildren();
  if (item) {
    parentComplete.textContent = done(item) ? '1차 일정 완료 취소' : '1차 일정 완료';
    loadSubtasks(item.id);
  }
};
async function loadSubtasks(parent) {
  try {
    const data = await api('/api/subtasks?parent=' + encodeURIComponent(parent));
    if (editing?.id !== parent || document.activeElement?.closest('#subtask-items')) return;
    renderSubtasks(data.subtasks);
  } catch (error) { toast(error.message); }
}
function renderSubtasks(items) {
  const snapshot = JSON.stringify(items);
  if (snapshot === subtaskSnapshot) return;
  subtaskSnapshot = snapshot;
  subtaskHeading.textContent = '2차 일정 · ' + items.filter(item => item.done).length + '/' + items.length;
  subtaskRows.replaceChildren();
  items.forEach(item => {
    const row = node('div', undefined, 'subtask-row');
    const check = node('input');
    check.type = 'checkbox';
    check.checked = !!item.done;
    check.setAttribute('aria-label', item.title + ' 완료');
    check.onchange = () => subtaskChange('toggle', item.id);
    const title = node('input');
    title.value = item.title;
    title.maxLength = 500;
    title.setAttribute('aria-label', '2차 일정 제목');
    title.onchange = () => subtaskChange('update', item.id, title.value);
    title.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); title.blur(); } };
    row.append(check, title);
    [['↑', 'move', -1], ['↓', 'move', 1], ['×', 'delete', null]].forEach(([text, action, direction]) => {
      const button = node('button', text);
      button.type = 'button';
      button.setAttribute('aria-label', text === '×' ? '2차 일정 삭제' : text === '↑' ? '위로 이동' : '아래로 이동');
      button.onclick = () => subtaskChange(action, item.id, undefined, direction);
      row.append(button);
    });
    subtaskRows.append(row);
  });
}
async function subtaskChange(action, id, title, direction) {
  if (!editing) return false;
  const parent = editing.id;
  try {
    const data = await api('/api/subtask', {parent, action, id, title, direction});
    if (editing?.id === parent) {
      if (action === 'update') subtaskSnapshot = JSON.stringify(data.subtasks);
      else renderSubtasks(data.subtasks);
    }
    return true;
  } catch (error) { toast(error.message); return false; }
}
subtaskAdd.onclick = async () => {
  if (await subtaskChange('add', undefined, subtaskInput.value)) {
    subtaskInput.value = '';
    subtaskInput.focus();
  }
};
subtaskInput.onkeydown = event => { if (event.key === 'Enter') { event.preventDefault(); subtaskAdd.click(); } };
parentComplete.onclick = async () => {
  if (!editing) return;
  const parent = editing.id;
  if (await mutate('/api/toggle', {id: parent})) {
    editing = state.items.find(item => item.id === parent);
    if (editing) parentComplete.textContent = done(editing) ? '1차 일정 완료 취소' : '1차 일정 완료';
  }
};
setInterval(() => {
  if (tab === 'editor' && editing && !document.hidden) {
    const parent = state.items.find(item => item.id === editing.id);
    if (!parent) { editing = null; showTab(previousTab); return; }
    parentComplete.disabled = state.busy;
    parentComplete.textContent = done(parent) ? '1차 일정 완료 취소' : '1차 일정 완료';
    loadSubtasks(editing.id);
  }
}, 2500);
