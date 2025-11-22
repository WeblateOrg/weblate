# Copyright © William
# 
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from weblate.trans.models import Translation


def auto_translate_via_openrouter(translation: "Translation") -> "Translation":
    """Auto translation via OpenRouter (modularized)."""
    # 1) Resolve configuration
    api_key, model, config_source = _resolve_openrouter_config(translation)
    if not api_key or not model:
        translation.log_warning(
            "OpenRouter configuration not found, skipping auto-translation for: %s",
            translation.full_slug,
        )
        return translation

    try:
        # 2) Collect units and build request
        units_qs, units_data, unit_map, expected_keys = (
            _prepare_batch_request(translation)
        )
        if not units_qs:
            return translation

        # 3) Call translator with validation/retries
        translated_data = _translate_with_retries(
            translation,
            units_data,
            expected_keys,
            api_key,
            model,
        )
        if translated_data is None:
            translation.log_warning(
                "Translation returned no data for: %s",
                translation.full_slug,
            )
            return translation

        # 4) Apply results
        _apply_batch_translations(translation, translated_data, unit_map, len(units_data))
        return translation
    except Exception as e:
        translation.log_error("Auto-translation failed for %s: %s", translation.full_slug, e)
        import traceback
        translation.log_error("traceback: %s", traceback.format_exc())
        return translation


def _resolve_openrouter_config(translation: "Translation"):
    from weblate.configuration.models import Setting, SettingCategory
    import os

    translation.log_info("AUTO-TRANSLATION TRIGGERED for %s", translation.full_slug)

    api_key = None
    model = None
    config_source = None

    try:
        settings = Setting.objects.get_settings_dict(SettingCategory.MT)
        openai_config = settings.get('openai', {})
        if openai_config:
            api_key = openai_config.get('key')
            model = openai_config.get('custom_model')
            if api_key and model:
                config_source = "Weblate configuration_setting"
                translation.log_info("Using OpenRouter settings from Weblate configuration")
    except Exception as e:
        translation.log_debug("Failed to read Weblate configuration: %s", e)

    if not (api_key and model):
        api_key = os.getenv('OPENROUTER_API_KEY')
        model = os.getenv('OPENROUTER_MODEL', 'deepseek/deepseek-chat')
        if api_key and model:
            config_source = "environment variables"
            translation.log_info("Using OpenRouter settings from environment variables")

    if not api_key:
        translation.log_warning(
            "OpenRouter API key not found. Please configure in Weblate settings or env vars. Skipping auto-translation."
        )
        return None, None, None
    if not model:
        translation.log_warning(
            "OpenRouter model not specified. Please configure in Weblate settings or env vars. Skipping auto-translation."
        )
        return None, None, None

    return api_key, model, config_source

def _prepare_batch_request(translation: "Translation"):
    from weblate.utils.openrouter_translator import OpenRouterTranslator  # noqa: F401 (import side-effect for types)
    import json

    # Collect untranslated units
    units_qs = translation.unit_set.all().order_by('position')
    if not units_qs.exists():
        return None, None, None, None, None

    units_data = {}
    unit_map = {}
    for unit in units_qs:
        units_data[str(unit.id)] = unit.source
        unit_map[unit.id] = unit

    expected_keys = set(units_data.keys())

    return units_qs, units_data, unit_map, expected_keys


def _create_chunks(units_data, chunk_size=50):
        """Split units data into chunks for batch processing."""
        units_list = list(units_data.items())
        chunks = []
        
        for i in range(0, len(units_data), chunk_size):
            chunk_dict = dict(units_list[i:i + chunk_size])
            chunks.append(chunk_dict)
        
        return chunks

