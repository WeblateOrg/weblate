# Copyright © Henry Wilkes <henry@torproject.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext, gettext_lazy

from weblate.checks.base import TargetCheck
from weblate.checks.fluent.utils import (
    FluentPatterns,
    FluentUnitConverter,
    format_html_code,
    format_html_error_list,
    translation_from_check,
    variant_name,
)
from weblate.utils.html import format_html_join_comma, list_to_tuples

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from django.utils.safestring import SafeString
    from django_stubs_ext import StrOrPromise
    from translate.storage.fluent import (
        FluentPart,
        FluentReference,
        FluentSelectorBranch,
        FluentSelectorNode,
    )

    from weblate.checks.fluent.utils import CheckModel, HighlightsType, TransUnitModel


class _Reference:
    """A class that wraps a FluentReference."""

    def __init__(self, fluent_ref: FluentReference) -> None:
        self.fluent_ref = fluent_ref
        # A reference can be flagged as shared if it was borrowed from another
        # branch.
        self.shared = False

    def share(self) -> _Reference:
        copy = self.__class__(self.fluent_ref)
        copy.shared = True
        return copy

    def present(self) -> str:
        """Show the reference in a presentable form."""
        ref_name = self.fluent_ref.name
        if self.fluent_ref.type_name == "term":
            ref_name = f"-{ref_name}"
        elif self.fluent_ref.type_name == "variable":
            ref_name = f"${ref_name}"
        return f"{{\xa0{ref_name}\xa0}}"

    def matches(self, other: _Reference) -> bool:
        """Whether the two references match in name and type."""
        return (
            self.fluent_ref.type_name == other.fluent_ref.type_name
            and self.fluent_ref.name == other.fluent_ref.name
        )


class _CountedReferences:
    """
    Tracks the number of matching _References in a list.

    This will collect matching references together so they can be counted and
    compared, without caring about the order.
    """

    def __init__(self, ref_list: Iterable[_Reference]) -> None:
        self.matching_refs: list[list[_Reference]] = []
        for ref in ref_list:
            add = True
            for other_refs in self.matching_refs:
                if other_refs[0].matches(ref):
                    add = False
                    other_refs.append(ref)
                    break
            if add:
                self.matching_refs.append([ref])

    def matches(self, other: _CountedReferences) -> bool:
        """
        Whether the two instances match.

        This will match if the two instances have matching _References with the
        same count in both.
        """
        if len(self.matching_refs) != len(other.matching_refs):
            return False
        for refs in self.matching_refs:
            has_match = False
            for _index, other_refs in enumerate(other.matching_refs):
                if refs[0].matches(other_refs[0]):
                    if len(refs) != len(other_refs):
                        return False
                    has_match = True
                    break
            if not has_match:
                return False
        # Both are the same length and each ref in self was matched, so there
        # shouldn't be any refs in other that were not matched once.
        return True

    def count(self, ref: _Reference, include_shared: bool = True) -> int:
        """
        How many references match the given reference.

        If `include_shared` is False, this will only count references that are
        not flagged as "shared".
        """
        for other_refs in self.matching_refs:
            if ref.matches(other_refs[0]):
                if include_shared:
                    return len(other_refs)
                count = 0
                for equiv_ref in other_refs:
                    if not equiv_ref.shared:
                        count += 1
                return count
        return 0


class _VariantReferences:
    """Represents a variant string and the references it contains."""

    def __init__(
        self,
        path: list[FluentSelectorBranch],
        references: list[_Reference],
    ) -> None:
        self.path = path
        self.references = references
        self.counted_references = _CountedReferences(references)

    def name(self) -> str:
        """Generate the name for this variant."""
        return variant_name(self.path)


class _DifferentBranchCountError(Exception):
    # Generic exception for when two branches under the same node have different
    # counts for some reference.
    pass


