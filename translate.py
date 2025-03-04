import os

import google.generativeai as genai
import polib

# Configure your API key
genai.configure(api_key="AIzaSyBAYNZ3ty4PU3bRFsg5twQpGEaYypcxWFU")

# Map common language codes to full language names for translation instructions.
LANGUAGE_MAP = {
    "fr": "French",
    "de": "German",
    "tr": "Turkish",
    # Add additional mappings as needed.
}


def translate_text(text, target_language_name):
    """
    Use Gemini AI to translate the given text into the target language.
    """
    generation_config = {
        "temperature": 0.3,
        "top_p": 0.95,
        "top_k": 40,
        "max_output_tokens": 256,
        "response_mime_type": "text/plain",
    }

    # The system instruction directs the model to translate text.
    system_instruction = (
        f"Translate the following text into {target_language_name}. "
        "Do not include any additional commentary or formatting:"
    )

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
    chat_session = model.start_chat()
    response = chat_session.send_message(text)
    translation = response.text.strip()
    return translation


def fill_missing_translations_with_gemini(translations_dir="translations"):
    """
    Walk through the translations folder, and for every .po file, fill in
    any empty msgstr fields by translating msgid via Gemini AI.
    """
    for root, dirs, files in os.walk(translations_dir):
        for filename in files:
            if filename.endswith(".po"):
                po_filepath = os.path.join(root, filename)
                po = polib.pofile(po_filepath)

                # Determine target language from the .po metadata.
                target_language_code = po.metadata.get("Language", "fr")
                target_language_name = LANGUAGE_MAP.get(
                    target_language_code, target_language_code
                )

                modified = False
                for entry in po:
                    # If translation is empty, translate the msgid.
                    if not entry.msgstr.strip():
                        try:
                            translation = translate_text(
                                entry.msgid, target_language_name
                            )
                            entry.msgstr = translation
                            print(
                                f"Translated '{entry.msgid}' -> '{translation}' in {po_filepath}"
                            )
                            modified = True
                        except Exception as e:
                            print(
                                f"Error translating '{entry.msgid}' in {po_filepath}: {e}"
                            )
                if modified:
                    po.save()
                    print(f"Saved updated translations in: {po_filepath}")
                else:
                    print(f"No missing translations in: {po_filepath}")


# Example usage:
if __name__ == "__main__":
    fill_missing_translations_with_gemini("translations")
