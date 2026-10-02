from types import SimpleNamespace
import pytest
from backend.adapters.esm2 import infer

@pytest.mark.parametrize("sequence", ["", "A" * 1023, ">FASTA\nAAAA", "ABC123"])
def test_esm2_rejects_invalid_sequence_before_loading(sequence):
    with pytest.raises(ValueError, match="1–1022"):
        infer(SimpleNamespace(sequence=sequence), [], {"weights": "missing.pt"})