class _SelectorReferences:
    """Class for extracting the references found underneath some selector branch."""

    def __init__(self, top_branch: FluentSelectorBranch) -> None:
        # Map from the selector branches to a list of their direct references.
        self._branch_references: dict[FluentSelectorBranch, list[_Reference]] = {}
        # Map from the selector node to a list of references found in their
        # SelectExpression selector expression.
        self._selector_references: dict[FluentSelectorNode, list[_Reference]] = {}

        # Populate the maps with references.
        self._set_refs(top_branch)

        # Try and share references between branches.
        self._share_refs_between_branches(top_branch)

        # Generate all possible variants and assign them the references that
        # would appear in their flat form, plus any shared references.
        self.variant_references = [
            _VariantReferences(path, list(self._refs_for_path(top_branch, path)))
            for path in top_branch.branch_paths()
        ]

    def _refs_for_path(
        self,
        top_branch: FluentSelectorBranch,
        branches: list[FluentSelectorBranch],
    ) -> Iterator[_Reference]:
        """
        Fetch all the references for a given branch path.

        Each branch path represents a possible variant of the original fluent
        entry.
        """
        yield from self._branch_references[top_branch]
        for branch in branches:
            yield from self._branch_references[branch]

    def _set_refs(self, branch: FluentSelectorBranch) -> None:
        self._branch_references[branch] = [
            _Reference(fluent_ref) for fluent_ref in branch.top_references
        ]
        for node in branch.child_nodes:
            # Only want unique refs for the selector references, otherwise this
            # can lead to double-sharing of these references.
            selector_refs: list[_Reference] = []
            for fluent_ref in node.selector_references:
                ref = _Reference(fluent_ref)
                add = True
                for other in selector_refs:
                    if other.matches(ref):
                        add = False
                        break
                if add:
                    selector_refs.append(ref)
            self._selector_references[node] = selector_refs

            for child in node.child_branches:
                self._set_refs(child)

    def _branch_ref_count(
        self,
        branch: FluentSelectorBranch,
        ref: _Reference,
    ) -> int:
        """
        Get the number of times a reference appears in a branch.

        If, for each node in the branch, each child branch of the node has the
        same reference count, then this will be added to the returned count.
        Otherwise, if they differ in count, this will raise the
        _DifferentBranchCountError exception to indicate that there is no
        consistent number to return.
        """
        count = 0
        for node in branch.child_nodes:
            same_count = None
            for child in node.child_branches:
                child_count = self._branch_ref_count(child, ref)
                if same_count is None:
                    # same_count is uninitialized so set it using this first
                    # branch.
                    same_count = child_count
                elif same_count != child_count:
                    # Two branches differ, so no consistent counting.
                    raise _DifferentBranchCountError
            if same_count is None:
                # Unexpected since each selector node should have at least one
                # child.
                raise _DifferentBranchCountError
            count += same_count
        # Add the count for the top references.
        # NOTE: this includes shared references that have been added earlier.
        for other in self._branch_references[branch]:
            if other.matches(ref):
                count += 1
        return count

    def _share_refs_between_branches(
        self,
        branch: FluentSelectorBranch,
    ) -> None:
        """
        Try and share references between branches.

        Each node below the given branch will represent a SelectExpression. If
        the SelectExpression's selector contains a reference that matches one of
        the references within one of its Variants, we want to share that
        reference between all the Variants *as if* each variant contains the
        reference.

        This should help adjust for the fact that a Variant's key may make the
        reference unnecessary. E.g. we might select over the number $num, but if
        we match with the [zero] or [one] category, then we might not need to or
        want to reference the { $num } value. Moreover, this could vary across
        different locales.
        """
        # Share depth-first to try and equalise the reference count between
        # sub-branches before moving up.
        for node in branch.child_nodes:
            for child in node.child_branches:
                self._share_refs_between_branches(child)

        for node in branch.child_nodes:
            try:
                # For each reference found in the selector, we want to count how
                # many times it appears in each child branch.
                ref_counts = {
                    ref: {
                        child: self._branch_ref_count(child, ref)
                        for child in node.child_branches
                    }
                    for ref in self._selector_references[node]
                }
            except _DifferentBranchCountError:
                # For at least one of the references, one of the children does
                # not have a consistent count.
                # E.g.
                # | { $num ->
                # |   [one] one
                # |  *[other] { $var ->
                # |     [a] { $num }
                # |    *[b] none
                # |   }
                # | }
                # Here the [other] branch does not have a consistent count for
                # $num between its child branches [a] and [b], so we do not
                # share it.
                continue
            for ref, child_counts in ref_counts.items():
                # We want each child to have the same reference count for the
                # purpose of comparison, so we find the maximum count and pad
                # the other branches with shared references.
                # NOTE: Each ref in selector_references should be unique to
                # avoid double adding at this stage.
                max_count = max(child_counts.values())
                for child, count in child_counts.items():
                    self._branch_references[child].extend(
                        ref.share() for _num in range(max_count - count)
                    )


