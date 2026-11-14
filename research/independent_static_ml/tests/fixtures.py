"""Synthetic (non-executable) fixtures for unit tests.

These are hand-built raw feature records and tiny in-memory models. They are
used ONLY to exercise error handling and the vector contract. They are NEVER
used to claim malware-detection accuracy (that is measured on the real labeled
EMBER test set by evaluate.py).
"""
from __future__ import annotations


def minimal_raw_record(entry=".text"):
    """A well-formed EMBER v2 raw record with all 9 groups and correct shapes."""
    return {
        "sha256": "0" * 64,
        "histogram": [1] * 256,
        "byteentropy": [1] * 256,
        "strings": {
            "numstrings": 10, "avlength": 6.0,
            "printabledist": [1] * 96, "printables": 96, "entropy": 3.0,
            "paths": 1, "urls": 0, "registry": 0, "MZ": 1,
        },
        "general": {
            "size": 4096, "vsize": 8192, "has_debug": 0, "exports": 0,
            "imports": 3, "has_relocations": 1, "has_resources": 1,
            "has_signature": 0, "has_tls": 0, "symbols": 0,
        },
        "header": {
            "coff": {"timestamp": 123456, "machine": "AMD64",
                     "characteristics": ["EXECUTABLE_IMAGE"]},
            "optional": {
                "subsystem": "WINDOWS_GUI", "dll_characteristics": ["NX_COMPAT"],
                "magic": "PE32_PLUS", "major_image_version": 1,
                "minor_image_version": 0, "major_linker_version": 14,
                "minor_linker_version": 0, "major_operating_system_version": 6,
                "minor_operating_system_version": 0, "major_subsystem_version": 6,
                "minor_subsystem_version": 0, "sizeof_code": 1024,
                "sizeof_headers": 512, "sizeof_heap_commit": 4096,
            },
        },
        "section": {
            "entry": entry,
            "sections": [
                {"name": ".text", "size": 1024, "entropy": 6.1, "vsize": 1024,
                 "props": ["CNT_CODE", "MEM_READ", "MEM_EXECUTE"]},
                {"name": ".data", "size": 512, "entropy": 3.2, "vsize": 512,
                 "props": ["MEM_READ", "MEM_WRITE"]},
            ],
        },
        "imports": {"kernel32.dll": ["CreateFileA", "ordinal12"],
                    "user32.dll": ["MessageBoxA"]},
        "exports": ["foo", "bar"],
        "datadirectories": [
            {"name": "EXPORT_TABLE", "size": 0, "virtual_address": 0},
            {"name": "IMPORT_TABLE", "size": 40, "virtual_address": 8192},
        ],
    }
