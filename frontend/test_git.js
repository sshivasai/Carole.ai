import fs from 'fs';
import path from 'path';
import os from 'os';
import git from 'isomorphic-git';

async function test() {
  try {
    const dir = path.join(os.homedir(), '.carole', 'workspaces', 'Test');
    const isRepo = fs.existsSync(path.join(dir, ".git"));
    console.log("Is Repo:", isRepo);
    
    const statusMatrix = await git.statusMatrix({ fs, dir });
    console.log("Status Matrix:", statusMatrix);
  } catch(e) {
    console.error("Error:", e);
  }
}
test();
