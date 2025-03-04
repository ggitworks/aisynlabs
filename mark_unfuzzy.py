import os

import polib


def remove_all_fuzzy_flags(translations_dir="translations"):
    for root, _, files in os.walk(translations_dir):
        for filename in files:
            if filename.endswith(".po"):
                po_filepath = os.path.join(root, filename)
                po = polib.pofile(po_filepath)
                modified = False
                for entry in po:
                    if "fuzzy" in entry.flags:
                        entry.flags.remove("fuzzy")
                        modified = True
                if modified:
                    po.save()
                    print(f"Removed fuzzy flags from {po_filepath}")
                else:
                    print(f"No fuzzy flags found in {po_filepath}")


if __name__ == "__main__":
    remove_all_fuzzy_flags("translations")