class _VariantReferencesDifference:
    """
    The difference between the references found in the source and target.

    Each variant in the source will be compared against each variant in the
    target to see if they have a matching set of references with the same number
    or appearances, but not necessarily in the same order.

    If there is any source variant that does not have at least one match in the
    target, it will be flagged as a missing variant. Similarly, if there is any
    target variant with no matching source variant, it will be flagged as an
    extra variant.
    """

    def __init__(
        self,
        source_part: FluentPart,
        target_part: FluentPart,
    ) -> None:
        self._part_name = source_part.name
        self._source_variants = _SelectorReferences(
            source_part.top_branch
        ).variant_references
        self._target_variants = _SelectorReferences(
            target_part.top_branch
        ).variant_references

        self._missing_variants = [
            variant
            for variant in self._source_variants
            if not self._has_match(variant, self._target_variants)
        ]
        self._extra_variants = [
            variant
            for variant in self._target_variants
            if not self._has_match(variant, self._source_variants)
        ]

    @classmethod
    def _has_match(
        cls, variant: _VariantReferences, search_list: list[_VariantReferences]
    ) -> bool:
        return any(
            variant.counted_references.matches(other.counted_references)
            for other in search_list
        )

    def __bool__(self) -> bool:
        return bool(self._missing_variants or self._extra_variants)

    def _missing_ref_message(
        self,
        ref: str,
        variants: str,
    ) -> SafeString:
        if self._part_name:
            if not variants:
                return format_html_code(
                    gettext(
                        "Fluent {attribute} attribute is missing a "
                        "{reference} Fluent reference."
                    ),
                    attribute=self._part_name,
                    reference=ref,
                )
            return format_html_code(
                gettext(
                    "Fluent {attribute} attribute is missing a {reference} "
                    "Fluent reference for the following variants: {variant_list}."
                ),
                attribute=self._part_name,
                reference=ref,
                variant_list=variants,
            )
        if not variants:
            return format_html_code(
                gettext("Fluent value is missing a {reference} Fluent reference."),
                reference=ref,
            )
        return format_html_code(
            gettext(
                "Fluent value is missing a {reference} Fluent reference "
                "for the following variants: {variant_list}."
            ),
            reference=ref,
            variant_list=variants,
        )

    def _extra_ref_message(
        self,
        ref: str,
        variants: str,
    ) -> SafeString:
        if self._part_name:
            if not variants:
                return format_html_code(
                    gettext(
                        "Fluent {attribute} attribute has an unexpected extra "
                        "{reference} Fluent reference."
                    ),
                    attribute=self._part_name,
                    reference=ref,
                )
            return format_html_code(
                gettext(
                    "Fluent {attribute} attribute has an unexpected extra {reference} "
                    "Fluent reference for the following variants: {variant_list}."
                ),
                attribute=self._part_name,
                reference=ref,
                variant_list=variants,
            )
        if not variants:
            return format_html_code(
                gettext(
                    "Fluent value has an unexpected extra {reference} Fluent reference."
                ),
                reference=ref,
            )
        return format_html_code(
            gettext(
                "Fluent value has an unexpected extra {reference} Fluent "
                "reference for the following variants: {variant_list}."
            ),
            reference=ref,
            variant_list=variants,
        )

    @staticmethod
    def _present_variant_list(
        variant_list: list[_VariantReferences] | None,
    ) -> str:
        if not variant_list:
            return ""
        return format_html_join_comma(
            "{}", list_to_tuples(variant.name() for variant in variant_list)
        )

    def _unique_target_refs(self) -> Iterator[_Reference]:
        unique_refs: list[_Reference] = []
        for variant in self._target_variants:
            for ref in variant.references:
                add = True
                for other in unique_refs:
                    if other.matches(ref):
                        add = False
                        break
                if add:
                    unique_refs.append(ref)
                    yield ref

    def _errors_relative_to(
        self,
        source_counted_refs: _CountedReferences,
    ) -> Iterator[SafeString]:
        # NOTE: The source_counted_refs may contain shared references, but we
        # ignore this property since at least one of the source variants
        # contains the actual reference, and we expect it to appear in the
        # targets as well.
        for refs in source_counted_refs.matching_refs:
            count = len(refs)
            variants_missing_ref = []
            all_variants = True
            for variant in self._target_variants:
                if variant.counted_references.count(refs[0]) < count:
                    variants_missing_ref.append(variant)
                else:
                    all_variants = False
            if not variants_missing_ref:
                continue
            yield self._missing_ref_message(
                refs[0].present(),
                self._present_variant_list(
                    None if all_variants else variants_missing_ref
                ),
            )

        for ref in self._unique_target_refs():
            count = source_counted_refs.count(ref)
            variants_extra_ref = []
            all_variants = True
            for variant in self._target_variants:
                # Here we are looking for extra references that shouldn't
                # appear, we only want to highlight the ones that are not shared
                # to avoid mentioning extra references for variants that do not
                # contain them explicitly.
                # NOTE: If there is a shared reference, then we expect at least
                # one of the target variants will have the excessive count, so
                # will be reported.
                if variant.counted_references.count(ref, False) > count:
                    variants_extra_ref.append(variant)
                else:
                    all_variants = False
            if not variants_extra_ref:
                continue
            yield self._extra_ref_message(
                ref.present(),
                self._present_variant_list(
                    None if all_variants else variants_extra_ref
                ),
            )

    def _missing_variants_message(
        self,
        variants: list[_VariantReferences],
    ) -> SafeString:
        # NOTE: variants should all have names since the source contains at
        # least two variants in order to reach this step.
        variant_list = self._present_variant_list(variants)
        if self._part_name:
            return format_html_code(
                gettext(
                    "The following variants in the original Fluent {attribute} "
                    "attribute do not have at least one matching variant in the "
                    "translation with the same set of Fluent references: "
                    "{variant_list}."
                ),
                attribute=self._part_name,
                variant_list=variant_list,
            )
        return format_html_code(
            gettext(
                "The following variants in the original Fluent value do not "
                "have at least one matching variant in the translation with "
                "the same set of Fluent references: {variant_list}."
            ),
            variant_list=variant_list,
        )

    def _extra_variants_message(
        self,
        variants: list[_VariantReferences] | None,
    ) -> SafeString:
        variant_list = self._present_variant_list(variants)
        if self._part_name:
            if not variant_list:
                return format_html_code(
                    gettext(
                        "The translated Fluent {attribute} attribute does not "
                        "have a matching variant in the original with the same "
                        "set of Fluent references."
                    ),
                    attribute=self._part_name,
                )
            return format_html_code(
                gettext(
                    "The following variants in the translated Fluent "
                    "{attribute} attribute do not have a matching variant in "
                    "the original with the same set of Fluent references: "
                    "{variant_list}."
                ),
                attribute=self._part_name,
                variant_list=variant_list,
            )
        if not variant_list:
            return format_html_code(
                gettext(
                    "The translated Fluent value does not "
                    "have a matching variant in the original with the same "
                    "set of Fluent references."
                ),
            )
        return format_html_code(
            gettext(
                "The following variants in the translated Fluent "
                "value do not have a matching variant in "
                "the original with the same set of Fluent references: "
                "{variant_list}."
            ),
            variant_list=variant_list,
        )

    def _errors_for_unmatched_variants(
        self,
    ) -> Iterator[SafeString]:
        if self._missing_variants:
            yield self._missing_variants_message(self._missing_variants)
        if self._extra_variants:
            # Don't want to print a list of variants if we only have one in the
            # original.
            have_target_variants = len(self._target_variants) > 1
            yield self._extra_variants_message(
                self._extra_variants if have_target_variants else None
            )

    def description(self) -> SafeString:
        # We want to be able to compare each target variant against some common
        # set of expected references. This allows us to determine which specific
        # references are missing or extra.
        # This is only possible if each variant in the source has the same set
        # of references (after sharing) to allow for this one-to-one comparison.
        # But we expect this will happen in most cases.
        common_refs: _CountedReferences | None = None
        for variant in self._source_variants:
            if common_refs is None:
                common_refs = variant.counted_references
            elif not common_refs.matches(variant.counted_references):
                common_refs = None
                break

        if common_refs is not None:
            return format_html_error_list(self._errors_relative_to(common_refs))
        # The source contains multiple variants with different references.
        return format_html_error_list(self._errors_for_unmatched_variants())


