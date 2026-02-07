// State
let currentPrompt = null;
let chatHistory = [];
let chatStreaming = false;
let viewMode = 'template'; // 'template' or 'materialized'

// Elements
const promptSelect = document.getElementById('prompt-select');
const modelSelect = document.getElementById('model-select');
const editor = document.getElementById('editor');
const materializedView = document.getElementById('materialized-view');
const runBtn = document.getElementById('run-btn');
const prBtn = document.getElementById('pr-btn');
const varsBtn = document.getElementById('vars-btn');
const varsPanel = document.getElementById('variables-panel');
const varList = document.getElementById('var-list');
const outputPanel = document.getElementById('output-panel');
const outputContent = document.getElementById('output-content');
const fabBtn = document.getElementById('fab-btn');
const chatPanel = document.getElementById('chat-panel');
const chatClose = document.getElementById('chat-close');
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('chat-input');
const chatSend = document.getElementById('chat-send');
const toggleTemplate = document.getElementById('toggle-template');
const toggleMaterialized = document.getElementById('toggle-materialized');
const varsClose = document.getElementById('vars-close');

// Load prompt list on startup
async function loadPrompts() {
  const res = await fetch('/api/prompts');
  const prompts = await res.json();
  prompts.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.name;
    opt.textContent = p.name;
    promptSelect.appendChild(opt);
  });
}

// Load a specific prompt
async function loadPrompt(name) {
  if (!name) {
    currentPrompt = null;
    editor.value = '';
    varList.innerHTML = '';
    runBtn.disabled = true;
    prBtn.disabled = true;
    return;
  }
  const res = await fetch(`/api/prompts/${name}`);
  const data = await res.json();
  currentPrompt = data;
  editor.value = data.content;
  runBtn.disabled = false;
  prBtn.disabled = false;
  renderVariables(data.variables, data.defaults);
}

// Render variable inputs
function renderVariables(variables, defaults) {
  varList.innerHTML = '';
  variables.forEach(v => {
    const group = document.createElement('div');
    group.className = 'var-group';

    const label = document.createElement('label');
    label.textContent = v;

    const wrapper = document.createElement('div');
    wrapper.className = 'var-input-wrapper';

    const input = document.createElement('textarea');
    input.rows = 1;
    input.dataset.var = v;
    input.value = defaults[v] || '';

    // Auto-resize to fit content
    const autoResize = () => {
      input.style.height = 'auto';
      input.style.height = input.scrollHeight + 'px';
    };
    input.addEventListener('input', () => { autoResize(); updateMaterialized(); });

    const clearBtn = document.createElement('button');
    clearBtn.className = 'var-clear';
    clearBtn.textContent = '\u00d7';
    clearBtn.onclick = () => { input.value = ''; autoResize(); updateMaterialized(); };

    wrapper.appendChild(input);
    wrapper.appendChild(clearBtn);
    group.appendChild(label);
    group.appendChild(wrapper);
    varList.appendChild(group);
  });
}

// Resize all var textareas (call when panel becomes visible)
function resizeAllVars() {
  varList.querySelectorAll('textarea[data-var]').forEach(ta => {
    ta.style.height = 'auto';
    ta.style.height = ta.scrollHeight + 'px';
  });
}

// Gather current variable values
function getVariables() {
  const vars = {};
  varList.querySelectorAll('textarea[data-var]').forEach(input => {
    vars[input.dataset.var] = input.value;
  });
  return vars;
}

// View toggle
function setViewMode(mode) {
  viewMode = mode;
  toggleTemplate.classList.toggle('active', mode === 'template');
  toggleMaterialized.classList.toggle('active', mode === 'materialized');
  if (mode === 'template') {
    editor.style.display = '';
    materializedView.style.display = 'none';
  } else {
    editor.style.display = 'none';
    materializedView.style.display = '';
    updateMaterialized();
  }
}

function updateMaterialized() {
  if (viewMode !== 'materialized') return;
  let rendered = editor.value;
  const vars = getVariables();
  for (const [key, val] of Object.entries(vars)) {
    rendered = rendered.replaceAll(`{${key}}`, val);
  }
  materializedView.textContent = rendered;
}

// Variables panel toggle
function toggleVars() {
  varsPanel.classList.toggle('open');
  if (varsPanel.classList.contains('open')) {
    requestAnimationFrame(resizeAllVars);
  }
}

// SSE stream reader
async function readStream(response, onText, onDone) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete line

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const payload = line.slice(6);
        if (payload === '[DONE]') {
          if (onDone) onDone();
          return;
        }
        try {
          const data = JSON.parse(payload);
          if (data.text) onText(data.text);
        } catch (e) {
          // skip invalid JSON
        }
      }
    }
  }
  if (onDone) onDone();
}

