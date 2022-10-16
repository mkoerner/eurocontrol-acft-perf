# Eurocontrol Aircraft Performance Database

This directory contains a simple scraper to download aircraft data from the
Eurocontrol aircraft performance database. Call using

```
python eurocontrol-actf-perf.py output.csv
```

To add additional functionality to the scraper, consider working on offline data
which you can store by adding a `--rawfile` flag

```
python eurocontrol-actf-perf.py output.csv --rawfile raw.pkl
```
