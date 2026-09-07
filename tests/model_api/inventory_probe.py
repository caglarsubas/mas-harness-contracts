"""Invoke the unchanged real inventory test in a disposable, normally imported tree.

Only launched by the complete outer suite inside the declared offline wrapper.
No patched globals, modified assertions, synthetic pass result or test deselection.
"""
from tests.model.test_lifecycle_contracts import (
    test_five_openapi_documents_have_local_resolvable_refs_and_no_servers,
)

if __name__ == "__main__":
    test_five_openapi_documents_have_local_resolvable_refs_and_no_servers()
    print("INVENTORY_PROBE_PASS")
