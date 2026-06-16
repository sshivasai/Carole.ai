import { NextRequest, NextResponse } from "next/server";
import fs from "fs";
import path from "path";
import os from "os";
import git from "isomorphic-git";

export const dynamic = 'force-dynamic';

// We use the same ~/.carole/workspaces directory as the Python backend
function getWorkspaceRoot(projectId: string | null): string {
  const workspacesDir = path.join(os.homedir(), ".carole", "workspaces");
  if (!projectId) return workspacesDir;
  
  // Try to find the exact project slug by checking db, 
  // but since we don't have db access here easily, we expect the frontend 
  // to pass the exact projectSlug instead of projectId for git ops!
  // Wait, if frontend passes projectSlug, we can just use it.
  // Let's assume the frontend passes `slug` as a query param.
  return workspacesDir; // We'll append slug later
}

export async function POST(req: NextRequest, { params }: { params: any }) {
  const resolvedParams = await params;
  const action = resolvedParams.action[0];
  const url = new URL(req.url);
  const slug = url.searchParams.get("slug");
  
  if (!slug) {
    return NextResponse.json({ status: "error", message: "Missing project slug" }, { status: 400 });
  }

  const dir = path.join(getWorkspaceRoot(null), slug);

  if (!fs.existsSync(dir)) {
    return NextResponse.json({ status: "error", message: "Project directory not found" }, { status: 404 });
  }

  try {
    const body = req.method !== "GET" ? await req.json().catch(() => ({})) : {};

    const FILE = 0, HEAD = 1, WORKDIR = 2, STAGE = 3;

    switch (action) {
      case "init":
        await git.init({ fs, dir });
        return NextResponse.json({ status: "success", message: "Repository initialized" });

      case "status":
        const isRepo = fs.existsSync(path.join(dir, ".git"));
        if (!isRepo) {
          return NextResponse.json({ status: "success", changes: [], message: "Not a git repository. Initialize it first." });
        }
        
        // Get all files
        const statusMatrix = await git.statusMatrix({ fs, dir });
        
        const changes = statusMatrix
          .filter(row => row[HEAD] !== row[WORKDIR] || row[HEAD] !== row[STAGE])
          .map(row => {
            const file = row[FILE];
            // Compute status string
            // 0 = absent, 1 = identical, 2 = modified
            let status = "";
            if (row[HEAD] === 0 && row[WORKDIR] === 2) status = "A"; // Added
            else if (row[HEAD] === 1 && row[WORKDIR] === 2) status = "M"; // Modified
            else if (row[HEAD] === 1 && row[WORKDIR] === 0) status = "D"; // Deleted
            else if (row[HEAD] === 0 && row[WORKDIR] === 0) status = "D"; // Should not happen
            else status = "?"; // Untracked
            
            return { file, status };
          });
          
        return NextResponse.json({ status: "success", changes });

      case "commit":
        const message = body.message;
        if (!message) return NextResponse.json({ status: "error", message: "Message required" }, { status: 400 });
        
        // Add all files
        const statusMatrixCommit = await git.statusMatrix({ fs, dir });
        for (const row of statusMatrixCommit) {
           const file = row[FILE];
           if (row[WORKDIR] === 2) {
             await git.add({ fs, dir, filepath: file });
           } else if (row[WORKDIR] === 0 && row[HEAD] === 1) {
             await git.remove({ fs, dir, filepath: file });
           }
        }
        
        const sha = await git.commit({
          fs,
          dir,
          message,
          author: { name: "User", email: "user@carole.ai" }
        });
        
        return NextResponse.json({ status: "success", message: `Committed ${sha.substring(0, 7)}` });

      case "show":
        const filepath = url.searchParams.get("file");
        if (!filepath) return NextResponse.json({ status: "error", message: "Missing file path" }, { status: 400 });
        
        try {
          const commitOid = await git.resolveRef({ fs, dir, ref: 'HEAD' });
          const { blob } = await git.readBlob({
            fs,
            dir,
            oid: commitOid,
            filepath
          });
          const content = Buffer.from(blob).toString('utf8');
          return NextResponse.json({ status: "success", content });
        } catch (e: any) {
          // File might be newly added (not in HEAD)
          if (e.code === 'NotFoundError' || e.code === 'ResolveRefError') {
             return NextResponse.json({ status: "success", content: "" });
          }
          throw e;
        }

      default:
        return NextResponse.json({ status: "error", message: "Unknown action" }, { status: 400 });
    }
  } catch (error: any) {
    return NextResponse.json({ status: "error", message: error.message }, { status: 500 });
  }
}

export async function GET(req: NextRequest, context: any) {
  return POST(req, context);
}
