#!/usr/bin/env python3
"""Recalculate statistics for all components in a project."""

import os
import sys
import django

# Setup Django
sys.path.insert(0, '/home/boost-weblate')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'weblate.settings')
django.setup()

from weblate.trans.models import Component, Project

def recalculate_stats(project_slug):
    """Recalculate statistics for all components in a project."""
    try:
        project = Project.objects.get(slug=project_slug)
    except Project.DoesNotExist:
        print(f"Project {project_slug} not found")
        return
    
    print(f"Recalculating statistics for project: {project.name}")
    print(f"Components: {project.component_set.count()}\n")
    
    components = project.component_set.all()
    total = components.count()
    
    for idx, comp in enumerate(components, 1):
        print(f"[{idx}/{total}] {comp.full_slug}...", end=" ", flush=True)
        
        # Invalidate cache and recalculate
        comp.invalidate_cache()
        
        # Update statistics for all translations
        for trans in comp.translation_set.all():
            trans.stats.update_stats(update_parents=False)
        
        # Update component statistics
        comp.stats.update_stats(update_parents=True)
        
        stats = comp.stats
        print(f"✓ {stats.translated}/{stats.all} ({stats.translated_percent:.1f}%)")
    
    # Update project statistics
    print("\nUpdating project statistics...")
    project.stats.update_stats()
    
    # Final summary
    project_stats = project.stats
    print(f"\n=== Project Summary ===")
    print(f"Total strings: {project_stats.all}")
    print(f"Translated: {project_stats.translated} ({project_stats.translated_percent:.1f}%)")
    print(f"Fuzzy: {project_stats.fuzzy} ({project_stats.fuzzy_percent:.1f}%)")
    print(f"Untranslated: {project_stats.all - project_stats.translated}")

if __name__ == '__main__':
    if len(sys.argv) >= 2:
        recalculate_stats(sys.argv[1])
    else:
        print("Usage: python recalculate_stats.py <project_slug>")
        sys.exit(1)

