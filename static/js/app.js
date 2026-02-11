const EXAMPLES = {
    fibonacci: `def fibonacci(n):
    a, b = 0, 1
    for i in range(n):
        a, b = b, a + b
    return a

result = fibonacci(6)
print(result)`,

    bubblesort: `def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr

data = [64, 34, 25, 12, 22]
sorted_data = bubble_sort(data)
print(sorted_data)`,

    factorial: `def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

result = factorial(5)
print(result)`,

    binary_search: `def binary_search(arr, target):
    low = 0
    high = len(arr) - 1
    while low <= high:
        mid = (low + high) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1

data = [2, 5, 8, 12, 16, 23, 38, 45, 67, 91]
index = binary_search(data, 23)
print(index)`,
};

function loadExample(name) {
    document.getElementById('code-input').value = EXAMPLES[name];
}

function setLoading(active, text = 'Executing code...') {
    const el = document.getElementById('loading');
    const textEl = document.getElementById('loading-text');
    el.className = active ? 'loading active' : 'loading';
    textEl.textContent = text;
    document.getElementById('btn-trace').disabled = active;
    document.getElementById('btn-explain').disabled = active;
}

async function runTrace() {
    const code = document.getElementById('code-input').value;
    if (!code.trim()) return;

    setLoading(true, 'Executing and tracing code...');
    try {
        const resp = await fetch('/api/trace', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code }),
        });
        const data = await resp.json();

        if (data.error && typeof data.error === 'string') {
            alert(data.error);
            return;
        }

        renderTrace(data);
        document.getElementById('explanation-panel').innerHTML =
            '<div style="color: var(--text-muted); font-size: 0.85rem;">Click "Trace + Explain" to generate AI-powered explanations.</div>';
        document.getElementById('explanation-depth').textContent = '';
        document.getElementById('raw-json').textContent = JSON.stringify(data, null, 2);
        document.getElementById('prompt-preview').textContent = '';
        document.getElementById('results').style.display = 'grid';
        document.getElementById('debug-section').classList.remove('hidden');
    } catch (e) {
        alert('Request failed: ' + e.message);
    } finally {
        setLoading(false);
    }
}

async function runExplain() {
    const code = document.getElementById('code-input').value;
    const depth = document.getElementById('depth').value;
    if (!code.trim()) return;

    setLoading(true, 'Executing code and generating AI explanation...');
    try {
        const resp = await fetch('/api/explain', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code, depth }),
        });
        const data = await resp.json();

        if (data.error && typeof data.error === 'string') {
            alert(data.error);
            return;
        }

        renderTrace(data.trace);
        renderExplanation(data);
        document.getElementById('raw-json').textContent = JSON.stringify(data.trace, null, 2);
        document.getElementById('prompt-preview').textContent = data.prompt_preview || '';
        document.getElementById('results').style.display = 'grid';
        document.getElementById('debug-section').classList.remove('hidden');
    } catch (e) {
        alert('Request failed: ' + e.message);
    } finally {
        setLoading(false);
    }
}