class FluentReferencesCheck(TargetCheck):
    r"""
    Check that the target uses the same Fluent references as the source.

    A Fluent Message or Term can reference another Message, Term, Attribute, or
    a variable. For example:

    | Here is a { message }, a { message.attribute } a { -term } and a { $variable }.
    | Within a function { NUMBER($num, minimumFractionDigits: 2) }

    Generally, translated Messages or Terms are expected to contain the same
    references as the source, although not necessarily in the same order of
    appearance. So this check ensures that translations use the same references
    in their value as the source value, the same number of times, and with no
    additions. For Messages, this will also check that each Attribute in the
    translation uses the same references as the matching Attribute in the
    source.

    When the source or translation contains Fluent Select Expressions, then each
    possible variant in the source must be matched with at least one variant in
    the translation with the same references, and vice versa.

    Moreover, if a variable reference appears both in the Select Expression's
    selector and within one of its variants, then all variants may also be
    considered as if they also contain that reference. The assumption being that
    the variant's key may have made the reference redundant for that variant.
    For example:

    | { $num ->
    |     [one] an apple
    |    *[other] { $num } apples
    | }

    Here, for the purposes of this check, the ``[one]`` variant will also be
    considered to contain the ``$num`` reference.

    However, a reference within the Select Expression's selector, which can only
    be a variable of a Term Attribute in Fluent's syntax, will not by itself
    count as a required reference because they do not form the actual text
    content of the string that the end-user will see, and the presence of a
    Select Expression is considered locale-specific. For example:

    | { -term.starts-with-vowel ->
    |     [yes] an { -term }
    |    *[no] a { -term }
    | }

    Here a reference to ``-term.starts-with-vowel`` is not expected to appear in
    translations, but a reference to ``-term`` is.
    """

    check_id = "fluent-references"
    name = gettext_lazy("Fluent references")
    description = gettext_lazy("Fluent references should match.")
    default_disabled = True

    @classmethod
    def _compare_references(
        cls, unit: TransUnitModel, source: str, target: str
    ) -> list[_VariantReferencesDifference]:
        # NOTE: If the source or target contains a syntax error, then
        # to_fluent_parts will return None. In this case, we just make it an
        # empty list. Then the returned difference will naturally be empty.
        source_unit = FluentUnitConverter(unit, source)
        is_message = source_unit.fluent_type() == "Message"
        source_parts = {
            part.name: part
            for part in (FluentUnitConverter(unit, source).to_fluent_parts() or [])
            # Always compare references in the values, but only compare
            # references in attributes for Messages (rather than Terms).
            if is_message or not part.name
        }
        differences: list[_VariantReferencesDifference] = []
        for part in FluentUnitConverter(unit, target).to_fluent_parts() or []:
            if part.name not in source_parts:
                # Ignore this part since we don't have anything to compare it
                # against. The FluentParts checker will capture this.
                continue
            diff = _VariantReferencesDifference(source_parts[part.name], part)
            if not diff:
                continue
            differences.append(diff)
        return differences

    def check_single(
        self,
        source: str,
        target: str,
        unit: TransUnitModel,
    ) -> bool:
        return bool(self._compare_references(unit, source, target))

    @classmethod
    def _get_all_references_in_branch(
        cls,
        branch: FluentSelectorBranch,
    ) -> Iterator[FluentReference]:
        """Get all references found across all variants as a single iterator."""
        yield from branch.top_references
        for node in branch.child_nodes:
            for child in node.child_branches:
                yield from cls._get_all_references_in_branch(child)

    def check_highlight(
        self,
        source: str,
        unit: TransUnitModel,
    ) -> HighlightsType:
        if self.should_skip(unit):
            return []

        fluent_unit = FluentUnitConverter(unit, source)
        is_message = fluent_unit.fluent_type() == "Message"

        highlight_patterns: list[str] = []
        # We simply match all references found in the source.
        for part in fluent_unit.to_fluent_parts() or []:
            if part.name and not is_message:
                continue
            highlight_patterns.extend(
                FluentPatterns.reference(fluent_ref)
                for fluent_ref in self._get_all_references_in_branch(part.top_branch)
            )
        return FluentPatterns.highlight_source(source, highlight_patterns)

    def get_description(self, check_model: CheckModel) -> StrOrPromise:
        (unit, source, target) = translation_from_check(check_model)
        differences = self._compare_references(unit, source, target)
        if not differences:
            return super().get_description(check_model)

        return format_html_error_list(diff.description() for diff in differences)