def _build_system_prompt(source_language, target_language):
        """Build the system prompt for translation."""
        return f"""You are a professional technical documentation translator specialized in translating from {source_language} to {target_language}.

        CRITICAL REQUIREMENTS:
        1. INPUT: You will receive a JSON object where keys are unit IDs and values are {source_language} source strings
        2. OUTPUT: You MUST return a VALID JSON OBJECT with the EXACT same keys - this is MANDATORY
        3. BATCH CONTEXT: This is a BATCH translation where all strings are related and from the same document. Ensure terminology consistency and contextual coherence across ALL translations in the batch.
        4. CHUNKED PROCESSING: IMPORTANT - This request may be part of a larger document split into chunks. Even though you only see this chunk, you MUST maintain consistency with potential other chunks from the same document. Use standard technical terminology that would be consistent across the entire document.
        
        TRANSLATION GUIDELINES:
        - Maintain CONSISTENT terminology and style across all translations in the batch AND across all chunks of the same document
        - Use the SAME {target_language} translation for recurring technical terms across all strings, even when processing different chunks
        - Maintain technical accuracy and formatting across all strings
        - Preserve code blocks, links, and markdown syntax in all strings
        - Use standard {target_language} technical terminology for C++ and Boost libraries CONSISTENTLY
        - When translating terms, use the standard, widely-accepted translation that would be consistent across the entire document, not just this chunk

        JSON FORMAT (NON-NEGOTIABLE):
        INPUT:  {{"1": "{source_language} text 1", "2": "{source_language} text 2", "3": "{source_language} text 3"}}
        OUTPUT: {{"1": "{target_language} translation 1", "2": "{target_language} translation 2", "3": "{target_language} translation 3"}}

        CRITICAL: Return ONLY the raw JSON object. NO markdown code fences, NO explanations, NO extra formatting.
        The response MUST be parseable as valid JSON or the entire batch will fail."""

def _build_user_prompt(chunk_json, source_language, target_language):
        """Build the user prompt for a specific chunk."""
        return f"""Translate the following strings from {source_language} to {target_language}. This is a chunk from a larger document - maintain consistency with standard technical terminology that would be used across the entire document.

        Return ONLY a valid JSON object with the same keys but translated values:
        {chunk_json}"""

def _translate_chunk_with_retries(
    translation: "Translation",
    translator, chunk_json, chunk_keys, chunk_idx, total_chunks, 
    system_prompt, user_prompt, max_retries=3
):
    """Translate a single chunk with retry logic."""
    translation.log_info(
        "Processing chunk %d/%d (%d units)",
        chunk_idx,
        total_chunks,
        len(chunk_keys),
    )
    
    for attempt in range(max_retries):
        try:
            translated_json = translator.translate_batch_json(
                chunk_json,
                system_prompt,
                user_prompt,
            )
            
            ok, chunk_translated = _validate_and_parse_response(
                translation, translated_json, chunk_keys
            )
            
            if ok:
                return chunk_translated
                
        except Exception as e:
            translation.log_warning(
                "Chunk %d/%d translation attempt %d/%d failed: %s",
                chunk_idx,
                total_chunks,
                attempt + 1,
                max_retries,
                e,
            )
    
    translation.log_error(
        "Chunk %d/%d translation failed after %d attempts. Skipping chunk.",
        chunk_idx,
        total_chunks,
        max_retries,
    )
    return None


def _validate_translation_completeness(translation: "Translation", all_translated_data, expected_keys):
    """Validate that all expected keys were translated."""
    translated_keys = set(all_translated_data.keys())
    
    if translated_keys == expected_keys:
        translation.log_info(
            "All chunks translated successfully. Total: %d units",
            len(all_translated_data),
        )
        return True
    
    missing_keys = expected_keys - translated_keys
    translation.log_error(
        "Translation incomplete. Missing %d units out of %d total",
        len(missing_keys),
        len(expected_keys),
    )
    return False