function renderTrace(trace) {
    const panel = document.getElementById('trace-panel');
    const status = document.getElementById('trace-status');

    if (trace.error) {
        status.innerHTML = `<span class="status-badge error">${trace.error.type}</span>`;
    } else if (trace.truncated) {
        status.innerHTML = `<span class="status-badge truncated">Truncated (${trace.step_count} steps)</span>`;
    } else {
        status.innerHTML = `<span class="status-badge success">${trace.step_count} steps</span>`;
    }

    let html = '';

    for (const step of trace.steps) {
        const hasChanges = step.changes &&
            (Object.keys(step.changes.created || {}).length > 0 ||
             Object.keys(step.changes.updated || {}).length > 0 ||
             Object.keys(step.changes.deleted || {}).length > 0);
        const hasControl = !!step.control_flow;

        let classes = 'trace-step';
        if (hasChanges) classes += ' has-changes';
        if (hasControl) classes += ' has-control-flow';

        html += `<div class="${classes}">`;
        html += `<div class="step-header">`;
        html += `<span class="step-number">Step ${step.step}</span>`;
        html += `<span class="step-event">${step.event}</span>`;
        html += `</div>`;
        html += `<div class="step-source"><span class="line-num">${step.line_number}</span>${escapeHtml(step.source_line)}</div>`;

        if (step.changes) {
            const c = step.changes;
            for (const [name, val] of Object.entries(c.created || {})) {
                html += `<div class="var-change var-created">+ ${name} = ${formatValue(val)}</div>`;
            }
            for (const [name, info] of Object.entries(c.updated || {})) {
                html += `<div class="var-change var-updated">~ ${name}: ${formatValue(info.from)} → ${formatValue(info.to)}</div>`;
            }
            for (const [name, val] of Object.entries(c.deleted || {})) {
                html += `<div class="var-change var-deleted">- ${name} (was ${formatValue(val)})</div>`;
            }
        }

        if (step.control_flow) {
            const cf = step.control_flow;
            let cfText = '';
            switch (cf.type) {
                case 'function_call':
                    cfText = `→ call ${cf.function}() [depth: ${cf.call_depth}]`;
                    break;
                case 'function_return':
                    cfText = `← return from ${cf.function}(): ${formatValue(cf.return_value)}`;
                    break;
                case 'conditional':
                    cfText = `? ${cf.expression}`;
                    break;
                case 'loop':
                    cfText = `↻ ${cf.expression}`;
                    break;
                case 'exception':
                    cfText = `✗ ${cf.exception_type}: ${cf.exception_message}`;
                    break;
                case 'return_statement':
                    cfText = `↩ ${cf.expression}`;
                    break;
            }
            if (cfText) {
                html += `<div class="control-flow-info">${escapeHtml(cfText)}</div>`;
            }
        }

        html += `</div>`;
    }

    if (trace.error) {
        html += `<div class="error-box">${escapeHtml(trace.error.type)}: ${escapeHtml(trace.error.message)}</div>`;
    }

    if (trace.steps.length === 0 && !trace.error) {
        html = '<div style="color: var(--text-muted);">No execution steps captured.</div>';
    }

    panel.innerHTML = html;
}

function renderExplanation(data) {
    const panel = document.getElementById('explanation-panel');
    const depthEl = document.getElementById('explanation-depth');

    if (data.ai_error) {
        panel.innerHTML = `<div class="error-box">${escapeHtml(data.ai_error)}</div>`;
        depthEl.textContent = '';
        return;
    }

    if (!data.explanation) {
        panel.innerHTML = '<div style="color: var(--text-muted);">No explanation generated.</div>';
        depthEl.textContent = '';
        return;
    }

    const expl = data.explanation;
    depthEl.innerHTML = `<span class="status-badge success">${expl.depth || 'intermediate'}</span>`;

    let html = '';

    if (expl.summary) {
        html += `<div class="explanation-summary">${escapeHtml(expl.summary)}</div>`;
    }

    if (expl.step_explanations) {
        for (const se of expl.step_explanations) {
            html += `<div class="explanation-step">`;
            html += `<div class="explanation-step-header">Step ${se.step} · Line ${se.line}</div>`;
            html += `<div class="explanation-text">${escapeHtml(se.explanation)}</div>`;
            html += `</div>`;
        }
    }

    if (expl.key_concepts && expl.key_concepts.length > 0) {
        html += `<div class="key-concepts">`;
        for (const concept of expl.key_concepts) {
            html += `<span class="concept-tag">${escapeHtml(concept)}</span>`;
        }
        html += `</div>`;
    }

    panel.innerHTML = html;
}

function formatValue(val) {
    if (val === null || val === undefined) return 'None';
    if (typeof val === 'object' && 'type' in val && 'value' in val) {
        const v = val.value;
        if (val.type === 'str') return `"${v}"`;
        if (Array.isArray(v)) {
            const inner = v.map(formatValue).join(', ');
            return val.type === 'tuple' ? `(${inner})` : `[${inner}]`;
        }
        if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
            const entries = Object.entries(v).map(([k, vv]) => `${k}: ${formatValue(vv)}`);
            return `{${entries.join(', ')}}`;
        }
        return String(v);
    }
    return String(val);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.getElementById('code-input').addEventListener('keydown', function(e) {
    if (e.key === 'Tab') {
        e.preventDefault();
        const start = this.selectionStart;
        const end = this.selectionEnd;
        this.value = this.value.substring(0, start) + '    ' + this.value.substring(end);
        this.selectionStart = this.selectionEnd = start + 4;
    }
});
