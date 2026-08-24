# Backend Full Regression

Command:

```text
conda run -n pythonLearn D:\DL\Anaconda3\envs\pythonLearn\python.exe -m pytest tests --ignore=tests/integration -q -p no:cacheprovider --basetemp <isolated writable path>
```

Final result: **846 passed, 2 skipped, 1 warning**.

The first root-level collection attempt was intentionally corrected to target `tests` because historical `artifacts/*/tests` review copies have duplicate test module names. No historical artifact was deleted or changed.