// Run prompt
async function runPrompt() {
  if (!currentPrompt) return;

  runBtn.disabled = true;
  runBtn.textContent = 'Running...';
  outputContent.textContent = '';
  outputPanel.classList.add('visible');

  try {
    const res = await fetch(`/api/prompts/${currentPrompt.name}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        variables: getVariables(),
        content: editor.value,
        model: modelSelect.value,
      }),
    });

    await readStream(res, text => {
      outputContent.textContent += text;
      outputPanel.scrollTop = outputPanel.scrollHeight;
    });
  } catch (e) {
    outputContent.textContent = `Error: ${e.message}`;
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = 'Run';
  }
}

// Save & PR
async function saveAndPR() {
  if (!currentPrompt) return;

  prBtn.disabled = true;
  prBtn.textContent = 'Creating PR...';

  try {
    const res = await fetch(`/api/prompts/${currentPrompt.name}/pr`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: editor.value }),
    });

    if (!res.ok) {
      const err = await res.json();
      showNotification(err.detail || 'Failed to create PR', 'error');
      return;
    }

    const data = await res.json();
    showNotification(`PR created: <a href="${data.pr_url}" target="_blank">${data.pr_url}</a>`, 'success');
  } catch (e) {
    showNotification(`Error: ${e.message}`, 'error');
  } finally {
    prBtn.disabled = false;
    prBtn.textContent = 'Save & PR';
  }
}

// Notifications
function showNotification(html, type) {
  const notif = document.getElementById('notification');
  const text = document.getElementById('notification-text');
  notif.className = `notification visible ${type}`;
  text.innerHTML = html;
}

function hideNotification() {
  document.getElementById('notification').classList.remove('visible');
}

// Chat
function toggleChat() {
  chatPanel.classList.toggle('open');
}

function renderChatMessage(role, content) {
  const msg = document.createElement('div');
  msg.className = 'chat-message';

  const roleEl = document.createElement('div');
  roleEl.className = 'role';
  roleEl.textContent = role === 'user' ? 'You' : 'Claude';

  const bodyEl = document.createElement('div');
  bodyEl.className = 'body';

  msg.appendChild(roleEl);
  msg.appendChild(bodyEl);
  chatMessages.appendChild(msg);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  return bodyEl;
}

// Parse edit blocks from chat response and add Apply buttons
function parseAndRenderEdits(bodyEl) {
  const text = bodyEl.textContent;
  const editRegex = /<<<EDIT>>>\s*<<<OLD>>>\s*([\s\S]*?)\s*<<<NEW>>>\s*([\s\S]*?)\s*<<<END>>>/g;

  let match;
  const edits = [];
  while ((match = editRegex.exec(text)) !== null) {
    edits.push({ old: match[1].trim(), new: match[2].trim(), full: match[0] });
  }

  if (edits.length === 0) return;

  // Rebuild body with apply buttons
  let html = escapeHtml(text);
  edits.forEach((edit, i) => {
    const escapedFull = escapeHtml(edit.full);
    const btnHtml = ` <button class="apply-btn" data-edit-idx="${i}">Apply</button>`;
    html = html.replace(escapedFull, escapedFull + btnHtml);
  });
  bodyEl.innerHTML = html;

  // Attach click handlers
  bodyEl.querySelectorAll('.apply-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const idx = parseInt(btn.dataset.editIdx);
      const edit = edits[idx];
      const currentContent = editor.value;
      if (currentContent.includes(edit.old)) {
        editor.value = currentContent.replace(edit.old, edit.new);
        btn.textContent = 'Applied';
        btn.classList.add('applied');
        btn.disabled = true;
        editor.classList.add('flash-highlight');
        setTimeout(() => editor.classList.remove('flash-highlight'), 1500);
      } else {
        btn.textContent = 'Not found';
        btn.disabled = true;
      }
    });
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

async function sendChat() {
  const text = chatInput.value.trim();
  if (!text || chatStreaming) return;

  chatInput.value = '';
  chatStreaming = true;
  chatSend.disabled = true;

  chatHistory.push({ role: 'user', content: text });
  renderChatMessage('user', text);
  // Set the user message body text
  chatMessages.lastChild.querySelector('.body').textContent = text;

  const bodyEl = renderChatMessage('assistant', '');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: chatHistory,
        prompt_content: editor.value,
      }),
    });

    let fullText = '';
    await readStream(res, chunk => {
      fullText += chunk;
      bodyEl.textContent = fullText;
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }, () => {
      chatHistory.push({ role: 'assistant', content: fullText });
      parseAndRenderEdits(bodyEl);
    });
  } catch (e) {
    bodyEl.textContent = `Error: ${e.message}`;
  } finally {
    chatStreaming = false;
    chatSend.disabled = false;
  }
}

// Event listeners
promptSelect.addEventListener('change', () => loadPrompt(promptSelect.value));
runBtn.addEventListener('click', runPrompt);
prBtn.addEventListener('click', saveAndPR);
varsBtn.addEventListener('click', toggleVars);
varsClose.addEventListener('click', toggleVars);
toggleTemplate.addEventListener('click', () => setViewMode('template'));
toggleMaterialized.addEventListener('click', () => setViewMode('materialized'));
editor.addEventListener('input', updateMaterialized);
fabBtn.addEventListener('click', toggleChat);
chatClose.addEventListener('click', toggleChat);
chatSend.addEventListener('click', sendChat);
chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
});

// Init
loadPrompts();
