# Backup & Rollback Guide

## Current State

**Backup committed:**
- File: `main.py.backup.20260118_220820` (1548 lines)
- Commit: `103475f`
- Tag: `backup-original-main` → points to `103475f`
- Tag: `pre-modularization` → points to `9fa05f0`

**Modularization uncommitted:**
- Modified: `main.py`, `Dockerfile`
- Untracked: `core/`, `config/loader.py`, `CLAUDE.md`

---

## Rollback Methods

### Method 1: File Backup (Fastest - 5 seconds)

```bash
# From project root
cp main.py.backup.20260118_220820 main.py
rm -rf core/ config/loader.py CLAUDE.md
git checkout -- Dockerfile

# Verify
wc -l main.py     # Should show ~1548 lines
git status         # Should be clean
```

### Method 2: Git Reset (Nuclear - discards ALL changes)

```bash
git reset --hard HEAD
git clean -fd

# Verify
git status         # Should be clean
wc -l main.py     # Should show ~1548 lines
```

### Method 3: Git Checkout from Tag

```bash
git checkout backup-original-main -- main.py
rm -rf core/ config/loader.py CLAUDE.md
git checkout -- Dockerfile

# Verify
wc -l main.py
git status
```

---

## Git Tags Explained

### What is a Tag?

**Tag = Fixed bookmark pointing to one commit**

```bash
git tag backup-original-main
```

- 📌 Stays at commit `103475f` forever
- Does NOT move when you make new commits
- Like a sticky note: "this is important"

### Tag vs Branch

**Tag:**
```
103475f ← backup-original-main (never moves)
```

**Branch:**
```
9fa05f0 → 103475f → [new] → [new]
                      ↑
                     dev (moves forward)
```

### Pushing Tags

**Tags are NOT pushed automatically:**

```bash
# Push specific tag
git push origin backup-original-main

# Push all tags
git push --tags

# Push commits + tags together
git push origin dev --tags
```

---

## Complete Workflow

### 1. Test First

```bash
docker build -t ubl-ai-server .
cd simulation && docker-compose up --build
```

### 2a. If Success → Commit & Push

```bash
git add main.py Dockerfile CLAUDE.md config/loader.py core/
git commit -m "modularize main.py: 1548→206 lines"
git push origin dev --tags  # Pushes commits + tags
```

### 2b. If Fail → Rollback

```bash
# Use Method 1 (fastest)
cp main.py.backup.20260118_220820 main.py
rm -rf core/ config/loader.py CLAUDE.md
git checkout -- Dockerfile
```

---

## Quick Reference

### View Current State

```bash
git status
git log --oneline -5
git tag -l
wc -l main.py
```

### Verify Backup Exists

```bash
ls -lh main.py.backup.*
git log backup-original-main -1
```

### Restore Original (One-liner)

```bash
cp main.py.backup.20260118_220820 main.py && rm -rf core/ config/loader.py CLAUDE.md && git checkout -- Dockerfile
```
