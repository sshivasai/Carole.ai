import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import { savedFileState } from '../src/features/files/document.ts';
const source = ts.transpileModule(readFileSync(new URL('../src/components/FileExplorerPanel.tsx', import.meta.url), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
}).outputText;
const flush = () => new Promise(resolve => setImmediate(resolve));
function harness(readFile, writeFile = async () => {}) {
  const slots = [], effects = [], notices = [];
  let cursor = 0, tree, currentProps = {};
  const react = {
    createElement: (type, props, ...children) => ({ type, props: { ...props, children }, children }),
    useRef(value) { const i = cursor++; return slots[i] ||= { current: value }; },
    useState(value) { const i = cursor++; if (!(i in slots)) slots[i] = typeof value === 'function' ? value() : value; return [slots[i], next => { slots[i] = typeof next === 'function' ? next(slots[i]) : next; }]; },
    useCallback(fn, deps) { return this.useMemo(() => fn, deps); },
    useMemo(fn, deps) { const i = cursor++; const old = slots[i]; if (!old || deps.some((value, j) => value !== old.deps[j])) slots[i] = { deps, value: fn() }; return slots[i].value; },
    useEffect(fn, deps) { const i = cursor++; const old = slots[i]; if (!old || deps.some((value, j) => value !== old.deps[j])) effects.push(() => { old?.cleanup?.(); slots[i] = { deps, cleanup: fn() }; }); },
  };
  react.useCallback = react.useCallback.bind(react);
  react.useLayoutEffect = react.useEffect;
  const addToast = notice => notices.push(notice);
  const modules = {
    react, 'react-dom': { createPortal: value => value }, 'lucide-react': {},
    '@/hooks/useApi': { api: { getProject: async () => ({ name: 'Project' }), listFiles: async () => [], readFile, writeFile }, getApiBase: () => '' },
    '@/hooks/useAuth': { useAuth: () => ({ user: null }) }, '@/hooks/useTheme': { useTheme: () => ({ theme: 'dark' }) },
    '@/hooks/useToast': { useToast: () => ({ addToast }) }, '@/features/files/document': { savedFileState },
    '@monaco-editor/react': { __esModule: true, default: 'Editor', DiffEditor: 'DiffEditor' },
    './Modal': { __esModule: true, default: 'Modal' }, 'react-resizable-panels': { PanelGroup: 'PanelGroup', Panel: 'Panel', PanelResizeHandle: 'Resize' },
  };
  const context = { exports: {}, require: name => modules[name] || {}, window: { addEventListener() {}, removeEventListener() {} }, document: { addEventListener() {}, removeEventListener() {} }, localStorage: { getItem: () => null }, console, URLSearchParams, setTimeout, clearTimeout };
  vm.runInNewContext(source, context);
  const all = node => !node || typeof node !== 'object' ? [] : Array.isArray(node) ? node.flatMap(all) : [node, ...all(node.children)];
  return {
    notices,
    render(props = currentProps) { currentProps = props; cursor = 0; tree = context.exports.default(props); effects.splice(0).forEach(effect => effect()); },
    find(predicate) { return all(tree).find(predicate); },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

test('the latest requested file wins when reads resolve out of order', async () => {
  const pending = new Map();
  const h = harness(path => new Promise(resolve => pending.set(path, resolve)));
  h.render({ projectId: 'a', pendingOpenFile: 'first.ts' });
  h.render({ projectId: 'a', pendingOpenFile: 'second.ts' });
  pending.get('second.ts')({ content: 'second' }); await flush(); h.render();
  pending.get('first.ts')({ content: 'first' }); await flush(); h.render();
  assert.equal(h.find(node => node.type === 'Editor').props.value, 'second');
  h.unmount();
});

test('editing during save keeps the newer draft dirty and closing asks before discarding', async () => {
  let finishSave;
  const h = harness(async () => ({ content: 'original' }), () => new Promise(resolve => { finishSave = resolve; }));
  h.render({ projectId: 'a', pendingOpenFile: 'file.ts' }); await flush(); h.render();
  h.find(node => node.type === 'Editor').props.onChange('saved version'); h.render();
  const save = h.find(node => node.type === 'button' && node.children.includes('Save'));
  const saving = save.props.onClick();
  h.find(node => node.type === 'Editor').props.onChange('newer draft'); h.render();
  finishSave(); await saving; h.render();
  assert.equal(h.find(node => node.type === 'Editor').props.value, 'newer draft');
  assert.equal(h.find(node => node.type === 'button' && node.children.includes('Save')).props.disabled, false);
  h.find(node => node.type === 'button' && node.props['aria-label'] === 'Close file.ts').props.onClick({ stopPropagation() {} }); h.render();
  assert.equal(h.find(node => node.type === 'Modal' && node.props.title === 'Discard unsaved changes?').props.open, true);
  h.unmount();
});

test('project switching keeps drafts separate and restores them on return', async () => {
  const h = harness(async () => ({ content: 'original' }));
  h.render({ projectId: 'a', pendingOpenFile: 'file.ts' }); await flush(); h.render();
  h.find(node => node.type === 'Editor').props.onChange('project a draft'); h.render();
  h.render({ projectId: 'b' }); h.render();
  assert.equal(h.find(node => node.type === 'Editor'), undefined);
  h.render({ projectId: 'a' }); h.render();
  assert.equal(h.find(node => node.type === 'Editor').props.value, 'project a draft');
  h.unmount();
});
