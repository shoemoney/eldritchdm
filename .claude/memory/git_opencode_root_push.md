# Git Push when running opencode as Root

When the Opencode server/agent is running via `sudo` (as the `root` user to avoid file permission lockouts), it cannot access the regular user's SSH keys or `SSH_AUTH_SOCK`. Attempting a standard `git push` or `git fetch` will fail with:

`git@github.com: Permission denied (publickey).`

**Solution:** Always execute git push (and other network-bound git commands) as the `shoemoney` user using `sudo -u`.

Example:
```bash
sudo -u shoemoney git push origin main
```

This forces the command to run as `shoemoney`, allowing Git to seamlessly use the local user's authenticated SSH keys or GitHub CLI credentials without modifying system permissions.
