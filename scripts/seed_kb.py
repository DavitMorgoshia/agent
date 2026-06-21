#!/usr/bin/env python3
"""Seed the ChromaDB knowledge base from knowledge_base/*.md files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.rag import seed_knowledge_base

if __name__ == "__main__":
    force = "--force" in sys.argv
    print(f"Seeding knowledge base (force={force})...")
    n = seed_knowledge_base(force=force)
    print(f"Done: {n} chunks loaded")
