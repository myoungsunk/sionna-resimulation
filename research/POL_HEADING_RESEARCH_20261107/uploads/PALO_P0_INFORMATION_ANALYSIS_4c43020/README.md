# PALO P0 summary NPZ

The supplied ZIP contains two summary CSV tables, a report, a receipt and three figures; it contains no NPZ or per-frame arrays. These NPZ files convert the CSV tables without recomputing results. CSV column names are NPZ keys; row order is preserved. Strings use Unicode arrays, counts use int64, and other numeric columns use float64 (source CSV precision only). Load with `numpy.load(path, allow_pickle=False)`. CONVERSION_MANIFEST.json records source and output SHA256 hashes. This format conversion does not validate scientific claims in the supplied report.
