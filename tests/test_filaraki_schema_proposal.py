from filoma.filaraki.models import SchemaProposal


def test_schema_proposal_construction():
    proposal = SchemaProposal(
        dataset_name="cifar10",
        num_files_sampled=100,
        columns=[
            {"name": "image", "dtype": "uint8", "nullable": False, "description": "Raw image data"},
            {"name": "label", "dtype": "int64", "nullable": False, "description": "Class label 0-9"},
        ],
        pipeline_config={"batch_size": 32, "shuffle": True},
        quality_gates={"duplicate_ratio_pct": 5.0, "corrupted_files": 0},
        issues=["Found 3 corrupted PNG files"],
        recommendations=["Re-encode corrupted PNGs with PIL"],
    )

    assert proposal.dataset_name == "cifar10"
    assert proposal.num_files_sampled == 100
    assert len(proposal.columns) == 2
    assert proposal.columns[0]["name"] == "image"
    assert "batch_size" in proposal.pipeline_config
    assert "duplicate_ratio_pct" in proposal.quality_gates
    assert len(proposal.issues) == 1
    assert len(proposal.recommendations) == 1


def test_schema_proposal_json_roundtrip():
    proposal = SchemaProposal(
        dataset_name="test_ds",
        num_files_sampled=10,
        columns=[],
        pipeline_config={},
        quality_gates={},
        issues=[],
        recommendations=[],
    )

    json_str = proposal.model_dump_json()
    reloaded = SchemaProposal.model_validate_json(json_str)

    assert reloaded.dataset_name == "test_ds"
    assert reloaded.num_files_sampled == 10


def test_schema_proposal_minimal():
    proposal = SchemaProposal(
        dataset_name="minimal",
        num_files_sampled=0,
        columns=[],
        pipeline_config={},
        quality_gates={},
        issues=[],
        recommendations=[],
    )
    assert proposal.dataset_name == "minimal"
