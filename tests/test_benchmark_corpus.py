from benchmarks.corpus_dataset import build_corpus


def test_generated_benchmark_corpus_has_50_entries() -> None:
    corpus = build_corpus(50)
    assert len(corpus) == 50
    assert len({fixture["name"] for fixture in corpus}) == 50