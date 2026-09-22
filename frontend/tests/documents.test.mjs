import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveDocumentLink, savedFileState } from '../src/features/files/document.ts';
test('Markdown links resolve relative to the document, preserving the fragment', () => {
  assert.deepEqual(resolveDocumentLink('../src/app.ts#usage', 'docs/guide.md'), { path: 'src/app.ts', hash: 'usage' });
  assert.deepEqual(resolveDocumentLink('./my%20file.md', 'docs/guide.md'), { path: 'docs/my file.md', hash: '' });
  assert.deepEqual(resolveDocumentLink('/README.md', 'docs/guide.md'), { path: 'README.md', hash: '' });
});
test('external links, malformed paths and root escapes are not opened as project files', () => {
  for (const href of ['https://example.com', '//example.com', 'mailto:a@example.com', '#section', '../../outside.md', '%ZZ']) assert.equal(resolveDocumentLink(href, 'docs/guide.md'), null);
});
test('a save only marks the exact saved content clean', () => {
  const files = [{ path: 'a.ts', content: 'new edits', isDirty: true }, { path: 'b.ts', content: 'other edits', isDirty: true }];
  assert.deepEqual(savedFileState(files, 'a.ts', 'old edits'), files);
  const saved = savedFileState(files, 'a.ts', 'new edits');
  assert.equal(saved[0].isDirty, false);
  assert.equal(saved[1].isDirty, true);
  assert.equal(files[0].isDirty, true);
});
