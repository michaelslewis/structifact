import os
import importlib


ADAPTERS = {
    ".yml": ("structifact.adapters.yaml", "load_yaml"),
    ".yaml": ("structifact.adapters.yaml", "load_yaml"),
    ".xlsx": ("structifact.adapters.excel", "load_excel"),
    ".csv": ("structifact.adapters.csv", "load_csv"),
}

def load_spec(path):
    extension = os.path.splitext(path)[1].lower()

    if extension not in ADAPTERS:
        raise ValueError(
            f"Unsupported specification format: {extension}"
        )

    module_name, function_name = ADAPTERS[extension]

    module = importlib.import_module(module_name)

    loader = getattr(module, function_name)

    return loader(path)