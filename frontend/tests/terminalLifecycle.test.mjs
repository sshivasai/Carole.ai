import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { webcrypto } from "node:crypto";
import ts from "typescript";

// Exercise the real component's effects with controlled tickets, sockets and fonts.
const source = ts.transpileModule(readFileSync(new URL("../src/components/TerminalPanel.tsx", import.meta.url), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, esModuleInterop: true },
}).outputText;
const flush = () => new Promise(resolve => setImmediate(resolve));
function harness({ fonts = Promise.resolve(), ticket = async () => ({ ticket: "test" }) } = {}) {
  const slots = [], effects = [], sockets = [], terminals = [];
  let cursor = 0;
  const container = { clientWidth: 800, clientHeight: 500, parentElement: null };
  const react = {
    createElement: () => null,
    useRef(value) { const i = cursor++; return slots[i] ||= { current: i === 0 ? container : value }; },
    useState(value) { const i = cursor++; if (!(i in slots)) slots[i] = value; return [slots[i], next => { slots[i] = typeof next === "function" ? next(slots[i]) : next; }]; },
    useEffect(fn, deps) { const i = cursor++; const old = slots[i]; if (!old || deps.some((value, j) => value !== old.deps[j])) { effects.push(() => { old?.cleanup?.(); slots[i] = { deps, cleanup: fn() }; }); } },
  };
  class Socket {
    static OPEN = 1;
    readyState = 0; sent = [];
    constructor(url) { this.url = url; sockets.push(this); }
    send(data) { this.sent.push(JSON.parse(data)); }
    open() { this.readyState = 1; this.onopen?.(); }
    close() { this.readyState = 3; this.onclose?.(); }
  }
  class Terminal {
    cols = 80; rows = 24;
    constructor(options) { this.options = options; terminals.push(this); }
    loadAddon() {} open() {} attachCustomKeyEventHandler(fn) { this.keyHandler = fn; }
    onResize() {} onData(fn) { this.input = fn; } write() {} dispose() { this.disposed = true; }
  }
  const modules = {
    react, 'lucide-react': {}, '@xterm/xterm': { Terminal }, '@xterm/addon-fit': { FitAddon: class { fit() {} } },
    '@/hooks/useApi': { api: { getWsTicket: ticket } }, '@/hooks/useWebSocket': { getWsBase: () => 'ws://test' },
  };
  const context = { crypto: webcrypto, exports: {}, require: name => modules[name] || {}, WebSocket: Socket, document: { fonts: { ready: fonts } }, getComputedStyle: () => ({ getPropertyValue: key => key === '--color-ink' ? '#ffffff' : '#111111' }), ResizeObserver: class { observe() {} disconnect() {} }, MutationObserver: class { observe() {} disconnect() {} }, requestAnimationFrame: () => 1, cancelAnimationFrame() {}, URLSearchParams, console };
  vm.runInNewContext(source, context);
  return {
    sockets, terminals,
    render(props) { cursor = 0; context.exports.default(props); effects.splice(0).forEach(effect => effect()); },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}

test('a command arriving while connecting is sent once after open', async () => {
  const h = harness(); h.render({ projectId: 'a' }); await flush();
  h.render({ projectId: 'a', triggerCommand: { cmd: 'echo ready', ts: 1 } });
  assert.equal(h.sockets[0].sent.length, 0);
  h.sockets[0].open();
  assert.equal(h.sockets[0].sent.filter(x => x.action === 'input').length, 1);
  h.render({ projectId: 'a', triggerCommand: { cmd: 'echo ready', ts: 1 } });
  assert.equal(h.sockets[0].sent.filter(x => x.action === 'input').length, 1);
  h.unmount();
});
test('project changes close the old socket before sending new commands', async () => {
  const h = harness(); h.render({ projectId: 'a' }); await flush(); h.sockets[0].open();
  h.render({ projectId: 'b', triggerCommand: { cmd: 'echo b', ts: 2 } }); await flush();
  assert.equal(h.sockets[0].readyState, 3);
  assert.equal(h.sockets[0].sent.filter(x => x.action === 'input').length, 0);
  assert.match(h.sockets[1].url, /\/b\?/); h.sockets[1].open();
  assert.equal(h.sockets[1].sent.filter(x => x.action === 'input').length, 1);
  h.unmount();
});
test('unmount while fonts load cannot open a socket or fetch a ticket', async () => {
  let release; let tickets = 0;
  const h = harness({ fonts: new Promise(resolve => { release = resolve; }), ticket: async () => { tickets++; return { ticket: 'test' }; } });
  h.render({ projectId: 'a' }); await flush(); h.unmount(); release(); await flush();
  assert.equal(tickets, 0); assert.equal(h.sockets.length, 0); assert.equal(h.terminals[0].disposed, true);
});
test('authentication failure does not attempt an anonymous terminal connection', async () => {
  const h = harness({ ticket: async () => { throw new Error('Unauthorized'); } });
  h.render({ projectId: 'a' }); await flush();
  assert.equal(h.sockets.length, 0); h.unmount();
});
