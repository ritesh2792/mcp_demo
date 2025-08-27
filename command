PS C:\Users\23jsr\Documents\Ritesh\MCP_DEMO> git init
Reinitialized existing Git repository in C:/Users/23jsr/Documents/Ritesh/MCP_DEMO/.git/
PS C:\Users\23jsr\Documents\Ritesh\MCP_DEMO> git status
On branch main
Your branch is up to date with 'origin/main'.

Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
        modified:   app.py
        new file:   gcp_users.db
        modified:   mcp_server.py
        new file:   users.db

PS C:\Users\23jsr\Documents\Ritesh\MCP_DEMO> git add .
PS C:\Users\23jsr\Documents\Ritesh\MCP_DEMO> git commit -m "modified app.py"
[main 73478fc] modified app.py
 4 files changed, 4 insertions(+), 6 deletions(-)
 create mode 100644 gcp_users.db
 create mode 100644 users.db
PS C:\Users\23jsr\Documents\Ritesh\MCP_DEMO> git remote add origin https://github.com/ritesh2792/mcp_demo.git
error: remote origin already exists.
PS C:\Users\23jsr\Documents\Ritesh\MCP_DEMO> git push -u origin main
Enumerating objects: 9, done.
Counting objects: 100% (9/9), done.
Delta compression using up to 8 threads
Compressing objects: 100% (6/6), done.
Writing objects: 100% (6/6), 1.50 KiB | 255.00 KiB/s, done.
Total 6 (delta 3), reused 0 (delta 0), pack-reused 0 (from 0)
remote: Resolving deltas: 100% (3/3), completed with 2 local objects.
To https://github.com/ritesh2792/mcp_demo.git
   adadb91..73478fc  main -> main
branch 'main' set up to track 'origin/main'.
PS C:\Users\23jsr\Documents\Ritesh\MCP_DEMO> 