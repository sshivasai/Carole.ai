const { createElement } = require('react');
const { renderToString } = require('react-dom/server');
const ReactMarkdown = require('react-markdown').default || require('react-markdown');
const remarkGfm = require('remark-gfm').default || require('remark-gfm');

const text = `We are in a team setting. I am Archer, the orchestrator. 
 The user is Shiva Sai, the project owner.

 Recent events:
 1. Oracle (researcher) introduced themselves.
 2. There was an API error 402 regarding token credits when trying to process a request (likely by another agent or system).
 3. The user added me (Archer) to the team.

 Current situation: 
 The user has not given a specific task yet. Since I'm the orchestrator, I should wait for instructions or a task from the user.

 However, note that there was an API error. As the orchestrator, I should be proactive about team health and issues. 
 But since the error might be from a previous action (before I was added) and the user hasn't directed me to handle it, I won't jump in unless asked.

 My next step: 
 Wait for the user (Shiva Sai) to give a task. If they don't, I can offer a brief status or ask how I can help.

 But note: The user just added me. They might be about to give a task. So I'll keep it short.

 Response:
 Since I just joined, I'll greet the user and let them know I'm ready to coordinate.
`;

const element = createElement(ReactMarkdown, { remarkPlugins: [remarkGfm] }, text);
console.log(renderToString(element));
