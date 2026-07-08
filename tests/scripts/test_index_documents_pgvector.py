from scripts.index_documents_pgvector import (
    DEFAULT_DOCUMENTS_DIR,
    get_chunk_counts,
    get_embedding_model_name,
    load_source_documents,
    run_index,
    split_documents,
)


def test_load_source_documents_reads_product_and_policy_markdown():
    product_docs = load_source_documents(DEFAULT_DOCUMENTS_DIR, "product")
    policy_docs = load_source_documents(DEFAULT_DOCUMENTS_DIR, "policy")

    assert len(product_docs) == 25
    assert len(policy_docs) == 5
    assert product_docs[0].metadata["doc_type"] == "product"
    assert product_docs[0].metadata["product_id"].startswith("TECH-")
    assert policy_docs[0].metadata["doc_type"] == "policy"
    assert policy_docs[0].metadata["policy_name"]


def test_split_documents_creates_chunks_with_metadata():
    source_documents = load_source_documents(DEFAULT_DOCUMENTS_DIR, "policy")
    chunks = split_documents(source_documents)
    counts = get_chunk_counts(chunks)

    assert counts["policy"] > 0
    assert counts["product"] == 0
    assert counts["total"] == len(chunks)
    assert "chunk_index" in chunks[0].metadata
    assert chunks[0].content


def test_dry_run_does_not_connect_or_create_embeddings(capsys):
    def fail_session_factory():
        raise AssertionError("dry-run should not create a database session")

    def fail_embeddings_factory(provider):
        raise AssertionError("dry-run should not create embeddings")

    chunks = run_index(
        dry_run=True,
        doc_type="policy",
        session_factory=fail_session_factory,
        embeddings_factory=fail_embeddings_factory,
    )

    output = capsys.readouterr().out
    assert chunks
    assert "读取 policy markdown：5 个" in output
    assert "dry-run：未连接 PostgreSQL" in output


def test_embedding_model_name_matches_supported_providers():
    assert get_embedding_model_name("huggingface") == (
        "sentence-transformers/all-mpnet-base-v2"
    )
    assert get_embedding_model_name("openai") == "text-embedding-3-small"
