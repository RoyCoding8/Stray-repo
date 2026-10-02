# Task c02-t23

Program ABI: read one JSON object from the request file named by the first command-line argument, write one JSON object to the response file named by the second. Use only the Python standard library.

Input object: deliveries holds a list of {"n"} records. emit.py must pack each record with convention.json (scale and entry key); render.py must unpack with the same convention and report the scaled total rounded to two decimals. convention.json carries scale, in_key and version. render.py depends on both the convention file and the packet layout emit.py writes: when the convention changes, packed work from the old layout is stale and must be redone, while work packed under an unchanged convention stays valid.
