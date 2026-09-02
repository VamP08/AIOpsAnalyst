# Corpus

Benchmark datasets are not committed (`corpus/data/` is gitignored). To reproduce the
clustering numbers, fetch Loghub-2.0 datasets from Zenodo record 8275861:

```
curl -L -o corpus/data/OpenSSH.zip "https://zenodo.org/records/8275861/files/OpenSSH.zip?download=1"
unzip corpus/data/OpenSSH.zip -d corpus/data
python eval/bench_loghub.py corpus/data/OpenSSH/OpenSSH_full.log_structured.csv
```

Each dataset ships the raw log, a structured CSV with per-line ground-truth EventId,
and the ground-truth template list. Licensed for research use by the LogPai project
(https://github.com/logpai/loghub-2.0).
