# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


class AutoFix:
    """Base class for AutoFixes."""

    fix_id = "auto"

    def get_identifier(self):
        return self.fix_id

    def fix_single_target(self, target, source, unit):
        """Fix a single target, implement this method in subclasses."""
        raise NotImplementedError

    def fix_target(self, target, unit):
        """Return a target translation array with a single fix applied."""
        source_strings = unit.get_source_plurals()
        if unit.translation.component.is_multivalue:
            results = [
                self.fix_single_target(text, source_strings[0], unit) for text in target
            ]
        elif len(source_strings) == 1 and len(target) == 1:
            results = [self.fix_single_target(target[0], source_strings[0], unit)]
        else:
            source_plural = unit.translation.component.source_language.plural
            target_plural = unit.translation.plural
            source_examples = {
                tuple(examples): number
                for number, examples in source_plural.examples.items()
            }
            target_examples = target_plural.examples
            plurals_map = [
                source_examples.get(tuple(target_examples.get(target_index, [])), -1)
                for target_index in range(target_plural.number)
            ]
            # Ensure we have a source strings for each map
            while len(source_strings) <= max(plurals_map):
                source_strings.append(source_strings[0])
            results = [
                self.fix_single_target(text, source_strings[plurals_map[i]], unit)
                for i, text in enumerate(target)
            ]
        return [r[0] for r in results], max(r[1] for r in results)