def _translate_with_retries(
    translation: "Translation",
    units_data, expected_keys, api_key, model_name
):
    """Translate units with chunking and retry logic."""
    from weblate.utils.openrouter_translator import OpenRouterTranslator
    import json

    # Initialize translator
    translator = OpenRouterTranslator(api_key=api_key, model=model_name, logger=translation)

    # Create chunks
    chunks = _create_chunks(units_data, chunk_size=50)

    # Get language names
    source_language = translation.component.source_language.name
    target_language = translation.language.name
    
    # Build system prompt (same for all chunks)
    system_prompt = _build_system_prompt(source_language, target_language)
    
    # Translate each chunk and combine results
    all_translated_data = {}
    
    for chunk_idx, chunk_data in enumerate(chunks, 1):
        chunk_json = json.dumps(chunk_data, ensure_ascii=False, indent=2)
        chunk_keys = set(chunk_data.keys())
        user_prompt = _build_user_prompt(
            chunk_json, source_language, target_language
        )
        
        chunk_translated = _translate_chunk_with_retries(
            translation=translation,
            translator=translator,
            chunk_json=chunk_json,
            chunk_keys=chunk_keys,
            chunk_idx=chunk_idx,
            total_chunks=len(chunks),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_retries=3,
        )
        
        if chunk_translated:
            all_translated_data.update(chunk_translated)

    # Validate completeness
    if _validate_translation_completeness(translation, all_translated_data, expected_keys):
        return all_translated_data
    
    return all_translated_data if all_translated_data else None


def _validate_and_parse_response(translation: "Translation", translated_json, expected_keys):
    import json
    try:
        data = json.loads(translated_json)
    except Exception as e:
        translation.log_warning("Invalid JSON: %s", e)
        translation.log_debug("Response preview: %s", translated_json[:500])
        return False, None

    if not isinstance(data, dict):
        translation.log_warning("Response is not a JSON object")
        return False, None

    translated_keys = set(data.keys())
    if translated_keys != expected_keys:
        missing_keys = expected_keys - translated_keys
        extra_keys = translated_keys - expected_keys
        translation.log_warning(
            "Key mismatch - Expected %d keys, got %d keys", len(expected_keys), len(translated_keys)
        )
        if missing_keys:
            translation.log_debug("Missing keys: %s", list(missing_keys)[:10])
        if extra_keys:
            translation.log_debug("Extra keys: %s", list(extra_keys)[:10])
        return False, None

    return True, data


def _apply_batch_translations(translation: "Translation", translated_data, unit_map, total_units):
    from weblate.utils.state import STATE_FUZZY
    
    translated_count = 0
    failed_count = 0

    for unit_id_str, target in translated_data.items():
        try:
            unit_id = int(unit_id_str)
        except ValueError:
            translation.log_warning("Invalid unit ID in response: %s", unit_id_str)
            failed_count += 1
            continue

        if not target:
            translation.log_warning("Empty translation for unit ID %s", unit_id)
            failed_count += 1
            continue

        unit = unit_map.get(unit_id)
        if not unit:
            translation.log_warning("Unit ID %s not found in map", unit_id)
            failed_count += 1
            continue

        try:
            from weblate.trans.models.pending import PendingUnitChange
            from weblate.auth.models import User
            
            unit.target = target
            unit.state = STATE_FUZZY  # fuzzy/needs editing per user request
            unit.save(update_fields=['target', 'state'])
            
            # Create pending change so file sync can write it to disk
            # Get or create a bot user for autobatch translation
            bot_user = User.objects.get_or_create_bot(
                scope="weblate", name="Autobatch_translatior", verbose="autobatch_translatior"
            )
            PendingUnitChange.store_unit_change(
                unit=unit,
                author=bot_user,
                target=target,
                state=STATE_FUZZY,
            )
            
            translated_count += 1
            translation.log_debug("Translated unit %d: %s -> %s", unit.id, unit.source[:30], target[:30])
        except Exception as e:
            translation.log_warning("Failed to save translation for unit %d: %s", unit_id, e)
            failed_count += 1

    translation.log_info(
        "Batch auto-translation completed: %d/%d units translated, %d failed",
        translated_count,
        total_units,
        failed_count,
    )
